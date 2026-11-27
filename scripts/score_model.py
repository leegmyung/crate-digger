"""학습 모델 비교 + 리드타임 + 점수 안정성 → docs/score_model.md

1) 손 공식(점수 v2, lab_sql.DEFAULTS)과 학습 모델(로지스틱 회귀, numpy 경사하강 + L2)을
   score_tune 과 같은 기준일 6개·같은 후보군·같은 지표(등급 가중 AUC, 상위 20·50 적중)로 비교한다.
   '기준일 하나 빼고 학습 → 뺀 기준일 채점'. 특징 표준화와 L2 강도 고르기는 학습 기준일로만 한다(누수 금지).
2) 리드타임: 정답 팀마다 '첫 신호 → 첫 정답' 개월 수를 출처·장르·정답 등급별로 (중앙값·사분위).
3) 점수 안정성: 스냅샷 두 개(docs/lab/data/snapshots/)의 순위 변동·상위 50 유지율·변동 원인.

실행: .venv/bin/python scripts/score_model.py   → docs/score_model.md
"""
from __future__ import annotations

import csv
import itertools
import math
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab_sql  # noqa: E402
import score_tune as st  # noqa: E402

OUT = lab_sql.ROOT / "docs" / "score_model.md"
SNAP_DIR = lab_sql.DATA_DIR / "snapshots"
L2_GRID = (0.001, 0.01, 0.1, 1.0)
GD_LR = 0.5
GD_MAX_ITERS = 4000
GD_TOL = 1e-7
BOOT_REPS = 300
DAYS_PER_MONTH = 30.4375
MIN_GROUP = 5            # 리드타임 표에서 이보다 적은 묶음은 '표본 부족'
TOP_KEEP = 50            # 안정성: 상위 몇 팀 유지율을 볼지
GRADE_RANK = {"S": 3, "A": 2, "B": 1}

# (특징, 설명) — 점수 v2 와 같은 변환 (feature_vector 순서)
FEATURES: Tuple[Tuple[str, str], ...] = (
    ("n_branch", "갈래 수 − 1"), ("best_stage", "선정 최고 단계"), ("venues", "ln(1+공연장 수)"),
    ("recent180", "ln(1+최근 180일 신호)"), ("peer_winner", "수상 팀과 같은 무대"),
    ("outlets", "min(발굴 매거진, 3)"), ("context_outlets", "min(맥락 매거진, 3)"),
    ("peer_selected", "선정 팀과 같은 무대"), ("dmz", "DMZ 출연"), ("gigs_1y", "ln(1+1년 공연 일수)"),
)
V2_KEY = {"n_branch": "w_branch", "best_stage": "w_stage", "venues": "w_venues", "recent180": "w_recent",
          "peer_winner": "w_winner", "outlets": "w_outlets", "context_outlets": "w_context",
          "peer_selected": "w_peer", "dmz": "w_dmz", "gigs_1y": "w_gigs"}


# ---------- 특징 ----------

def feature_vector(r: dict) -> List[float]:
    cap = st.OUTLET_CAP
    return [r["n_branch"] - 1, float(r["best_stage"]), math.log(1 + r["venues"]), math.log(1 + r["recent180"]),
            float(r["peer_winner"]), float(min(r["outlets"], cap)), float(min(r.get("context_outlets") or 0, cap)),
            float(r["peer_selected"]), float(r["dmz"]), math.log(1 + r["gigs_1y"])]


def v2_weights() -> Dict[str, float]:
    return {k: float(lab_sql.DEFAULTS[k]) for k, _ in st.V0_WEIGHTS}


