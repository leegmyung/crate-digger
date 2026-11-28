"""인디고 아티스트 페이지 → 팀 공식 인스타 → data/raw/state/indiego_sns.json (비공개, indistreet_sns.json 과 같은 모양)

    .venv/bin/python scripts/collect_indiego_sns.py               # 상위 500+정답 팀 → 최근 2년 인디고 공연 팀, 30일마다
    .venv/bin/python scripts/collect_indiego_sns.py --limit 400   # 첫 회는 나눠 돌린다
    .venv/bin/python scripts/collect_indiego_sns.py --all

인디고 아티스트 페이지(www.indiego.co.kr/artists/<번호>-<이름>)에는 구조화 데이터(JSON-LD)가 두 개 있다:
사이트 자체(Organization, sameAs = 인디고 인스타)와 아티스트(mainEntityOfPage = 그 페이지, sameAs = 팀 공식 인스타).
아티스트 블록의 sameAs 만 읽는다(collect_indistreet_sns 와 같은 규칙: 인스타가 정확히 하나일 때만, 페이지 여럿인 팀은 뺌).
robots.txt: /api/ 만 막음. 한 번에 한 페이지, 페이지가 올 때까지만 기다린다. 표본 20페이지 중 20개에 팀 인스타가 있었다(2026-11-28).
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import sys
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_indistreet_sns as cis  # noqa: E402  (pick_instagram·target_keys·due·fetch 를 같이 쓴다)

STATE = cis.RAW_DIR / "state" / "indiego_sns.json"
PAGE_PREFIX = "https://www.indiego.co.kr/artists/"


def parse_same_as(html: str, page_url: str) -> List[str]:
    """아티스트 블록(mainEntityOfPage 또는 url 이 그 페이지)의 sameAs. 사이트 자체 블록은 안 씀."""
    want = cis._norm_url(page_url)
    for block in cis.LD_JSON.findall(html or ""):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        for item in data if isinstance(data, list) else [data]:
            if not isinstance(item, dict):
                continue
            main = item.get("mainEntityOfPage")
            if want in (cis._norm_url(main if isinstance(main, str) else ""), cis._norm_url(item.get("url", ""))):
                same = item.get("sameAs") or []
                return [s for s in ([same] if isinstance(same, str) else same) if isinstance(s, str)]
    return []


def quoted(url: str) -> str:
    """한글이 든 주소 → 요청할 수 있게 경로만 % 인코딩."""
    p = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((p.scheme, p.netloc, urllib.parse.quote(p.path), p.query, ""))


def team_pages(rows: Iterable[Mapping], key_of: Callable[[str], str]) -> Dict[str, str]:
    """팀 키 → 인디고 아티스트 페이지 (페이지가 하나뿐인 팀만)."""
    pages: Dict[str, set] = {}
    for r in rows:
        url = cis._norm_url(r.get("artist_url") or "")
        if url.startswith(PAGE_PREFIX) and (r.get("artist_text") or "").strip():
            pages.setdefault(key_of(r["artist_text"]), set()).add(url)
    return {k: next(iter(v)) for k, v in pages.items() if k and len(v) == 1}


def _gig_rows() -> List[dict]:
    rows: List[dict] = []
    for f in sorted(glob.glob(str(cis.RAW_DIR / "raw_kr_gig_*indiego*.csv"))):
        with open(f, encoding="utf-8", newline="") as fh:
            rows += list(csv.DictReader(fh))
    return rows


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="인디고 아티스트 페이지 공식 인스타")
    ap.add_argument("--all", action="store_true", help="인디고 공연에 나온 모든 팀")
    ap.add_argument("--limit", type=int, default=300)
    args = ap.parse_args(argv)
    from artist_xref import canonical_key, load_xref

    index = load_xref()
    key_of = lambda n: canonical_key(n, index)  # noqa: E731
    rows = _gig_rows()
    pages = team_pages(rows, key_of)
    today = f"{datetime.now(cis.KST):%Y-%m-%d}"
    if args.all:
        keys = list(pages)
    else:
        coverage = cis._load(cis.COVERAGE).get("teams", []) + cis._load(cis.WATCH).get("teams", [])
        keys = cis.target_keys(pages, coverage, rows, key_of=key_of, today=today)
    state = cis._load(STATE)
    todo = cis.due(keys, state, today)[:args.limit]
    found = failed = 0
    STATE.parent.mkdir(parents=True, exist_ok=True)
    for i, k in enumerate(todo, 1):
        html = cis.fetch(quoted(pages[k]))
        if html is None:
            failed += 1
            continue
        same = parse_same_as(html, pages[k])
        handle = cis.pick_instagram(same)
        state[k] = {"url": pages[k], "checked": today, "instagram": handle, "same_as": same}
        found += bool(handle)
        if i % 25 == 0:
            STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    total = sum(1 for v in state.values() if v.get("instagram"))
    print(f"✅ 인디고 공식 인스타: 대상 {len(keys)}팀 중 이번 {len(todo)}팀 확인 → 인스타 {found}팀 (실패 {failed}) · 누적 {total}팀 → {STATE.relative_to(cis.ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
