"""data/raw/ CSV → PostgreSQL (raw 스키마). 표 정의는 scripts/csv_schema.py 에서 자동으로 만든다.

    python3 scripts/load_pg.py              # 전부 다시 적재 (표를 지우고 새로 만듦)
    PGDATABASE=crate_digger python3 scripts/load_pg.py

- 형식 검사(validate_csv)를 통과한 파일만 넣는다. 어느 파일에서 왔는지 source_file 칸에 남긴다.
- 모든 표에 정규화 이름 키를 붙인다: artist_key(끝 괄호 별칭 제거), alias_key(끝 괄호 속 별칭). 표끼리 같은 팀을 잇는 열쇠.
- '2024', '2024-05'처럼 일부만 아는 날짜는 원문을 두고, <이름>_start(기간 첫날)·<이름>_end(기간 마지막 날)를 함께 넣는다.
  백테스트에서 후보 신호는 _end, 정답은 _start로 비교한다 (scripts/timing.py 와 같은 규칙).
- PostgreSQL 실행 파일: 환경변수 PSQL, 없으면 Homebrew postgresql@17 경로.
"""
import csv
import glob
import html
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import validate_csv
from csv_schema import CAREER_FILTER_YEARS, CAREER_FILTERED, OUTCOME_SAME_FAMILY, OUTCOME_TIER, SAME_PROGRAM, STAGE_RANK, TABLES
from newcomer import FAME_FANS, FAME_YEARS, FAME_YEARS_MIN_FANS, MAX_ALBUMS, MAX_YEARS
from normalize import artist_key, split_artist_cell
from timing import outcome_date, signal_date
from venue_xref import canonical_venue_text

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
PSQL = os.environ.get("PSQL", "/opt/homebrew/opt/postgresql@17/bin/psql")
DB = os.environ.get("PGDATABASE", "crate_digger")
TYPES = {"date": "date", "datetime_tz": "timestamptz", "int_pos": "integer", "int0": "integer", "flag01": "smallint"}
TRAILING_ALIAS = re.compile(r"[\(\[]([^\)\]]+)[\)\]]\s*$")


def pg_type(kind):
    return TYPES.get(kind, "text")


def _base(name):
    return re.sub(r"_(at|date)$", "", name)


def columns(table):
    fields = TABLES[table]["fields"]
    cols = [f.name for f in fields]
    for f in fields:
        if f.kind == "date_partial":
            cols += [f"{_base(f.name)}_start", f"{_base(f.name)}_end"]
    if "artist_key" not in cols:
        cols.append("artist_key")
    return cols + ["alias_key", "source_file"]


def ddl(table):
    kinds = {f.name: f.kind for f in TABLES[table]["fields"]}
    parts = []
    for c in columns(table):
        if c in kinds:
            typ = pg_type(kinds[c])
        elif c.endswith(("_start", "_end")):
            typ = "date"
        else:
            typ = "text"
        parts.append(f"  {c} {typ}")
    return f"CREATE TABLE raw.{table} (\n" + ",\n".join(parts) + "\n);"


def alias_key(name):
    m = TRAILING_ALIAS.search(name or "")
    return (artist_key(m.group(1)) or None) if m else None


def _unescape(text):
    """'&amp;amp;' 처럼 두 번 감싼 HTML 기호까지 원래 글자로 (같은 팀이 둘로 갈라지는 것 방지)."""
    prev = None
    while text and text != prev:
        prev, text = text, html.unescape(text)
    return text


def normalize_row(table, row, source_file):
    row = {k: _unescape(v) if isinstance(v, str) else v for k, v in row.items()}
    if table == "raw_kr_gig" and row.get("venue_text"):
        # '라이브홀 (KT&G 상상마당 홍대)' → 'KT&G 상상마당 홍대 라이브홀': SQL 이 괄호 앞만 공연장으로 자르므로 (venue_xref 와 같은 규칙)
        row["venue_text"] = canonical_venue_text(row["venue_text"])
    rec = {c: (row.get(c) or "").strip() or None for c in columns(table)}
    for f in TABLES[table]["fields"]:
        if f.kind == "date_partial":
            rec[f"{_base(f.name)}_start"] = outcome_date(rec[f.name] or "") or None
            rec[f"{_base(f.name)}_end"] = signal_date(rec[f.name] or "") or None
    name = row.get("artist_text", "")
    rec["artist_key"] = artist_key(name) or rec["artist_key"] or None   # 기호를 푼 이름으로 다시 계산
    rec["alias_key"] = alias_key(name)
    rec["source_file"] = source_file
    return [rec[c] for c in columns(table)]


SPLIT_SOURCES = {"overtone"}     # 한 칸에 여러 팀을 쉼표로 적는 출처 — 원본은 두고 적재 때 팀별 행으로 (2026-11-27, 약 25건)


def expand_rows(table, row):
    """원본 한 줄 → 적재할 줄들. raw_press 의 오버톤 행만 'A, B'를 팀별 줄로 나누고 나머지는 그대로."""
    if table != "raw_press" or row.get("source") not in SPLIT_SOURCES:
        return [row]
    names = split_artist_cell(row.get("artist_text", ""))
    if names == [row.get("artist_text", "")] or not names:
        return [row]
    return [dict(row, artist_text=n, artist_key="") for n in names]


DEBUT_OVERRIDES = ROOT / "config" / "debut_overrides.json"   # 사람이 확인한 데뷔일 (export_lab_data.py 와 같은 파일)
FULL_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def load_debut_overrides(path=DEBUT_OVERRIDES):
    """config/debut_overrides.json → {팀 키: 항목}. 파일이 없거나 깨졌으면 빈 dict (항목 검사는 export_lab_data.py 가 함)."""
    try:
        teams = json.loads(Path(path).read_text(encoding="utf-8")).get("teams")
    except (OSError, ValueError, AttributeError):
        return {}
    return teams if isinstance(teams, dict) else {}


