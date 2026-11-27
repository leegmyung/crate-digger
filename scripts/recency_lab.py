"""최근 기간 시험 — '공연장 수'·'수상 팀과 같은 무대'를 최근 1·2년 공연으로만 셌다면? (시험만, 점수 정의는 안 바꿈)

    .venv/bin/python scripts/recency_lab.py      # → docs/dormant_check.md 의 '최근 기간 시험' 자동 칸

지금 lab_scored 는 신호 보는 기간(lookback_years=3) 안의 공연으로 두 특징을 센다. 그래서 2024년에 여러 클럽을 돌고
멈춘 팀이 지금도 위에 남는다(docs/dormant_check.md). 여기서는 features.sql 을 고치지 않고 score_tune.features 결과에
기간을 줄인 값을 바꿔 끼워(feature_lab 방식) 같은 기준일 6개·같은 지표로 비교한다.
- 공연: 발굴(discovery) 신호, 공연장 이름 있는 것만, 기준일 N년 전 ~ 기준일 전 (features.sql gig 와 같은 규칙).
- 수상 팀 같은 무대: 같은 날·같은 공연장에 '그날 이미 정답을 받은' 다른 팀이 있었나 (정답은 기준일 전 발표만).
- 3년 판은 SQL 값과 똑같아야 한다(맞춤 검사 — 결과 머리에 적음).
- 가중치: ① v2 그대로(venues 1·winner 2) ② 두 가중치만 기준일 하나 빼고 다시 고르기(score_tune 과 같은 교차 검증).
- 휴면 팀: 마지막 신호(모든 역할) 1년 이상 전 + 최근 1년 공연 0 (dormant_check 과 같은 규칙), 앱 순서 상위 100 안.
"""
from __future__ import annotations

import itertools
import json
import sys
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dormant_check as dc  # noqa: E402
import feature_lab as fl  # noqa: E402
import lab_sql  # noqa: E402
import score_tune as st  # noqa: E402

DOC = dc.DOC
UNKNOWN_VENUES = ("", "공연장 미정")
TOP_K = 100
W_VENUES_GRID = (0.0, 0.5, 1.0, 1.5, 2.0)
W_WINNER_GRID = (0.0, 1.0, 2.0, 3.0)
FEATS = ("venues", "peer_winner")
# (이름, 바꿀 특징, 기간 년) — 첫 줄 = 지금 그대로
VARIANTS: Tuple[Tuple[str, Tuple[str, ...], int], ...] = (
    ("지금 (둘 다 3년)", (), 3),
    ("공연장 수만 2년", ("venues",), 2),
    ("공연장 수만 1년", ("venues",), 1),
    ("수상 팀 무대만 2년", ("peer_winner",), 2),
    ("수상 팀 무대만 1년", ("peer_winner",), 1),
    ("둘 다 2년", FEATS, 2),
    ("둘 다 1년", FEATS, 1),
)


def years_before(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year - years)
    except ValueError:                     # 2월 29일 → 2월 28일
        return d.replace(year=d.year - years, day=28)


def _date(v) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])


def short_feats(sigs: Sequence[dict], outs: Sequence[dict], cutoff: date, years: int) -> Dict[str, Dict[str, int]]:
    """팀마다 최근 years 년 발굴 공연으로 센 서로 다른 공연장 수·수상 팀과 같은 무대(0/1)."""
    start = years_before(cutoff, years)
    shows = {(s["team_key"], _date(s["signal_date"]), s["venue"]) for s in sigs
             if s.get("role") == "discovery" and s.get("branch") == "공연"
             and (s.get("venue") or "") not in UNKNOWN_VENUES and start <= _date(s["signal_date"]) < cutoff}
    first_win: Dict[str, date] = {}
    for o in outs:
        d = _date(o["announced_date"])
        if o.get("counted") and d < cutoff:
            first_win[o["team_key"]] = min(first_win.get(o["team_key"], d), d)
    stage: Dict[Tuple[date, str], set] = {}
    for team, d, venue in shows:
        stage.setdefault((d, venue), set()).add(team)
    out: Dict[str, Dict[str, int]] = {}
    for team, d, venue in shows:
        f = out.setdefault(team, {"venues": set(), "peer_winner": 0})
        f["venues"].add(venue)
        if any(o != team and o in first_win and first_win[o] <= d for o in stage[(d, venue)]):
            f["peer_winner"] = 1
    return {t: {"venues": len(f["venues"]), "peer_winner": f["peer_winner"]} for t, f in out.items()}


