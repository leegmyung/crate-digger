"""PostgreSQL 분석·검증 SQL(sql/kr/) → BigQuery 문법(sql/bigquery/) 자동 변환·검사.

왜: 현업 데이터 창고(BigQuery 등)에서도 같은 분석을 돌릴 수 있는지 보이려고. 변환은 sqlglot(SQL 문법 변환 도구)로 하고,
    바꾼 결과를 BigQuery 문법으로 다시 읽어 오류가 없는지 검사한다. 머리 주석(질문·읽는 법)은 그대로 둔다.
    PostgreSQL 전용 문법 예: DISTINCT ON → ROW_NUMBER() 창 함수, x::int → CAST(x AS INT64),
    count(*) FILTER (WHERE …) → COUNTIF(…), INTERVAL '3 years' → INTERVAL '3' YEAR.
한계: 문법 변환·파싱 검사까지. 실제 BigQuery에서 실행해 결과를 맞춰 본 것은 아니다(데이터셋 이름 raw.·core.·ref.은 그대로).

실행: .venv/bin/python scripts/sql_to_bigquery.py   (sqlglot 필요: .venv/bin/pip install sqlglot)
"""
from __future__ import annotations

import sys
import re
from pathlib import Path
from typing import Dict, List

import sqlglot
from sqlglot.errors import ErrorLevel

ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "sql" / "kr"
DST_DIR = ROOT / "sql" / "bigquery"
NOTE = "-- (BigQuery 문법으로 자동 변환: scripts/sql_to_bigquery.py — 원문은 sql/kr/ 의 같은 파일)"
# 자동 변환 대상에서 빼는 파일과 이유 (BigQuery 판은 사람이 따로 써야 함)
EXCLUDED: Dict[str, str] = {}
# 00_core_views.sql 의 절차형 블록(DO $$ … $$)은 '연결표가 있으면 이 정의' 분기를 고르는 것뿐이라,
# 운영처럼 ref.artist_xref·ref.venue_xref 가 있다고 보고 그 분기의 뷰 정의로 펼친 뒤 변환한다.
CORE_VIEWS = "00_core_views.sql"
FLAT_TEAM_MAP = """CREATE VIEW core.v_team_map AS
WITH alias_map AS (
    SELECT alias_key, MIN(artist_key) AS main_key
    FROM core.v_signal_base
    WHERE alias_key IS NOT NULL AND alias_key <> '' AND alias_key <> artist_key
    GROUP BY alias_key
)
SELECT x.variant_key, x.artist_key AS team_key, 'xref' AS via
FROM ref.artist_xref x
UNION ALL
SELECT am.alias_key, COALESCE(x2.artist_key, am.main_key), 'alias'
FROM alias_map am
LEFT JOIN ref.artist_xref x2 ON x2.variant_key = am.main_key
WHERE NOT EXISTS (SELECT 1 FROM ref.artist_xref x WHERE x.variant_key = am.alias_key);"""
FLAT_VENUE_MAP = "CREATE VIEW core.v_venue_map AS SELECT variant, venue FROM ref.venue_xref;"
CORE_SKIP_PREFIXES = ("CREATE SCHEMA", "DROP VIEW", "CREATE TABLE")   # BigQuery 데이터셋·뷰 교체·ref 표는 운영 방식에 맞게 따로


def convert(sql: str, notes: List[str] | None = None) -> str:
    """PostgreSQL SQL 전체 → BigQuery SQL. 의미가 조금 달라질 수 있는 변환(예: STRING_AGG 안 정렬의 NULLS FIRST/LAST)은
    예외 대신 notes에 '주의'로 남기고 변환한다. 그 밖에 변환 못 하는 문법은 예외."""
    try:
        stmts = sqlglot.transpile(sql, read="postgres", write="bigquery", pretty=True,
                                  unsupported_level=ErrorLevel.RAISE)
    except sqlglot.errors.UnsupportedError as e:
        if "NULLS" not in str(e) or notes is None:
            raise
        notes.append("STRING_AGG 안 정렬의 NULLS FIRST/LAST는 BigQuery에서 지원 안 됨 → 이어 붙인 목록의 순서만 다를 수 있음")
        stmts = sqlglot.transpile(sql, read="postgres", write="bigquery", pretty=True,
                                  unsupported_level=ErrorLevel.IGNORE)
    return ";\n\n".join(stmts) + ";\n"


