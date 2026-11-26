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
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import validate_csv
from csv_schema import CAREER_FILTER_YEARS, CAREER_FILTERED, OUTCOME_SAME_FAMILY, OUTCOME_TIER, SAME_PROGRAM, STAGE_RANK, TABLES
from newcomer import FAME_FANS, FAME_YEARS, FAME_YEARS_MIN_FANS, MAX_ALBUMS, MAX_YEARS
from normalize import artist_key
from timing import outcome_date, signal_date

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


def ref_sql():
    """분류 규칙(csv_schema)을 SQL에서도 쓰도록 ref 스키마의 작은 표로 만든다."""
    tiers = ", ".join(f"('{p}', '{t}', {'true' if p in CAREER_FILTERED else 'false'})" for p, t in sorted(OUTCOME_TIER.items()))
    ranks = ", ".join(f"('{s}', {r})" for s, r in sorted(STAGE_RANK.items(), key=lambda x: x[1]))
    fam = ", ".join(f"('{a}', '{b}')" for a, bs in sorted(OUTCOME_SAME_FAMILY.items()) for b in sorted(bs)) or None
    same = ", ".join(f"('{a}', '{b}')" for a, bs in sorted(SAME_PROGRAM.items()) for b in sorted(bs))
    parts = [
        "CREATE SCHEMA IF NOT EXISTS ref;",
        "DROP TABLE IF EXISTS ref.outcome_tier, ref.stage_rank, ref.outcome_same_family, ref.same_program, ref.settings CASCADE;",
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
                rows.extend(normalize_row(table, r, Path(f).name) for r in csv.DictReader(fh))
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
