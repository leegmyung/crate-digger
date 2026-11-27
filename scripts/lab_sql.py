"""랩 SQL(docs/lab/sql/*.sql)을 파이썬 DuckDB로 돌리는 도우미. 브라우저 앱(docs/app/db.js)과 같은 규칙.

- 자리표시자 {{이름}}을 문자열로 치환한다(값은 SQL 조각: 날짜는 "'2025-01-01'", 목록은 "['공연']").
- tests/test_lab_sql.py, scripts/lab_snapshot.py가 쓴다. duckdb는 .venv에만 있을 수 있다.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = ROOT / "docs" / "lab" / "sql"
DATA_DIR = ROOT / "docs" / "lab" / "data"
CAPACITY = ROOT / "config" / "venue_capacity.json"   # 공연장 체급(S·M·L·XL) — venue_tiers 표의 원본
TABLES = ("signals", "teams", "outcomes", "programs")
# 협업(피처링) 표: collabs.csv 가 없을 때 만드는 빈 표 (앱 docs/app/db.js 도 같은 정의). features.sql 이 이 표를 읽는다.
COLLABS_DDL = ("CREATE TABLE collabs(team_key VARCHAR, partner_key VARCHAR, partner_name VARCHAR, "
               "release_date DATE, role VARCHAR, partner_established BOOLEAN)")
# 보조 표 3개 (없으면 빈 표, 앱 docs/app/db.js 도 같은 정의로 만들면 같은 SQL이 돈다) — docs/peer_rising.md
#   snapshots: docs/lab/data/snapshots/<날짜>.csv 를 모두 합친 것 (rank_change.sql)
#   team_cities: docs/lab/data/team_cities.csv (scripts/city_profiles.py, rank_change.sql 의 지역 안 순위)
#   venue_tiers: config/venue_capacity.json 의 공연장 체급 (rising_preset.sql 의 체급 상한)
SNAPSHOTS_DDL = "CREATE TABLE snapshots(snap_date DATE, team_key VARCHAR, score DOUBLE, rank INTEGER)"
TEAM_CITIES_DDL = ("CREATE TABLE team_cities(team_key VARCHAR, home_city VARCHAR, cities INTEGER, first_city VARCHAR, "
                   "first_date VARCHAR, seoul_first_date VARCHAR, months_to_seoul VARCHAR, nights INTEGER)")
VENUE_TIERS_DDL = "CREATE TABLE venue_tiers(venue VARCHAR, tier VARCHAR)"

DEFAULTS: Dict[str, str] = {
    "lookback_years": "3", "newcomer_years": "3", "exclude_famous": "true", "outcome_tier": "'any'",
    "horizon_months": "24", "genre": "''", "branches": "['공연','선정·지원','발매','큐레이션']",
    # 점수 v2 기본 가중치 (2026-11-27): 발굴 신호만 + 맥락 매체 약하게, 정답 등급 가중 교차 검증(docs/score_tuning.md)
    "w_branch": "1", "w_stage": "1", "w_peer": "0", "w_dmz": "0", "w_gigs": "0", "w_outlets": "1",
    "outlet_cap": "3", "w_recent": "0", "w_venues": "1", "w_winner": "2", "w_context": "0.5", "w_collab": "0",
    "k_list": "[20,50,100,200]", "only_no_outcome": "true", "limit": "100",
    # 이웃 비교·떠오르는 팀 (docs/peer_rising.md)
    "team": "''", "min_peers": "30", "window_days": "30", "min_recent": "2", "max_tier": "'M'", "max_fans": "10000",
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


def _sql_path(path: Path) -> str:
    return path.as_posix().replace("'", "''")


def venue_tier_rows(capacity_path: Path = CAPACITY) -> List[tuple]:
    """config/venue_capacity.json → [(공연장, 체급)]. 파일이 없거나 깨졌거나 체급을 모르는 곳은 뺀다."""
    try:
        data = json.loads(Path(capacity_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    venues = data.get("venues") if isinstance(data, dict) else None
    return sorted((name, str(info["tier"])) for name, info in (venues or {}).items()
                  if isinstance(info, dict) and info.get("tier"))


def load_extras(con, data_dir: Path = DATA_DIR, capacity_path: Optional[Path] = CAPACITY) -> None:
    """보조 표 snapshots·team_cities·venue_tiers 를 만든다. 원본이 없으면 빈 표."""
    con.execute(SNAPSHOTS_DDL)
    snap_dir = data_dir / "snapshots"
    if snap_dir.is_dir() and any(snap_dir.glob("*.csv")):
        con.execute(f"""INSERT INTO snapshots
            SELECT CAST(regexp_extract(filename, '(\\d{{4}}-\\d{{2}}-\\d{{2}})\\.csv$', 1) AS DATE),
                   CAST(team_key AS VARCHAR), CAST(score AS DOUBLE), CAST(rank AS INTEGER)
            FROM read_csv('{_sql_path(snap_dir)}/*.csv', header=true, filename=true,
                          columns={{'team_key': 'VARCHAR', 'score': 'DOUBLE', 'rank': 'INTEGER'}})""")
    con.execute(TEAM_CITIES_DDL)
    cities = data_dir / "team_cities.csv"
    if cities.exists():
        con.execute(f"INSERT INTO team_cities SELECT * FROM read_csv('{_sql_path(cities)}', header=true, all_varchar=true)")
    con.execute(VENUE_TIERS_DDL)
    rows = venue_tier_rows(capacity_path) if capacity_path else []
    if rows:
        con.executemany("INSERT INTO venue_tiers VALUES (?, ?)", rows)


def connect(data_dir: Path = DATA_DIR, capacity_path: Optional[Path] = CAPACITY):
    """CSV 4개를 표로 올리고 보조 표(load_extras)와 공통 매크로(features.sql)를 만든 DuckDB 연결."""
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
    for col, typ in (("same_house_sources", "VARCHAR DEFAULT ''"), ("same_house_scored", "BOOLEAN DEFAULT false")):
        con.execute(f"ALTER TABLE outcomes ADD COLUMN IF NOT EXISTS {col} {typ}")   # '같은 집안' 열이 없는 옛 CSV도 읽게
    con.execute("ALTER TABLE teams ADD COLUMN IF NOT EXISTS newcomer_check VARCHAR")   # 신인 판정 확인 상태가 없는 옛 CSV도 읽게
    load_extras(con, data_dir, capacity_path)
    con.execute(read_sql("features.sql"))
    return con


def query(con, name: str, **params: str) -> List[dict]:
    cur = con.execute(fill(read_sql(name), **params))
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]
