"""docs/source_roles.md 의 출처 성적표 구간을 자동 생성으로 교체한다 (주석 마커 사이만, 나머지 글은 그대로).

    .venv/bin/python scripts/source_roles_doc.py        # 주 1회(월요일)면 충분

- 숫자: docs/lab/sql/source_scorecard.sql 결과 (같은 집안 짝 정답 제외, 과거 기준일엔 '지금 팬 수' 유명 판정 안 씀 — SQL 에 반영됨)
- 역할: config/source_roles.json (성적표 SQL 의 role 칸과 같음)
- 마커: <!-- AUTO:SUMMARY:START --> … END, <!-- AUTO:SCORECARD:START --> … END, <!-- AUTO:PENDING:START --> … END
"""
from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path
from typing import Dict, List, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab_sql  # noqa: E402

DOC = lab_sql.ROOT / "docs" / "source_roles.md"
CUTOFFS = ("2024-07-01", "2025-01-01", "2025-07-01")   # 출처 성적표 기준일 (앱·엑셀과 같음)
SINCE = "2024-01-01"                                   # 수상 팀 = 이 날 이후 처음 정답
HORIZON = 24
ROLE_ORDER = {"discovery": 0, "context": 1, "pending": 2, "excluded": 3}
REEVAL_MONTHS = 3
LABELS = {
    "선정·지원:band_discovery": "상상마당 밴드 디스커버리", "선정·지원:muse_sejong": "뮤즈 인 세종",
    "선정·지원:yoojaeha_finalist": "유재하 경연 본선", "공연:sangsangmadang": "상상마당 공연", "큐레이션:musicy": "음악취향Y",
    "공연:indistreet": "인디스트릿 공연", "큐레이션:rhythmer": "리드머", "선정·지원:dmz_lineup": "DMZ 피스트레인 라인업",
    "선정·지원:gb_creation": "경북 창작소", "큐레이션:hiphople": "힙합엘이 국내 뉴스", "선정·지원:superrookie": "슈퍼루키챌린지",
    "큐레이션:instagram": "인스타 매거진", "공연:instagram": "공연장 인스타 라인업", "공연:indiego": "인디고",
    "선정·지원:burock_rookies": "부산록페 루키즈",
}


def replace_block(text: str, name: str, body: str) -> str:
    start, end = f"<!-- AUTO:{name}:START -->", f"<!-- AUTO:{name}:END -->"
    pat = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)
    if not pat.search(text):
        raise ValueError(f"문서에 마커가 없음: {start} … {end}")
    return pat.sub(lambda _: f"{start}\n{body}\n{end}", text, count=1)


def _name(src: str, labels: Dict[str, str]) -> str:
    return f"{src} ({labels[src]})" if src in labels else src


def _pct(v) -> str:
    if v is None:
        return "—"
    return "0%" if float(v) == 0 else f"{float(v):.2f}%"


def _num(v) -> str:
    return "—" if v is None else f"{float(v):g}"


def scored_table(rows: Sequence[dict], labels: Dict[str, str]) -> List[str]:
    out = ["| 출처 | 역할 | 기록 시작 | 팀 | 적중 | 적중률 | 배수 | 먼저 잡은 수상 팀 (가장 먼저 / 유일) | 선행 개월(중앙값) |",
           "|---|---|---|---|---|---|---|---|---|"]
    shown = [r for r in rows if r["teams"] or r["winners_seen"]]
    for r in sorted(shown, key=lambda r: (ROLE_ORDER.get(r["role"], 9), -(float(r["rate"] or 0)), r["src"])):
        seen = f"{r['winners_seen']} ({r['first_to_see']} / {r['only_source']})" if r["winners_seen"] else "0"
        lift = "—" if not r["hits"] else _num(r["lift"])
        out.append(f"| {_name(r['src'], labels)} | {r['role']} | {str(r['since_date'])[:7]} | {r['teams']:,} | {r['hits']} | "
                   f"{_pct(r['rate'])} | {lift} | {seen} | {_num(r['median_lead_months'])} |")
    return out


