"""사진·바로 듣기 수집 대상 팀 목록 + 커버리지 보고

    .venv/bin/python scripts/coverage_targets.py                 # 대상 저장 + docs/lab/data 기준 커버리지
    .venv/bin/python scripts/coverage_targets.py --data-dir DIR  # 다른 폴더(시험 내보내기)의 images·players 로 커버리지

- 대상: 오늘 점수(docs/lab/sql/candidates.sql, 브라우저와 같은 계산) 상위 TOP_N 팀 → 그다음 정답 팀(outcomes.csv).
  저장: data/raw/state/coverage_targets.json (비공개) — collect_spotify·collect_artist_images·collect_musicbrainz·
  collect_yt_channels 가 이 순서대로 먼저 처리한다 (하루 한도가 있는 수집은 앞 팀부터).
- 커버리지: 상위 300·500·정답 팀 중 사진(images.csv)·바로 듣기(players.csv; 없으면 스포티파이 링크 ∪ videos.csv) 비율.
- docs/lab/data 는 읽기만 한다. duckdb 필요(.venv).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "docs" / "lab" / "data"
TARGETS_FILE = ROOT / "data" / "raw" / "state" / "coverage_targets.json"
TOP_N = 500
REPORT_GROUPS = (300, 500)


def build_targets(ranked: List[str], outcomes: Iterable[str], display: Dict[str, str],
                  top_n: int = TOP_N) -> List[dict]:
    """점수 순위 상위 top_n → 그 밖의 정답 팀(키 순). 각 줄: team_key·display_name·rank(상위 밖이면 None)·outcome."""
    outcome_set = set(outcomes)
    top = list(dict.fromkeys(ranked))[:top_n]
    rows = [{"team_key": k, "display_name": display.get(k, k), "rank": i, "outcome": k in outcome_set}
            for i, k in enumerate(top, 1)]
    in_top = set(top)
    rows += [{"team_key": k, "display_name": display.get(k, k), "rank": None, "outcome": True}
             for k in sorted(outcome_set - in_top)]
    return rows


def _share(keys: List[str], photo: Set[str], play: Set[str]) -> dict:
    n = len(keys)
    p, q = sum(k in photo for k in keys), sum(k in play for k in keys)
    pct = (lambda x: round(100.0 * x / n, 1) if n else 0.0)
    return {"teams": n, "photo": p, "play": q, "photo_pct": pct(p), "play_pct": pct(q)}


def coverage(targets: List[dict], photo: Set[str], play: Set[str], groups=REPORT_GROUPS) -> Dict[str, dict]:
    ranked = sorted((t for t in targets if t.get("rank")), key=lambda t: t["rank"])
    out = {f"top{g}": _share([t["team_key"] for t in ranked[:g]], photo, play) for g in groups}
    out["outcomes"] = _share([t["team_key"] for t in targets if t.get("outcome")], photo, play)
    return out


def save_targets(path: Path, targets: List[dict], as_of: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"as_of": as_of, "teams": targets}, ensure_ascii=False, indent=0), encoding="utf-8")


def load_targets(path: Path = TARGETS_FILE) -> List[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("teams") or []
    except (OSError, ValueError, AttributeError):
        return []


def _csv(path: Path) -> List[dict]:
    try:
        with open(path, encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except OSError:
        return []


def media_sets(data_dir: Path) -> tuple:
    """(사진 있는 팀, 바로 듣기 가능한 팀)."""
    photo = {r["team_key"] for r in _csv(data_dir / "images.csv")}
    players = _csv(data_dir / "players.csv")
    if players:
        play = {r["team_key"] for r in players}
    else:
        play = {r["team_key"] for r in _csv(data_dir / "links.csv") if r.get("platform") == "spotify"}
        play |= {r["team_key"] for r in _csv(data_dir / "videos.csv")}
    return photo, play


def ranked_today(as_of: str, limit: int = TOP_N) -> List[str]:
    import lab_sql
    con = lab_sql.connect()
    rows = lab_sql.query(con, "candidates.sql", as_of=f"'{as_of}'", limit=str(limit))
    return [r["team_key"] for r in sorted(rows, key=lambda r: (-float(r["score"]), str(r["team_key"])))]


def print_coverage(cov: Dict[str, dict]) -> None:
    for name, c in cov.items():
        print(f"  {name}: {c['teams']}팀 — 사진 {c['photo']} ({c['photo_pct']}%) · 바로 듣기 {c['play']} ({c['play_pct']}%)")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="사진·바로 듣기 수집 대상 + 커버리지")
    ap.add_argument("--data-dir", type=Path, default=DATA_DIR, help="커버리지를 셀 images·players 폴더")
    args = ap.parse_args(argv)
    try:
        meta = json.loads((DATA_DIR / "meta.json").read_text(encoding="utf-8"))
        ranked = ranked_today(meta["data_end"])
    except (OSError, ValueError, KeyError, ImportError) as e:
        print(f"❌ 대상 계산 실패 (export_lab_data 먼저, .venv에 duckdb 필요): {e}", file=sys.stderr)
        return 1
    display = {r["team_key"]: r["display_name"] for r in _csv(DATA_DIR / "teams.csv")}
    outcomes = {r["team_key"] for r in _csv(DATA_DIR / "outcomes.csv")}
    targets = build_targets(ranked, outcomes, display)
    save_targets(TARGETS_FILE, targets, meta["data_end"])
    print(f"✅ 사진·바로 듣기 대상 {len(targets)}팀 (상위 {min(TOP_N, len(ranked))} + 정답) → {TARGETS_FILE.relative_to(ROOT)}")
    print_coverage(coverage(targets, *media_sets(args.data_dir)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
