"""인디스트릿 아티스트 페이지 → 팀 공식 SNS(인스타 등) → data/raw/state/indistreet_sns.json (비공개)

    .venv/bin/python scripts/collect_indistreet_sns.py            # 대상 중 아직 안 본 / 30일 지난 팀 (기본 최대 300페이지)
    .venv/bin/python scripts/collect_indistreet_sns.py --all      # 인디스트릿 공연에 나온 모든 팀
    .venv/bin/python scripts/collect_indistreet_sns.py --limit 400   # 첫 회는 나눠 돌린다 (이어서 하면 안 본 팀부터)

대상(기본): coverage_targets.json 의 오늘 점수 상위 500 + 정답 팀 → 인디스트릿 공연 기록이 최근 2년 안에 있는 팀 전체(최근 공연 순).

왜: 팔로워 30일 변화(docs/followers_plan.md)를 보려면 팀 ↔ 인스타 계정이 있어야 하는데, 관찰 300팀 중 links.csv 에 인스타가
있는 팀이 15팀뿐이다. 인디스트릿 아티스트 페이지의 구조화 데이터(JSON-LD MusicGroup)의 sameAs 에는 팀이 직접 적은 공식
채널이 들어 있다(소개글 속 멤버 개인 계정은 sameAs 에 없음).
- 팀 ↔ 페이지: 인디스트릿 공연 원본(raw_kr_gig_*indistreet*.csv)의 artist_text·artist_url, 팀 키는 artist_xref.canonical_key.
  한 팀에 페이지가 여럿이면(동명 의심) 뺀다.
- 인스타: sameAs 안 인스타 계정이 정확히 하나일 때만 (둘 이상이면 어느 쪽이 팀 계정인지 모름 → 뺌).
- robots.txt: /artists/ 허용(/api/ 만 막음). 한 번에 한 페이지씩, 페이지가 올 때까지만 기다린다. 30일 안에 본 팀은 다시 안 본다.
결과는 export_lab_data 의 연결 목록(artist_xref·musicbrainz 와 같은 자리)에 넣을 수 있다 — 제안은 docs/followers_plan.md.
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
STATE = RAW_DIR / "state" / "indistreet_sns.json"
WATCH = RAW_DIR / "state" / "followers_watch.json"
COVERAGE = RAW_DIR / "state" / "coverage_targets.json"
RECENT_YEARS = 2
KST = timezone(timedelta(hours=9))
PAGE_PREFIX = "https://indistreet.com/artists/"
RECHECK_DAYS = 30
TIMEOUT_SEC = 20
USER_AGENT = "Mozilla/5.0 (compatible; GigleResearch/1.0; +https://github.com/leegmyung/gigle-research)"
LD_JSON = re.compile(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', re.S)
INSTA = re.compile(r"^https?://(?:www\.)?instagram\.com/([A-Za-z0-9._]+)/?(?:\?.*)?$")
INSTA_NOT_ACCOUNT = {"p", "reel", "reels", "explore", "stories", "tv"}


def _norm_url(u: str) -> str:
    return (u or "").split("?")[0].rstrip("/")


def parse_same_as(html: str, page_url: str) -> List[str]:
    """그 페이지 아티스트 블록(JSON-LD, url 이 페이지 주소와 같은 것)의 sameAs 목록. 없거나 깨졌으면 []."""
    want = _norm_url(page_url)
    for block in LD_JSON.findall(html or ""):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        for item in data if isinstance(data, list) else [data]:
            if isinstance(item, dict) and _norm_url(item.get("url", "")) == want:
                same = item.get("sameAs") or []
                return [s for s in ([same] if isinstance(same, str) else same) if isinstance(s, str)]
    return []


def pick_instagram(same_as: Iterable[str]) -> Optional[str]:
    """sameAs 안 인스타 계정이 정확히 하나면 그 계정, 아니면 None."""
    handles = []
    for u in same_as:
        m = INSTA.match(u.strip())
        if m and m.group(1).lower() not in INSTA_NOT_ACCOUNT and m.group(1) not in handles:
            handles.append(m.group(1))
    return handles[0] if len(handles) == 1 else None


def team_pages(rows: Iterable[Mapping], key_of: Callable[[str], str]) -> Dict[str, str]:
    """팀 키 → 인디스트릿 아티스트 페이지 (페이지가 하나뿐인 팀만)."""
    pages: Dict[str, set] = {}
    for r in rows:
        url = _norm_url(r.get("artist_url") or "")
        if not url.startswith(PAGE_PREFIX) or not (r.get("artist_text") or "").strip():
            continue
        pages.setdefault(key_of(r["artist_text"]), set()).add(url)
    return {k: next(iter(v)) for k, v in pages.items() if k and len(v) == 1}


def target_keys(pages: Mapping[str, str], coverage: Sequence[Mapping], gig_rows: Iterable[Mapping],
                key_of: Callable[[str], str], today: str, years: int = RECENT_YEARS) -> List[str]:
    """볼 팀 순서: coverage_targets(상위 순위 → 정답 팀) 중 페이지가 있는 팀 → 최근 years 년 안 인디스트릿 공연 팀(최근 공연 순)."""
    since = (date.fromisoformat(today) - timedelta(days=365 * years)).isoformat()
    first = [t["team_key"] for t in sorted(coverage, key=lambda t: (t.get("rank") is None, t.get("rank") or 0))
             if t.get("team_key") in pages]
    last_gig: Dict[str, str] = {}
    for r in gig_rows:
        d = (r.get("gig_date") or "")[:10]
        if d >= since and (r.get("artist_text") or "").strip():
            k = key_of(r["artist_text"])
            if k in pages and d > last_gig.get(k, ""):
                last_gig[k] = d
    recent = sorted(last_gig, key=lambda k: last_gig[k], reverse=True)
    return list(dict.fromkeys(first + recent))


def due(keys: Sequence[str], state: Mapping[str, Mapping], today: str, days: int = RECHECK_DAYS) -> List[str]:
    """안 본 팀 먼저, 그다음 마지막으로 본 지 days 일 지난 팀(오래된 순)."""
    cut = (date.fromisoformat(today) - timedelta(days=days)).isoformat()
    new = [k for k in keys if k not in state]
    old = sorted((k for k in keys if k in state and (state[k].get("checked") or "") <= cut), key=lambda k: state[k]["checked"])
    return new + old


def fetch(url: str) -> Optional[str]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "ko"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, ValueError):
        return None


def _gig_rows() -> List[dict]:
    rows: List[dict] = []
    for f in sorted(glob.glob(str(RAW_DIR / "raw_kr_gig_*indistreet*.csv"))):
        with open(f, encoding="utf-8", newline="") as fh:
            rows += list(csv.DictReader(fh))
    return rows


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="인디스트릿 아티스트 페이지 공식 SNS")
    ap.add_argument("--all", action="store_true", help="상위·정답·최근 2년 팀만이 아니라 인디스트릿 공연에 나온 모든 팀")
    ap.add_argument("--limit", type=int, default=300)
    args = ap.parse_args(argv)
    from artist_xref import canonical_key, load_xref

    index = load_xref()
    rows = _gig_rows()
    pages = team_pages(rows, key_of=lambda n: canonical_key(n, index))   # 페이지 하나뿐인 팀만
    today = f"{datetime.now(KST):%Y-%m-%d}"
    if args.all:
        keys = list(pages)
    else:
        coverage = _load(COVERAGE).get("teams", []) + _load(WATCH).get("teams", [])   # 관찰 목록(관심 팀 포함)도 앞에
        keys = target_keys(pages, coverage, rows, key_of=lambda n: canonical_key(n, index), today=today)
    state = _load(STATE)
    todo = due(keys, state, today)[:args.limit]
    found = failed = 0
    STATE.parent.mkdir(parents=True, exist_ok=True)
    for i, k in enumerate(todo, 1):
        html = fetch(pages[k])
        if html is None:
            failed += 1
            continue
        same = parse_same_as(html, pages[k])
        handle = pick_instagram(same)
        state[k] = {"url": pages[k], "checked": today, "instagram": handle, "same_as": same}
        found += bool(handle)
        if i % 25 == 0:                        # 중간에 끊겨도 이어서
            STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    total = sum(1 for v in state.values() if v.get("instagram"))
    print(f"✅ 인디스트릿 공식 SNS: 대상 {len(keys)}팀 중 이번 {len(todo)}팀 확인 → 인스타 {found}팀 (실패 {failed}) · 누적 인스타 {total}팀 → {STATE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.exit(main())
