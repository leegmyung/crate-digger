"""signals.csv 의 Parquet 판 → docs/lab/data/signals.parquet (CSV 는 그대로 둔다 — 다른 도구·파이썬 랩 호환).

    .venv/bin/python scripts/export_signals_parquet.py [--data-dir 폴더]   (scripts/build_app_extras.sh 맨 앞)

앱 첫 진입에서 가장 큰 파일이 signals.csv(약 4MB, GitHub Pages gzip 약 0.5MB)다. 같은 내용을 Parquet(zstd)로 내면
약 0.33MB 이고, 브라우저 DuckDB 가 CSV 를 칸 추측하며 읽는 것보다 빨리 읽는다.
칸 모양은 DuckDB read_csv_auto 가 CSV 에서 고르는 것과 같게 만든다(앱 features.sql 이 그대로 돌게).
앱(docs/app/db.js)은 meta.json extras_rows['signals.parquet'] 행 수가 rows.signals 와 같을 때만 Parquet 을 읽는다
(scripts/update_meta_extras.py 가 CSV 보다 오래된 Parquet 은 목록에서 뺀다).
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path
from typing import Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab_sql  # noqa: E402


def _sql_path(p: Path) -> str:
    return str(p).replace("'", "''")


def export(src: Path, out: Path) -> int:
    """CSV → Parquet(zstd). 행 수를 돌려준다. 임시 파일에 쓰고 바꿔 끼워 반쯤 쓴 파일을 앱이 읽지 않게."""
    import duckdb   # .venv 에만 있어 여기서 불러온다

    fd, tmp = tempfile.mkstemp(dir=out.parent, prefix=".signals.", suffix=".parquet")
    os.close(fd)
    try:
        con = duckdb.connect()
        con.execute(f"COPY (SELECT * FROM read_csv_auto('{_sql_path(src)}', header=true)) "
                    f"TO '{_sql_path(Path(tmp))}' (FORMAT parquet, COMPRESSION zstd)")
        rows = con.execute(f"SELECT COUNT(*) FROM read_parquet('{_sql_path(Path(tmp))}')").fetchone()[0]
        con.close()
        os.replace(tmp, out)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return int(rows)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="signals.csv → signals.parquet")
    ap.add_argument("--data-dir", type=Path, default=lab_sql.DATA_DIR)
    args = ap.parse_args(argv)
    src = args.data_dir / "signals.csv"
    if not src.is_file():
        print(f"❌ {src} 가 없어요 — export_lab_data.py 를 먼저 돌리세요", file=sys.stderr)
        return 1
    out = args.data_dir / "signals.parquet"
    rows = export(src, out)
    print(f"✅ signals {rows}행 → {out} ({out.stat().st_size // 1024}KB, CSV {src.stat().st_size // 1024}KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
