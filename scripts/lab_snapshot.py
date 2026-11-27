"""매일 점수 스냅샷: 기본 가중치로 계산한 후보 상위 팀을 docs/lab/data/snapshots/<날짜>.csv에 남긴다.

앱의 '오늘 볼 것' 화면이 최신 2개를 비교해 '새로 후보에 들어온 팀', '순위가 크게 오른 팀'을 보여 준다.
점수는 브라우저와 같은 SQL(docs/lab/sql/candidates.sql)로 계산한다(계산식은 한 곳에만).

실행: .venv/bin/python scripts/lab_snapshot.py   (export_lab_data.py 다음에, duckdb 필요)
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab_sql  # noqa: E402

SNAP_DIR = lab_sql.DATA_DIR / "snapshots"
TOP_N = 300          # 기록할 상위 팀 수
KEEP_DAYS = 120      # 남길 스냅샷 개수(오래된 것부터 지움, 저장소 크기 관리)


def write_snapshot(rows: List[dict], out_dir: Path, day: str, keep: int = KEEP_DAYS,
                   reconstructed: bool = False) -> Path:
    """점수 높은 순으로 순위를 매겨 저장하고, 날짜 목록(index.json)을 갱신한다."""
    ranked = sorted(rows, key=lambda r: (-float(r["score"]), str(r["team_key"])))
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{day}.csv"
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["team_key", "score", "rank"])
        for i, r in enumerate(ranked, 1):
            w.writerow([r["team_key"], f"{float(r['score']):g}", i])

    index_path = out_dir / "index.json"
    try:
        rebuilt = set(json.loads(index_path.read_text(encoding="utf-8")).get("reconstructed", []))
    except (OSError, ValueError):
        rebuilt = set()
    rebuilt = (rebuilt | {day}) if reconstructed else (rebuilt - {day})
    days = sorted((p.stem for p in out_dir.glob("*.csv")), reverse=True)
    for old in days[keep:]:
        (out_dir / f"{old}.csv").unlink()
    index = {"dates": days[:keep], "reconstructed": sorted(d for d in rebuilt if d in days[:keep])}
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main(argv: List[str]) -> int:
    """--as-of YYYY-MM-DD: 그날까지의 신호만으로 과거 스냅샷을 다시 만든다(재구성 표시)."""
    as_of = argv[argv.index("--as-of") + 1] if "--as-of" in argv else None
    if as_of and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", as_of):
        print("❌ --as-of 는 YYYY-MM-DD 형식", file=sys.stderr)
        return 2
    try:
        meta = json.loads((lab_sql.DATA_DIR / "meta.json").read_text(encoding="utf-8"))
        con = lab_sql.connect()
    except (OSError, ImportError) as e:
        print(f"❌ 스냅샷 준비 실패 (export_lab_data.py 먼저, .venv에 duckdb 필요): {e}", file=sys.stderr)
        return 1
    day = as_of or meta["data_end"]
    rows = lab_sql.query(con, "candidates.sql", as_of=f"'{day}'", limit=str(TOP_N))
    path = write_snapshot(rows, SNAP_DIR, day, reconstructed=bool(as_of))
    print(f"✅ 점수 스냅샷 {len(rows)}팀 → {path.relative_to(lab_sql.ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
