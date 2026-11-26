"""sql/queries/*.sql 을 실행해 대시보드용 JSON을 out/ 에 저장.

    python3 scripts/run_queries.py [bandcamp.db] [입력 CSV 이름]

각 JSON은 {"rows": [...], "meta": [...]} 형태이며, meta 에 실행한 SQL 원문을
그대로 넣어 대시보드의 Sources 패널에서 쿼리를 확인할 수 있게 합니다.
"""
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main(db_path, input_name):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    out = ROOT / "out"
    out.mkdir(exist_ok=True)
    for q in sorted((ROOT / "sql/queries").glob("*.sql")):
        sql = q.read_text(encoding="utf-8")
        rows = [dict(r) for r in con.execute(sql)]
        payload = {
            "rows": rows,
            "meta": [
                {"label": q.name, "value": sql, "type": "code", "lang": "sql"},
                {"label": "Input", "value": f"{input_name} → sql/schema.sql + sql/load.sql (SQLite)"},
            ],
        }
        dest = out / (q.stem + ".json")
        dest.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{q.name:24s} {len(rows):>4} rows → {dest.relative_to(ROOT)}")
    con.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "bandcamp.db"),
         sys.argv[2] if len(sys.argv) > 2 else "data/sample_salesfeed.csv")
