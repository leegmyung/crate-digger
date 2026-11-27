"""점수 가중치 고르기 — 기준일 하나를 빼고(leave-one-cutoff-out) 고른 뒤, 뺀 기준일로 채점한다.

왜: 결과를 보고 가중치를 맞추면 우연을 외운 점수가 된다. 고를 때 쓰지 않은 시점에서도 나아야 진짜 개선이다.
지표: 가중 AUC(정답 팀이 후보 전체 중 위쪽에 있는 정도, 0.5 = 무작위, 1 = 완벽 — 정답 등급 S=3·A=2·B=1로 가중,
      config/source_roles.json) — 상위 K 적중 수보다 덜 흔들림. 등급 없는 보통 AUC도 함께 적는다.
      보조로 상위 50팀 적중 수.
순서: 앱 후보 목록(docs/lab/sql/candidates.sql)과 같다 — ROUND(score, 2) 높은 순 → 마지막 신호 최근 순 → md5(team_key).
      AUC도 이 순서로 매긴다(동점을 절반으로 치지 않음, 2026-11-27부터 — 문서 숫자가 앱 화면 순위와 같도록).
특징값은 브라우저와 같은 계산식(docs/lab/sql/features.sql의 lab_scored)에서 가져온다.

실행: .venv/bin/python scripts/score_tune.py   → docs/score_tuning.md
"""
from __future__ import annotations

import bisect
import hashlib
import itertools
import math
import sys
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab_sql  # noqa: E402

CUTOFFS = ["2023-01-01", "2023-07-01", "2024-01-01", "2024-07-01", "2025-01-01", "2025-07-01"]
HORIZON_MONTHS = 24
OUTLET_CAP = 3
V0_WEIGHTS = (("w_branch", 2.0), ("w_stage", 1.0), ("w_peer", 1.0), ("w_dmz", 0.5), ("w_gigs", 0.5),
              ("w_outlets", 1.0), ("w_recent", 0.0), ("w_venues", 0.0), ("w_winner", 0.0), ("w_context", 0.0),
              ("w_collab", 0.0))
# 1차 탐색(v0 특징 6개만)에서 DMZ는 늘 0, 선정 단계는 2가 골라졌다 → 새 특징 3개를 넣고 범위를 좁혀 다시 탐색
GRID = {"w_branch": (0, 1, 2, 3), "w_stage": (1, 2, 3), "w_peer": (0, 1), "w_dmz": (0,),
        "w_gigs": (0,), "w_outlets": (0.5, 1, 2), "w_recent": (0, 1, 2, 3), "w_venues": (0, 1, 2),
        "w_winner": (0, 1, 2), "w_context": (0, 0.25, 0.5, 1),   # 맥락 매체(기준선 이하 큰 매거진)는 약하게 — 차등
        "w_collab": (0, 0.5, 1, 2)}   # 기성 파트너와의 협업(스포티파이) — 데이터가 없으면 active_grid 가 0만 남김
OUT = lab_sql.ROOT / "docs" / "score_tuning.md"
# 순위 규칙을 앱과 같게 바꾸기 직전(옛 규칙: AUC 동점 절반·상위 K 팀 이름 순)의 결과 — 같은 랩 데이터로 잰 값, 문서 머리말 비교용
TIE_RULE_CHANGE = {"date": "2026-11-27", "data": "랩 데이터 2026-11-27 20:36", "pick": 0.786, "v0": 0.783,
                   "hits_pick": 23, "hits_v0": 22,
                   "after": {"pick": 0.805, "v0": 0.799, "hits_pick": 23, "hits_v0": 22}}   # 같은 데이터, 새 규칙
# 랩 데이터가 크게 바뀌기 직전 문서의 숫자 (같은 규칙, 이전 데이터) — 문서 머리말 비교용
DATA_REFRESH = {"date": "2026-11-28", "what": "2021~25 정답 보강 적재(outcomes.csv 723 → 1,272행)",
                "rows": 8434, "pos": 81, "pick": 0.805, "v0": 0.799, "hits_pick": 23, "hits_v0": 22}


# ---------- 지표 ----------