def _sql_text(text):
    return "'" + str(text).replace("'", "''") + "'"


def _debut_values(overrides):
    """(팀 키, DATE '데뷔일') 목록 — 날짜 모양이 YYYY-MM-DD 가 아니면 건너뛴다."""
    vals = []
    for key, e in sorted((overrides or {}).items()):
        debut = (e or {}).get("debut", "") if isinstance(e, dict) else ""
        if key and FULL_DATE.match(debut or ""):
            vals.append(f"({_sql_text(key)}, DATE '{debut}')")
    return ", ".join(vals)


def ref_sql(debut_overrides=None):
    """분류 규칙(csv_schema)을 SQL에서도 쓰도록 ref 스키마의 작은 표로 만든다.
    ref.debut_overrides: 사람이 확인한 데뷔일 — core.v_team_profile 이 프로필 첫 발매와 비교해 이른 쪽을 쓴다
    (랩 팀 표 export_lab_data.py 와 같은 규칙이라 정답 '셈' 판정이 두 곳에서 같아진다)."""
    debuts = _debut_values(load_debut_overrides() if debut_overrides is None else debut_overrides)
    tiers = ", ".join(f"('{p}', '{t}', {'true' if p in CAREER_FILTERED else 'false'})" for p, t in sorted(OUTCOME_TIER.items()))
    ranks = ", ".join(f"('{s}', {r})" for s, r in sorted(STAGE_RANK.items(), key=lambda x: x[1]))
    fam = ", ".join(f"('{a}', '{b}')" for a, bs in sorted(OUTCOME_SAME_FAMILY.items()) for b in sorted(bs)) or None
    same = ", ".join(f"('{a}', '{b}')" for a, bs in sorted(SAME_PROGRAM.items()) for b in sorted(bs))
    parts = [
        "CREATE SCHEMA IF NOT EXISTS ref;",
        "DROP TABLE IF EXISTS ref.outcome_tier, ref.stage_rank, ref.outcome_same_family, ref.same_program, ref.settings, "
        "ref.debut_overrides CASCADE;",
        "CREATE TABLE ref.outcome_tier (program text PRIMARY KEY, tier text, career_filtered boolean);",
        f"INSERT INTO ref.outcome_tier VALUES {tiers};",
        "CREATE TABLE ref.stage_rank (stage text PRIMARY KEY, rank integer);",
        f"INSERT INTO ref.stage_rank VALUES {ranks};",
        "CREATE TABLE ref.outcome_same_family (mid_program text, final_program text);",
        f"INSERT INTO ref.outcome_same_family VALUES {fam};" if fam else "",
        "CREATE TABLE ref.same_program (selection_program text, outcome_program text);",
        f"INSERT INTO ref.same_program VALUES {same};",
        "CREATE TABLE ref.settings (name text PRIMARY KEY, value numeric);",
        f"INSERT INTO ref.settings VALUES ('career_filter_years', {CAREER_FILTER_YEARS}), ('fame_fans', {FAME_FANS}), "
        f"('fame_years', {FAME_YEARS}), ('fame_years_min_fans', {FAME_YEARS_MIN_FANS}), ('newcomer_years', {MAX_YEARS}), ('newcomer_albums', {MAX_ALBUMS});",
        "CREATE TABLE ref.debut_overrides (team_key text PRIMARY KEY, debut date);",
        f"INSERT INTO ref.debut_overrides VALUES {debuts};" if debuts else "",
    ]
    return "\n".join(p for p in parts if p)


def psql(sql_text):
    proc = subprocess.run([PSQL, "-v", "ON_ERROR_STOP=1", "-q", "-d", DB, "-c", sql_text],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip()[:500])
    return proc.stdout


def load(raw_dir=RAW_DIR):
    psql("CREATE SCHEMA IF NOT EXISTS raw;")
    psql(ref_sql())
    counts, skipped = {}, []
    for table in TABLES:
        psql(f"DROP TABLE IF EXISTS raw.{table} CASCADE;")
        psql(ddl(table))
        files = sorted(p for p in glob.glob(str(Path(raw_dir) / f"{table}_*.csv")) if validate_csv.table_for(p) == table)
        rows = []
        for f in files:
            if [i for i in validate_csv.validate_file(f) if i.level == "error"]:
                skipped.append(Path(f).name)
                continue
            with open(f, encoding="utf-8-sig", newline="") as fh:
                rows.extend(normalize_row(table, x, Path(f).name) for r in csv.DictReader(fh) for x in expand_rows(table, r))
        if rows:
            with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8", newline="") as tmp:
                csv.writer(tmp).writerows([columns(table)] + rows)
            try:
                psql(f"\\copy raw.{table} ({', '.join(columns(table))}) FROM '{tmp.name}' WITH (FORMAT csv, HEADER true)")
            finally:
                os.unlink(tmp.name)
        counts[table] = len(rows)
    views = ROOT / "sql" / "kr" / "00_core_views.sql"   # 표를 새로 만들면 뷰가 함께 지워지므로 다시 만든다
    if views.exists():
        proc = subprocess.run([PSQL, "-v", "ON_ERROR_STOP=1", "-q", "-d", DB, "-f", str(views)], capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip()[:500])
    return counts, skipped


def main():
    counts, skipped = load()
    for t, n in counts.items():
        print(f"  raw.{t}: {n:,}행")
    if skipped:
        print("⚠️ 형식 검사 실패로 뺀 파일: " + ", ".join(skipped))
    print(f"✅ PostgreSQL '{DB}'에 적재 완료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
