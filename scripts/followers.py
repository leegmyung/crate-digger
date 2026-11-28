"""플랫폼별 팔로워 30일 변화 → docs/lab/data/followers.csv (뼈대 — 기록이 3~4주 쌓인 뒤 매일 실행에 넣는다)

    .venv/bin/python scripts/followers.py              # 쌓인 기록으로 표 만들기
    .venv/bin/python scripts/followers.py --dry-run    # 파일은 안 쓰고 몇 줄 나올지만

설계: docs/followers_plan.md. 원본(모두 비공개 data/raw/):
  인스타  raw_artist_profile_<날짜>_instagram*.csv (fan_count = 팔로워, artist_source_id = 계정) — collect_ig_artists --handles-file 이 7일마다
  멜론    raw_artist_profile_<날짜>_melon*.csv (fan_count = 팬 수, artist_source_id = 멜론 번호) — collect_artists --refresh 가 7일마다
  스포티파이 state/followers_spotify.jsonl (collect_spotify 가 검색 응답에 팔로워가 있을 때만 한 줄씩)
팀 키: 인스타·멜론은 docs/lab/data/links.csv 의 주소로(계정·번호 → 팀), 스포티파이는 줄에 적힌 team_key.
비교: 팀·플랫폼마다 가장 최근 기록(latest)과, 그보다 21~35일 앞 기록 중 30일에 가장 가까운 것(base). base 가 없으면 줄을 안 쓴다
(짧은 간격 변화를 30일 변화처럼 보이지 않게). 앱은 update_meta_extras EXTRAS 에 followers.csv 를 넣은 뒤 팀 개요 변화 칸에서 읽는다.
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
DATA_DIR = ROOT / "docs" / "lab" / "data"
OUT = DATA_DIR / "followers.csv"
SPOTIFY_LOG = RAW_DIR / "state" / "followers_spotify.jsonl"
MIN_DAYS, MAX_DAYS, TARGET_DAYS = 21, 35, 30
COLUMNS = ("team_key", "platform", "latest_date", "latest", "base_date", "base", "change", "change_pct")
MELON_ID = re.compile(r"[?&]artistId=(\d+)")
INSTA = re.compile(r"^https://(?:www\.)?instagram\.com/([A-Za-z0-9._]+)/?$")

History = Dict[Tuple[str, str], Dict[str, int]]   # (팀, 플랫폼) → {날짜: 값}


def _count(text: str) -> Optional[int]:
    t = (text or "").replace(",", "").strip()
    return int(t) if t.isdigit() else None


def history(rows: Iterable[Mapping], platform: str, key_of: Mapping[str, str]) -> History:
    """원본 프로필 행 → (팀, 플랫폼) 별 날짜 → 값 (같은 날 여러 번이면 마지막 값, 팀을 모르거나 값이 없으면 뺌)."""
    out: History = {}
    for r in sorted(rows, key=lambda r: r.get("collected_at") or ""):
        team = key_of.get(r.get("artist_source_id") or "")
        value = _count(r.get("fan_count") or "")
        day = (r.get("collected_at") or "")[:10]
        if team and value is not None and day:
            out.setdefault((team, platform), {})[day] = value
    return out


def spotify_history(lines: Iterable[str]) -> History:
    out: History = {}
    for line in lines:
        try:
            d = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(d, dict) and d.get("team_key") and isinstance(d.get("followers"), int) and d.get("date"):
            out.setdefault((d["team_key"], "spotify"), {})[str(d["date"])[:10]] = d["followers"]
    return out


def _days(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def compare(hist: History) -> List[dict]:
    rows = []
    for (team, platform), series in sorted(hist.items()):
        latest_day = max(series)
        cands = [d for d in series if MIN_DAYS <= _days(d, latest_day) <= MAX_DAYS]
        if not cands:
            continue
        base_day = min(cands, key=lambda d: (abs(_days(d, latest_day) - TARGET_DAYS), d))
        latest, base = series[latest_day], series[base_day]
        rows.append({"team_key": team, "platform": platform, "latest_date": latest_day, "latest": latest,
                     "base_date": base_day, "base": base, "change": latest - base,
                     "change_pct": round((latest - base) / base * 100, 1) if base else None})
    return rows


def _csv(pattern: str) -> List[dict]:
    rows: List[dict] = []
    for f in sorted(glob.glob(str(RAW_DIR / pattern))):
        with open(f, encoding="utf-8", newline="") as fh:
            rows += list(csv.DictReader(fh))
    return rows


def link_maps(links_path: Path) -> Tuple[Dict[str, str], Dict[str, str]]:
    """links.csv → (멜론 번호 → 팀, 인스타 계정 → 팀)."""
    melon: Dict[str, str] = {}
    insta: Dict[str, str] = {}
    if not links_path.exists():
        return melon, insta
    with open(links_path, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            url = r.get("url") or ""
            if r.get("platform") == "melon" and (m := MELON_ID.search(url)):
                melon.setdefault(m.group(1), r["team_key"])
            elif r.get("platform") == "instagram" and (m := INSTA.match(url.strip())):
                insta.setdefault(m.group(1), r["team_key"])
    return melon, insta


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="플랫폼별 팔로워 30일 변화")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    melon_key, insta_key = link_maps(DATA_DIR / "links.csv")
    hist: History = {}
    hist.update(history(_csv("raw_artist_profile_*_instagram*.csv"), "instagram", insta_key))
    hist.update(history(_csv("raw_artist_profile_*_melon*.csv"), "melon", melon_key))
    if SPOTIFY_LOG.exists():
        hist.update(spotify_history(SPOTIFY_LOG.read_text(encoding="utf-8").splitlines()))
    rows = compare(hist)
    by_platform = {p: sum(1 for r in rows if r["platform"] == p) for p in ("instagram", "melon", "spotify")}
    print(f"팀·플랫폼 기록 {len(hist)}개 → 30일 비교 가능 {len(rows)}줄 {by_platform}")
    if args.dry_run:
        return 0
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows([{c: ("" if r[c] is None else r[c]) for c in COLUMNS} for r in rows])
    print(f"✅ → {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