def fit_standardizer(x: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    mean = x.mean(axis=0)
    std = x.std(axis=0)
    return mean, np.where(std > 0, std, 1.0)


def apply_standardizer(x: np.ndarray, mean: np.ndarray, std: np.ndarray) -> np.ndarray:
    return (x - mean) / std


def sample_weights(rows: Sequence[dict]) -> np.ndarray:
    """정답 팀은 등급 가중치(S3·A2·B1), 아닌 팀은 1. 정답 쪽 총 무게를 아닌 쪽과 같게 맞춘다(정답이 1%라서)."""
    hit_w = np.array([float(r.get("hit_weight") or 0) if r["is_hit"] else 0.0 for r in rows])
    neg = np.array([0.0 if r["is_hit"] else 1.0 for r in rows])
    if hit_w.sum() > 0:
        hit_w = hit_w * (neg.sum() / hit_w.sum())
    return hit_w + neg


# ---------- 로지스틱 회귀 (경사하강 + L2) ----------

def fit_logistic(x: np.ndarray, y: np.ndarray, w: np.ndarray, l2: float) -> Tuple[np.ndarray, float]:
    """가중 평균 로그 손실 + (l2/2)·|계수|² 를 경사하강으로 최소화. 절편은 벌점 없음."""
    coef = np.zeros(x.shape[1])
    b = 0.0
    wn = w / w.sum()
    for _ in range(GD_MAX_ITERS):
        with np.errstate(all="ignore"):      # macOS Accelerate 의 가짜 부동소수 경고 무시 (값은 아래에서 검사)
            p = 1.0 / (1.0 + np.exp(-np.clip(x @ coef + b, -30, 30)))
            err = wn * (p - y)
            g_coef = x.T @ err + l2 * coef
        g_b = err.sum()
        coef = coef - GD_LR * g_coef
        b -= GD_LR * g_b
        if max(np.abs(g_coef).max(), abs(g_b)) < GD_TOL:
            break
    if not (np.all(np.isfinite(coef)) and math.isfinite(b)):
        raise FloatingPointError("로지스틱 학습이 발산함 (계수에 nan/inf)")
    return coef, b


@dataclass(frozen=True)
class LogisticModel:
    mean: np.ndarray
    std: np.ndarray
    coef: np.ndarray
    intercept: float
    l2: float

    def predict(self, rows: Sequence[dict]) -> np.ndarray:
        x = np.array([feature_vector(r) for r in rows])
        with np.errstate(all="ignore"):
            return apply_standardizer(x, self.mean, self.std) @ self.coef + self.intercept


def train_logistic(rows: Sequence[dict], l2: float) -> LogisticModel:
    x = np.array([feature_vector(r) for r in rows])
    mean, std = fit_standardizer(x)            # 학습 행으로만
    y = np.array([float(r["is_hit"]) for r in rows])
    coef, b = fit_logistic(apply_standardizer(x, mean, std), y, sample_weights(rows), l2)
    return LogisticModel(mean, std, coef, b, l2)


def _stack(data: Dict[str, List[dict]], keep: Sequence[str]) -> List[dict]:
    return [r for c in keep for r in data[c]]


def _decimals(key: str) -> Optional[int]:
    """손 공식은 앱처럼 소수 둘째 자리로 반올림해 순서를 매기고, 앱에 안 보이는 로지스틱 점수는 반올림하지 않는다."""
    return None if key == "lr" else st.APP_SCORE_DECIMALS


def _wauc(rows: Sequence[dict], scores: Sequence[float],
          decimals: Optional[int] = st.APP_SCORE_DECIMALS) -> Optional[float]:
    """앱 순서 기준 가중 AUC (동점은 마지막 신호 최근 순 → md5, score_tune.app_auc)."""
    return st.app_auc([float(v) for v in scores], [float(r.get("hit_weight") or 0) for r in rows],
                      [r["team_key"] for r in rows], [r.get("last_seen") for r in rows], decimals=decimals)


def choose_l2(data: Dict[str, List[dict]], grid: Sequence[float] = L2_GRID) -> float:
    """주어진(학습) 기준일 안에서만 다시 '하나 빼고' 검증해 L2 강도를 고른다. 동점이면 더 강한 쪽."""
    cutoffs = sorted(data)
    best, best_val = max(grid), float("-inf")
    for l2 in sorted(grid, reverse=True):
        vals = []
        for held in cutoffs:
            train = _stack(data, [c for c in cutoffs if c != held])
            if not any(r["is_hit"] for r in train):
                continue
            v = _wauc(data[held], train_logistic(train, l2).predict(data[held]), decimals=None)
            if v is not None:
                vals.append(v)
        mean = sum(vals) / len(vals) if vals else float("-inf")
        if mean > best_val + 1e-12:
            best, best_val = l2, mean
    return best


def _plus_months(d: str, m: int) -> str:
    y, mo, day = map(int, d.split("-"))
    total = y * 12 + (mo - 1) + m
    return f"{total // 12:04d}-{total % 12 + 1:02d}-{day:02d}"


def forward_folds(cutoffs: Sequence[str], horizon_months: int) -> List[Tuple[str, List[str]]]:
    """엄격한 시간 분리: 학습 기준일의 관찰 기간이 채점 기준일 전에 끝나는 것만 학습에 쓴다."""
    folds = []
    for test in cutoffs:
        train = [c for c in cutoffs if _plus_months(c, horizon_months) <= test]
        if train:
            folds.append((test, train))
    return folds


# ---------- 평가 ----------

def metrics(rows: Sequence[dict], scores: Sequence[float], decimals: Optional[int] = st.APP_SCORE_DECIMALS) -> dict:
    """앱 순서 기준 지표 (score_tune.evaluate 와 같은 규칙). 로지스틱은 decimals=None."""
    s = [float(v) for v in scores]
    y = [int(r["is_hit"]) for r in rows]
    order = st.app_order(s, [r["team_key"] for r in rows], [r.get("last_seen") for r in rows], decimals=decimals)
    return {"auc": st.ranked_weighted_auc(order, [float(r.get("hit_weight") or 0) for r in rows]),
            "plain_auc": st.ranked_weighted_auc(order, y), "hits20": sum(y[i] for i in order[:20]),
            "hits50": sum(y[i] for i in order[:50]), "n": len(rows), "pos": sum(y)}


def hand_scores(rows: Sequence[dict], w: Dict[str, float]) -> List[float]:
    return [st.score(r, w) for r in rows]


# ---------- 손 공식 격자 탐색을 행렬로 (score_tune 과 같은 후보 1만여 가지, 빠르게) ----------

GRID_CHUNK = 200
SCORE_DECIMALS = 9       # 행렬 곱의 미세한 반올림 차이로 동점이 깨지지 않게


def weight_vector(w: Dict[str, float]) -> np.ndarray:
    return np.array([float(w.get(V2_KEY[name], 0)) for name, _ in FEATURES])


def round_app_matrix(scores: np.ndarray) -> np.ndarray:
    """score_tune._round_app 과 같은 반올림(앱 ROUND(score, 2))을 행렬 전체에."""
    m = 10 ** st.APP_SCORE_DECIMALS
    return np.copysign(np.floor(np.abs(scores) * m + 0.5 + 1e-9) / m, scores)


def weighted_auc_matrix(scores: np.ndarray, weights: np.ndarray, ties: np.ndarray) -> np.ndarray:
    """scores(팀 × 가중치 후보)의 열마다 st.app_auc 와 같은 값(앱처럼 반올림, 동점은 ties 순 = st.tie_ranks).
    정답이나 비정답이 없으면 nan."""
    pos, neg = weights > 0, weights == 0
    if not pos.any() or not neg.any():
        return np.full(scores.shape[1], np.nan)
    scores = round_app_matrix(scores)
    sp, sn, wp = scores[pos], scores[neg], weights[pos]
    tp, tn = ties[pos][:, None, None], ties[neg][None, :, None]
    out = np.empty(scores.shape[1])
    for a in range(0, scores.shape[1], GRID_CHUNK):
        p, n = sp[:, None, a:a + GRID_CHUNK], sn[None, :, a:a + GRID_CHUNK]
        below = (n < p) | ((n == p) & (tn > tp))                                  # 비정답이 정답보다 아래
        frac = below.sum(axis=1) / sn.shape[0]   # 정답 × 후보
        out[a:a + GRID_CHUNK] = (wp[:, None] * frac).sum(axis=0) / wp.sum()
    return out


def grid_table(data: Dict[str, List[dict]]) -> Tuple[List[dict], Dict[str, Dict[str, Optional[float]]]]:
    """score_tune.main 과 같은 격자 전부의 기준일별 가중 AUC. table[str(후보 번호)][기준일]."""
    space = st.active_grid(data)
    grid = [dict(zip(space, combo)) for combo in itertools.product(*space.values())]
    grid = [w for w in grid if any(w.values())]
    wmat = np.array([weight_vector(w) for w in grid]).T                       # 특징 × 후보
    table: Dict[str, Dict[str, Optional[float]]] = {str(i): {} for i in range(len(grid))}
    for c, rows in data.items():
        with np.errstate(all="ignore"):      # macOS Accelerate 의 가짜 경고 (값은 테스트로 손 공식과 같음을 확인)
            s = np.round(np.array([feature_vector(r) for r in rows]) @ wmat, SCORE_DECIMALS)
        ties = np.array(st.tie_ranks([r["team_key"] for r in rows], [r.get("last_seen") for r in rows]))
        aucs = weighted_auc_matrix(s, np.array([float(r.get("hit_weight") or 0) for r in rows]), ties)
        for i, v in enumerate(aucs):
            table[str(i)][c] = None if np.isnan(v) else float(v)
    return grid, table


def pick_best(table: Dict[str, Dict[str, Optional[float]]], cutoffs: Sequence[str]) -> int:
    """주어진 기준일들의 평균 AUC가 가장 높은 후보 (동점은 score_tune.loco_pick 과 같은 순서)."""
    def mean(name: str) -> float:
        vals = [table[name][c] for c in cutoffs if table[name].get(c) is not None]
        return sum(vals) / len(vals) if vals else float("-inf")
    return int(max(sorted(table), key=mean))


def paired_bootstrap(per_cut: Dict[str, Tuple[List[dict], Dict[str, np.ndarray]]], a_key: str, b_key: str,
                     reps: int = BOOT_REPS, seed: int = 0) -> Tuple[float, float, float]:
    """(모델 a − 모델 b) 평균 AUC 차이와 95% 구간. 기준일마다 정답·비정답을 따로 다시 뽑는다(같은 표본으로 두 모델 채점)."""
    rng = np.random.default_rng(seed)
    diffs = []
    for _ in range(reps):
        d = []
        for rows, scores in per_cut.values():
            a, b = scores[a_key], scores[b_key]
            pos = [i for i, r in enumerate(rows) if r["is_hit"]]
            neg = [i for i, r in enumerate(rows) if not r["is_hit"]]
            idx = np.concatenate([rng.choice(pos, len(pos)), rng.choice(neg, len(neg))])
            sub = [rows[i] for i in idx]
            va, vb = _wauc(sub, a[idx], _decimals(a_key)), _wauc(sub, b[idx], _decimals(b_key))
            if va is not None and vb is not None:
                d.append(va - vb)
        diffs.append(sum(d) / len(d))
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return float(np.mean(diffs)), float(lo), float(hi)


# ---------- 리드타임 ----------

def months_between(d1: str, d2: str) -> float:
    return (date.fromisoformat(str(d2)[:10]) - date.fromisoformat(str(d1)[:10])).days / DAYS_PER_MONTH


def quartiles(values: Sequence[float]) -> Optional[Tuple[float, float, float]]:
    if not values:
        return None
    q1, med, q3 = np.percentile(np.array(values, dtype=float), [25, 50, 75])
    return float(q1), float(med), float(q3)


def lead_times(signals: Sequence[dict], outcomes: Sequence[dict]) -> List[dict]:
    """팀×출처마다 '첫 정답보다 엄격하게 앞선 가장 이른 신호' → 첫 정답까지 개월. 등급은 첫 정답 날의 가장 높은 등급."""
    first: Dict[str, Tuple[str, str]] = {}
    for o in outcomes:
        k, d, g = o["team_key"], str(o["announced_date"])[:10], o.get("grade") or ""
        cur = first.get(k)
        if cur is None or d < cur[0] or (d == cur[0] and GRADE_RANK.get(g, 0) > GRADE_RANK.get(cur[1], 0)):
            first[k] = (d, g)
    earliest: Dict[Tuple[str, str], str] = {}
    for s in signals:
        k, d = s["team_key"], str(s["signal_date"])[:10]
        if k not in first or d >= first[k][0]:
            continue
        key = (k, s["source"])
        if key not in earliest or d < earliest[key]:
            earliest[key] = d
    return [{"team_key": k, "source": src, "signal_date": d, "outcome_date": first[k][0],
             "grade": first[k][1], "months": months_between(d, first[k][0])}
            for (k, src), d in sorted(earliest.items())]


def first_signal_leads(leads: Sequence[dict]) -> List[dict]:
    """팀마다 가장 이른 출처 하나만 (팀 전체의 '첫 신호 → 첫 정답')."""
    best: Dict[str, dict] = {}
    for r in leads:
        cur = best.get(r["team_key"])
        if cur is None or (r["signal_date"], r["source"]) < (cur["signal_date"], cur["source"]):
            best[r["team_key"]] = r
    return [best[k] for k in sorted(best)]


# ---------- 점수 안정성 ----------

def compare_snapshots(prev: Sequence[dict], cur: Sequence[dict], top: int = TOP_KEEP) -> dict:
    """moves: 두 스냅샷에 모두 있는 팀의 (이전 순위 − 지금 순위), +면 오름."""
    pr = {r["team_key"]: int(r["rank"]) for r in prev}
    cr = {r["team_key"]: int(r["rank"]) for r in cur}
    top_prev = {k for k, v in pr.items() if v <= top}
    top_cur = {k for k, v in cr.items() if v <= top}
    return {"entered": sorted((k for k in cr if k not in pr), key=cr.get),
            "exited": sorted((k for k in pr if k not in cr), key=pr.get),
            "top_kept": len(top_prev & top_cur), "top_prev": len(top_prev),
            "moves": {k: pr[k] - cr[k] for k in sorted(pr) if k in cr}}


def rank_change_summary(moves: Dict[str, int]) -> dict:
    """순위 변동(이전 − 지금) 분포: 그대로인 비율, |변동| 10 이상 비율, |변동| 사분위."""
    vals = list(moves.values())
    if not vals:
        return {"n": 0, "unchanged": 0.0, "moved10": 0.0, "moved50": 0.0, "abs_q": None}
    return {"n": len(vals), "unchanged": sum(v == 0 for v in vals) / len(vals),
            "moved10": sum(abs(v) >= 10 for v in vals) / len(vals),
            "moved50": sum(abs(v) >= 50 for v in vals) / len(vals),
            "abs_q": quartiles([abs(v) for v in vals])}


def change_reason(prev_feat: Optional[dict], cur_feat: Optional[dict],
                  weights: Optional[Dict[str, float]] = None) -> str:
    """두 날짜의 후보 행(없으면 None)을 비교해 변동 원인 한 가지를 고른다. weights 를 주면 점수에 쓰는 특징만 원인으로 센다."""
    if prev_feat is None and cur_feat is None:
        return "두 날 모두 후보 아님"
    if cur_feat is None:
        return "후보에서 빠짐"
    if prev_feat is None:
        return "새로 후보가 됨"
    changed = [(name, label) for name, label in FEATURES if prev_feat.get(name) != cur_feat.get(name)]
    if not changed:
        return "내 특징은 그대로(다른 팀이 움직임)"
    if weights is not None:
        used = [label for name, label in changed if weights.get(V2_KEY[name], 0)]
        if not used:
            return "점수에 안 쓰는 특징만 변함(다른 팀이 움직임)"
        return "특징 변화: " + ", ".join(used)
    return "특징 변화: " + ", ".join(label for _, label in changed)


# ---------- 문서 ----------

def _fa(v: Optional[float]) -> str:
    return "—" if v is None else f"{v:.3f}"


def _fq(q: Optional[Tuple[float, float, float]]) -> str:
    return "—" if q is None else f"{q[1]:.1f} ({q[0]:.1f}~{q[2]:.1f})"


MODEL_KEYS = ("v2", "grid", "lr", "g", "b")


def _loco_rows(data: Dict[str, List[dict]], w2: Dict[str, float], grid: List[dict],
               table: Dict[str, Dict[str, Optional[float]]]) -> Tuple[List[str], dict]:
    cutoffs = list(st.CUTOFFS)
    refs = {"g": st._single("w_gigs"), "b": st._single("w_branch")}
    rows_md, per_cut, l2s = [], {}, []
    agg: Dict[str, List[float]] = {k: [] for k in MODEL_KEYS}
    hits = {k: [0, 0] for k in ("v2", "grid", "lr")}
    for held in cutoffs:
        train_cuts = [c for c in cutoffs if c != held]
        l2 = choose_l2({c: data[c] for c in train_cuts})
        l2s.append(l2)
        rows = data[held]
        scores = {"v2": np.array(hand_scores(rows, w2)),
                  "grid": np.array(hand_scores(rows, grid[pick_best(table, train_cuts)])),
                  "lr": train_logistic(_stack(data, train_cuts), l2).predict(rows),
                  "g": np.array(hand_scores(rows, refs["g"])), "b": np.array(hand_scores(rows, refs["b"]))}
        m = {k: metrics(rows, v, _decimals(k)) for k, v in scores.items()}
        per_cut[held] = (rows, scores)
        for key, mm in m.items():
            if mm["auc"] is not None:
                agg[key].append(mm["auc"])
        for key in hits:
            hits[key][0] += m[key]["hits20"]
            hits[key][1] += m[key]["hits50"]
        rows_md.append(f"| {held} | {m['v2']['n']:,} | {m['v2']['pos']} | {_fa(m['v2']['auc'])} | {_fa(m['grid']['auc'])} | "
                       f"{_fa(m['lr']['auc'])} (L2 {l2:g}) | {_fa(m['g']['auc'])} | {_fa(m['b']['auc'])} | "
                       f"{m['v2']['hits20']} / {m['grid']['hits20']} / {m['lr']['hits20']} | "
                       f"{m['v2']['hits50']} / {m['grid']['hits50']} / {m['lr']['hits50']} |")
    mean = {k: sum(v) / len(v) for k, v in agg.items()}

    def wins(a: str, b: str) -> int:
        return sum(1 for c in cutoffs if (_wauc(per_cut[c][0], per_cut[c][1][a], _decimals(a)) or 0)
                   > (_wauc(per_cut[c][0], per_cut[c][1][b], _decimals(b)) or 0))
    return rows_md, {"mean": mean, "hits": hits, "wins_lr_grid": wins("lr", "grid"), "wins_lr_v2": wins("lr", "v2"),
                     "per_cut": per_cut, "l2s": l2s}


def _forward_rows(data: Dict[str, List[dict]], w2: Dict[str, float], grid: List[dict],
                  table: Dict[str, Dict[str, Optional[float]]]) -> List[str]:
    out = []
    for test, train in forward_folds(st.CUTOFFS, st.HORIZON_MONTHS):
        l2 = choose_l2({c: data[c] for c in train}) if len(train) > 1 else max(L2_GRID)
        rows = data[test]
        m_lr = metrics(rows, train_logistic(_stack(data, train), l2).predict(rows), decimals=None)
        m_gr = metrics(rows, hand_scores(rows, grid[pick_best(table, train)]))
        m_v2 = metrics(rows, hand_scores(rows, w2))
        n_pos = sum(int(r["is_hit"]) for r in _stack(data, train))
        out.append(f"| {test} | {', '.join(train)} (정답 {n_pos}) | {_fa(m_v2['auc'])} | {_fa(m_gr['auc'])} | "
                   f"{_fa(m_lr['auc'])} | {m_v2['hits50']} / {m_gr['hits50']} / {m_lr['hits50']} |")
    return out


def _coef_rows(data: Dict[str, List[dict]], w2: Dict[str, float], l2s: List[float]) -> Tuple[List[str], float, dict]:
    cutoffs = list(st.CUTOFFS)
    full_l2 = choose_l2(data)
    full = train_logistic(_stack(data, cutoffs), full_l2)
    fold = np.array([train_logistic(_stack(data, [c for c in cutoffs if c != h]), l2).coef
                     for h, l2 in zip(cutoffs, l2s)])
    v2_std = weight_vector(w2) * full.std
    lr_share = np.abs(full.coef) / np.abs(full.coef).sum()
    v2_share = np.abs(v2_std) / np.abs(v2_std).sum()
    out = []
    for i, (name, label) in enumerate(FEATURES):
        lo, hi = fold[:, i].min(), fold[:, i].max()
        if name == "dmz" and not fold[:, i].any():
            sign = "값이 늘 0"
        else:
            sign = "⚠️ 바뀜" if lo < 0 < hi else ("+" if lo >= 0 else "−")
        out.append(f"| {label} | {full.coef[i]:+.3f} | {lo:+.2f} ~ {hi:+.2f} | {sign} | "
                   f"{lr_share[i] * 100:.0f}% | {v2_share[i] * 100:.0f}% |")
    shares = {name: (float(lr_share[i]), float(v2_share[i]), float(fold[:, i].min()), float(fold[:, i].max()))
              for i, (name, _) in enumerate(FEATURES)}
    return out, full_l2, shares


def section_models(data: Dict[str, List[dict]]) -> Tuple[List[str], dict]:
    cutoffs = list(st.CUTOFFS)
    w2 = v2_weights()
    grid, table = grid_table(data)
    rows_md, res = _loco_rows(data, w2, grid, table)
    boot_g = paired_bootstrap(res["per_cut"], "lr", "grid")
    boot_v = paired_bootstrap(res["per_cut"], "lr", "v2")
    fwd_md = _forward_rows(data, w2, grid, table)
    coef_md, full_l2, coefs = _coef_rows(data, w2, res["l2s"])
    mean, hits = res["mean"], res["hits"]
    pos_total = sum(sum(int(r["is_hit"]) for r in data[c]) for c in cutoffs)
    n_total = sum(len(data[c]) for c in cutoffs)
    best_all = pick_best(table, cutoffs)
    best_all_mean = sum(table[str(best_all)].values()) / len(cutoffs)
    lines = [
        "## 1. 학습 모델 vs 손 공식 (기준일 하나 빼고 학습 → 뺀 기준일 채점)", "",
        f"기준일 6개({', '.join(cutoffs)}), 관찰 {st.HORIZON_MONTHS}개월. 후보군·특징·지표는 `score_tune`과 같다"
        f"(앱·[점수 교차 검증](score_tuning.md)·[방법론](methods.md)과 같은 계산). 6개 기준일을 합치면 후보 {n_total:,}행, 정답 {pos_total}행.", "",
        "- **v2 (고정)**: 지금 기본 손 공식(`lab_sql.DEFAULTS`)을 그대로 채점. ⚠️ v2 가중치는 기준일 6개 **전부**를 보고 고른 값이라"
        " 이 열은 '시험 문제를 미리 본' 점수다(공정한 비교 상대가 아니라 참고용). "
        f"지금 데이터로 6개 전부를 보고 다시 고르면 `{st._fmt_w(grid[best_all])}`(평균 {best_all_mean:.3f})이고 v2는 {mean['v2']:.3f}로 거의 최상위다.",
        "- **손 공식 (교차 검증)**: `score_tune`과 같은 가중치 후보 1만여 가지 중, **뺀 기준일을 빼고** 평균 AUC가 가장 높은 것을 골라 채점. "
        "학습 모델과 **공정하게 견줄 상대**.",
        "- **로지스틱 회귀**: 같은 특징 10개(v2와 같은 변환)에 계수를 데이터로 맞춘 모델. numpy 경사하강 + L2 벌점(계수가 너무 커지지 않게 누름), "
        "정답 등급(S3·A2·B1)을 표본 가중치로 쓰고 정답 쪽 총 무게를 비정답 쪽과 같게 맞춤. "
        "특징 표준화(평균 0·표준편차 1)와 L2 강도 고르기는 **학습 기준일 5개로만** 했다 — L2는 그 5개 안에서 다시 하나 빼기로 골랐다(뺀 기준일은 끝까지 안 봄).",
        "- **기준선**: 공연 수만 · 갈래 수만.", "",
        "| 뺀 기준일 | 후보 | 정답 | AUC v2(고정) | AUC 손 공식(교차) | AUC 로지스틱 | AUC 공연 수만 | AUC 갈래 수만 | 상위20 v2 / 손 / 로지 | 상위50 v2 / 손 / 로지 |",
        "|---|---|---|---|---|---|---|---|---|---|", *rows_md, "",
        f"- **평균 AUC**: 손 공식(교차) **{mean['grid']:.3f}** · 로지스틱 **{mean['lr']:.3f}** · 공연 수만 {mean['g']:.3f} · "
        f"갈래 수만 {mean['b']:.3f} · (참고: v2 고정 {mean['v2']:.3f})",
        f"- **상위 20 / 50 적중 합계**: 손 공식(교차) {hits['grid'][0]} / {hits['grid'][1]} · 로지스틱 {hits['lr'][0]} / {hits['lr'][1]} · "
        f"(참고: v2 고정 {hits['v2'][0]} / {hits['v2'][1]})",
        f"- **로지스틱이 이긴 기준일**: 손 공식(교차)보다 {res['wins_lr_grid']}/{len(cutoffs)}, v2 고정보다 {res['wins_lr_v2']}/{len(cutoffs)}",
        f"- **평균 AUC 차이의 95% 구간** (기준일마다 정답·비정답 팀을 {BOOT_REPS}번 다시 뽑은 부트스트랩, 구간이 0을 지나면 '차이가 있다'고 말할 수 없음):",
        f"  - 로지스틱 − 손 공식(교차): {boot_g[0]:+.3f} ({boot_g[1]:+.3f} ~ {boot_g[2]:+.3f})",
        f"  - 로지스틱 − v2 고정: {boot_v[0]:+.3f} ({boot_v[1]:+.3f} ~ {boot_v[2]:+.3f})", "",
        "### 1-1. 더 엄격하게: 과거로만 학습", "",
        "위 방식은 뒤 기준일로 학습해 앞 기준일을 채점하기도 한다(`score_tune`과 같은 한계). "
        f"그래서 **학습 기준일의 관찰 기간({st.HORIZON_MONTHS}개월)이 채점 기준일 전에 끝난 것만** 학습에 쓰는 경우를 따로 쟀다. "
        "학습에 쓸 수 있는 정답이 아주 적어 참고용이다.", "",
        "| 채점 기준일 | 학습 기준일 | AUC v2(고정) | AUC 손 공식(과거로 고름) | AUC 로지스틱 | 상위50 v2 / 손 / 로지 |",
        "|---|---|---|---|---|---|", *fwd_md, "",
        f"### 1-2. 계수 (기준일 6개 전체로 학습, L2 {full_l2:g})", "",
        "계수 = 표준화된 특징이 1(표준편차 하나)만큼 클 때 정답 가능성(로그 오즈)이 얼마나 오르는지. "
        "'기준일별 범위'는 하나 빼고 학습한 6번의 계수 최소~최대이고, 부호가 바뀌면 그 특징의 방향은 믿기 어렵다. "
        "'비중'은 |계수|를 합이 100%가 되게 나눈 것이고, v2 비중은 v2 가중치에 특징 표준편차를 곱해 같은 단위로 바꾼 것. "
        "DMZ는 '제외' 출처라 특징값이 늘 0이다.", "",
        "| 특징 | 계수 | 기준일별 범위 | 부호 | 로지스틱 비중 | v2 비중 |", "|---|---|---|---|---|---|", *coef_md, "",
    ]
    summary = {"mean": mean, "hits": hits, "boot_g": boot_g, "boot_v": boot_v, "shares": coefs,
               "l2s": res["l2s"], "pos_total": pos_total, "best_all": grid[best_all]}
    return lines + interpret_models(summary), summary


def interpret_models(sm_: dict) -> List[str]:
    """숫자를 보고 해석·권고 문단을 만든다(다시 돌려도 숫자와 어긋나지 않게 조건으로)."""
    mean, (dg, lo_g, hi_g) = sm_["mean"], sm_["boot_g"]
    label = dict(FEATURES)
    if lo_g > 0:
        verdict = f"학습 모델이 공정한 손 공식보다 **확실히 낫다**(차이 {dg:+.3f}, 구간이 0 위)."
    elif hi_g < 0:
        verdict = f"학습 모델이 공정한 손 공식보다 **확실히 못하다**(차이 {dg:+.3f}, 구간이 0 아래)."
    else:
        verdict = (f"학습 모델과 공정한 손 공식은 **사실상 같다**(차이 {dg:+.3f}, 95% 구간 {lo_g:+.3f}~{hi_g:+.3f}가 0을 지남). "
                   "학습 모델이 손 공식보다 확실히 낫다고 말할 근거가 없다.")
    optimism = mean["v2"] - mean["grid"]
    stable_pos = [label[n] for n, (_, _, lo, hi) in sm_["shares"].items() if lo > 0 and n != "dmz"]
    flips = [label[n] for n, (_, _, lo, hi) in sm_["shares"].items() if lo < 0 < hi]
    negs = [label[n] for n, (_, _, lo, hi) in sm_["shares"].items() if hi < 0]
    gaps = sorted(((lr - v2, n) for n, (lr, v2, _, _) in sm_["shares"].items() if abs(lr - v2) >= 0.10), reverse=True)
    gap_txt = "; ".join(f"{label[n]} — 로지스틱 {sm_['shares'][n][0] * 100:.0f}% vs v2 {sm_['shares'][n][1] * 100:.0f}%"
                        for _, n in gaps) or "없음"
    l2s = sm_["l2s"]
    return [
        "### 1-3. 해석", "",
        f"1. **공정 비교 결과**: {verdict}",
        f"2. **v2 숫자는 부풀려져 있다**: 같은 손 공식이라도 고를 때 본 시점에서 채점하면(v2 고정 {mean['v2']:.3f}) "
        f"안 본 시점에서 채점할 때(손 공식 교차 {mean['grid']:.3f})보다 **{optimism:.3f}** 높다. "
        f"앱·문서의 v2 AUC는 새 시점에서 기대할 실제 성능보다 이만큼 높게 읽어야 한다(실제 기대치는 {mean['grid']:.2f} 안팎).",
        f"3. **과적합 위험**: 6개 기준일 정답이 {sm_['pos_total']}행(같은 팀이 여러 기준일에 다시 셈)이고 특징이 10개라 특징 하나당 정답이 10개도 안 된다. "
        f"기준일마다 고른 L2 강도도 {min(l2s):g}~{max(l2s):g}로 크게 흔들렸다. 손 공식 교차 검증에서도 뺀 기준일마다 골라지는 가중치가 달랐다 "
        "(→ [점수 교차 검증](score_tuning.md)). 지금 표본으로는 어느 방법이든 '정확한 가중치'를 찾기 어렵다.",
        "4. **계수 부호와 상식**: "
        + (f"늘 플러스인 특징 — {', '.join(stable_pos)} → 상식과 맞다(선정·공연장 다양성·매체 소개·최근 활동이 많을수록 정답 가능성↑). " if stable_pos else "")
        + (f"부호가 기준일마다 바뀐 특징 — {', '.join(flips)} → 방향을 믿기 어렵다. " if flips else "")
        + (f"늘 마이너스인 특징 — {', '.join(negs)}. " if negs else "")
        + "'1년 공연 일수'가 마이너스로 나오는 건 '공연장 수'와 겹치기 때문으로 보인다(공연장 수가 같다면 같은 곳에 자주 서는 것은 덜 중요하다는 뜻). "
          "'갈래 수'가 0 근처인 것도 선정·매체·공연장 특징이 이미 갈래 정보를 담고 있어서다.",
        f"5. **손 공식과 비중이 크게 다른 특징**(10%p 이상): {gap_txt}. "
        "로지스틱 쪽이 무조건 맞다는 뜻은 아니지만, 다음 가중치 점검 때 볼 곳이다.", "",
        "### 1-4. 권고 (바꾸지 않고 제안만)", "",
        "- **기본 점수는 손 공식(v2)을 유지**한다. 학습 모델이 공정 비교에서 이기지 못했고, 손 공식은 발굴 담당자가 '왜 위에 있나'를 바로 읽을 수 있다.",
        "- 학습 모델은 **가중치 점검 도구**로 쓴다: 정답이 쌓일 때마다 이 스크립트를 돌려 계수 부호가 뒤집히거나 비중이 크게 벌어지는 특징을 찾는다.",
        f"- 앱·문서에서 v2 성능을 말할 때는 고를 때 안 본 시점 기준({mean['grid']:.2f} 안팎)을 함께 적는 것을 제안한다.",
        *([f"- 최근 활동(최근 180일 신호)은 로지스틱에서 꾸준히 플러스이고"
           + (f", 지금 데이터로 전체를 다시 고른 손 공식에도 가중치 {sm_['best_all']['w_recent']:g}로 들어간다"
              if sm_["best_all"].get("w_recent") else "")
           + " → 다음 `score_tune` 때 후보로 다시 볼 것."] if sm_["shares"]["recent180"][2] > 0 else []),
        "- 다시 비교할 때: 정답이 지금의 2~3배(기준일 합산 200행 이상)가 되거나, 검증 대기 출처(인스타·발매)가 첫 정답 시즌을 지난 뒤.", "",
    ]


# ---------- 2. 리드타임 문서 ----------

LEAD_SIGNAL_SQL = ("SELECT team_key, branch || ':' || CASE WHEN branch = '선정·지원' THEN program ELSE source END AS source, "
                   "role, CAST(signal_date AS VARCHAR) AS signal_date FROM signals")
LEAD_OUTCOME_SQL = ("SELECT team_key, CAST(announced_date AS VARCHAR) AS announced_date, grade FROM outcomes "
                    "WHERE counted")


def _rows(con, sql: str) -> List[dict]:
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _lead_line(name: str, vals: List[float], extra: str = "") -> str:
    if len(vals) < MIN_GROUP:
        return f"| {name}{extra} | {len(vals)} | 표본 부족 | — |"
    long_share = sum(v >= 12 for v in vals) / len(vals)
    return f"| {name}{extra} | {len(vals)} | {_fq(quartiles(vals))} | {long_share * 100:.0f}% |"


def _group(leads: Sequence[dict], key) -> Dict[str, List[float]]:
    out: Dict[str, List[float]] = {}
    for r in leads:
        out.setdefault(key(r), []).append(r["months"])
    return out


# 분석용 장르: profile·press(·확신도 없는 옛 CSV)만 — 추정·리뷰·확신 낮음(inferred·review·inferred_low)은 '미분류'.
# genre_bias.analysis_genre·peer_compare.sql 과 같은 규칙 (2026-11-27·28 결정, docs/genre_fill.md 6-1)
ANALYSIS_GENRE_SQL = ("CASE WHEN COALESCE(t.genre_confidence, '') NOT IN ('', 'profile', 'press') THEN '미분류' "
                      "ELSE COALESCE(NULLIF(TRIM(t.primary_genre), ''), '미분류') END")


def team_genres(con) -> Dict[str, str]:
    """팀 → 분석용 장르 (추정·리뷰·확신 낮음은 미분류)."""
    return dict(con.execute(f"SELECT t.team_key, {ANALYSIS_GENRE_SQL} FROM teams t").fetchall())


def section_lead(con) -> Tuple[List[str], dict]:
    signals = _rows(con, LEAD_SIGNAL_SQL)
    outcomes = _rows(con, LEAD_OUTCOME_SQL)
    genre = team_genres(con)
    role = {s["source"]: s["role"] for s in signals}
    start = {}
    for s in signals:
        start[s["source"]] = min(start.get(s["source"], s["signal_date"]), s["signal_date"])
    by_source = lead_times(signals, outcomes)
    scored = [s for s in signals if s["role"] in ("discovery", "context")]
    overall = first_signal_leads(lead_times(scored, outcomes))
    winners = {o["team_key"] for o in outcomes}
    head = ["| 묶음 | 정답 팀 | 개월 중앙값 (사분위 25%~75%) | 12개월 이상 앞섬 |", "|---|---|---|---|"]
    lines = ["## 2. 리드타임: 첫 신호 → 첫 정답", "",
             "정답(센 정답, `counted`)을 처음 받은 날과, 그보다 **엄격하게 앞선** 가장 이른 신호 날짜 사이의 개월 수. "
             "날짜를 일부만 알 때 신호는 기간 마지막 날·정답은 첫날로 저장돼 있어(방법론 2절) 리드타임이 부풀지 않는 쪽이다. "
             f"정답 팀 {len(winners)}팀 중 첫 정답 전에 신호가 하나라도 있던 팀은 {len(overall)}팀"
             f"({len(overall) / len(winners) * 100:.0f}%, 발굴·맥락 출처 기준).", "",
             "### 2-1. 전체 · 정답 등급별 · 장르별 (팀마다 가장 이른 발굴·맥락 신호)", "", *head,
             _lead_line("전체", [r["months"] for r in overall])]
    for g, vals in sorted(_group(overall, lambda r: f"등급 {r['grade'] or '?'}").items()):
        lines.append(_lead_line(g, vals))
    for g, vals in sorted(_group(overall, lambda r: genre.get(r["team_key"], "미분류")).items(), key=lambda x: -len(x[1])):
        lines.append(_lead_line(f"장르 {g}", vals))
    for g, vals in sorted(_group(overall, lambda r: f"첫 정답 {r['outcome_date'][:4]}년").items()):
        lines.append(_lead_line(g, vals))
    src_groups = _group(by_source, lambda r: r["source"])
    lines += ["", "### 2-2. 출처별 (그 출처의 가장 이른 신호 → 첫 정답, 모든 역할)", "",
              "| 출처 | 역할 | 기록 시작 | 정답 팀 | 개월 중앙값 (사분위) | 12개월 이상 앞섬 |", "|---|---|---|---|---|---|"]
    for src, vals in sorted(src_groups.items(), key=lambda x: -len(x[1])):
        line = _lead_line(src, vals)
        cells = line.split(" | ")
        lines.append(f"| {src} | {role.get(src, '?')} | {start[src][:7]} | " + " | ".join(cells[1:]))
    med_all = quartiles([r["months"] for r in overall])
    grade_med = {g: quartiles(v)[1] for g, v in _group(overall, lambda r: r["grade"]).items() if len(v) >= MIN_GROUP}
    year_n = {y: len(v) for y, v in _group(overall, lambda r: r["outcome_date"][:4]).items()}
    lines += ["", "### 2-3. 읽는 법", "",
              f"- 전체 중앙값 {med_all[1]:.1f}개월: 정답 팀의 절반은 첫 신호 뒤 {med_all[1]:.0f}개월 안에 첫 정답을 받았다. "
              "점수가 맞혀도 담당자가 움직일 시간이 이 정도라는 뜻이다.",
              "- **출처마다 기록 시작이 달라 리드타임이 잘린다**: 인디스트릿 공연은 2024-01부터, 큐레이션은 2023년부터만 있어서 "
              "그 전에 이미 활동한 팀도 '첫 신호'가 기록 시작 시점으로 늦춰진다. 출처끼리 길이를 비교할 때는 기록 시작을 같이 본다. "
              "선정 출처(밴드 디스커버리·유재하)는 기록이 길어 리드타임도 길게 나온다.",
              f"- 정답 팀의 {100 - len(overall) * 100 // len(winners)}%는 첫 정답 전에 우리 신호가 하나도 없다(이유 후보: 신호 기록이 얇은 시기의 정답, "
              "공연·매체 데이터가 덮지 못하는 장르·지역 팀). 첫 정답 연도별 신호 있는 팀: "
              + ", ".join(f"{y}년 {n}팀" for y, n in sorted(year_n.items())) + ".",
              *([f"- 등급별 중앙값: " + ", ".join(f"{g} {m:.1f}개월" for g, m in sorted(grade_med.items()))
                 + (" — 전국 단위 최종 수상(S)은 첫 신호에서 정답까지가 더 짧다. S 정답 팀은 이미 주목받은 뒤에야 우리 신호(매체 소개 등)에 잡히는 경우가 많다는 뜻일 수 있다."
                    if grade_med.get("S", 99) < grade_med.get("A", 0) else "") + " 표본이 작아 방향으로만 본다."] if grade_med else []),
              "- 장르별 리드타임은 [장르 편향 점검](genre_bias.md)과 같은 이유(장르가 붙은 팀이 이미 주목받은 팀 위주)로 조심해서 읽는다.", ""]
    return lines, {"n_winners": len(winners), "n_with_signal": len(overall), "median": med_all[1]}


# ---------- 3. 점수 안정성 문서 ----------

def _candidates(con, day: str) -> Dict[str, dict]:
    rows = lab_sql.query(con, "candidates.sql", as_of=f"'{day}'", limit="100000")
    return {r["team_key"]: r for r in rows}


def section_stability(con) -> Tuple[List[str], dict]:
    days = sorted(p.stem for p in SNAP_DIR.glob("*.csv"))
    if len(days) < 2:
        return ["## 3. 점수 안정성", "", "스냅샷이 2개 미만이라 건너뜀.", ""], {}
    d0, d1 = days[-2], days[-1]
    prev, cur = load_csv(SNAP_DIR / f"{d0}.csv"), load_csv(SNAP_DIR / f"{d1}.csv")
    cmp_ = compare_snapshots(prev, cur)
    summ = rank_change_summary(cmp_["moves"])
    c0, c1 = _candidates(con, d0), _candidates(con, d1)
    w2 = v2_weights()
    names = {**{k: r.get("display_name") or k for k, r in c0.items()}, **{k: r.get("display_name") or k for k, r in c1.items()}}
    recomputed = [k for k, _ in sorted(c0.items(), key=lambda kv: (-float(kv[1]["score"]), kv[0]))][:len(prev)]
    same = len(set(recomputed) & {r["team_key"] for r in prev})
    reasons: Dict[str, int] = {}
    for k in sorted(set(cmp_["moves"]) | set(cmp_["entered"]) | set(cmp_["exited"])):
        if k in cmp_["moves"] and cmp_["moves"][k] == 0:
            continue
        rs = change_reason(c0.get(k), c1.get(k), w2)
        if k in cmp_["exited"] and k in c1:
            rs = "점수는 남았지만 300위 밖으로 밀림"
        elif k in cmp_["entered"] and k in c0:
            rs = "300위 밖에서 안으로 올라옴"
        key = rs if not rs.startswith("특징 변화") else "점수 특징 변화(새 신호·창 밖으로 빠진 신호)"
        reasons[key] = reasons.get(key, 0) + 1
    movers = sorted(cmp_["moves"].items(), key=lambda kv: (-abs(kv[1]), kv[0]))[:10]
    q = summ["abs_q"]
    lines = ["## 3. 점수 안정성: 스냅샷 두 개 비교", "",
             f"`docs/lab/data/snapshots/`의 {d0} ↔ {d1} 상위 {len(prev)}팀(앱 '오늘 볼 것'이 비교하는 두 날짜). "
             f"{d0}는 그날까지의 신호로 **다시 만든(재구성)** 스냅샷이다. 지금 데이터로 {d0} 상위 {len(prev)}을 다시 계산하면 "
             f"저장된 스냅샷과 {same}팀이 겹친다(다르면 그 사이 연결표·분류표가 바뀐 몫).", "",
             f"- **상위 {TOP_KEEP} 유지율**: {cmp_['top_kept']}/{cmp_['top_prev']} ({cmp_['top_kept'] / max(cmp_['top_prev'], 1) * 100:.0f}%)",
             f"- **두 날 모두 상위 {len(prev)}에 있던 팀**: {summ['n']}팀 — 순위 그대로 {summ['unchanged'] * 100:.0f}%, "
             f"10계단 이상 변동 {summ['moved10'] * 100:.0f}%, 50계단 이상 {summ['moved50'] * 100:.0f}%"
             + (f", |변동| 중앙값 {q[1]:.0f}계단 (사분위 {q[0]:.0f}~{q[2]:.0f})" if q else ""),
             f"- **새로 들어옴 / 빠짐**: {len(cmp_['entered'])}팀 / {len(cmp_['exited'])}팀", "",
             "**변동 원인** (순위가 바뀌었거나 들어오고 나간 팀, 두 날짜의 특징값을 비교):", "",
             "| 원인 | 팀 수 |", "|---|---|", *[f"| {k} | {v} |" for k, v in sorted(reasons.items(), key=lambda kv: -kv[1])], "",
             "**가장 크게 움직인 팀 10** (+는 오름):", "", "| 팀 | 변동 | 원인 |", "|---|---|---|"]
    for k, mv in movers:
        lines.append(f"| {names.get(k, k)} | {mv:+d} | {change_reason(c0.get(k), c1.get(k), w2)} |")
    lines += ["", "**읽는 법**: 한 주 사이 점수가 바뀌는 이유는 ① 새 신호(공연·매체 소개)로 특징이 바뀜, ② 신호가 3년 창 밖으로 빠지거나 "
              "신인 기간이 지남, ③ 정답을 받아 후보에서 빠짐, ④ 내 점수는 그대로인데 다른 팀이 올라오거나 내려가 순위만 바뀜이다. "
              "점수가 같은 팀이 많아(동점) ④번만으로도 순위가 몇 계단씩 흔들린다 — 앱에서는 순위보다 점수·점수 구성을 같이 보는 것이 안전하다.", ""]
    return lines, {"top_kept": cmp_["top_kept"], "top_prev": cmp_["top_prev"], "summ": summ,
                   "entered": len(cmp_["entered"]), "exited": len(cmp_["exited"]), "reasons": reasons}


def load_csv(path: Path) -> List[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main(argv: Sequence[str] = ()) -> int:
    """--skip-models: 1절(학습 모델, 약 15초)을 건너뛰고 2·3절만 (디버그용)."""
    con = lab_sql.connect()
    lines = ["# 학습 모델 비교 · 리드타임 · 점수 안정성", "",
             "_자동 생성: `.venv/bin/python scripts/score_model.py` (해석 문단은 생성 시점 숫자를 조건으로 만든 것)_", ""]
    if "--skip-models" not in argv:
        data = {c: st.features(con, c) for c in st.CUTOFFS}
        lines += section_models(data)[0]
    lines += section_lead(con)[0]
    lines += section_stability(con)[0]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"✅ → {OUT.relative_to(lab_sql.ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
