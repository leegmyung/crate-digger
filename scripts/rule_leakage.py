"""후보 규칙의 시점 누수 점검 → docs/rule_leakage.md

유명 팀 제외(profile_status='famous')는 '지금' 멜론 팬 수와 '오늘' 날짜로 정해진다(sql/kr/00_core_views.sql v_artist_status:
팬 1만 이상, 또는 첫 발매가 오늘보다 5년 넘게 전 & 팬 1천 이상). 과거 기준일 백테스트에 쓰면 미래 정보다
(정답을 받은 뒤 팬이 늘어난 팀이 과거에서도 빠짐 — docs/missed_analysis.md 의 (d)).
신인 규칙(COALESCE(첫 발매, 첫 등장) 3년)도 기간을 바꿔 본다.

방법: lab_scored 를 유명 제외 끔·신인 기준 60년(사실상 끔)으로 불러 넓은 후보군을 얻고, 대안 규칙은 이 스크립트에서 거른다
(features.sql 은 고치지 않음). 지금 규칙으로 거른 결과가 score_tune.features 와 똑같은지 먼저 확인한다.
지표: score_tune 과 같은 기준일 6개·관찰 24개월·등급 가중 AUC·상위 20/50 적중, 가중치 교차 검증(score_model.grid_table).
멜론 프로필(첫 발매일·팬 수)이 늘면 결과가 바뀌므로 다시 돌린다.

실행: .venv/bin/python scripts/rule_leakage.py   → docs/rule_leakage.md
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from typing import Callable, Dict, List, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab_sql  # noqa: E402
import missed_analysis as ma  # noqa: E402
import score_model as sm  # noqa: E402
import score_tune as st  # noqa: E402

OUT = lab_sql.ROOT / "docs" / "rule_leakage.md"
WIDE_NEWCOMER_YEARS = 60          # 신인 규칙을 사실상 끈 넓은 후보군
TENURE_YEARS = 5                  # 대안 '연차+신호 수': 기준일에 첫 발매 후 이 해 수를 넘고
TENURE_MIN_SIGNALS = 10           # 기준일 전 신호(모든 출처)가 이만큼 이상이면 '이미 알려진 팀'
TOP = 100
FAME_KNOWN_FROM = date(2026, 11, 26)   # features.sql 의 fame_known_from() 과 같아야 함 (build 에서 확인)
FEATURE_COLS = ("team_key, n_branch, best_stage, peer_selected, dmz, gigs_1y, outlets, recent180, venues, "
                "peer_winner, context_outlets, collab_est, is_hit, hit_weight")


def years_before(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year - years)
    except ValueError:                       # 2월 29일
        return d.replace(year=d.year - years, day=28)


# ---------- 규칙 ----------

def _tenure_signals(t: dict, c: date) -> bool:
    fr = t.get("first_release")
    return bool(fr) and fr < years_before(c, TENURE_YEARS) and (t.get("signals_before") or 0) >= TENURE_MIN_SIGNALS


def _prior_record(t: dict, c: date) -> bool:
    return bool(t.get("prior_any_outcome") or t.get("prior_festival"))


FAME: Dict[str, Callable[[dict, date], bool]] = {
    "applied": lambda t, c: c >= FAME_KNOWN_FROM and t.get("profile_status") == "famous",   # 적용된 규칙 (2026-11-27~)
    "current": lambda t, c: t.get("profile_status") == "famous",          # 옛 규칙 (지금 팬 수를 과거 기준일에도)
    "off": lambda t, c: False,                                              # 유명 제외 끔
    "tenure_signals": _tenure_signals,                                      # 기준일 시점: 첫 발매 5년 초과 & 신호 10개 이상
    "prior_record": _prior_record,                                          # 기준일 전 정답(기성 팀이라 안 센 것 포함)·DMZ 출연
    "combo": lambda t, c: _tenure_signals(t, c) or _prior_record(t, c),
}
FAME_LABEL = {"applied": "적용된 규칙 (판정 가능한 날부터만)", "current": "옛 규칙 (지금 팬 수를 과거에도)", "off": "유명 제외 끔", "tenure_signals": "기준일 시점 연차+신호 수",
              "prior_record": "기준일 전 정답·DMZ 출연", "combo": "연차+신호 수 또는 정답·DMZ"}


def newcomer_ok(t: dict, c: date, years: int, mode: str) -> bool:
    if mode == "none":
        return True
    first = t.get("first_seen") if mode == "signal_first" else (t.get("first_release") or t.get("first_seen"))
    return first is None or first >= years_before(c, years)


NEW_LABEL = {"release_first": "첫 발매 우선", "signal_first": "첫 신호(우리 데이터 첫 등장)", "none": "신인 규칙 끔"}

VARIANTS: List[dict] = [
    {"key": "base", "fame": "applied", "new_years": 3, "new_mode": "release_first"},
    {"key": "old", "fame": "current", "new_years": 3, "new_mode": "release_first"},
    {"key": "fame_off", "fame": "off", "new_years": 3, "new_mode": "release_first"},
    {"key": "fame_tenure", "fame": "tenure_signals", "new_years": 3, "new_mode": "release_first"},
    {"key": "fame_prior", "fame": "prior_record", "new_years": 3, "new_mode": "release_first"},
    {"key": "fame_combo", "fame": "combo", "new_years": 3, "new_mode": "release_first"},
    {"key": "new4", "fame": "applied", "new_years": 4, "new_mode": "release_first"},
    {"key": "new5", "fame": "applied", "new_years": 5, "new_mode": "release_first"},
    {"key": "new_signal3", "fame": "applied", "new_years": 3, "new_mode": "signal_first"},
    {"key": "new_off", "fame": "applied", "new_years": 3, "new_mode": "none"},
    {"key": "pit3", "fame": "combo", "new_years": 3, "new_mode": "release_first"},
    {"key": "pit4", "fame": "combo", "new_years": 4, "new_mode": "release_first"},
]


def variant_label(v: dict) -> str:
    new = NEW_LABEL[v["new_mode"]] + ("" if v["new_mode"] == "none" else f" {v['new_years']}년")
    return f"유명: {FAME_LABEL[v['fame']]} · 신인: {new}"


def apply_variant(rows: Sequence[dict], attrs: Dict[str, dict], c: date, v: dict) -> List[dict]:
    fame = FAME[v["fame"]]
    out = []
    for r in rows:
        t = attrs.get(r["team_key"], {})
        if fame(t, c) or not newcomer_ok(t, c, v["new_years"], v["new_mode"]):
            continue
        out.append(r)
    return out


def top_change(base: Sequence[str], alt: Sequence[str], n: int = TOP) -> dict:
    b, a = list(base[:n]), list(alt[:n])
    return {"kept": len(set(b) & set(a)), "entered": [k for k in a if k not in b], "left": [k for k in b if k not in a]}


# ---------- 데이터 ----------

def wide_rows(con, cutoff: str) -> List[dict]:
    zero = {k: "0" for k, _ in st.V0_WEIGHTS}
    q = (f"SELECT {FEATURE_COLS} FROM lab_scored(DATE '{{c}}', 3, {WIDE_NEWCOMER_YEARS}, false, 'any', {{h}}, '', "
         "['공연','선정·지원','발매','큐레이션'], {w_branch}, {w_stage}, {w_peer}, {w_dmz}, {w_gigs}, {w_outlets}, {cap}, "
         "{w_recent}, {w_venues}, {w_winner}, {w_context}, w_collab := {w_collab}) WHERE NOT had_outcome")
    cur = con.execute(q.format(c=cutoff, h=st.HORIZON_MONTHS, cap=st.OUTLET_CAP, **zero))
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def team_attrs(con, cutoff: str) -> Dict[str, dict]:
    q = f"""SELECT t.team_key, t.profile_status, t.first_release, t.first_seen, t.fan_count,
                   (SELECT COUNT(*) FROM signals s WHERE s.team_key = t.team_key AND s.signal_date < DATE '{cutoff}'),
                   EXISTS (SELECT 1 FROM outcomes o WHERE o.team_key = t.team_key AND o.announced_date < DATE '{cutoff}'),
                   EXISTS (SELECT 1 FROM signals s WHERE s.team_key = t.team_key AND s.program = 'dmz_lineup'
                           AND s.signal_date < DATE '{cutoff}')
            FROM teams t"""
    keys = ("profile_status", "first_release", "first_seen", "fan_count", "signals_before", "prior_any_outcome", "prior_festival")
    return {r[0]: dict(zip(keys, r[1:])) for r in con.execute(q).fetchall()}


def load(con, cutoffs: Sequence[str]):
    return {c: wide_rows(con, c) for c in cutoffs}, {c: team_attrs(con, c) for c in cutoffs}


def evaluate_variant(wide, attrs, v: dict) -> dict:
    data = {c: apply_variant(wide[c], attrs[c], date.fromisoformat(c), v) for c in st.CUTOFFS}
    w2 = sm.v2_weights()
    m = {c: sm.metrics(data[c], sm.hand_scores(data[c], w2)) for c in st.CUTOFFS}
    grid, table = sm.grid_table(data)
    cv = []
    for held in st.CUTOFFS:
        w = grid[sm.pick_best(table, [c for c in st.CUTOFFS if c != held])]
        a = sm.metrics(data[held], sm.hand_scores(data[held], w))["auc"]
        if a is not None:
            cv.append(a)
    aucs = [x["auc"] for x in m.values() if x["auc"] is not None]
    return {"n": sum(x["n"] for x in m.values()), "pos": sum(x["pos"] for x in m.values()),
            "v2_auc": sum(aucs) / len(aucs), "hits20": sum(x["hits20"] for x in m.values()),
            "hits50": sum(x["hits50"] for x in m.values()), "cv_auc": sum(cv) / len(cv)}


def ranked_keys(rows: Sequence[dict]) -> List[str]:
    w2 = sm.v2_weights()
    scored = [{"team_key": r["team_key"], "score": st.score(r, w2)} for r in rows]
    return [k for k, _ in sorted(ma.ranks(scored).items(), key=lambda kv: kv[1])]


# ---------- 문서 ----------

def build(con) -> List[str]:
    macro = con.execute("SELECT fame_known_from()").fetchone()[0]
    if macro != FAME_KNOWN_FROM:
        raise SystemExit(f"FAME_KNOWN_FROM({FAME_KNOWN_FROM})이 features.sql fame_known_from()({macro})과 다름 — 맞춰 주세요")
    wide, attrs = load(con, st.CUTOFFS)
    base_v = VARIANTS[0]
    same = all({r["team_key"] for r in apply_variant(wide[c], attrs[c], date.fromisoformat(c), base_v)}
               == {r["team_key"] for r in st.features(con, c)} for c in st.CUTOFFS)
    results = [(v, evaluate_variant(wide, attrs, v)) for v in VARIANTS]
    base = results[0][1]

    # 놓친 팀 분석의 (c)·(d) 팀이 대안에서는 몇 위였나 (정답 6개월 전)
    missed = [r for r in ma.analyse(con) if r["horizon"] == 6 and r["reason"] in ("c_newcomer_rule", "d_famous")]
    m_cut = sorted({r["cutoff"].isoformat() for r in missed})
    m_wide, m_attrs = load(con, m_cut)
    rescue = {}
    for v in VARIANTS[1:]:
        ranks_by_cut = {c: {k: i for i, k in enumerate(ranked_keys(apply_variant(m_wide[c], m_attrs[c], date.fromisoformat(c), v)), 1)}
                        for c in m_cut}
        rk = [ranks_by_cut[r["cutoff"].isoformat()].get(r["team_key"]) for r in missed]
        rescue[v["key"]] = (sum(1 for x in rk if x is not None), sum(1 for x in rk if x is not None and x <= TOP))

    meta = json.loads((lab_sql.DATA_DIR / "meta.json").read_text(encoding="utf-8"))
    today = meta["data_end"]
    t_wide, t_attrs = load(con, [today])
    t_base = ranked_keys(apply_variant(t_wide[today], t_attrs[today], date.fromisoformat(today), base_v))
    names = dict(con.execute("SELECT team_key, display_name FROM teams").fetchall())
    profiles = con.execute("SELECT COUNT(*) FILTER (WHERE first_release IS NOT NULL), "
                           "COUNT(*) FILTER (WHERE fan_count IS NOT NULL), COUNT(*) FILTER (WHERE profile_status = 'famous') FROM teams").fetchone()

    lines = ["# 후보 규칙의 시점 누수 점검 — 유명 팀 제외·신인 규칙", "",
             "_자동 생성: `.venv/bin/python scripts/rule_leakage.py` (멜론 프로필이 늘면 결과가 바뀌니 다시 돌림)_", "",
             "## 0. 적용함 (2026-11-27, 사용자 결정 '검증만 기준일 시점으로')", "",
             f"- 랩 계산식(`docs/lab/sql/features.sql`)에 `fame_known_from()` = **{FAME_KNOWN_FROM}**(멜론 팬 수를 처음 모은 날)을 두고, "
             "그보다 이른 기준일에는 '지금 팬 수' 유명 판정으로 후보를 빼지 않는다. 출처 성적표(`source_scorecard.sql`)·데뷔 코호트 성적표도 같은 조건.",
             "- **앱의 오늘 후보 목록은 그대로**다(오늘은 그 날짜 뒤라 유명 팀을 계속 뺀다).",
             "- 아래 표에서 '적용된 규칙'이 지금 쓰는 규칙이고, '옛 규칙'은 비교용이다. 교차 검증 숫자는 [점수 교차 검증](score_tuning.md)·[방법론](methods.md) 참고.", "",
             "## 1. 유명 판정은 무엇으로 정해지나", "",
             "- 규칙(`sql/kr/00_core_views.sql`의 `core.v_artist_status`, 기준값 `ref.settings`): **멜론 팬 1만 명 이상**, 또는 "
             "**첫 발매가 '오늘'보다 5년 넘게 전 & 팬 1천 명 이상**이면 `famous`. 프로필이 없으면 `unknown`(제외 안 함).",
             "- 팬 수는 멜론 프로필을 **수집한 날(2026-11-26~27)의 값**이고, 연차도 '오늘' 기준이다. 그래서 과거 기준일(2023~2025) 백테스트에 쓰면 "
             "**그 뒤에 커진 팀이 과거에서도 빠진다** — 정답(상)을 받고 팬이 는 팀일수록 잘 빠지는, 정답과 엮인 누수다([놓친 팀 분석](missed_analysis.md)의 (d) 9팀, 대부분 CJ 튠업 수상 팀).",
             f"- 지금 팀 표: 첫 발매일이 있는 팀 {profiles[0]:,}, 팬 수가 있는 팀 {profiles[1]:,}, 유명 판정 {profiles[2]:,}팀. "
             "멜론 프로필을 대량으로 받는 중이라 이 숫자와 아래 결과는 바뀐다.", "",
             "**대안 (기준일 당시 알 수 있던 정보만)**",
             f"- 연차+신호 수: 기준일에 첫 발매 후 {TENURE_YEARS}년 초과 **그리고** 기준일 전 우리 신호 {TENURE_MIN_SIGNALS}개 이상 → 이미 알려진 팀으로 제외.",
             "- 정답·DMZ: 기준일 전에 정답(기성 팀이라 '센 정답'으로 안 친 것 포함)을 받았거나 DMZ 피스트레인(기성 팀이 많이 서는 페스티벌)에 섰으면 제외.",
             "- 둘 중 하나(합침). 그리고 아예 끄기.", "",
             "확인: 적용된 규칙으로 넓은 후보군을 거르면 `score_tune.features`와 " + ("**똑같은 후보군**이 나온다." if same else "⚠️ 다른 후보군이 나온다 — 확인 필요."), "",
             f"## 2. 교차 검증 비교 (기준일 {len(st.CUTOFFS)}개 합산, 관찰 {st.HORIZON_MONTHS}개월, 점수 v2)", "",
             "| 규칙 | 후보 (행) | 정답 | v2 평균 AUC | 상위20 | 상위50 | 상위50 ÷ 정답 | 교차 검증 AUC | 놓친 (c)(d) 팀 중 후보로 돌아옴 / 상위 100 |",
             "|---|---|---|---|---|---|---|---|---|"]
    for v, r in results:
        rs = rescue.get(v["key"])
        rs_txt = "—" if rs is None else f"{rs[0]} / {rs[1]}"
        bold = "**" if v["key"] == "base" else ""
        lines.append(f"| {bold}{variant_label(v)}{bold} | {r['n']:,} | {r['pos']} | {r['v2_auc']:.3f} | {r['hits20']} | {r['hits50']} | "
                     f"{r['hits50'] / r['pos'] * 100:.0f}% | {r['cv_auc']:.3f} | {rs_txt} |")
    d_teams = [r for r in missed if r["reason"] == "d_famous"]
    d_also_old = sum(1 for r in d_teams if not newcomer_ok(m_attrs[r["cutoff"].isoformat()].get(r["team_key"], {}),
                                                            r["cutoff"], 3, "release_first"))
    lines += ["", f"(놓친 팀 = [놓친 팀 분석](missed_analysis.md)에서 정답 6개월 전 (c) 신인 규칙·(d) 유명 제외에 걸린 팀, 지금 {len(missed)}팀. "
              f"(d) {len(d_teams)}팀 중 {d_also_old}팀은 첫 발매도 기준일보다 3년 넘게 전이라 **신인 규칙에도 함께 걸린다** — "
              "그래서 유명 규칙만 바꿔서는 돌아오지 않고, 신인 기간을 늘린 경우에야 돌아온다.)", "",
              f"## 3. 지금({today}) 후보 상위 100은 얼마나 바뀌나", "",
              "| 규칙 | 후보 수 | 상위 100 유지 | 새로 들어옴 (예) | 빠짐 (예) |", "|---|---|---|---|---|"]
    for v in VARIANTS:
        alt = ranked_keys(apply_variant(t_wide[today], t_attrs[today], date.fromisoformat(today), v))
        ch = top_change(t_base, alt)
        ex_in = ", ".join(names.get(k, k) for k in ch["entered"][:3]) or "—"
        ex_out = ", ".join(names.get(k, k) for k in ch["left"][:3]) or "—"
        lines.append(f"| {variant_label(v)} | {len(alt):,} | {ch['kept']} | {len(ch['entered'])} ({ex_in}) | {len(ch['left'])} ({ex_out}) |")
    lines += [""] + interpret(results, rescue)
    return lines


def interpret(results, rescue) -> List[str]:
    r = {v["key"]: x for v, x in results}
    b, old = r["base"], r["old"]
    best_pit = max(("fame_prior", "fame_combo", "pit3", "pit4"), key=lambda k: r[k]["cv_auc"])
    lbl = {v["key"]: variant_label(v) for v, _ in results}
    famous_rows, famous_pos = b["n"] - old["n"], b["pos"] - old["pos"]
    lines = ["## 4. 해석", "",
             f"- **옛 규칙(지금 팬 수를 과거에도)이 빼던 후보는 기준일 6개 합쳐 {famous_rows}행뿐인데, 그중 {famous_pos}행이 나중에 정답을 받은 팀이었다.** "
             "유명 판정이 '정답을 받아 커진 팀'을 골라서 빼고 있었다는 뜻이다(미래 정보 누수). 적용된 규칙은 과거 기준일에 이 판정을 쓰지 않는다.",
             f"- 옛 규칙 → 적용된 규칙: 후보 {old['n']:,} → {b['n']:,}행, 정답 {old['pos']} → {b['pos']}행, 교차 검증 AUC {old['cv_auc']:.3f} → {b['cv_auc']:.3f}, "
             f"상위 50 적중 {old['hits50']} → {b['hits50']}(정답 중 {old['hits50'] / old['pos'] * 100:.0f}% → {b['hits50'] / b['pos'] * 100:.0f}%).",
             f"- 기준일 시점 정보로 유명 팀을 따로 거르는 대안 중 교차 검증 AUC가 가장 높은 것: **{lbl[best_pit]}** ({r[best_pit]['cv_auc']:.3f}, 상위 50 {r[best_pit]['hits50']}). "
             "다만 정답 수가 달라(아래 표) 적용된 규칙과 바로 우열을 가리기 어렵다.",
             ("- '기준일 시점 연차+신호 수'는 신인 3년 규칙과 함께 쓰면 '끔'과 결과가 같다 — 첫 발매 5년 넘은 팀은 신인 규칙이 이미 뺀다."
              if r["fame_tenure"] == r["fame_off"] else None),
             f"- 신인 기간을 늘리면(4년 {r['new4']['cv_auc']:.3f}·5년 {r['new5']['cv_auc']:.3f}) 후보가 {r['new4']['n']:,}·{r['new5']['n']:,}행으로 늘고 "
             f"(c) 늦게 뜬 팀이 돌아온다. 첫 신호 기준은 {r['new_signal3']['cv_auc']:.3f}, 신인 규칙을 끄면 {r['new_off']['cv_auc']:.3f}.",
             "- 숫자를 비교할 때: 후보군·정답 수가 규칙마다 달라 AUC만으로 우열을 가리기 어렵다. '상위50 ÷ 정답'과 놓친 (c)(d) 팀이 돌아오는지를 같이 본다.",
             "- **오늘 후보 목록에는 영향이 없다** — 오늘은 판정 가능한 날 뒤라 적용된 규칙도 지금 팬 수로 유명 팀을 뺀다(3절의 첫 줄과 '옛 규칙' 줄이 같음).", "",
             "## 5. 남은 권고", "",
             "1. **팬 수를 날짜별로 쌓기**(이미 시작) → 1년 뒤부터는 '기준일 당시 팬 수'로 판정할 수 있다. 그때 `fame_known_from()`을 그 날짜로 두면 된다.",
             f"2. 신인 기간(3년)은 지금은 그대로 둔다 — 4·5년으로 늘리면 정답이 {b['pos']} → {r['new4']['pos']}·{r['new5']['pos']}행으로 늘어 상위 50 적중 수도 늘지만, "
             f"정답 중 상위 50에 든 비율은 {b['hits50'] / b['pos'] * 100:.0f}% → {r['new4']['hits50'] / r['new4']['pos'] * 100:.0f}%·{r['new5']['hits50'] / r['new5']['pos'] * 100:.0f}%로 "
             "거의 그대로라 뚜렷한 개선은 아니다(늘어난 정답은 '늦게 뜬 팀'이라는 정의 변경 몫). 멜론 프로필 수집이 끝나면 다시 잰다.",
             "3. 멜론 프로필 수집이 끝나면 이 스크립트를 다시 돌린다(첫 발매일이 늘면 신인 규칙 결과가 바뀜).", ""]
    return [ln for ln in lines if ln is not None]


def main() -> int:
    con = lab_sql.connect()
    lines = build(con)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"✅ → {OUT.relative_to(lab_sql.ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
