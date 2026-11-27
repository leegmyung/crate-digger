"""공연장 체급 → docs/lab/data/venue_tiers.csv — 앱(브라우저)이 config/ 를 못 읽어서 랩 데이터로 내보낸다.

원본: config/venue_capacity.json (수용 인원을 확인한 공연장만 체급 S ~150 · M ~400 · L ~1,000 · XL 1,001~).
칸: venue(랩 signals.csv 의 공연장 대표 이름), tier. 체급을 모르는 곳은 뺀다. 원본이 없으면 헤더만 쓴다.
쓰는 곳: docs/lab/sql/rising_preset.sql 의 체급 상한 (lab_sql.connect 의 venue_tiers 표와 같은 칸, docs/peer_rising.md).

실행: .venv/bin/python scripts/export_venue_tiers.py [--capacity 파일] [--out 파일]   (매일: scripts/build_app_extras.sh)
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab_sql  # noqa: E402

OUT = lab_sql.DATA_DIR / "venue_tiers.csv"
FIELDS = ("venue", "tier")


def export(capacity_path: Path = lab_sql.CAPACITY, out: Path = OUT) -> int:
    """체급을 아는 공연장을 이름순으로 쓰고 행 수를 돌려준다."""
    rows = lab_sql.venue_tier_rows(capacity_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(FIELDS)
        w.writerows(rows)
    return len(rows)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="config/venue_capacity.json → docs/lab/data/venue_tiers.csv")
    ap.add_argument("--capacity", type=Path, default=lab_sql.CAPACITY)
    ap.add_argument("--out", type=Path, default=OUT, help="쓸 파일 (21~23시엔 랩 데이터 대신 다른 곳으로)")
    args = ap.parse_args(argv)
    n = export(args.capacity, args.out)
    print(f"✅ 공연장 체급 {n}곳 → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
