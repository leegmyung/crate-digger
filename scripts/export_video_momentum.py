"""팀별 유튜브 7일 조회수 증가량 → docs/lab/data/video_momentum.csv (공개: 팀 키·숫자만)

    python3 scripts/export_video_momentum.py

- 입력: data/raw/raw_video_stats_*.csv (collect_video_stats.py, 영상 번호별 날짜별 조회수) + docs/lab/data/videos.csv (영상 → 팀).
- views_7d_gain = 팀 영상마다 (가장 최근 날짜 조회수 − 그보다 BASE_DAYS 일 이상 이전 중 가장 늦은 기록 조회수)의 합.
  7일 전 기록이 있는 영상이 하나도 없으면 빈 칸(아직 모름). latest_views = 가장 최근 날짜 조회수 합, videos = 그날 기록이 있는 영상 수.
- 기록은 2026-11-28부터 쌓인다 → 7일 증가량은 1주 뒤부터. 반응 지표라 출처 역할은 '검증 대기'.
"""
from __future__ import annotations

import csv
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
VIDEOS = ROOT / "docs" / "lab" / "data" / "videos.csv"
OUT = ROOT / "docs" / "lab" / "data" / "video_momentum.csv"
FIELDS = ["team_key", "views_7d_gain", "latest_views", "videos"]
BASE_DAYS = 7


def _views(r: dict):
    v = str(r.get("view_count") or "")
    return int(v) if v.isdigit() else None


def momentum_rows(stats: List[dict], videos: List[dict]) -> List[dict]:
    history: Dict[str, Dict[str, int]] = {}          # 영상 → {날짜: 조회수}
    for r in stats:
        v = _views(r)
        if v is not None and r.get("video_id") and r.get("date"):
            history.setdefault(r["video_id"], {})[r["date"][:10]] = v
    if not history:
        return []
    latest = max(d for h in history.values() for d in h)
    base_limit = (date.fromisoformat(latest) - timedelta(days=BASE_DAYS)).isoformat()
    teams: Dict[str, dict] = {}
    seen = set()
    for row in videos:
        team, vid = row.get("team_key"), row.get("video_id")
        h = history.get(vid or "")
        if not team or not h or latest not in h or (team, vid) in seen:
            continue
        seen.add((team, vid))
        t = teams.setdefault(team, {"team_key": team, "views_7d_gain": "", "latest_views": 0, "videos": 0})
        t["latest_views"] += h[latest]
        t["videos"] += 1
        base_days = [d for d in h if d <= base_limit]
        if base_days:
            gain = h[latest] - h[max(base_days)]
            t["views_7d_gain"] = (t["views_7d_gain"] or 0) + gain
    return [teams[k] for k in sorted(teams)]


def _read(paths) -> List[dict]:
    rows: List[dict] = []
    for p in paths:
        with open(p, encoding="utf-8") as f:
            rows.extend(csv.DictReader(f))
    return rows


def write_csv(path: Path, rows: List[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    return path


def main() -> int:
    stats = _read(sorted(RAW_DIR.glob("raw_video_stats_*.csv")))
    videos = _read([VIDEOS]) if VIDEOS.exists() else []
    rows = momentum_rows(stats, videos)
    write_csv(OUT, rows)
    known = sum(1 for r in rows if r["views_7d_gain"] != "")
    print(f"✅ 유튜브 7일 증가량 → {OUT.relative_to(ROOT)} (팀 {len(rows):,}, 7일 증가량 계산된 팀 {known:,})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
