"""유튜브 매일 지표 수집 → data/raw/raw_video_stats_<날짜>.csv (영상 번호별 조회수·좋아요·댓글 수, 비공개 원본)

    python3 scripts/collect_video_stats.py

- 대상: docs/lab/data/videos.csv 의 영상(팀별 무대·공식 영상). YouTube Data API videos.list(part=statistics)를
  50개씩 묶어 부른다(1회 = 1단위). 하루 예산 DAILY_BUDGET 단위 — 지금 영상 약 1,700개면 35단위 정도.
- 키는 .env 의 YOUTUBE_API_KEY (collect_videos.py 의 load_env·YouTubeClient 재사용, 키는 출력·기록하지 않음).
- 같은 날 다시 돌리면 그날 파일을 덮어쓴다(하루 1행/영상). 팀 연결은 export_video_momentum.py 가 videos.csv 로 한다 —
  이 파일엔 team_key 를 넣지 않아 export_lab_data.py(raw_video_*.csv 를 영상 목록으로 읽음)에 섞이지 않는다.
- 기록이 오늘부터 쌓이므로 7일 증가량은 1주 뒤부터 나온다 (출처 역할: 검증 대기).
"""
from __future__ import annotations

import csv
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_videos as cv  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
VIDEOS = ROOT / "docs" / "lab" / "data" / "videos.csv"
RAW_DIR = ROOT / "data" / "raw"
COLUMNS = ["date", "video_id", "view_count", "like_count", "comment_count"]
BATCH = 50              # videos.list 한 번에 최대 50개
DAILY_BUDGET = 500      # 하루 쓸 API 단위 상한 (다른 유튜브 수집과 나눠 씀)


def video_ids(rows: List[dict]) -> List[str]:
    """영상 목록 → 중복 없는 올바른 영상 번호 (처음 나온 순서)."""
    return list(dict.fromkeys(r["video_id"] for r in rows if cv.valid_video_id(r.get("video_id"))))


def _count(stats: dict, key: str):
    v = stats.get(key)
    return int(v) if str(v or "").isdigit() else ""      # 좋아요 숨김 등은 빈 칸


def fetch_stats(ids: List[str], get: Callable[[str, dict, int], dict], day: str) -> List[dict]:
    """50개씩 조회. 한도에 닿으면 그때까지 받은 것만 돌려준다."""
    rows: List[dict] = []
    for i in range(0, len(ids), BATCH):
        try:
            body = get("videos", {"part": "statistics", "id": ",".join(ids[i:i + BATCH])}, cv.COST_LIST)
        except cv.QuotaExceeded as e:
            print(f"⚠️ 유튜브 한도에 닿아 멈춤 (받은 것까지 저장): {e}", file=sys.stderr)
            break
        for item in body.get("items") or []:
            s = item.get("statistics") or {}
            rows.append({"date": day, "video_id": item.get("id", ""), "view_count": _count(s, "viewCount"),
                         "like_count": _count(s, "likeCount"), "comment_count": _count(s, "commentCount")})
    return rows


def write_rows(raw_dir: Path, day: str, rows: List[dict]) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"raw_video_stats_{day}.csv"
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    return path


def main() -> int:
    key = cv.load_env(cv.ENV_FILE).get("YOUTUBE_API_KEY")
    if not key:
        print("❌ YOUTUBE_API_KEY 가 없어요 (.env)", file=sys.stderr)
        return 1
    try:
        with open(VIDEOS, encoding="utf-8") as f:
            ids = video_ids(list(csv.DictReader(f)))
    except OSError:
        print("❌ docs/lab/data/videos.csv 가 없어요 (export_lab_data.py 먼저)", file=sys.stderr)
        return 1
    day = f"{datetime.now(cv.KST):%Y-%m-%d}"
    client = cv.YouTubeClient(key, quota=cv.Quota(DAILY_BUDGET))
    try:
        rows = fetch_stats(ids, client.get, day)
    except cv.YouTubeError as e:
        print(f"❌ 유튜브 조회 실패: {e}", file=sys.stderr)
        return 1
    path = write_rows(RAW_DIR, day, rows)
    print(f"✅ 유튜브 지표: 영상 {len(ids):,}개 중 {len(rows):,}개 → {path.relative_to(ROOT)} (사용 {client.quota.used}단위)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
