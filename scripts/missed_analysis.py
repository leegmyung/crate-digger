"""놓친 팀 분석 → docs/missed_analysis.md

2025-01-01 이후 S·A 정답(정리 규칙이 적용된 outcomes.csv)을 받은 팀마다, 첫 S·A 정답 6·12개월 전 기준일에서
점수 v2 후보 순위가 어땠는지 본다. 상위 100 안이면 '잡음', 아니면 원인을 하나 고른다(아래 순서대로 먼저 걸리는 것).
  f 다른 정답을 먼저 받아 후보에서 빠짐 · d 유명 팀 제외(판정 가능한 날 fame_known_from() 이후만) · c 신인 규칙(첫 발매·첫 등장 3년 넘음)
  a 기준일 전 3년 안에 어느 출처에도 신호 없음 · b 신호는 있지만 검증 대기·제외 출처뿐 → 그 출처를 발굴로 넣었으면 몇 위였나
  e 점수는 있었지만 순위가 낮음 → 상위 100 팀들은 흔히 있는데 이 팀엔 없던 특징
후보군·점수·순위 규칙은 score_tune.features()·score()·hits_at_k()와 같다(동점은 앱처럼 마지막 신호 최근 순 → md5).
멜론 프로필(first_release)이 늘면 결과가 바뀌므로 언제든 다시 돌린다.

실행: .venv/bin/python scripts/missed_analysis.py   → docs/missed_analysis.md
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab_sql  # noqa: E402
import score_tune as st  # noqa: E402
from score_model import ANALYSIS_GENRE_SQL  # noqa: E402  (추정·리뷰·확신 낮음 장르는 미분류 — genre_bias.analysis_genre 와 같은 규칙)

OUT = lab_sql.ROOT / "docs" / "missed_analysis.md"
SINCE = date(2025, 1, 1)
GRADES = ("S", "A")
HORIZONS = (6, 12)
TOP = 100
LOOKBACK_YEARS = 3
UNSCORED_ROLES = ("pending", "excluded")
SRC_KEY = "branch || ':' || CASE WHEN branch = '선정·지원' THEN program ELSE source END"
WEAK_SHARE = 0.5          # 상위 100 팀 중 이 비율 이상이 가진 특징이 이 팀엔 0이면 '약한 특징'
EXAMPLES = 4
REASONS = {
    "caught": "잡음 (상위 100 안)",
    "e_low_rank": "e 점수는 있었지만 순위가 낮음",
    "b_unscored_sources": "b 검증 대기·제외 출처에만 나옴",
    "a_no_signal": "a 3년 안 신호 없음 (출처·장르 공백)",
    "c_newcomer_rule": "c 신인 규칙에 걸림 (첫 발매·첫 등장 3년 넘음)",
    "d_famous": "d 유명 팀 제외",
    "f_prior_outcome": "f 다른 정답을 먼저 받아 후보에서 빠짐",
    "z_other": "기타",
}
# 점수 v2에서 가중치가 있는 특징 (값은 v2와 같은 기준: 갈래 수는 −1)
FEATURE_LABELS = {"n_branch": "갈래 수", "best_stage": "선정 단계", "venues": "공연장 다양성", "outlets": "발굴 매거진",
                  "context_outlets": "맥락 매거진", "peer_winner": "수상 팀과 같은 무대"}


# ---------- 순수 함수 ----------

def minus_months(d: date, months: int) -> date:
    total = d.year * 12 + d.month - 1 - months
    y, m = total // 12, total % 12 + 1
    last = [31, 29 if (y % 4 == 0 and (y % 100 or y % 400 == 0)) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return date(y, m, min(d.day, last))


def ranks(rows: Sequence[dict]) -> Dict[str, int]:
    """점수 높은 순 순위 — 앱과 같은 순서(score_tune.app_order: 반올림 점수 → 마지막 신호 최근 순 → md5)."""
    idx = st.app_order([float(r["score"]) for r in rows], [r["team_key"] for r in rows], [r.get("last_seen") for r in rows])
    order = [rows[i] for i in idx]
    return {r["team_key"]: i for i, r in enumerate(order, 1)}


def classify(info: dict, top: int = TOP) -> str:
    if info["in_pool"]:
        return "caught" if info["rank"] is not None and info["rank"] <= top else "e_low_rank"
    if info["prior_outcome"]:
        return "f_prior_outcome"
    if info["famous"]:
        return "d_famous"
    if info["too_old"]:
        return "c_newcomer_rule"
    if not info["signals_window"]:
        return "a_no_signal"
    if not info["scored_signals"]:
        return "b_unscored_sources"
    return "z_other"


def no_signal_kind(info: dict) -> str:
    """(a) 신호 없음을 둘로: 기준일 뒤·정답 전에야 처음 나옴(late) / 정답 전엔 어디에도 없음(absent)."""
    return "late" if info.get("signals_before_outcome") else "absent"


def weak_features(team: dict, top_rows: Sequence[dict], names: Sequence[str]) -> List[str]:
    """상위 팀 중 WEAK_SHARE 이상이 가진(>0) 특징인데 이 팀은 0인 것 — 흔한 순서로."""
    if not top_rows:
        return []
    shares = {n: sum(1 for r in top_rows if (r.get(n) or 0) > 0) / len(top_rows) for n in names}
    weak = [n for n in names if (team.get(n) or 0) <= 0 and shares[n] >= WEAK_SHARE]
    return sorted(weak, key=lambda n: -shares[n])


def reason_counts(results: Sequence[dict], horizon: int) -> Dict[str, int]:
    return dict(Counter(r["reason"] for r in results if r["horizon"] == horizon))


def source_gain(results: Sequence[dict], horizon: int, top: int = TOP) -> List[Tuple[str, int, int]]:
    """(출처, 그 출처를 발굴로 넣으면 상위 top 에 들어올 놓친 팀 수, 그 출처에 있던 놓친 팀 수)."""
    gained, seen = Counter(), Counter()
    for r in results:
        if r["horizon"] != horizon:
            continue
        for src, rk in (r.get("what_if") or {}).items():
            seen[src] += 1
            gained[src] += int(rk is not None and rk <= top)
    return sorted(((s, gained[s], seen[s]) for s in seen), key=lambda t: (-t[1], -t[2], t[0]))


# ---------- 데이터 ----------

def v2_weights() -> Dict[str, float]:
    return {k: float(lab_sql.DEFAULTS[k]) for k, _ in st.V0_WEIGHTS}


def targets(con) -> List[dict]:
    """팀마다 2025-01-01 이후 첫 S·A 정답 (같은 날 여럿이면 등급 높은 것)."""
    q = f"""SELECT team_key, announced_date, grade, program_label, weight FROM outcomes
            WHERE counted AND grade IN {tuple(GRADES)} AND announced_date >= DATE '{SINCE}'"""
    best: Dict[str, dict] = {}
    for k, d, g, label, w in con.execute(q).fetchall():
        cur = best.get(k)
        if cur is None or (d, -float(w or 0)) < (cur["date"], -cur["weight"]):
            best[k] = {"team_key": k, "date": d, "grade": g, "program": label, "weight": float(w or 0)}
    return sorted(best.values(), key=lambda t: (t["date"], t["team_key"]))


class Scorer:
    """기준일별 후보군·v2 점수·순위를 한 번만 계산해 둔다. what_if 는 출처 하나를 발굴로 바꾼 연결로."""

    def __init__(self, con):
        self.con = con
        self.w2 = v2_weights()
        self._cache: Dict[Tuple[str, str], Tuple[Dict[str, dict], Dict[str, int]]] = {}
        self._cons: Dict[str, object] = {}

    def _con_for(self, src: str):
        if not src:
            return self.con
        if src not in self._cons:
            c = lab_sql.connect()
            c.execute(f"UPDATE signals SET role = 'discovery' WHERE {SRC_KEY} = ?", [src])
            self._cons[src] = c
        return self._cons[src]

    def pool(self, cutoff: date, src: str = "") -> Tuple[Dict[str, dict], Dict[str, int]]:
        key = (cutoff.isoformat(), src)
        if key not in self._cache:
            rows = st.features(self._con_for(src), cutoff.isoformat())
            for r in rows:
                r["score"] = st.score(r, self.w2)
            self._cache[key] = ({r["team_key"]: r for r in rows}, ranks(rows))
        return self._cache[key]


def team_info(con, k: str, cutoff: date, outcome_date: Optional[date] = None) -> dict:
    c = cutoff.isoformat()
    od = (outcome_date or cutoff).isoformat()
    row = con.execute(f"""
        SELECT
          EXISTS (SELECT 1 FROM outcomes o WHERE o.team_key = t.team_key AND o.counted AND o.announced_date < DATE '{c}'),
          t.profile_status = 'famous' AND DATE '{c}' >= fame_known_from(),   -- 유명 판정은 판정 가능한 날부터만 (features.sql)
          COALESCE(t.first_release, t.first_seen) < DATE '{c}' - INTERVAL {LOOKBACK_YEARS} YEAR,
          (SELECT COUNT(*) FROM signals s WHERE s.team_key = t.team_key AND s.signal_date < DATE '{c}'
             AND s.signal_date >= DATE '{c}' - INTERVAL {LOOKBACK_YEARS} YEAR),
          (SELECT COUNT(*) FROM signals s WHERE s.team_key = t.team_key
             AND s.signal_date < DATE '{c}' - INTERVAL {LOOKBACK_YEARS} YEAR),
          (SELECT COUNT(*) FROM signals s WHERE s.team_key = t.team_key AND s.signal_date < DATE '{c}'
             AND s.signal_date >= DATE '{c}' - INTERVAL {LOOKBACK_YEARS} YEAR AND s.role IN ('discovery','context')),
          t.first_release, t.first_seen, {ANALYSIS_GENRE_SQL}, t.display_name,
          (SELECT COUNT(*) FROM signals s WHERE s.team_key = t.team_key AND s.signal_date >= DATE '{c}'
             AND s.signal_date < DATE '{od}')
        FROM teams t WHERE t.team_key = ?""", [k]).fetchone()
    if row is None:
        return {"prior_outcome": False, "famous": False, "too_old": False, "signals_window": 0, "signals_older": 0,
                "scored_signals": 0, "first_release": None, "first_seen": None, "genre": "미분류", "name": k,
                "signals_before_outcome": 0}
    keys = ("prior_outcome", "famous", "too_old", "signals_window", "signals_older", "scored_signals",
            "first_release", "first_seen", "genre", "name", "signals_before_outcome")
    return dict(zip(keys, row))


def unscored_sources(con, k: str, cutoff: date) -> List[str]:
    c = cutoff.isoformat()
    q = (f"SELECT DISTINCT {SRC_KEY} FROM signals WHERE team_key = ? AND signal_date < DATE '{c}' "
         f"AND signal_date >= DATE '{c}' - INTERVAL {LOOKBACK_YEARS} YEAR AND role IN {UNSCORED_ROLES}")
    return sorted(s for (s,) in con.execute(q, [k]).fetchall())


def analyse(con) -> List[dict]:
    scorer = Scorer(con)
    out = []
    for t in targets(con):
        for h in HORIZONS:
            cutoff = minus_months(t["date"], h)
            rows, rk = scorer.pool(cutoff)
            info = team_info(con, t["team_key"], cutoff, t["date"])
            info.update({"in_pool": t["team_key"] in rows, "rank": rk.get(t["team_key"])})
            reason = classify(info)
            res = {**t, "horizon": h, "cutoff": cutoff, "reason": reason, "rank": info["rank"], "pool_size": len(rows),
                   "genre": info["genre"], "name": info["name"] or t["team_key"], "first_release": info["first_release"],
                   "first_seen": info["first_seen"], "no_signal_kind": no_signal_kind(info) if reason == "a_no_signal" else ""}
            if reason == "b_unscored_sources":
                res["what_if"] = {s: scorer.pool(cutoff, s)[1].get(t["team_key"]) for s in unscored_sources(con, t["team_key"], cutoff)}
            if reason == "e_low_rank":
                top_rows = [rows[k] for k, r in rk.items() if r <= TOP]
                fv = lambda r: {**{n: r.get(n) for n in FEATURE_LABELS}, "n_branch": (r.get("n_branch") or 1) - 1}  # noqa: E731
                res["weak"] = weak_features(fv(rows[t["team_key"]]), [fv(r) for r in top_rows], list(FEATURE_LABELS))
                res["score"] = rows[t["team_key"]]["score"]
            out.append(res)
    return out


# ---------- 문서 ----------

def _example(r: dict) -> str:
    extra = ""
    if r["reason"] == "e_low_rank":
        extra = f", {r['rank']}위/{r['pool_size']:,}" + (f", 없던 것: {'·'.join(FEATURE_LABELS[w] for w in r['weak'][:2])}" if r.get("weak") else "")
    elif r["reason"] == "caught":
        extra = f", {r['rank']}위"
    elif r["reason"] == "b_unscored_sources":
        extra = ", " + "·".join(f"{s}→{'—' if v is None else f'{v}위'}" for s, v in r["what_if"].items())
    elif r["reason"] == "c_newcomer_rule":
        extra = f", 첫 발매 {r['first_release'] or '?'} / 첫 등장 {r['first_seen']}"
    return f"{r['name']} ({r['program']} {r['grade']}{extra})"


def horizon_section(results: List[dict], h: int) -> List[str]:
    rs = [r for r in results if r["horizon"] == h]
    n = len(rs)
    counts = reason_counts(results, h)
    lines = [f"### 정답 {h}개월 전 기준일", "",
             "| 원인 | 팀 | 비율 | 장르 (많은 순) | 대표 사례 |", "|---|---|---|---|---|"]
    for code in REASONS:
        group = [r for r in rs if r["reason"] == code]
        if not group:
            continue
        genres = ", ".join(f"{g} {c}" for g, c in Counter(r["genre"] for r in group).most_common(3))
        ex = "; ".join(_example(r) for r in sorted(group, key=lambda r: (-r["weight"], r["date"]))[:EXAMPLES])
        lines.append(f"| {REASONS[code]} | {counts[code]} | {counts[code] / n * 100:.0f}% | {genres} | {ex} |")
    weak = Counter(w for r in rs if r["reason"] == "e_low_rank" for w in r.get("weak", []))
    if weak:
        lines += ["", "순위가 낮았던 팀(e)에 없던 특징 (상위 100 팀의 절반 이상이 가진 것): "
                  + ", ".join(f"{FEATURE_LABELS[w]} {c}팀" for w, c in weak.most_common())]
    return lines


def build(results: List[dict]) -> List[str]:
    teams = sorted({r["team_key"] for r in results})
    lines = ["# 놓친 팀 분석 — 2025년 이후 S·A 정답 팀은 정답 전에 후보 상위 100 안에 있었나", "",
             "_자동 생성: `.venv/bin/python scripts/missed_analysis.py` (멜론 프로필이 늘면 결과가 바뀌니 다시 돌림)_", "",
             f"대상: 2025-01-01 이후 첫 S·A 정답(정리 규칙 적용된 `outcomes.csv`, 센 정답만)을 받은 **{len(teams)}팀**. "
             f"첫 S·A 정답일의 6개월·12개월 전을 기준일로, 점수 v2(`lab_sql.DEFAULTS`)·같은 후보군(`score_tune.features`)으로 순위를 매겼다. "
             "놓쳤으면 원인을 하나만 고른다 — f 다른 정답 먼저 → d 유명 팀 → c 신인 규칙 → a 신호 없음 → b 점수에 안 쓰는 출처뿐 → e 순위 낮음 순서로 먼저 걸리는 것.", "",
             "## 1. 요약", "", "| 기준일 | 잡음 (상위 100) | 순위 낮음 (e) | 점수 밖 출처뿐 (b) | 신호 없음 (a) | 신인 규칙 (c) | 유명 (d) | 다른 정답 먼저 (f) |",
             "|---|---|---|---|---|---|---|---|"]
    for h in HORIZONS:
        c = reason_counts(results, h)
        n = sum(c.values())
        cells = [f"{c.get(k, 0)} ({c.get(k, 0) / n * 100:.0f}%)" for k in
                 ("caught", "e_low_rank", "b_unscored_sources", "a_no_signal", "c_newcomer_rule", "d_famous", "f_prior_outcome")]
        lines.append(f"| 정답 {h}개월 전 | " + " | ".join(cells) + " |")
    lines += ["", "## 2. 원인별 자세히", ""]
    for h in HORIZONS:
        lines += horizon_section(results, h) + [""]
    lines += ["## 3. 어떤 출처를 보강하면 몇 팀을 더 잡나", "",
              "(b) 팀마다, 그 팀이 나온 '점수에 안 쓰는 출처'를 발굴 출처로 바꿔(다른 팀도 모두 같은 조건으로) 다시 순위를 매겼다.", "",
              "| 출처 | 정답 6개월 전: 상위 100에 들어올 팀 / 그 출처에 있던 놓친 팀 | 정답 12개월 전 |", "|---|---|---|"]
    g6, g12 = ({s: (a, b) for s, a, b in source_gain(results, h)} for h in HORIZONS)
    for s in sorted(set(g6) | set(g12), key=lambda s: (-(g6.get(s, (0, 0))[0] + g12.get(s, (0, 0))[0]), s)):
        a6, a12 = g6.get(s, (0, 0)), g12.get(s, (0, 0))
        lines.append(f"| {s} | {a6[0]} / {a6[1]} | {a12[0]} / {a12[1]} |")
    if not (g6 or g12):
        lines.append("| (해당 없음) | — | — |")
    lines += ["", "**(a) 신호 없음을 둘로 나누면** — '늦음' = 기준일 뒤·정답 전에야 우리 출처에 처음 나옴(출처는 있지만 늦게 잡음), "
              "'없음' = 정답 전엔 어느 출처에도 없음(새 출처가 필요).", "",
              "| 기준일 | 늦음 | 없음 | '없음' 팀 장르 | '없음' 팀 정답 |", "|---|---|---|---|---|"]
    for h in HORIZONS:
        a = [r for r in results if r["horizon"] == h and r["reason"] == "a_no_signal"]
        absent = [r for r in a if r["no_signal_kind"] == "absent"]
        lines.append(f"| 정답 {h}개월 전 | {len(a) - len(absent)} | {len(absent)} | "
                     + (", ".join(f"{g} {c}" for g, c in Counter(r["genre"] for r in absent).most_common(4)) or "—") + " | "
                     + (", ".join(f"{p} {c}" for p, c in Counter(r["program"] for r in absent).most_common(4)) or "—") + " |")
    lines += ["", "장르 공백은 [장르 편향 점검](genre_bias.md)·[힙합·R&B 출처 조사](research_2026-11-27_hiphop_rnb_sources.md) 참고.", ""]
    lines += interpret(results)
    lines += ["## 부록. 팀별 (정답 순)", "", "| 팀 | 정답 | 장르 | 12개월 전 | 6개월 전 |", "|---|---|---|---|---|"]
    by_team: Dict[str, Dict[int, dict]] = defaultdict(dict)
    for r in results:
        by_team[r["team_key"]][r["horizon"]] = r
    for k in sorted(by_team, key=lambda k: (by_team[k][6]["date"], k)):
        r6, r12 = by_team[k][6], by_team[k][12]
        cell = lambda r: (f"{r['rank']}위" if r["rank"] else "후보 아님") + f" · {REASONS[r['reason']].split(' ')[0]}"  # noqa: E731
        lines.append(f"| {r6['name']} | {r6['date']} {r6['program']} {r6['grade']} | {r6['genre']} | {cell(r12)} | {cell(r6)} |")
    return lines + [""]


def interpret(results: List[dict]) -> List[str]:
    c6, c12 = reason_counts(results, 6), reason_counts(results, 12)
    n = sum(c6.values())
    missed6 = n - c6.get("caught", 0)
    top_reason = max((k for k in c6 if k != "caught"), key=lambda k: c6[k], default=None)
    gain = source_gain(results, 6)
    lines = ["## 4. 읽는 법", "",
             f"- 정답 6개월 전에 상위 100 안에 있던 팀은 {c6.get('caught', 0)}/{n}팀, 12개월 전에는 {c12.get('caught', 0)}/{n}팀이다. "
             f"무작위로 100팀을 뽑았다면 기대값은 약 {sum(TOP / r['pool_size'] for r in results if r['horizon'] == 6 and r['pool_size']):.1f}팀"
             "(기준일마다 후보 수가 달라 팀별 100/후보 수의 합)이다."]
    if top_reason:
        lines.append(f"- 놓친 {missed6}팀(6개월 전) 중 가장 큰 원인은 **{REASONS[top_reason]}**({c6[top_reason]}팀)이다.")
    a6 = [r for r in results if r["horizon"] == 6 and r["reason"] == "a_no_signal"]
    late6 = sum(1 for r in a6 if r["no_signal_kind"] == "late")
    if a6:
        lines.append(f"- 그중 {late6}팀은 기준일 뒤·정답 전에야 우리 출처에 처음 나왔다(출처는 있지만 늦게 잡음 — 6개월 앞서 알기엔 너무 늦은 신호). "
                     f"{len(a6) - late6}팀은 정답 전엔 어느 출처에도 없었다(새 출처가 필요).")
    if gain and gain[0][1]:
        lines.append(f"- 출처 보강 효과가 가장 큰 곳은 {gain[0][0]}(정답 6개월 전 기준 {gain[0][1]}팀 더 상위 100). "
                     "다만 '같은 집안' 효과가 있는 출처(예: 힙합엘이↔한국힙합어워즈, [same_house.md](same_house.md))는 이 숫자가 부풀 수 있다.")
    elif gain:
        lines.append(f"- **지금 있는 '점수 밖 출처'({', '.join(s for s, _, _ in gain)})를 발굴로 넣어도 상위 100에 들어오는 팀은 0팀**이다. "
                     "보강할 곳은 새 출처(a '없음'), 신인·유명 판정 규칙(c·d), 점수 특징(e)이다.")
    e6 = Counter(w for r in results if r["horizon"] == 6 and r["reason"] == "e_low_rank" for w in r.get("weak", []))
    if e6:
        lines.append("- 순위가 낮았던 팀(e)은 주로 " + ", ".join(FEATURE_LABELS[w] for w, _ in e6.most_common(3))
                     + "이 없었다 — 상위 팀은 여러 갈래·매거진·수상 팀과 같은 무대를 갖췄는데, 이 팀들은 한 갈래(주로 공연 하나 또는 매거진 하나)에만 나왔다.")
    lines += ["- (c) 신인 규칙에 걸린 팀은 첫 발매가 3년보다 오래된 '늦게 뜬 팀'이다. 신인 기준을 바꿀지는 이 팀들의 정답 비중을 보고 정한다(방법론 1절).",
              ("- (d) 유명 팀 제외: 2026-11-27부터 점수 검증에서는 '지금 팬 수' 유명 판정을 과거 기준일에 쓰지 않는다(미래 정보 — "
               "[규칙 시점 점검](rule_leakage.md)). 그래서 과거 기준일에서 (d)로 놓친 팀은 없고, 예전에 (d)였던 팀은 이제 후보로 들어와 "
               "순위(e)나 신인 규칙(c)으로 다시 분류된다." if not c6.get("d_famous") else
               "- **(d) 유명 팀 제외는 미래 정보 문제일 가능성이 크다.** 유명 판정은 '지금' 멜론 팬 수로 하는데, 정답을 받은 뒤 팬이 늘어난 팀이 "
               "과거 기준일에서도 빠진다. 기준일 당시 팬 수로 판정하면 이 팀들이 후보로 돌아온다."),
              "- (f) 다른 정답을 먼저 받은 팀은 이미 '찾은 팀'이라 놓친 것이 아니다(중간 단계 정답 → 큰 상).", ""]
    return lines + [""]


def main() -> int:
    con = lab_sql.connect()
    results = analyse(con)
    lines = build(results)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:60]))
    print(f"✅ → {OUT.relative_to(lab_sql.ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
