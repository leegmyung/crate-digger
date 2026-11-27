"""데뷔 코호트 성적표 → docs/debut_cohort.md

과거 이력 없는 '백지 신인'(첫 발매 전 신호 0)이 첫 발매를 낸 뒤 어느 출처가 N개월 안에 언급했고,
그 팀이 기준일 뒤 정답을 받았는지를 출처별로 잰다. 계산은 docs/lab/sql/source_scorecard_debut.sql 한 곳에만 있다.

실행: .venv/bin/python scripts/debut_cohort.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab_sql  # noqa: E402
import score_tune as st  # noqa: E402

OUT = lab_sql.ROOT / "docs" / "debut_cohort.md"
SQL = "source_scorecard_debut.sql"
MENTION_MONTHS = (3, 6, 12)      # 언급 창 민감도 (기본 6)
DEFAULT_MONTHS = 6
MIN_TEAMS = 5                    # 이보다 적게 언급한 출처는 '표본 부족'


def cutoffs_sql(cutoffs: Sequence[str]) -> str:
    return ", ".join(f"(DATE '{c}')" for c in cutoffs)


def scorecard(con, cutoffs: Sequence[str], months: int, horizon: int = st.HORIZON_MONTHS) -> List[dict]:
    return lab_sql.query(con, SQL, cutoffs=cutoffs_sql(cutoffs), mention_months=str(months), horizon_months=str(horizon))


def _f(v, digits: int = 1) -> str:
    return "—" if v is None else f"{float(v):.{digits}f}"


def source_table(rows: List[dict]) -> List[str]:
    out = ["| 출처 | 역할 | 언급한 백지 신인 | 그중 정답 | 적중률 | 배수 | 첫 발매→첫 언급 (일, 중앙값) | 가장 먼저 언급 |",
           "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        small = r["teams"] < MIN_TEAMS and r["src"] != "(언급 없음)"
        rate = f"{_f(r['rate'])}%" + (" (표본 부족)" if small else "")
        out.append(f"| {r['src']} | {r['role'] or '—'} | {r['teams']} | {r['hits']} | {rate} | {_f(r['lift'])} | "
                   f"{_f(r['median_days'], 0)} | {r['first_mention'] if r['first_mention'] is not None else '—'} |")
    return out


def cohort_line(rows: List[dict]) -> Dict[str, float]:
    if not rows:
        return {"n": 0, "hits": 0, "base": 0.0}
    r = rows[0]
    return {"n": int(r["cohort_teams"]), "hits": int(r["cohort_hits"]), "base": float(r["base_rate"] or 0)}


def build(con) -> List[str]:
    cuts = list(st.CUTOFFS)
    main = scorecard(con, cuts, DEFAULT_MONTHS)
    base = cohort_line(main)
    per_cut = [(c, cohort_line(scorecard(con, [c], DEFAULT_MONTHS))) for c in cuts]
    unm = next((r for r in main if r["src"] == "(언급 없음)"), None)
    lines = ["# 데뷔 코호트 성적표 — 백지 신인을 누가 먼저 언급했나", "",
             "_자동 생성: `.venv/bin/python scripts/debut_cohort.py` · 계산식: [`source_scorecard_debut.sql`](lab/sql/source_scorecard_debut.sql)_", "",
             "**질문**: 과거 이력이 없는 신인이 첫 앨범(싱글 포함)을 냈을 때, 어느 출처가 먼저 그 팀을 언급하고, 그렇게 언급된 팀이 나중에 정답(수상·선정)을 받았나? "
             "기존 [출처 성적표](source_roles.md)가 '기준일 전 3년 안에 나온 팀 전체'를 본다면, 이것은 **데뷔 직후**만 본다.", "",
             "## 1. 정의", "",
             f"- **백지 신인**: 첫 발매일(`teams.first_release`, 멜론·스포티파이 프로필) 전에 우리 데이터의 신호가 하나도 없는 팀. 유명 팀·기준일 전에 이미 정답 받은 팀은 뺀다.",
             f"- **코호트**: 기준일마다 첫 발매가 기준일보다 {DEFAULT_MONTHS + 6}~{DEFAULT_MONTHS}개월 전인 백지 신인(= 기준일 전 1년 안 첫 발매, 언급 창이 기준일 전에 끝나게). "
             f"기준일 {len(cuts)}개({', '.join(cuts)})는 6개월 간격이라 한 팀은 한 번만 들어간다.",
             f"- **언급**: 첫 발매 뒤 {DEFAULT_MONTHS}개월 안에 그 출처에 나옴(모든 역할의 출처). **정답**: 기준일 뒤 {st.HORIZON_MONTHS}개월 안 센 정답.",
             "- 배수 = 그 출처가 언급한 팀의 적중률 ÷ 코호트 전체 적중률.", "",
             "## 2. 코호트 크기 (표본 한계 — 먼저 볼 것)", "",
             "| 기준일 | 백지 신인 (첫 발매 12~6개월 전) | 그중 정답 |", "|---|---|---|",
             *[f"| {c} | {v['n']} | {v['hits']} |" for c, v in per_cut],
             f"| **합계** | **{base['n']}** | **{base['hits']}** (기준율 {base['base']:.1f}%) |", "",
             "- 첫 발매일은 프로필이 있는 팀(전체 약 7,300팀 중 280여 팀)에만 있다. 프로필은 상위 후보와 정답 팀 위주로 모았기 때문에 "
             "**코호트 기준율이 실제 신인 전체보다 훨씬 높게 나온다**(후보 전체 기준율은 약 1%). 숫자는 방향으로만 읽는다.",
             "- 발매·인스타 출처는 2026-11부터만 있어 이 코호트(첫 발매 2022~2025)에는 거의 나오지 않는다.", "",
             f"## 3. 출처별 성적 (언급 창 {DEFAULT_MONTHS}개월, 기준일 {len(cuts)}개 합산)", "",
             *source_table(main), ""]
    if unm and base["n"]:
        lines += [f"- 백지 신인 {base['n']}팀 중 {unm['teams']}팀({unm['teams'] / base['n'] * 100:.0f}%)은 첫 발매 뒤 {DEFAULT_MONTHS}개월 안에 "
                  f"어느 출처에도 안 나왔다. 그중 정답을 받은 팀이 {unm['hits']}팀 — 우리 출처가 데뷔 직후를 놓치는 몫이다.", ""]
    lines += ["## 4. 언급 창 민감도", "", "| 언급 창 | 코호트 | 정답 | 언급 없음 (그중 정답) | 가장 많이 언급한 출처 (팀 / 정답) |", "|---|---|---|---|---|"]
    for m in MENTION_MONTHS:
        rows = scorecard(con, cuts, m)
        b = cohort_line(rows)
        u = next((r for r in rows if r["src"] == "(언급 없음)"), {"teams": 0, "hits": 0})
        top = next((r for r in rows if r["src"] != "(언급 없음)"), None)
        top_txt = f"{top['src']} ({top['teams']} / {top['hits']})" if top else "—"
        lines.append(f"| {m}개월 | {b['n']} | {b['hits']} | {u['teams']} ({u['hits']}) | {top_txt} |")
    lines += ["", "(언급 창을 바꾸면 코호트도 바뀐다: N개월 창이면 첫 발매가 기준일 N+6~N개월 전인 팀.)", "",
              "## 5. 읽는 법과 다음 단계", "",
              "- 이 성적표는 **데뷔 직후 첫 언급의 질**을 본다. 적중률이 높고 첫 언급까지 일수가 짧은 출처가 '백지 신인 발굴'에 좋은 출처다.",
              "- 표본이 작아 출처 간 차이를 결론으로 쓰면 안 된다. 첫 발매일을 아는 팀이 늘어야(스포티파이·멜론 프로필을 정답과 상관없이 후보 전체로) 믿을 만해진다.",
              "- 새 출처(슈퍼루키챌린지·힙합엘이 등)를 넣으면 이 표에 바로 나타난다 — 데뷔 직후 언급이 많은지로 1차 평가할 수 있다.", ""]
    return lines


def main() -> int:
    con = lab_sql.connect()
    lines = build(con)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"✅ → {OUT.relative_to(lab_sql.ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
