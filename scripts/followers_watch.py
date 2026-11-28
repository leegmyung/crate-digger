"""팔로워 기록용 관찰 목록 → data/raw/state/followers_watch.json (+ 수집기용 번호·계정 목록)

    .venv/bin/python scripts/followers_watch.py          # 주 1회 (daily_run.sh 월요일 블록)

왜: 팔로워 30일 변화(docs/followers_plan.md)를 보려면 같은 팀의 팔로워 수가 날짜별로 쌓여야 한다. 수집기는 한 번 본 팀을
다시 보지 않으므로, 주 1회 다시 볼 팀을 정해 준다.
- 대상: 오늘 점수 상위 300(data/raw/state/coverage_targets.json, scripts/coverage_targets.py) +
  앱 '내 목록 → 관심 팀 CSV 내려받기' 파일(data/raw/review/watchlist*.csv, 관심 팀은 브라우저에만 있어서 사람이 내려받아 둠).
- 팀 → 멜론 번호·인스타 계정은 docs/lab/data/links.csv (읽기만). links.csv 에 인스타가 없으면 인디스트릿 아티스트 페이지에
  팀이 직접 적은 공식 계정(data/raw/state/indistreet_sns.json, scripts/collect_indistreet_sns.py)으로 채운다.
- 결과 (모두 비공개 data/raw/state/):
    followers_watch.json              {as_of, teams: [{team_key, why(top|watch), melon_id, instagram}]}
    followers_watch_melon_extra.txt   멜론 번호 — 관심 팀 중 상위 300 밖만 (상위 팀은 collect_artists --refresh 가 이미 7일마다 다시 봄)
    followers_watch_instagram.txt     인스타 계정 — 관찰 팀 전체 (collect_ig_artists --handles-file 이 다시 봄)
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "data" / "raw" / "state"
REVIEW = ROOT / "data" / "raw" / "review"
DATA_DIR = ROOT / "docs" / "lab" / "data"
TARGETS = STATE / "coverage_targets.json"
OUT = STATE / "followers_watch.json"
MELON_OUT = STATE / "followers_watch_melon_extra.txt"
INSTA_OUT = STATE / "followers_watch_instagram.txt"
INDISTREET_SNS = STATE / "indistreet_sns.json"
TOP_N = 300
MELON_ID = re.compile(r"[?&]artistId=(\d+)")
INSTA = re.compile(r"^https://(?:www\.)?instagram\.com/([A-Za-z0-9._]+)/?$")
INSTA_NOT_ACCOUNT = {"p", "reel", "reels", "explore", "stories", "tv"}


def melon_id(url: str) -> Optional[str]:
    m = MELON_ID.search(url or "")
    return m.group(1) if m else None


def insta_handle(url: str) -> Optional[str]:
    m = INSTA.match((url or "").strip())
    return m.group(1) if m and m.group(1).lower() not in INSTA_NOT_ACCOUNT else None


def build_watch(targets: Sequence[Mapping], watch: Sequence[str], name_to_key: Mapping[str, str],
                top_n: int = TOP_N) -> List[dict]:
    """점수 상위 top_n(순위 순) → 관심 팀(이름을 팀 키로, 못 찾은 이름은 뺌). 같은 팀은 한 번."""
    top = [t["team_key"] for t in sorted((t for t in targets if t.get("rank")), key=lambda t: t["rank"])][:top_n]
    out = [{"team_key": k, "why": "top"} for k in dict.fromkeys(top)]
    have = set(top)
    for name in watch:
        k = name_to_key.get(name.strip())
        if k and k not in have:
            out.append({"team_key": k, "why": "watch"})
            have.add(k)
    return out


def attach_links(teams: Sequence[Mapping], links: Mapping[str, Mapping[str, str]]) -> List[dict]:
    out = []
    for t in teams:
        lk = links.get(t["team_key"], {})
        row = dict(t)
        mid, handle = melon_id(lk.get("melon", "")), insta_handle(lk.get("instagram", ""))
        if mid:
            row["melon_id"] = mid
        if handle:
            row["instagram"] = handle
        out.append(row)
    return out


def merge_indistreet(links: Mapping[str, Mapping[str, str]], sns: Mapping[str, Mapping]) -> Dict[str, Dict[str, str]]:
    """links 에 인스타가 없는 팀만 인디스트릿 공식 계정으로 채운 새 표 (이미 있는 연결이 먼저)."""
    out = {k: dict(v) for k, v in links.items()}
    for k, v in sns.items():
        handle = (v or {}).get("instagram")
        if handle and not out.get(k, {}).get("instagram"):
            out.setdefault(k, {})["instagram"] = f"https://www.instagram.com/{handle}/"
    return out


def melon_extra_ids(teams: Sequence[Mapping]) -> List[str]:
    return list(dict.fromkeys(t["melon_id"] for t in teams if t.get("why") == "watch" and t.get("melon_id")))


def instagram_handles(teams: Sequence[Mapping]) -> List[str]:
    return list(dict.fromkeys(t["instagram"] for t in teams if t.get("instagram")))


def watch_names(paths: Iterable[Path]) -> List[str]:
    """앱 '관심 팀 CSV' 의 '팀' 칸 (여러 파일이면 합침, 같은 이름은 한 번)."""
    names: List[str] = []
    for p in paths:
        with open(p, encoding="utf-8-sig", newline="") as f:
            names += [(r.get("팀") or "").strip() for r in csv.DictReader(f)]
    return list(dict.fromkeys(n for n in names if n))


def _csv(path: Path) -> List[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="팔로워 기록용 관찰 목록")
    ap.add_argument("--top", type=int, default=TOP_N)
    args = ap.parse_args(argv)
    try:
        targets = json.loads(TARGETS.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"❌ {TARGETS.name} 를 못 읽음 — scripts/coverage_targets.py 먼저: {e}", file=sys.stderr)
        return 1
    name_to_key: Dict[str, str] = {}
    for r in _csv(DATA_DIR / "teams.csv"):
        name_to_key.setdefault(r["display_name"], r["team_key"])
        name_to_key.setdefault(r["team_key"], r["team_key"])
    links: Dict[str, Dict[str, str]] = {}
    for r in _csv(DATA_DIR / "links.csv"):
        links.setdefault(r["team_key"], {}).setdefault(r["platform"], r["url"])
    try:
        links = merge_indistreet(links, json.loads(INDISTREET_SNS.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    watch = watch_names(sorted(REVIEW.glob("watchlist*.csv")))
    teams = attach_links(build_watch(targets.get("teams", []), watch, name_to_key, args.top), links)
    STATE.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"as_of": targets.get("as_of"), "teams": teams}, ensure_ascii=False, indent=1), encoding="utf-8")
    MELON_OUT.write_text("\n".join(melon_extra_ids(teams)) + "\n", encoding="utf-8")
    INSTA_OUT.write_text("\n".join(instagram_handles(teams)) + "\n", encoding="utf-8")
    n_watch = sum(1 for t in teams if t["why"] == "watch")
    print(f"✅ 관찰 {len(teams)}팀 (상위 {len(teams) - n_watch} + 관심 {n_watch}) · 멜론 추가 {len(melon_extra_ids(teams))}개 · "
          f"인스타 {len(instagram_handles(teams))}개 → {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