def with_feats(rows: Sequence[dict], feats: Dict[str, Dict[str, int]], which: Sequence[str]) -> List[dict]:
    """which 특징만 기간 줄인 값으로 바꾼 새 행 목록 (기간 안 공연이 없으면 0)."""
    return [{**r, **{k: (feats.get(r["team_key"]) or {}).get(k, 0) for k in which}} for r in rows]


def changed_rows(rows: Sequence[dict], feats: Dict[str, Dict[str, int]]) -> Tuple[int, int]:
    """기간을 줄였을 때 값이 바뀌는 후보 행 수 (공연장 수, 수상 팀 무대) — 시험이 구분할 힘이 있는지 보는 용도."""
    def get(r, k):
        return (feats.get(r["team_key"]) or {}).get(k, 0)
    return (sum(1 for r in rows if get(r, "venues") != int(r["venues"])),
            sum(1 for r in rows if get(r, "peer_winner") != int(r["peer_winner"])))


def dormant_in_top(rows: Sequence[dict], scores: Sequence[float], act: Dict[str, Tuple[str, int]],
                   cutoff: date, k: int) -> List[str]:
    """앱 순서 상위 k팀 중 휴면 팀(dormant_check 규칙)의 키 — 순위 순."""
    order = st.app_order(scores, [r["team_key"] for r in rows], [r.get("last_seen") for r in rows])
    return [rows[i]["team_key"] for i in order[:k] if dc.is_dormant(dc.merge_activity(rows[i], act), cutoff)]


# ---------- 평가 ----------

def _weights(w_venues: float, w_winner: float) -> Dict[str, float]:
    return {**fl.v2_weights(), "w_venues": w_venues, "w_winner": w_winner}


def _scores(rows: Sequence[dict], w: Dict[str, float]) -> List[float]:
    return [st.score(r, w) for r in rows]


def evaluate_variant(data: Dict[str, List[dict]], dormant_act: Dict[str, dict]) -> dict:
    """v2 가중치 그대로 + 두 가중치만 교차 검증으로 다시 고른 결과."""
    cutoffs = list(data)
    combos = list(itertools.product(W_VENUES_GRID, W_WINNER_GRID))
    scores = {cb: {c: _scores(data[c], _weights(*cb)) for c in cutoffs} for cb in combos}
    mets = {cb: {c: fl.metrics(data[c], scores[cb][c]) for c in cutoffs} for cb in combos}
    v2 = (float(lab_sql.DEFAULTS["w_venues"]), float(lab_sql.DEFAULTS["w_winner"]))
    ordered = [v2] + [cb for cb in combos if cb != v2]          # 동점이면 v2 그대로
    picks = {c: fl._pick(mets, ordered, [k for k in cutoffs if k != c]) for c in cutoffs}
    cv = {c: mets[picks[c]][c] for c in cutoffs}
    base = {c: mets[v2][c] for c in cutoffs}
    hits = ("hits20", "hits50", "hits100")
    dorm = {c: len(dormant_in_top(data[c], scores[v2][c], dormant_act[c], date.fromisoformat(c), TOP_K)) for c in cutoffs}
    return {"v2_mean": fl._mean(base[c]["auc"] for c in cutoffs), "cv_mean": fl._mean(cv[c]["auc"] for c in cutoffs),
            "v2_hits": {k: sum(base[c][k] for c in cutoffs) for k in hits},
            "cv_hits": {k: sum(cv[c][k] for c in cutoffs) for k in hits},
            "picks": picks, "dormant_past": dorm, "v2_scores": {c: scores[v2][c] for c in cutoffs},
            "cv_scores": {c: scores[picks[c]][c] for c in cutoffs}}


def today_dormant(rows: Sequence[dict], act, today: date, k: int) -> List[str]:
    w2 = fl.v2_weights()
    return dormant_in_top(rows, _scores(rows, w2), act, today, k)


