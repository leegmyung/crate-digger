"""랩 SQL(docs/lab/sql/*.sql)을 파이썬 DuckDB로 돌리는 도우미. 브라우저 앱(docs/app/db.js)과 같은 규칙.

- 자리표시자 {{이름}}을 문자열로 치환한다(값은 SQL 조각: 날짜는 "'2025-01-01'", 목록은 "['공연']").
- tests/test_lab_sql.py, scripts/lab_snapshot.py가 쓴다. duckdb는 .venv에만 있을 수 있다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = ROOT / "docs" / "lab" / "sql"
DATA_DIR = ROOT / "docs" / "lab" / "data"
TABLES = ("signals", "teams", "outcomes", "programs")
# 협업(피처링) 표: collabs.csv 가 없을 때 만드는 빈 표 (앱 docs/app/db.js 도 같은 정의). features.sql 이 이 표를 읽는다.
COLLABS_DDL = ("CREATE TABLE collabs(team_key VARCHAR, partner_key VARCHAR, partner_name VARCHAR, "
               "release_date DATE, role VARCHAR, partner_established BOOLEAN)")

DEFAULTS: Dict[str, str] = {
    "lookback_years": "3", "newcomer_years": "3", "exclude_famous": "true", "outcome_tier": "'any'",
    "horizon_months": "24", "genre": "''", "branches": "['공연','선정·지원','발매','큐레이션']",
    # 점수 v2 기본 가중치 (2026-11-27): 발굴 신호만 + 맥락 매체 약하게, 정답 등급 가중 교차 검증(docs/score_tuning.md)
    "w_branch": "1", "w_stage": "1", "w_peer": "0", "w_dmz": "0", "w_gigs": "0", "w_outlets": "1",
    "outlet_cap": "3", "w_recent": "0", "w_venues": "1", "w_winner": "2", "w_context": "0.5", "w_collab": "0",
    "k_list": "[20,50,100,200]", "only_no_outcome": "true", "limit": "100",
}
V0_WEIGHTS: Dict[str, str] = {"w_branch": "2", "w_stage": "1", "w_peer": "1", "w_dmz": "0.5", "w_gigs": "0.5",
                              "w_outlets": "1", "w_recent": "0", "w_venues": "0", "w_winner": "0", "w_context": "0"}


def fill(sql: str, **params: str) -> str:
    """자리표시자를 채운다. 남은 자리표시자가 있으면 어떤 것인지 알려 주고 멈춘다."""
    for key, value in {**DEFAULTS, **params}.items():
        sql = sql.replace("{{" + key + "}}", value)
    if "{{" in sql:
        i = sql.index("{{")
        raise ValueError(f"채우지 않은 자리표시자: {sql[i:sql.index('}}', i) + 2]}")
    return sql


def read_sql(name: str) -> str:
    return (SQL_DIR / name).read_text(encoding="utf-8")


def connect(data_dir: Path = DATA_DIR):
    """CSV 4개를 표로 올리고 공통 매크로(features.sql)를 만든 DuckDB 연결."""
    import duckdb

    con = duckdb.connect()
    for t in TABLES:
        path = (data_dir / f"{t}.csv").as_posix().replace("'", "''")
        con.execute(f"CREATE TABLE {t} AS SELECT * FROM read_csv_auto('{path}', header=true)")
    collabs = data_dir / "collabs.csv"
    if collabs.exists():
        path = collabs.as_posix().replace("'", "''")
        con.execute(f"CREATE TABLE collabs AS SELECT * FROM read_csv_auto('{path}', header=true)")
    else:
        con.execute(COLLABS_DDL)
    con.execute(read_sql("features.sql"))
    return con


def query(con, name: str, **params: str) -> List[dict]:
    cur = con.execute(fill(read_sql(name), **params))
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]
