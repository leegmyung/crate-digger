"""점수 가중치 고르기 — 기준일 하나를 빼고(leave-one-cutoff-out) 고른 뒤, 뺀 기준일로 채점한다.

왜: 결과를 보고 가중치를 맞추면 우연을 외운 점수가 된다. 고를 때 쓰지 않은 시점에서도 나아야 진짜 개선이다.
지표: 가중 AUC(정답 팀이 후보 전체 중 위쪽에 있는 정도, 0.5 = 무작위, 1 = 완벽 — 정답 등급 S=3·A=2·B=1로 가중,
      config/source_roles.json) — 상위 K 적중 수보다 덜 흔들림. 등급 없는 보통 AUC도 함께 적는다.
      보조로 상위 50팀 적중 수.
특징값은 브라우저와 같은 계산식(docs/lab/sql/features.sql의 lab_scored)에서 가져온다.

실행: .venv/bin/python scripts/score_tune.py   → docs/score_tuning.md
"""
from __future__ import annotations

import bisect
import itertools
import math
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab_sql  # noqa: E402

CUTOFFS = ["2023-01-01", "2023-07-01", "2024-01-01", "2024-07-01", "2025-01-01", "2025-07-01"]
HORIZON_MONTHS = 24
OUTLET_CAP = 3
V0_WEIGHTS = (("w_branch", 2.0), ("w_stage", 1.0), ("w_peer", 1.0), ("w_dmz", 0.5), ("w_gigs", 0.5),
              ("w_outlets", 1.0), ("w_recent", 0.0), ("w_venues", 0.0), ("w_winner", 0.0), ("w_context", 0.0))
# 1차 탐색(v0 특징 6개만)에서 DMZ는 늘 0, 선정 단계는 2가 골라졌다 → 새 특징 3개를 넣고 범위를 좁혀 다시 탐색
GRID = {"w_branch": (0, 1, 2, 3), "w_stage": (1, 2, 3), "w_peer": (0, 1), "w_dmz": (0,),
        "w_gigs": (0,), "w_outlets": (0.5, 1, 2), "w_recent": (0, 1, 2, 3), "w_venues": (0, 1, 2),
        "w_winner": (0, 1, 2), "w_context": (0, 0.25, 0.5, 1)}   # 맥락 매체(기준선 이하 큰 매거진)는 약하게 — 차등
OUT = lab_sql.ROOT / "docs" / "score_tuning.md"


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


def hits_at_k(scores: Sequence[float], labels: Sequence[int], keys: Sequence[str], k: int) -> int:
    """점수 상위 k팀 중 정답 수. 동점은 팀 키 순(정답 여부로 순서가 바뀌지 않게)."""
    order = sorted(range(len(scores)), key=lambda i: (-scores[i], keys[i]))
    return sum(labels[i] for i in order[:k])


def score(f: dict, w: dict) -> float:
    return (w["w_branch"] * (f["n_branch"] - 1) + w["w_stage"] * f["best_stage"] + w["w_peer"] * f["peer_selected"]
            + w["w_dmz"] * f["dmz"] + w["w_gigs"] * math.log(1 + f["gigs_1y"])
            + w["w_outlets"] * min(f["outlets"], OUTLET_CAP) + w["w_recent"] * math.log(1 + f["recent180"])
            + w["w_venues"] * math.log(1 + f["venues"]) + w["w_winner"] * f["peer_winner"]
            + w.get("w_context", 0) * min(f.get("context_outlets", 0), OUTLET_CAP))


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
         "peer_winner, context_outlets, is_hit, hit_weight "
         "FROM lab_scored(DATE '{c}', 3, 3, true, 'any', {h}, '', ['공연','선정·지원','발매','큐레이션'], "
         "{w_branch}, {w_stage}, {w_peer}, {w_dmz}, {w_gigs}, {w_outlets}, {cap}, {w_recent}, {w_venues}, "
         "{w_winner}, {w_context}) WHERE NOT had_outcome")
    cur = con.execute(q.format(c=cutoff, h=HORIZON_MONTHS, cap=OUTLET_CAP, **zero))
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def evaluate(data: Dict[str, List[dict]], w: dict) -> Dict[str, dict]:
    out = {}
    for c, rows in data.items():
        s = [score(r, w) for r in rows]
        y = [int(r["is_hit"]) for r in rows]
        keys = [r["team_key"] for r in rows]
        hit_w = [float(r.get("hit_weight") or 0) for r in rows]
        out[c] = {"auc": weighted_auc(s, hit_w), "plain_auc": auc(s, y),
                  "hits50": hits_at_k(s, y, keys, 50), "hits20": hits_at_k(s, y, keys, 20),
                  "n": len(rows), "pos": sum(y)}
    return out


def _single(name: str) -> dict:
    return {k: (1.0 if k == name else 0.0) for k, _ in V0_WEIGHTS}


def _fmt_w(w: dict) -> str:
    return " · ".join(f"{k[2:]} {v:g}" for k, v in w.items())


def main() -> int:
    con = lab_sql.connect()
    data = {c: features(con, c) for c in CUTOFFS}
    grid = [dict(zip(GRID, combo)) for combo in itertools.product(*GRID.values())]
    grid = [w for w in grid if any(w.values())]
    names = {i: w for i, w in enumerate(grid)}
    evals = {i: evaluate(data, w) for i, w in names.items()}
    table = {str(i): {c: e[c]["auc"] for c in CUTOFFS} for i, e in evals.items()}
    picks = loco_pick(table)

    v0 = dict(V0_WEIGHTS)
    refs = {"점수 v0": v0, "공연 수만": _single("w_gigs"), "갈래 수만": _single("w_branch")}
    ref_evals = {k: evaluate(data, w) for k, w in refs.items()}

    lines = ["# 점수 가중치 고르기 (교차 검증)", "",
             "_자동 생성: `.venv/bin/python scripts/score_tune.py`_", "",
             "기준일 하나를 빼고 나머지 기준일의 평균 AUC가 가장 높은 가중치를 고른 뒤, **뺀 기준일**에서 채점했다(고를 때 안 본 시점).",
             f"관찰 기간 {HORIZON_MONTHS}개월(2025-07-01은 데이터 끝 2026-11까지라 약 17개월), 신호 3년·신인 3년·유명 팀 제외. "
             f"가중치 후보 {len(grid):,}가지.", "",
             "AUC = 정답 팀 하나와 아닌 팀 하나를 골랐을 때 정답 팀 점수가 더 높을 확률(0.5 = 무작위). "
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
