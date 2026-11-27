"""PostgreSQL 분석·검증 SQL을 실행해 '쿼리 원문 + 결과 표' 문서를 만든다 → docs/sql/README.md

    python3 scripts/load_pg.py            # 먼저 적재
    python3 scripts/run_pg_queries.py     # 뷰 만들기 → sql/kr/analysis/*.sql, sql/kr/checks/*.sql 실행

각 SQL 파일 맨 위 '-- ' 주석(질문 / 왜 중요한가 / 읽는 법)을 설명으로 쓰고, 결과는 앞 RESULT_LIMIT행만 싣는다.
(예전 판매 대시보드용 run_queries.py 와는 별개)
"""
import csv
import io
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = ROOT / "sql" / "kr"
OUT = ROOT / "docs" / "sql" / "README.md"
PSQL = os.environ.get("PSQL", "/opt/homebrew/opt/postgresql@17/bin/psql")
DB = os.environ.get("PGDATABASE", "crate_digger")
RESULT_LIMIT = 15
KST = timezone(timedelta(hours=9))
SECTIONS = [("analysis", "분석 SQL", "신호가 나중의 성공(정답)을 얼마나 먼저 알려 주는지"),
            ("checks", "데이터 검증 SQL", "아티스트 매칭·메타데이터 검수: 수집 데이터의 문제 행 찾기")]


def split_header(sql_text):
    head, body, in_head = [], [], True
    for line in sql_text.splitlines():
        if in_head and line.startswith("--"):
            head.append(line.lstrip("-").strip())
        elif in_head and not line.strip():
            continue
        else:
            in_head = False
            body.append(line)
    return [h for h in head if h], "\n".join(body).strip()


def csv_to_markdown(csv_text, limit=RESULT_LIMIT):
    rows = list(csv.reader(io.StringIO(csv_text)))
    if not rows:
        return "_결과 없음_", 0
    header, data = rows[0], rows[1:]
    if not data:
        return "_결과 없음_", 0
    cell = lambda v: (v or "").replace("|", "\\|").replace("\n", " ")
    lines = ["| " + " | ".join(cell(h) for h in header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(cell(v) for v in r) + " |" for r in data[:limit]]
    if len(data) > limit:
        lines.append(f"\n_{len(data)}행 중 {limit}행만 표시_")
    return "\n".join(lines), len(data)


def run_file(path):
    proc = subprocess.run([PSQL, "-v", "ON_ERROR_STOP=1", "-q", "--csv", "-d", DB, "-f", str(path)],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"{path.name}: {proc.stderr.strip()[:300]}")
    return proc.stdout


def build():
    run_file(SQL_DIR / "00_core_views.sql")
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    doc = [f"# SQL 분석·검증 결과 (PostgreSQL)", "",
           f"_자동 생성: `python3 scripts/run_pg_queries.py` · {now} 기준 데이터_", "",
           "모든 쿼리는 `sql/kr/`에 원문이 있어요. 같은 팀 잇기는 대표 팀 키(`team_key` — 연결표 `ref.artist_xref` 우선, 없으면 괄호 별칭), "
           "날짜는 후보 신호 = 기간 끝, 정답 = 기간 첫날로 비교해요 (`sql/kr/00_core_views.sql`).", ""]
    failed = []
    for folder, title, desc in SECTIONS:
        files = sorted((SQL_DIR / folder).glob("*.sql"))
        if not files:
            continue
        doc += [f"## {title}", "", desc, ""]
        for f in files:
            head, body = split_header(f.read_text(encoding="utf-8"))
            try:
                table, n = csv_to_markdown(run_file(f))
            except RuntimeError as e:
                failed.append(str(e))
                table, n = f"_실행 실패: {e}_", 0
            doc += [f"### {f.stem}", ""] + [f"- {h}" for h in head] + ["",
                    "<details><summary>쿼리 보기</summary>", "", "```sql", body, "```", "", "</details>", "",
                    f"결과 {n}행", "", table, ""]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(doc) + "\n", encoding="utf-8")
    return failed


def main():
    failed = build()
    print(f"✅ {OUT.relative_to(ROOT)}" + (f" (실패 {len(failed)}개)" if failed else ""))
    for f in failed:
        print("  ⚠️", f)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