def check(sql: str) -> List[str]:
    """BigQuery 문법으로 다시 읽어 본 오류 목록 (없으면 [])."""
    try:
        sqlglot.parse(sql, read="bigquery", error_level=ErrorLevel.RAISE)
        return []
    except sqlglot.errors.ParseError as e:
        return [str(e)[:200]]


def convert_file_text(text: str, notes: List[str] | None = None) -> str:
    """머리 주석(맨 위 -- 줄들)은 그대로 두고 그 아래 SQL만 변환."""
    lines = text.splitlines()
    head = []
    for line in lines:
        if line.startswith("--"):
            head.append(line)
        else:
            break
    body = "\n".join(lines[len(head):])
    local: List[str] = []
    sql = convert(body, local)
    if notes is not None:
        notes.extend(local)
    warn = [f"-- 주의: {n}" for n in dict.fromkeys(local)]
    return "\n".join([*head, NOTE, *warn, sql])


def flatten_core_views(text: str) -> str:
    """00_core_views.sql: DO 블록 2개를 연결표가 있는 분기의 뷰 정의로 바꾸고, 스키마 만들기·뷰 지우기 문은 뺀다."""
    out, i = [], 0
    blocks = [FLAT_TEAM_MAP, FLAT_VENUE_MAP]
    while True:
        j = text.find("DO $$", i)
        if j < 0:
            out.append(text[i:])
            break
        k = text.find("END $$;", j)
        out.append(text[i:j])
        out.append(blocks.pop(0) if blocks else "")
        i = k + len("END $$;")
    # 문장 끝 ';' 뒤에 줄 끝 주석이 붙은 경우(';   -- 설명')도 문장 경계로 본다 (주석은 버림)
    stmts = [st for st in re.split(r";[ \t]*(?:--[^\n]*)?\n", "".join(out)) if st.strip()]
    def first_code(st: str) -> str:   # 앞의 주석 줄은 건너뛰고 첫 SQL 줄로 판정
        return next((line.strip() for line in st.splitlines() if line.strip() and not line.strip().startswith("--")), "")

    def comments(st: str) -> List[str]:
        return [line for line in st.splitlines() if line.strip().startswith("--")]

    keep, carry = [], []
    for st in stmts:
        code = first_code(st)
        if not code or code.upper().startswith(CORE_SKIP_PREFIXES):
            carry += comments(st)        # 건너뛴 문장(스키마·뷰 지우기·ref 표)의 앞 주석은 다음 문장에 붙여 남김
            continue
        keep.append("\n".join([*carry, st.lstrip("\n")]) if carry else st)
        carry = []
    return ";\n".join(keep) + ";\n"


def build(src: Path = SRC_DIR, dst: Path = DST_DIR) -> Dict[str, object]:
    converted, failed, noted, skipped = 0, [], [], []
    for path in sorted(src.rglob("*.sql")):
        rel = path.relative_to(src)
        if path.name in EXCLUDED:
            skipped.append(f"{rel}: {EXCLUDED[path.name]}")
            continue
        try:
            notes: List[str] = []
            text = path.read_text(encoding="utf-8")
            if path.name == CORE_VIEWS:
                text = flatten_core_views(text)
            out = convert_file_text(text, notes)
            if notes:
                noted.append(str(rel))
            problems = check(out)
            if problems:
                failed.append(f"{rel}: {problems[0]}")
                continue
        except (sqlglot.errors.ParseError, sqlglot.errors.UnsupportedError) as e:
            failed.append(f"{rel}: {str(e)[:200]}")
            continue
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(out, encoding="utf-8")
        converted += 1
    report: Dict[str, object] = {"converted": converted, "failed": failed}
    if noted:
        report["noted"] = noted
    if skipped:
        report["skipped"] = skipped
    return report


def main() -> int:
    report = build()
    print(f"✅ BigQuery 변환 {report['converted']}개 → {DST_DIR.relative_to(ROOT)}")
    for f in report.get("noted", []):
        print(f"  ⚠️ {f}: 변환은 됐지만 주의 (파일 맨 위 '주의' 주석 참고)")
    for f in report.get("skipped", []):
        print(f"  ➖ {f}")
    for f in report["failed"]:
        print(f"  ❌ {f}")
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