def _plus_months(d: date, months: int) -> date:
    total = d.year * 12 + d.month - 1 + months
    return date(total // 12, total % 12 + 1, min(d.day, 28))


def pending_table(rows: Sequence[dict], labels: Dict[str, str]) -> List[str]:
    out = ["| 출처 | 기록 시작 | 지금까지 행 수 | 1차 재평가 (기록 3개월 뒤) |", "|---|---|---|---|"]
    for r in sorted((r for r in rows if not r["teams"] and not r["winners_seen"]), key=lambda r: (str(r["since_date"]), r["src"])):
        start = date.fromisoformat(str(r["since_date"])[:10])
        out.append(f"| {_name(r['src'], labels)} | {start} | {r['signal_rows']:,} | {_plus_months(start, REEVAL_MONTHS)} 이후 |")
    return out


def summary_line(cutoffs: Sequence[str], winners: int, base_rate: float) -> str:
    return (f"- 이 문서의 성적표 숫자: 랩 데이터로 출처 성적표를 실행한 값입니다(자동 생성: `scripts/source_roles_doc.py`, {date.today()}). "
            f"기준일 {len(cutoffs)}개({'·'.join(cutoffs)})를 합산했고, 수상 팀은 {SINCE} 이후 처음 정답을 받은 **{winners}팀**, "
            f"기준선(후보 전체의 적중률)은 **{base_rate:.2f}%** 입니다. 같은 집안 짝 정답은 그 출처의 적중으로 세지 않고"
            "([같은 집안 점검](same_house.md)), 과거 기준일엔 '지금 팬 수' 유명 판정을 쓰지 않습니다([규칙 시점 점검](rule_leakage.md)).")


def reading_notes(rows: Sequence[dict], labels: Dict[str, str], winners: int) -> List[str]:
    by = {r["src"]: r for r in rows}
    notes = ["읽는 법:"]
    top = max((r for r in rows if r["role"] == "discovery"), key=lambda r: r["winners_seen"], default=None)
    if top and top["winners_seen"]:
        notes.append(f"- **{_name(top['src'], labels)}**는 적중률 {_pct(top['rate'])}지만 수상 팀 {winners}팀 중 {top['winners_seen']}팀을 정답 전에 잡았고 "
                     f"그중 {top['only_source']}팀은 이 출처에만 나왔습니다. 빼면 놓치는 팀이 가장 많은 출처라 발굴로 둡니다.")
    low_ctx = [r for r in rows if r["role"] == "context" and r["teams"] >= 100 and (r["lift"] or 0) < 1]
    if low_ctx:
        notes.append("- " + "·".join(_name(r["src"], labels) for r in low_ctx) + "는 수상 팀을 먼저 다루기도 하지만 이미 알려진 팀을 훨씬 많이 다뤄 "
                     "적중률이 기준선 아래입니다. 크게 넣으면 순위를 흐리므로 맥락으로 두고 약하게만 반영합니다.")
    hl = by.get("큐레이션:hiphople")
    if hl and hl["teams"]:
        notes.append(f"- **힙합엘이**는 한국힙합어워즈 공동 주최라 그 상을 빼고 잽니다(같은 집안). 그 뒤 적중 {hl['hits']}팀·배수 {_num(hl['lift'])} → 검증 대기.")
    for r in rows:
        if r["role"] == "excluded" and r["teams"] >= 50 and not r["hits"]:
            notes.append(f"- **{_name(r['src'], labels)}**은 {r['teams']}팀 중 적중이 0입니다 → 제외.")
    return notes


def build(con) -> Dict[str, str]:
    cut_sql = ", ".join(f"(DATE '{c}')" for c in CUTOFFS)
    rows = lab_sql.query(con, "source_scorecard.sql", cutoffs=cut_sql, since=f"'{SINCE}'", horizon_months=str(HORIZON))
    winners = con.execute(f"""SELECT COUNT(*) FROM (SELECT team_key FROM outcomes WHERE counted GROUP BY team_key
                              HAVING MIN(announced_date) >= DATE '{SINCE}')""").fetchone()[0]
    base = float(next((r["base_rate"] for r in rows if r["base_rate"] is not None), 0))
    return {"SUMMARY": summary_line(CUTOFFS, winners, base),
            "SCORECARD": "\n".join(scored_table(rows, LABELS) + [""] + reading_notes(rows, LABELS, winners)),
            "PENDING": "\n".join(pending_table(rows, LABELS))}


def main() -> int:
    con = lab_sql.connect()
    text = DOC.read_text(encoding="utf-8")
    for name, body in build(con).items():
        text = replace_block(text, name, body)
    DOC.write_text(text, encoding="utf-8")
    print(f"✅ {DOC.relative_to(lab_sql.ROOT)} 성적표 구간 갱신")
    return 0


if __name__ == "__main__":
    sys.exit(main())