def _avg_ranks(values: Sequence[float]) -> List[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def auc(scores: Sequence[float], labels: Sequence[int]) -> Optional[float]:
    """정답 팀 하나와 아닌 팀 하나를 뽑았을 때 정답 팀 점수가 더 높을 확률 (동점은 절반)."""
    pos = sum(labels)
    neg = len(labels) - pos
    if pos == 0 or neg == 0:
        return None
    ranks = _avg_ranks(scores)
    rank_sum = sum(r for r, y in zip(ranks, labels) if y)
    return (rank_sum - pos * (pos + 1) / 2) / (pos * neg)


def weighted_auc(scores: Sequence[float], weights: Sequence[float]) -> Optional[float]:
    """정답 팀마다 등급 가중치(S=3·A=2·B=1)를 준 AUC: 각 정답 팀이 '아닌 팀'보다 위에 있는 비율을 가중 평균."""
    neg = sum(1 for w in weights if not w)
    total = sum(w for w in weights if w)
    if not neg or not total:
        return None
    neg_scores = sorted(s for s, w in zip(scores, weights) if not w)
    acc = 0.0
    for sc, w in zip(scores, weights):
        if not w:
            continue
        below = bisect.bisect_left(neg_scores, sc)
        ties = bisect.bisect_right(neg_scores, sc) - below
        acc += w * (below + 0.5 * ties) / neg
    return acc / total


# ---------- 앱과 같은 순서 (docs/lab/sql/candidates.sql: ROUND(score, 2) DESC, last_seen DESC, md5(team_key)) ----------

APP_SCORE_DECIMALS = 2      # 앱은 ROUND(score, 2) AS score 로 정렬한다


def _round_app(x: float, decimals: int = APP_SCORE_DECIMALS) -> float:
    """DuckDB ROUND 처럼 반올림(0.5는 0에서 먼 쪽). 부동소수 오차로 동점이 깨지지 않게 아주 작은 여유를 둔다."""
    m = 10 ** decimals
    return math.copysign(math.floor(abs(x) * m + 0.5 + 1e-9) / m, x)


def _day(d) -> Optional[int]:
    if d is None or d == "":
        return None
    return (d if isinstance(d, date) else date.fromisoformat(str(d)[:10])).toordinal()


def tie_ranks(keys: Sequence[str], last_seen: Optional[Sequence] = None) -> List[int]:
    """점수가 같을 때의 순서(0 = 먼저): 마지막 신호 최근 순(없으면 맨 뒤) → md5(team_key) 순. 정답 여부와 무관."""
    seen = [_day(d) for d in last_seen] if last_seen is not None else [None] * len(keys)
    md5 = [hashlib.md5(str(k).encode("utf-8")).hexdigest() for k in keys]
    order = sorted(range(len(keys)), key=lambda i: (seen[i] is None, -(seen[i] or 0), md5[i]))
    ranks = [0] * len(keys)
    for pos, i in enumerate(order):
        ranks[i] = pos
    return ranks


def app_order(scores: Sequence[float], keys: Sequence[str], last_seen: Optional[Sequence] = None,
              ties: Optional[Sequence[int]] = None, decimals: Optional[int] = APP_SCORE_DECIMALS) -> List[int]:
    """앱 후보 목록과 같은 순서(위 → 아래)의 위치 목록. ties 를 주면(미리 계산한 tie_ranks) 다시 계산하지 않는다.
    decimals=None 이면 반올림하지 않는다(앱에 표시되지 않는 모델 점수용 — 동점 순서만 같게)."""
    ties = ties if ties is not None else tie_ranks(keys, last_seen)
    rounded = [float(v) for v in scores] if decimals is None else [_round_app(float(v), decimals) for v in scores]
    return sorted(range(len(scores)), key=lambda i: (-rounded[i], ties[i]))


def ranked_weighted_auc(order: Sequence[int], weights: Sequence[float]) -> Optional[float]:
    """순서(위 → 아래)가 정해졌을 때의 가중 AUC: 정답 팀마다 '자기보다 아래 있는 비정답 비율'을 등급 가중 평균."""
    neg = sum(1 for w in weights if not w)
    total = sum(w for w in weights if w)
    if not neg or not total:
        return None
    acc, neg_above = 0.0, 0
    for i in order:
        if weights[i]:
            acc += weights[i] * (neg - neg_above) / neg
        else:
            neg_above += 1
    return acc / total


def app_auc(scores: Sequence[float], weights: Sequence[float], keys: Sequence[str],
            last_seen: Optional[Sequence] = None, ties: Optional[Sequence[int]] = None,
            decimals: Optional[int] = APP_SCORE_DECIMALS) -> Optional[float]:
    """앱이 보여 주는 순서 기준 가중 AUC (동점을 절반으로 치지 않고 앱처럼 가른다)."""
    return ranked_weighted_auc(app_order(scores, keys, last_seen, ties, decimals), weights)


def hits_at_k(scores: Sequence[float], labels: Sequence[int], keys: Sequence[str], k: int,
              last_seen: Optional[Sequence] = None, decimals: Optional[int] = APP_SCORE_DECIMALS) -> int:
    """앱 순서로 상위 k팀 중 정답 수 (동점은 마지막 신호 최근 순 → md5(team_key), 정답 여부로 순서가 바뀌지 않게)."""
    return sum(labels[i] for i in app_order(scores, keys, last_seen, decimals=decimals)[:k])


def score(f: dict, w: dict) -> float:
    return (w["w_branch"] * (f["n_branch"] - 1) + w["w_stage"] * f["best_stage"] + w["w_peer"] * f["peer_selected"]
            + w["w_dmz"] * f["dmz"] + w["w_gigs"] * math.log(1 + f["gigs_1y"])
            + w["w_outlets"] * min(f["outlets"], OUTLET_CAP) + w["w_recent"] * math.log(1 + f["recent180"])
            + w["w_venues"] * math.log(1 + f["venues"]) + w["w_winner"] * f["peer_winner"]
            + w.get("w_context", 0) * min(f.get("context_outlets", 0), OUTLET_CAP)
            + w.get("w_collab", 0) * math.log(1 + f.get("collab_est", 0)))


def active_grid(data: Dict[str, List[dict]]) -> Dict[str, tuple]:
    """특징값이 모두 0인 가중치는 0만 후보로 (협업 데이터 0건일 때 동점끼리 엉뚱한 값이 골라지지 않게)."""
    has_collab = any((r.get("collab_est") or 0) > 0 for rows in data.values() for r in rows)
    return {**GRID, "w_collab": GRID["w_collab"] if has_collab else (0,)}


def loco_pick(table: Dict[str, Dict[str, Optional[float]]]) -> Dict[str, str]:
    """table[가중치][기준일] = 지표. 기준일마다 '그 기준일을 뺀 평균'이 가장 높은 가중치를 고른다."""
    cutoffs = sorted({c for row in table.values() for c in row})
    picks = {}
    for held in cutoffs:
        def train_mean(name: str) -> float:
            vals = [v for c, v in table[name].items() if c != held and v is not None]
            return sum(vals) / len(vals) if vals else float("-inf")
        picks[held] = max(sorted(table), key=train_mean)
    return picks


# ---------- 데이터 ----------

def features(con, cutoff: str) -> List[dict]:
    zero = {k: "0" for k, _ in V0_WEIGHTS}
    q = ("SELECT team_key, n_branch, best_stage, peer_selected, dmz, gigs_1y, outlets, recent180, venues, "
         "peer_winner, context_outlets, collab_est, is_hit, hit_weight, last_seen "
         "FROM lab_scored(DATE '{c}', 3, 3, true, 'any', {h}, '', ['공연','선정·지원','발매','큐레이션'], "
         "{w_branch}, {w_stage}, {w_peer}, {w_dmz}, {w_gigs}, {w_outlets}, {cap}, {w_recent}, {w_venues}, "
         "{w_winner}, {w_context}, w_collab := {w_collab}) WHERE NOT had_outcome")
    cur = con.execute(q.format(c=cutoff, h=HORIZON_MONTHS, cap=OUTLET_CAP, **zero))
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def data_ties(data: Dict[str, List[dict]]) -> Dict[str, List[int]]:
    """기준일마다 동점 순서(tie_ranks) — 가중치와 무관하니 한 번만 계산해 evaluate 에 넘긴다."""
    return {c: tie_ranks([r["team_key"] for r in rows], [r.get("last_seen") for r in rows]) for c, rows in data.items()}


def evaluate(data: Dict[str, List[dict]], w: dict, ties: Optional[Dict[str, List[int]]] = None) -> Dict[str, dict]:
    """기준일마다 앱 순서 기준 지표: 가중 AUC(auc)·보통 AUC(plain_auc)·상위 20/50 적중."""
    ties = ties or data_ties(data)
    out = {}
    for c, rows in data.items():
        s = [score(r, w) for r in rows]
        y = [int(r["is_hit"]) for r in rows]
        hit_w = [float(r.get("hit_weight") or 0) for r in rows]
        order = app_order(s, [], ties=ties[c])
        out[c] = {"auc": ranked_weighted_auc(order, hit_w), "plain_auc": ranked_weighted_auc(order, y),
                  "hits50": sum(y[i] for i in order[:50]), "hits20": sum(y[i] for i in order[:20]),
                  "n": len(rows), "pos": sum(y)}
    return out


def _single(name: str) -> dict:
    return {k: (1.0 if k == name else 0.0) for k, _ in V0_WEIGHTS}


def _fmt_w(w: dict) -> str:
    return " · ".join(f"{k[2:]} {v:g}" for k, v in w.items())


def tune(con=None) -> dict:
    """교차 검증 계산만 (문서는 안 씀). scripts/score_review.py 가 같은 결과를 받아 기본값과 비교한다."""
    con = con or lab_sql.connect()
    data = {c: features(con, c) for c in CUTOFFS}
    space = active_grid(data)
    grid = [dict(zip(space, combo)) for combo in itertools.product(*space.values())]
    grid = [w for w in grid if any(w.values())]
    names = {i: w for i, w in enumerate(grid)}
    ties = data_ties(data)
    evals = {i: evaluate(data, w, ties) for i, w in names.items()}
    table = {str(i): {c: e[c]["auc"] for c in CUTOFFS} for i, e in evals.items()}
    picks = loco_pick(table)
    refs = {"점수 v0": dict(V0_WEIGHTS), "공연 수만": _single("w_gigs"), "갈래 수만": _single("w_branch")}
    ref_evals = {k: evaluate(data, w, ties) for k, w in refs.items()}
    return {"data": data, "grid": grid, "names": names, "evals": evals, "table": table, "picks": picks,
            "ref_evals": ref_evals}


def tie_rule_note() -> str:
    """머리말 한 줄: 순위 규칙을 앱과 같게 바꾼 이유와 전후 숫자 (바꾼 날의 같은 데이터로 잰 고정값)."""
    b = TIE_RULE_CHANGE
    a = b["after"]
    mean, hits = {"pick": a["pick"], "v0": a["v0"]}, {"pick": a["hits_pick"], "v0": a["hits_v0"]}
    return (f"**순위 규칙 변경 ({b['date']})**: 동점 처리를 앱 후보 목록과 같게 바꿨다(점수 → 마지막 신호 최근 순 → md5). "
            "전에는 AUC에서 동점을 절반으로, 상위 K에서 팀 이름 순으로 쳐서 문서 숫자가 앱 화면 순위와 달랐다. "
            f"같은 데이터({b['data']})로 전 → 후: 고른 가중치 평균 AUC {b['pick']:.3f} → {mean.get('pick', float('nan')):.3f}, "
            f"v0 {b['v0']:.3f} → {mean.get('v0', float('nan')):.3f}, 상위 50 적중 합계 고른 것 {b['hits_pick']} → {hits['pick']}, "
            f"v0 {b['hits_v0']} → {hits['v0']}.\n")


def data_refresh_note(mean: Dict[str, float], hits: Dict[str, int], n_rows: int, n_pos: int) -> str:
    """머리말 한 줄: 데이터 갱신 전후 숫자 (같은 순위 규칙)."""
    b = DATA_REFRESH
    return (f"**데이터 갱신 ({b['date']})**: {b['what']}. 전 → 후: 후보 {b['rows']:,} → {n_rows:,}행, "
            f"정답 {b['pos']} → {n_pos}행, 고른 가중치 평균 AUC {b['pick']:.3f} → {mean.get('pick', float('nan')):.3f}, "
            f"v0 {b['v0']:.3f} → {mean.get('v0', float('nan')):.3f}, 상위 50 적중 합계 고른 것 {b['hits_pick']} → {hits['pick']}, "
            f"v0 {b['hits_v0']} → {hits['v0']}.\n")


def main(res: Optional[dict] = None) -> int:
    """docs/score_tuning.md 를 쓴다. res 를 주면(score_review.py) 다시 계산하지 않는다."""
    res = res or tune()
    data, grid, names, evals, table, picks, ref_evals = (
        res[k] for k in ("data", "grid", "names", "evals", "table", "picks", "ref_evals"))

    lines = ["# 점수 가중치 고르기 (교차 검증)", "",
             "_자동 생성: `.venv/bin/python scripts/score_tune.py`_", "",
             "기준일 하나를 빼고 나머지 기준일의 평균 AUC가 가장 높은 가중치를 고른 뒤, **뺀 기준일**에서 채점했다(고를 때 안 본 시점).",
             f"관찰 기간 {HORIZON_MONTHS}개월(2025-07-01은 데이터 끝 2026-11까지라 약 17개월), 신호 3년·신인 3년·유명 팀 제외, "
             f"공연장 수는 최근 {lab_sql.DEFAULTS['venue_years']}년(2026-11-28 사용자 결정, docs/methods.md). "
             f"가중치 후보 {len(grid):,}가지.", "",
             "AUC = 정답 팀 하나와 아닌 팀 하나를 골랐을 때 **앱 순위에서** 정답 팀이 더 위에 있을 확률(0.5 = 무작위). "
             "순위는 앱 후보 목록과 같다 — 점수(소수 둘째 자리) 높은 순 → 마지막 신호 최근 순 → md5(team_key). "
             "아래 AUC는 정답 등급 가중(S=3·A=2·B=1). 점수에는 '발굴 신호' 출처만 쓴다(config/source_roles.json).", "",
             "| 뺀 기준일 | 후보 | 정답 | 고른 가중치(나머지로 고름) | AUC 고른 것 | AUC v0 | AUC 공연 수만 | AUC 갈래 수만 | 상위50 고른 것 | 상위50 v0 |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    sums = {"pick": [], "v0": [], "g": [], "b": []}
    hits = {"pick": 0, "v0": 0}
    for c in CUTOFFS:
        e = evals[int(picks[c])][c]
        r0, rg, rb = ref_evals["점수 v0"][c], ref_evals["공연 수만"][c], ref_evals["갈래 수만"][c]
        fa = lambda v: "—" if v is None else f"{v:.3f}"  # noqa: E731
        lines.append(f"| {c} | {e['n']:,} | {e['pos']} | {_fmt_w(names[int(picks[c])])} | {fa(e['auc'])} | "
                     f"{fa(r0['auc'])} | {fa(rg['auc'])} | {fa(rb['auc'])} | {e['hits50']} | {r0['hits50']} |")
        for key, val in (("pick", e["auc"]), ("v0", r0["auc"]), ("g", rg["auc"]), ("b", rb["auc"])):
            if val is not None:
                sums[key].append(val)
        hits["pick"] += e["hits50"]
        hits["v0"] += r0["hits50"]
    mean = {k: sum(v) / len(v) for k, v in sums.items() if v}
    n_rows = sum(len(data[c]) for c in CUTOFFS)
    n_pos = sum(int(r["is_hit"]) for c in CUTOFFS for r in data[c])
    lines.insert(4, data_refresh_note(mean, hits, n_rows, n_pos))
    lines.insert(5, tie_rule_note())
    wins = sum(1 for c in CUTOFFS
               if (evals[int(picks[c])][c]["auc"] or 0) > (ref_evals["점수 v0"][c]["auc"] or 0))
    lines += ["", f"**평균 AUC (뺀 기준일 기준)**: 고른 가중치 {mean['pick']:.3f} · v0 {mean['v0']:.3f} · "
              f"공연 수만 {mean['g']:.3f} · 갈래 수만 {mean['b']:.3f}",
              f"**상위 50 적중 합계**: 고른 가중치 {hits['pick']} · v0 {hits['v0']} · "
              f"고른 가중치가 v0보다 AUC가 높았던 기준일 {wins}/{len(CUTOFFS)}", ""]

    best_all = max(names, key=lambda i: sum(v for v in table[str(i)].values() if v is not None))
    chosen = [names[int(picks[c])] for c in CUTOFFS]
    lines += ["## 추천 가중치 (기준일 전체로 고름)", "", f"`{_fmt_w(names[best_all])}`", "",
              "교차 검증에서 기준일마다 골라진 가중치의 범위(안정성 확인):", ""]
    for k in GRID:
        vals = sorted({w[k] for w in chosen})
        lines.append(f"- {k[2:]}: {', '.join(f'{v:g}' for v in vals)}")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[-20:]))
    print(f"✅ → {OUT.relative_to(lab_sql.ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