def run() -> dict:
    con = lab_sql.connect()
    meta = json.loads((lab_sql.DATA_DIR / "meta.json").read_text(encoding="utf-8"))
    today = date.fromisoformat(meta.get("data_end") or date.today().isoformat())
    sigs, outs = fl.load_events(con)
    data = {c: st.features(con, c) for c in st.CUTOFFS}
    now_rows = st.features(con, today.isoformat())
    days = list(st.CUTOFFS) + [today.isoformat()]
    feats = {(c, y): short_feats(sigs, outs, date.fromisoformat(c), y) for c in days for y in (1, 2, 3)}
    acts = {c: dc.activity(sigs, date.fromisoformat(c)) for c in days}
    check = _sanity(data, feats)
    results, now = {}, {}
    for name, which, years in VARIANTS:
        vdata = {c: with_feats(data[c], feats[(c, years)], which) for c in st.CUTOFFS}
        results[name] = evaluate_variant(vdata, acts)
        vnow = with_feats(now_rows, feats[(today.isoformat(), years)], which)
        now[name] = {k: today_dormant(vnow, acts[today.isoformat()], today, k) for k in (TOP_K, 300)}
    base = results[VARIANTS[0][0]]
    for name in results:
        if name != VARIANTS[0][0]:
            res = results[name]
            res["boot"] = fl.bootstrap_diff(data, {"cv_scores": res["v2_scores"], "base_scores": base["v2_scores"]})
    changed = {(c, y): changed_rows(data[c], feats[(c, y)]) for c in st.CUTOFFS for y in (1, 2)}
    return {"today": today, "check": check, "results": results, "now": now, "changed": changed,
            "n": {c: (len(r), sum(int(x["is_hit"]) for x in r)) for c, r in data.items()}}


def _sanity(data: Dict[str, List[dict]], feats) -> Tuple[int, int]:
    """3년 판이 SQL(lab_scored) 값과 같은 행 수 / 전체 행 수."""
    same = total = 0
    for c, rows in data.items():
        f3 = feats[(c, 3)]
        for r in rows:
            total += 1
            got = f3.get(r["team_key"]) or {"venues": 0, "peer_winner": 0}
            same += int(got["venues"] == int(r["venues"]) and got["peer_winner"] == int(r["peer_winner"]))
    return same, total


# ---------- 문서 ----------

def _f(v: Optional[float]) -> str:
    return "—" if v is None else f"{v:.3f}"


def render(res: dict) -> str:
    same, total = res["check"]
    base_name = VARIANTS[0][0]
    pos = sum(p for _, p in res["n"].values())
    lines = [f"기준일 6개({st.CUTOFFS[0]}~{st.CUTOFFS[-1]}, 관찰 {st.HORIZON_MONTHS}개월) · 후보 {sum(n for n, _ in res['n'].values()):,}행 · "
             f"정답 {pos}행 · 맞춤 검사: 3년 판이 SQL 값과 같은 행 {same:,}/{total:,}", "",
             "| 판 | AUC (v2 가중치 그대로) | 차이 [95% 구간] | 상위 50 적중 | 상위 100 적중 | AUC (두 가중치 다시 고름, 교차 검증) | 상위 50 적중 | "
             "과거 기준일 상위 100 휴면 팀 (평균) | 지금 상위 100 휴면 팀 | 지금 상위 300 휴면 팀 |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for name, _, _ in VARIANTS:
        r, now = res["results"][name], res["now"][name]
        boot = r.get("boot")
        diff = "—" if not boot else f"{boot[0]:+.3f} [{boot[1]:+.3f}, {boot[2]:+.3f}]"
        past = sum(r["dormant_past"].values()) / len(r["dormant_past"])
        lines.append(f"| {name} | {_f(r['v2_mean'])} | {diff} | {r['v2_hits']['hits50']} | {r['v2_hits']['hits100']} | "
                     f"{_f(r['cv_mean'])} | {r['cv_hits']['hits50']} | {past:.1f} | {len(now[TOP_K])} | {len(now[300])} |")
    picks = {name: sorted({f"공연장 {p[0]:g}·수상 무대 {p[1]:g}" for p in res["results"][name]["picks"].values()})
             for name, _, _ in VARIANTS}
    lines += ["", "다시 고른 가중치(기준일마다 하나 빼고 고름): "
              + " / ".join(f"{n}: {', '.join(p)}" for n, p in picks.items())]
    lines += ["", f"'차이'는 v2 가중치 그대로 쓴 판과 '{base_name}'의 평균 AUC 차이(정답·비정답을 다시 뽑아 200번, 95% 구간).",
              "", "**기간을 줄이면 값이 바뀌는 후보 행 수** (공연장 수 / 수상 팀 무대) — 공연 기록이 2024-01부터라 이른 기준일에선 거의 안 바뀐다:", "",
              "| 기준일 | 후보 | 1년 | 2년 |", "|---|---|---|---|"]
    for c in st.CUTOFFS:
        (v1, w1), (v2_, w2) = res["changed"][(c, 1)], res["changed"][(c, 2)]
        lines.append(f"| {c} | {res['n'][c][0]:,} | {v1} / {w1} | {v2_} / {w2} |")
    return "\n".join(lines)


def main() -> int:
    res = run()
    text = DOC.read_text(encoding="utf-8") if DOC.exists() else ""
    DOC.write_text(dc.replace_block(text, "RECENCY", render(res)), encoding="utf-8")
    print(render(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
