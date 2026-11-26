"""크롤 CSV → SQLite DB 구축.

    python3 scripts/build_db.py data/my_crawl.csv  [bandcamp.db]

1) sql/schema.sql 로 테이블 생성 (기존 DB는 초기화)
2) CSV를 stg_salesfeed 에 적재 (없는 컬럼은 NULL)
3) sql/load.sql 로 차원/사실 테이블 채움
"""
import csv
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NUMERIC = {"item_price", "amount_paid", "amount_paid_usd"}


def to_val(col, v):
    if v is None or v == "":
        return None
    if col in NUMERIC:
        try:
            return float(str(v).replace(",", ""))
        except ValueError:
            return None
    return v


def main(csv_path, db_path):
    con = sqlite3.connect(db_path)
    con.executescript((ROOT / "sql/schema.sql").read_text(encoding="utf-8"))
    cols = [r[1] for r in con.execute("PRAGMA table_info(stg_salesfeed)")]
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        data = [tuple(to_val(c, row.get(c)) for c in cols) for row in reader]
    con.executemany(f"INSERT INTO stg_salesfeed ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", data)
    con.executescript((ROOT / "sql/load.sql").read_text(encoding="utf-8"))
    con.commit()
    for t in ["stg_salesfeed", "dim_artist", "dim_item", "dim_country", "dim_currency", "item_tags", "fact_sales"]:
        print(f"{t:15s} {con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]:>8,}")
    con.close()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else str(ROOT / "bandcamp.db"))
