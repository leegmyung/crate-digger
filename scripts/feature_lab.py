"""점수 새 특징 실험 (제안만 — 점수·계산식은 바꾸지 않음) → docs/feature_lab.md

점수 v2(lab_sql.DEFAULTS)에 새 특징을 **하나씩** 더했을 때 교차 검증 AUC·상위 적중이 오르는지 잰다.
- 후보군·정답·지표는 score_tune 과 같다(기준일 6개, score_tune.features, 등급 가중 AUC, 상위 20·50·100 적중).
- 새 특징은 features.sql 을 고치지 않고 이 스크립트 안에서 signals·outcomes 표로 팀마다 계산해 붙인다.
- 누수 금지: 신호는 기준일 '전'만, 정답은 기준일 '전'에 발표된 것만(공연장 질·정답 팀까지 거리), 자기 자신은 뺀다.
- 과적합 주의: 특징마다 크기를 표준편차로 맞춘 뒤 가중치는 세 개만(+0 = v2 그대로) — 1차 {-0.5, 0.5, 1}(미리 정함),
  2차 {-0.1, 0.1, 0.3}(1차가 너무 거칠어 결과를 본 뒤 추가 — 문서에 그렇게 적는다).
  기준일 하나를 빼고 나머지 5개 평균 AUC로 가중치를 고른 뒤 뺀 기준일에서 채점(score_tune 과 같은 방식).

실행: .venv/bin/python scripts/feature_lab.py [--data-dir 폴더]   → docs/feature_lab.md
"""
from __future__ import annotations

import argparse
import itertools
import math
import re
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab_sql  # noqa: E402
import score_tune as st  # noqa: E402

OUT = lab_sql.ROOT / "docs" / "feature_lab.md"
LOOKBACK_YEARS = 3          # lab_sql.DEFAULTS lookback_years 와 같게
GRID = (-0.5, 0.5, 1.0)     # 1차(미리 정함): 표준편차 1만큼의 특징에 줄 v2 점수(점) — 방향을 모르는 특징도 있어 음수 하나 포함
GRID_FINE = (-0.1, 0.1, 0.3)   # 2차(1차 결과를 본 뒤): v2 점수 표준편차가 0.92점이라 1차 격자는 기존 점수를 덮어썼다
VQ_PRIOR = 20               # 공연장 질 평활: 다른 팀 20팀 분량의 '전체 평균'을 섞는다(작은 공연장의 우연 줄이기)
MAX_HOPS = 3                # 정답 팀까지 거리: 3칸까지만
WINDOW_DAYS = 180
YEAR_DAYS = 365.25
BOOT_REPS = 200
TIEBREAK_W = 0.001          # '동점 가르기만' 확인용 아주 작은 가중치
ADOPT_MIN_GAIN = 0.005      # 채택 기준: 교차 검증 평균 AUC 이만큼 이상 오를 것
UNKNOWN_VENUES = ("", "공연장 미정")
REGIONS = ("부산", "대구", "인천", "광주", "대전", "울산", "세종", "수원", "성남", "고양", "안양", "부천", "춘천",
           "원주", "강릉", "청주", "천안", "전주", "군산", "포항", "경주", "창원", "김해", "제주", "여수", "순천")

Gig = Tuple[str, date, str]   # (팀, 날짜, 공연장)
Extra = Dict[str, Dict[str, Dict[str, float]]]   # extra[기준일][팀][특징] = 값

# (특징 키, 이름, 정의) — 문서 표 순서
FEATURES: Tuple[Tuple[str, str, str], ...] = (
    ("venue_quality", "공연장 질", "그 팀이 선 공연장(기준일 전 전체 기록)마다 '다른 팀 중 기준일 전에 정답을 받은 비율'을 "
                                "전체 비율로 나눈 배수(평활 20팀), 공연장 평균 − 1. 자기 자신 제외"),
    ("winner_proximity", "정답 팀까지 거리", "기준일 전 3년 같은 날·같은 공연장 그래프에서 기준일 전 정답 팀까지 1칸 1·2칸 0.5·3칸 0.33"),
    ("scene_degree", "씬 이웃 수", "같은 그래프에서 함께 무대에 선 서로 다른 팀 수, ln(1+수)"),
    ("peer_score", "동료 팀 점수 평균", "함께 무대에 선 후보 팀들의 같은 기준일 v2 점수 평균(이웃이 후보군에 없으면 0)"),
    ("acceleration", "신호 가속도", "ln(1+직전 180일 발굴 신호 수) − ln(1+그 전 180일)"),
    ("tenure_years", "첫 신호 후 경과", "기준일 − 우리 데이터 첫 신호(발굴·맥락, 기간 제한 없음), 년"),
    ("last_gap_years", "마지막 신호 후 공백", "기준일 − 마지막 발굴·맥락 신호, 년"),
    ("source_count", "서로 다른 발굴 출처 수", "기준일 전 3년 발굴 신호의 (출처, 프로그램) 종류 수"),
    ("region_spread", "공연 지역 다양성", "공연장 이름 앞머리 도시명으로 본 서로 다른 지역 수 − 1 (없으면 서울)"),
    ("stage_rise", "선정 단계 상승", "직전 1년 선정 최고 단계 − 그 전 최고 단계(0 아래는 0, DMZ 제외)"),
)
NAMES = {f: n for f, n, _ in FEATURES}
LEAKAGE_NOTES = {
    "venue_quality": "정답은 기준일 전 발표분만, 공연도 기준일 전만. 후보 팀은 기준일 전 정답이 없어(had_outcome 제외) "
                     "분자에 자신이 들어갈 일이 없고, 분모에서도 자신을 뺀다.",
    "winner_proximity": "정답 팀 = 기준일 전 발표. 그래프는 기준일 전 3년 공연만. 미래 공연·미래 정답 없음.",
    "scene_degree": "기준일 전 3년 공연만.",
    "peer_score": "이웃 점수도 같은 기준일 특징(기준일 전 신호)으로 계산 — 정답 라벨은 안 씀.",
    "acceleration": "기준일 전 360일 신호만.",
    "tenure_years": "첫 신호 날짜는 기준일 전 신호에서만 찾음(나중 신호로 바뀌지 않음).",
    "last_gap_years": "기준일 전 신호만.",
    "source_count": "기준일 전 3년 발굴 신호만.",
    "region_spread": "기준일 전 3년 공연만. 공연장 이름만 보므로 지역 판정은 시점과 무관.",
    "stage_rise": "선정 날짜는 기간 마지막 날로 저장돼 있어 보수적(실제보다 늦게 앎).",
}


# ---------- 신호 거르기 ----------

def window(signals: Iterable[dict], cutoff: date, years: Optional[int], roles: Sequence[str]) -> List[dict]:
    """기준일 전, (years 가 있으면) 기준일 − years 년 이후, 역할이 roles 인 신호."""
    start = date(cutoff.year - years, cutoff.month, cutoff.day) if years else None
    return [s for s in signals if s["role"] in roles and s["signal_date"] < cutoff
            and (start is None or s["signal_date"] >= start)]


def winners_before(outcomes: Iterable[dict], cutoff: date) -> Set[str]:
    """기준일 전에 '센 정답'을 받은 팀 (features.sql winner_first 와 같은 조건)."""
    return {o["team_key"] for o in outcomes if o["counted"] and o["announced_date"] < cutoff}


def gigs(signals: Iterable[dict]) -> List[Gig]:
    """공연 신호 → (팀, 날짜, 공연장). 공연장 없음·미정은 뺀다 (features.sql gig 과 같게)."""
    return sorted({(s["team_key"], s["signal_date"], s["venue"]) for s in signals
                   if s["branch"] == "공연" and (s["venue"] or "") not in UNKNOWN_VENUES})


# ---------- 그래프 특징 ----------

def cobill_graph(gig_rows: Iterable[Gig]) -> Dict[str, Set[str]]:
    """같은 날·같은 공연장에 선 팀끼리 잇는다."""
    nights: Dict[Tuple[date, str], Set[str]] = defaultdict(set)
    for team, d, venue in gig_rows:
        nights[(d, venue)].add(team)
    adj: Dict[str, Set[str]] = defaultdict(set)
    for teams in nights.values():
        for t in teams:
            adj[t] |= teams - {t}
    return dict(adj)


def winner_proximity(adj: Dict[str, Set[str]], winners: Set[str], max_hops: int = MAX_HOPS) -> Dict[str, float]:
    """정답 팀에서 넓이 우선 탐색: 거리 d칸이면 1/d (정답 팀 자신은 제외)."""
    dist = {w: 0 for w in winners if w in adj}
    frontier = list(dist)
    for hop in range(1, max_hops + 1):
        nxt = []
        for t in frontier:
            for n in adj.get(t, ()):
                if n not in dist:
                    dist[n] = hop
                    nxt.append(n)
        frontier = nxt
    return {t: 1.0 / d for t, d in dist.items() if d > 0}


def peer_score(adj: Dict[str, Set[str]], scores: Dict[str, float]) -> Dict[str, float]:
    """후보 팀마다 '함께 무대에 선 후보 팀' 점수 평균."""
    out = {}
    for t in scores:
        vals = [scores[n] for n in adj.get(t, ()) if n in scores]
        if vals:
            out[t] = sum(vals) / len(vals)
    return out


def venue_quality(gig_rows: Iterable[Gig], winners: Set[str], prior: float = VQ_PRIOR) -> Dict[str, float]:
    """공연장마다 '다른 팀 중 정답 팀 비율'(평활)을 전체 비율로 나눈 배수, 팀이 선 공연장 평균 − 1. 정답 팀 자신은 값 없음."""
    at_venue: Dict[str, Set[str]] = defaultdict(set)
    for team, _, venue in gig_rows:
        at_venue[venue].add(team)
    all_teams: Set[str] = set().union(*at_venue.values()) if at_venue else set()
    p0 = len(all_teams & winners) / len(all_teams) if all_teams else 0.0
    team_venues: Dict[str, Set[str]] = defaultdict(set)
    for venue, teams in at_venue.items():
        for t in teams:
            team_venues[t].add(venue)
    out = {}
    for t, venues in team_venues.items():
        if t in winners:
            continue
        if p0 == 0:
            out[t] = 0.0
            continue
        lifts = []
        for v in venues:
            others = at_venue[v] - {t}
            n, k = len(others), len(others & winners)
            rate = (k + prior * p0) / (n + prior) if n + prior > 0 else p0
            lifts.append(rate / p0)
        out[t] = sum(lifts) / len(lifts) - 1
    return out


# ---------- 단순 특징 ----------

def _by_team(signals: Iterable[dict]) -> Dict[str, List[dict]]:
    out: Dict[str, List[dict]] = defaultdict(list)
    for s in signals:
        out[s["team_key"]].append(s)
    return out


def acceleration(signals: Iterable[dict], cutoff: date, days: int = WINDOW_DAYS) -> Dict[str, float]:
    recent_from, prev_from = cutoff - timedelta(days=days), cutoff - timedelta(days=2 * days)
    out = {}
    for t, rows in _by_team(signals).items():
        r = sum(1 for s in rows if recent_from <= s["signal_date"] < cutoff)
        p = sum(1 for s in rows if prev_from <= s["signal_date"] < recent_from)
        out[t] = math.log(1 + r) - math.log(1 + p)
    return out


def tenure_years(signals: Iterable[dict], cutoff: date) -> Dict[str, float]:
    return {t: (cutoff - min(s["signal_date"] for s in rows)).days / YEAR_DAYS for t, rows in _by_team(signals).items()}


def last_gap_years(signals: Iterable[dict], cutoff: date) -> Dict[str, float]:
    return {t: (cutoff - max(s["signal_date"] for s in rows)).days / YEAR_DAYS for t, rows in _by_team(signals).items()}


def source_count(signals: Iterable[dict]) -> Dict[str, int]:
    return {t: len({(s["source"], s["program"]) for s in rows}) for t, rows in _by_team(signals).items()}


def region_of(venue: str) -> str:
    """공연장 이름 앞머리의 도시명으로 지역을 정한다. 없으면 서울(수집 공연장 대부분이 홍대·서울)."""
    m = re.match("(" + "|".join(REGIONS) + ")", venue or "")
    return m.group(1) if m else "서울"


def region_spread(gig_rows: Iterable[Gig]) -> Dict[str, int]:
    regions: Dict[str, Set[str]] = defaultdict(set)
    for team, _, venue in gig_rows:
        regions[team].add(region_of(venue))
    return {t: len(r) - 1 for t, r in regions.items()}


def stage_rise(signals: Iterable[dict], cutoff: date) -> Dict[str, int]:
    """직전 1년 선정 최고 단계 − 그 전 최고 단계 (0 아래는 0). DMZ 라인업은 v2 best_stage 처럼 뺀다."""
    split = cutoff - timedelta(days=365)
    sel = (s for s in signals if s["branch"] == "선정·지원" and s["program"] != "dmz_lineup"
           and s["stage_rank"] is not None)
    out = {}
    for t, rows in _by_team(sel).items():
        recent = max((s["stage_rank"] for s in rows if split <= s["signal_date"] < cutoff), default=0)
        before = max((s["stage_rank"] for s in rows if s["signal_date"] < split), default=0)
        out[t] = max(0, recent - before)
    return out


# ---------- 팀별 특징 묶기 ----------

def v2_weights() -> Dict[str, float]:
    return {k: float(lab_sql.DEFAULTS[k]) for k, _ in st.V0_WEIGHTS}


def team_features(signals: Sequence[dict], outcomes: Sequence[dict], rows: Sequence[dict],
                  cutoff: date) -> Dict[str, Dict[str, float]]:
    """후보 팀(rows)마다 새 특징 값. 기준일 전 정보만 쓴다."""
    disc = window(signals, cutoff, LOOKBACK_YEARS, ("discovery",))
    both_all = window(signals, cutoff, None, ("discovery", "context"))
    gigs_lb = gigs(disc)
    winners = winners_before(outcomes, cutoff)
    adj = cobill_graph(gigs_lb)
    w2 = v2_weights()
    base = {r["team_key"]: st.score(r, w2) for r in rows}
    parts = {
        "venue_quality": venue_quality(gigs(window(signals, cutoff, None, ("discovery",))), winners),
        "winner_proximity": winner_proximity(adj, winners),
        "scene_degree": {t: math.log(1 + len(n)) for t, n in adj.items()},
        "peer_score": peer_score(adj, base),
        "acceleration": acceleration(disc, cutoff),
        "tenure_years": tenure_years(both_all, cutoff),
        "last_gap_years": last_gap_years(both_all, cutoff),
        "source_count": source_count(disc),
        "region_spread": region_spread(gigs_lb),
        "stage_rise": stage_rise(disc, cutoff),
    }
    return {t: {k: float(v.get(t, 0.0)) for k, v in parts.items()} for t in base}


# ---------- 평가 ----------

def _value(extra: Dict[str, Dict[str, float]], team: str, feat: str) -> float:
    return extra.get(team, {}).get(feat, 0.0)


def feature_scale(data: Dict[str, List[dict]], extra: Extra, feat: str) -> float:
    """후보 전체(기준일 6개 합침)의 표준편차 — 정답 라벨은 안 본다. 0이면 1."""
    vals = [_value(extra.get(c, {}), r["team_key"], feat) for c, rows in data.items() for r in rows]
    if not vals:
        return 1.0
    mean = sum(vals) / len(vals)
    sd = math.sqrt(sum((v - mean) ** 2 for v in vals) / len(vals))
    return sd if sd > 1e-12 else 1.0


def metrics(rows: Sequence[dict], scores: Sequence[float]) -> dict:
    """앱 순서 기준 지표 (score_tune.evaluate 와 같은 규칙: 반올림 점수 → 마지막 신호 최근 순 → md5)."""
    y = [int(r["is_hit"]) for r in rows]
    order = st.app_order(scores, [r["team_key"] for r in rows], [r.get("last_seen") for r in rows])
    return {"auc": st.ranked_weighted_auc(order, [float(r.get("hit_weight") or 0) for r in rows]),
            "plain_auc": st.ranked_weighted_auc(order, y),
            "hits20": sum(y[i] for i in order[:20]), "hits50": sum(y[i] for i in order[:50]),
            "hits100": sum(y[i] for i in order[:100])}


def _mean(vals: Iterable[Optional[float]]) -> float:
    v = [x for x in vals if x is not None]
    return sum(v) / len(v) if v else float("nan")


def combined_scores(rows: Sequence[dict], extra: Dict[str, Dict[str, float]],
                    weights: Dict[str, float], scales: Dict[str, float]) -> List[float]:
    w2 = v2_weights()
    return [st.score(r, w2) + sum(w * _value(extra, r["team_key"], f) / scales[f] for f, w in weights.items())
            for r in rows]


def _pick(mets: Dict[tuple, Dict[str, dict]], combos: Sequence[tuple], keep: Sequence[str]) -> tuple:
    """keep 기준일 평균 AUC가 가장 높은 조합. 동점이면 앞의 것(첫 번째 = 모두 0 = v2 그대로)."""
    best, best_v = combos[0], _mean(mets[combos[0]][c]["auc"] for c in keep)
    for cb in combos[1:]:
        v = _mean(mets[cb][c]["auc"] for c in keep)
        if v > best_v + 1e-12:
            best, best_v = cb, v
    return best


def evaluate_combo(data: Dict[str, List[dict]], extra: Extra, feats: Sequence[str],
                   grid: Sequence[float] = GRID) -> dict:
    """특징 묶음(feats)의 가중치 조합을 기준일 하나 빼고 고른 뒤 채점. 특징 1개면 단독 실험."""
    cutoffs = list(data)
    scales = {f: feature_scale(data, extra, f) for f in feats}
    combos = [tuple(c) for c in itertools.product((0.0,) + tuple(grid), repeat=len(feats))]
    scores = {cb: {c: combined_scores(data[c], extra.get(c, {}), dict(zip(feats, cb)), scales) for c in cutoffs}
              for cb in combos}
    mets = {cb: {c: metrics(data[c], scores[cb][c]) for c in cutoffs} for cb in combos}
    zero = combos[0]
    picks = {c: _pick(mets, combos, [k for k in cutoffs if k != c]) for c in cutoffs}
    cv = {c: mets[picks[c]][c] for c in cutoffs}
    base = {c: mets[zero][c] for c in cutoffs}
    full = _pick(mets, combos, cutoffs)
    hit_keys = ("hits20", "hits50", "hits100")
    return {
        "feats": list(feats), "scales": scales, "picks": picks, "cv": cv, "base": base, "full_pick": full,
        "cv_mean": _mean(cv[c]["auc"] for c in cutoffs), "base_mean": _mean(base[c]["auc"] for c in cutoffs),
        "full_mean": _mean(mets[full][c]["auc"] for c in cutoffs),
        "cv_hits": {k: sum(cv[c][k] for c in cutoffs) for k in hit_keys},
        "base_hits": {k: sum(base[c][k] for c in cutoffs) for k in hit_keys},
        "wins": sum(1 for c in cutoffs if (cv[c]["auc"] or 0) > (base[c]["auc"] or 0) + 1e-12),
        "losses": sum(1 for c in cutoffs if (cv[c]["auc"] or 0) < (base[c]["auc"] or 0) - 1e-12),
        "cv_scores": {c: scores[picks[c]][c] for c in cutoffs},
        "base_scores": {c: scores[zero][c] for c in cutoffs},
    }


def evaluate_feature(data: Dict[str, List[dict]], extra: Extra, feat: str, grid: Sequence[float] = GRID) -> dict:
    res = evaluate_combo(data, extra, [feat], grid)
    return {**res, "picks": {c: p[0] for c, p in res["picks"].items()}, "full_pick": res["full_pick"][0]}


def bootstrap_diff(data: Dict[str, List[dict]], res: dict, reps: int = BOOT_REPS,
                   seed: int = 0) -> Tuple[float, float, float]:
    """(새 특징 교차 검증 점수 − v2) 평균 AUC 차이와 95% 구간 — score_model.paired_bootstrap 재사용."""
    import numpy as np
    import score_model as sm

    per_cut = {c: (data[c], {"a": np.array(res["cv_scores"][c]), "b": np.array(res["base_scores"][c])})
               for c in data}
    return sm.paired_bootstrap(per_cut, "a", "b", reps=reps, seed=seed)


def describe(data: Dict[str, List[dict]], extra: Extra, feat: str) -> dict:
    """참고용(라벨을 봄 — 가중치 고르기엔 안 씀): 값이 0 아닌 후보 비율, 정답 팀·아닌 팀 평균."""
    hit, non, nz, n = [], [], 0, 0
    for c, rows in data.items():
        for r in rows:
            v = _value(extra.get(c, {}), r["team_key"], feat)
            (hit if r["is_hit"] else non).append(v)
            nz += v != 0
            n += 1
    return {"nonzero": nz / n if n else 0.0, "hit_mean": _mean(hit), "non_mean": _mean(non)}


# ---------- 데이터 ----------

def load_events(con) -> Tuple[List[dict], List[dict]]:
    def rows(sql: str) -> List[dict]:
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    sigs = rows("SELECT team_key, branch, source, program, stage_rank, CAST(signal_date AS DATE) AS signal_date, "
                "venue, role FROM signals WHERE signal_date IS NOT NULL")
    outs = rows("SELECT team_key, CAST(announced_date AS DATE) AS announced_date, "
                "COALESCE(CAST(counted AS BOOLEAN), false) AS counted FROM outcomes WHERE announced_date IS NOT NULL")
    return sigs, outs


def run(data_dir: Path = lab_sql.DATA_DIR) -> dict:
    con = lab_sql.connect(data_dir)
    data = {c: st.features(con, c) for c in st.CUTOFFS}
    sigs, outs = load_events(con)
    extra = {c: team_features(sigs, outs, data[c], date.fromisoformat(c)) for c in st.CUTOFFS}
    coarse = {f: evaluate_feature(data, extra, f, GRID) for f, _, _ in FEATURES}
    singles = {f: evaluate_feature(data, extra, f, GRID_FINE) for f, _, _ in FEATURES}
    for f, res in singles.items():
        res["boot"] = bootstrap_diff(data, res)
        res["desc"] = describe(data, extra, f)
    ranked = sorted(singles, key=lambda f: singles[f]["cv_mean"] - singles[f]["base_mean"], reverse=True)
    top = [f for f in ranked if singles[f]["cv_mean"] > singles[f]["base_mean"]][:2]
    combo = None
    if len(top) == 2:
        combo = evaluate_combo(data, extra, top, GRID_FINE)
        combo["boot"] = bootstrap_diff(data, combo)
    ties = {c: (distinct_scores(data[c]), len(data[c])) for c in st.CUTOFFS}
    for res in singles.values():   # 같은 방향, 아주 작은 가중치 = 순수 동점 가르기일 때의 평균 AUC (참고)
        sign = math.copysign(1.0, res["full_pick"]) if res["full_pick"] else 0.0
        res["tiebreak_mean"] = _mean(metrics(data[c], combined_scores(
            data[c], extra[c], {res["feats"][0]: sign * TIEBREAK_W}, res["scales"]))["auc"] for c in st.CUTOFFS)
    return {"data": data, "singles": singles, "ranked": ranked, "combo": combo, "coarse": coarse, "ties": ties}


def distinct_scores(rows: Sequence[dict]) -> int:
    """v2 점수의 서로 다른 값 개수 — 값이 적으면 동점이 많아, 작은 가중치의 특징은 주로 그 동점 안의 순서를 정한다."""
    w2 = v2_weights()
    return len({round(st.score(r, w2), 9) for r in rows})


# ---------- 문서 ----------

def _fa(v: Optional[float]) -> str:
    return "—" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v:.3f}"


def _fw(ws: Iterable[float]) -> str:
    return ", ".join(f"{w:g}" for w in sorted(set(ws)))


def _hits(h: dict) -> str:
    return f"{h['hits20']} / {h['hits50']} / {h['hits100']}"


def classify(res: dict) -> Tuple[List[str], List[str], List[str]]:
    """미리 정한 기준으로 채택 후보·지켜볼 것·효과 없음 나누기."""
    adopt, watch, drop = [], [], []
    for f in res["ranked"]:
        r = res["singles"][f]
        gain = r["cv_mean"] - r["base_mean"]
        keeps_hits = r["cv_hits"]["hits50"] >= r["base_hits"]["hits50"]
        if gain >= ADOPT_MIN_GAIN and r["boot"][1] > 0 and keeps_hits:
            adopt.append(f)
        elif gain > 0 and keeps_hits:
            watch.append(f)
        else:
            drop.append(f)
    return adopt, watch, drop


def _header(res: dict) -> List[str]:
    data = res["data"]
    n_rows = sum(len(r) for r in data.values())
    n_pos = sum(int(x["is_hit"]) for r in data.values() for x in r)
    lines = [
        "# 점수 새 특징 실험 (제안만 — 점수는 바꾸지 않음)", "",
        "_자동 생성: `.venv/bin/python scripts/feature_lab.py`_", "",
        "점수 v2(`lab_sql.DEFAULTS`)에 새 특징을 **하나씩** 더했을 때 나아지는지 쟀다. 후보군·정답·지표는 "
        "[점수 교차 검증](score_tuning.md)과 같다 — 기준일 6개(" + ", ".join(st.CUTOFFS) + f"), 관찰 {st.HORIZON_MONTHS}개월, "
        f"후보 {n_rows:,}행·정답 {n_pos}행, 정답 등급 가중 AUC(S3·A2·B1).", "",
        "- **방법**: 특징마다 크기를 표준편차 1로 맞추고, 가중치 후보는 0(= v2 그대로)과 세 개뿐(과적합 방지). "
        "기준일 하나를 빼고 나머지 5개 평균 AUC가 가장 높은 가중치를 골라 **뺀 기준일**에서 채점했다(고를 때 안 본 시점). "
        "동점이면 0을 고른다.",
        f"- **격자 두 번**: 1차는 미리 정한 {_fw(GRID)}점. v2 점수 자체의 표준편차가 0.92점이라 이 크기는 기존 점수를 "
        "덮어써서 거의 모든 특징이 0을 골랐다(4절). 그래서 1차 결과를 본 뒤 2차 "
        f"{_fw(GRID_FINE)}점을 더 쟀다 — ⚠️ **격자를 결과를 보고 고쳤으므로** 2차 숫자는 그만큼 낙관적이다. 아래 2·3절은 2차 기준.",
        "- **비교 상대 v2**: 가중치를 기준일 6개 전부로 고른 값이라 그 자체로 조금 유리하다. 새 특징 쪽은 그 위에 "
        "가중치 하나만 교차 검증으로 더하므로 '더해서 오르는가'의 비교는 공정하다.",
        f"- **95% 구간**: 기준일마다 정답·비정답 팀을 다시 뽑은 부트스트랩({BOOT_REPS}번). 0을 지나면 '차이가 있다'고 말할 수 없다.",
        "- ⚠️ 공연 기록(인디스트릿)은 2024-01부터라, 공연·무대 그래프 특징은 2023년 기준일 3개에서 거의 0이다.", "",
        "## 1. 특징 정의와 누수 점검", "",
        "| 특징 | 정의 | 누수 점검 (기준일 시점 정보만 쓰는가) |", "|---|---|---|",
    ]
    lines += [f"| {name} (`{f}`) | {desc} | {LEAKAGE_NOTES[f]} |" for f, name, desc in FEATURES]
    return lines


def _results(res: dict) -> List[str]:
    singles, ranked, combo = res["singles"], res["ranked"], res["combo"]
    any_res = singles[ranked[0]]
    lines = ["", "## 2. 결과 — v2에 하나씩 더하기 (AUC 차이 큰 순)", "",
             f"v2 그대로: 평균 AUC **{_fa(any_res['base_mean'])}**, 상위 20 / 50 / 100 적중 합계 {_hits(any_res['base_hits'])}.", "",
             "| 특징 | 평균 AUC (교차) | 차이 | 95% 구간 | 오른·내린 기준일 | 상위 20 / 50 / 100 | 기준일마다 고른 가중치 | "
             "전체로 고른 가중치 (AUC) | 0 아닌 후보 | 평균: 정답 / 아닌 팀 |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for f in ranked:
        r, b = singles[f], singles[f]["boot"]
        lines.append(
            f"| {NAMES[f]} | {_fa(r['cv_mean'])} | {r['cv_mean'] - r['base_mean']:+.3f} | {b[1]:+.3f} ~ {b[2]:+.3f} | "
            f"{r['wins']} / {r['losses']} | {_hits(r['cv_hits'])} | {_fw(r['picks'].values())} | "
            f"{r['full_pick']:g} ({_fa(r['full_mean'])}) | {r['desc']['nonzero']:.0%} | "
            f"{r['desc']['hit_mean']:.2f} / {r['desc']['non_mean']:.2f} |")
    lines += ["", "(평균 정답 / 아닌 팀은 표준화 전 원래 값, 기준일 6개 합침 — 참고용 설명이라 라벨을 본다. 가중치 고르기에는 안 썼다.)",
              "", "### 기준일별 (가중 AUC: v2 → 특징 더함, 괄호는 그 기준일을 빼고 고른 가중치)", "",
              "| 특징 | " + " | ".join(st.CUTOFFS) + " |", "|---|" + "---|" * len(st.CUTOFFS)]
    for f in ranked:
        r = singles[f]
        lines.append(f"| {NAMES[f]} | " + " | ".join(
            f"{_fa(r['base'][c]['auc'])} → {_fa(r['cv'][c]['auc'])} ({r['picks'][c]:g})" for c in st.CUTOFFS) + " |")
    ties = res["ties"]
    lines += ["", "**v2 점수의 서로 다른 값 개수 / 후보 수** (값 종류가 적어 동점이 많다 — 2차 격자의 작은 가중치는 "
              "주로 이 동점 안의 순서를 정하는 역할): " + ", ".join(f"{c} {k}/{n:,}" for c, (k, n) in ties.items())]
    if combo:
        b = combo["boot"]
        lines += ["", f"### 위 두 개 함께 ({' + '.join(NAMES[f] for f in combo['feats'])})", "",
                  f"가중치 조합 16가지(2차 격자) 중 교차 검증으로 고름: 평균 AUC {_fa(combo['cv_mean'])} "
                  f"(v2 대비 {combo['cv_mean'] - combo['base_mean']:+.3f}, 95% 구간 {b[1]:+.3f} ~ {b[2]:+.3f}), "
                  f"상위 20 / 50 / 100 {_hits(combo['cv_hits'])}, 오른·내린 기준일 {combo['wins']} / {combo['losses']}, "
                  "전체로 고른 가중치 " + ", ".join(f"{NAMES[f]} {w:g}" for f, w in zip(combo["feats"], combo["full_pick"])) + "."]
    return lines


def interpret(res: dict) -> List[str]:
    """숫자를 조건으로 권고 문장을 만든다."""
    singles = res["singles"]
    adopt, watch, drop = classify(res)

    def gain(f: str) -> str:
        return f"{singles[f]['cv_mean'] - singles[f]['base_mean']:+.3f}"
    out = ["", "## 3. 해석과 권고", "",
           f"채택 기준(결과를 보기 전에 정함): 교차 검증 평균 AUC **+{ADOPT_MIN_GAIN} 이상**, 95% 구간 하한이 0보다 크고, "
           "상위 50 적중이 줄지 않을 것.", "",
           "- **채택 후보**: " + (", ".join(f"{NAMES[f]}({gain(f)}, 전체로 고른 가중치 {singles[f]['full_pick']:g})"
                                         for f in adopt) or "없음"),
           "- **지켜볼 것** (조금 오르지만 기준 미달 — 데이터가 쌓이면 다시): " + (", ".join(
               f"{NAMES[f]}({gain(f)})" for f in watch) or "없음"),
           "- **효과 없음·나빠짐**: " + (", ".join(f"{NAMES[f]}({gain(f)})" for f in drop) or "없음"), ""]
    tb = singles[watch[0]]["tiebreak_mean"] - singles[watch[0]]["base_mean"] if watch else 0.0
    if watch and tb >= ADOPT_MIN_GAIN:   # 동점 가르기만으로 의미 있게 오를 때만 이 제안을 쓴다
        f = watch[0]
        w = singles[f]["full_pick"]
        order = "작은 팀" if w < 0 else "큰 팀"
        out += [f"가장 가까운 후보는 **{NAMES[f]}**(가중치 {w:g}). 가중치를 {TIEBREAK_W:g}로 거의 없애 **v2가 같은 팀끼리의 "
                f"순서만** 정하게 해도(기준일 6개로 계산, 참고) 평균 AUC가 {tb:+.3f} 오른다 — 효과 대부분이 동점 가르기에서 나온다. "
                f"점수 정의를 바꾸지 않고도, 앱·리포트 정렬에서 v2 점수가 같을 때 '{NAMES[f]}' 값이 {order}을 먼저 두는 방법으로 "
                "같은 효과를 낼 수 있다(제안).", ""]
    if app_ties_by_recency():
        out += ["**동점 순서**: 지표는 앱 후보 목록(`docs/lab/sql/candidates.sql`)과 같은 순서로 잰다 — 반올림 점수 → "
                "마지막 신호 최근 순 → md5(team_key). 그래서 v2 기준선에 '최근 신호 우선' 동점 가르기가 이미 들어 있다"
                "(2026-11-27 첫 실험 때는 동점을 절반·팀 이름 순으로 쳐서 '마지막 신호 후 공백'이 +0.012로 보였다).", ""]
    if adopt:
        out.append("**요청(코디네이터)**: 채택 후보는 `docs/lab/sql/features.sql`의 `lab_scored`에 기본 0인 인자로 넣고"
                   f"(예: `w_{adopt[0]} := 0`), 같은 계산을 SQL로 옮긴 뒤 `score_tune.GRID`에 그 인자를 넣어 다시 고른다. "
                   "앱 기본값 반영은 사용자 확인 뒤.")
    else:
        out.append("**요청(코디네이터)**: 지금은 `lab_scored`에 넣을 특징이 없다. 공연 기록이 1년 더 쌓인 뒤"
                   "(또는 놓친 정답 '신호 없음'을 줄일 새 출처가 들어온 뒤) 이 실험을 다시 돌린다.")
    out += ["", "**읽는 법**: 기준일이 6개뿐이고 정답이 기준일마다 5~23팀이라, AUC 0.01 안쪽 차이는 우연으로도 생긴다. "
            "그래서 평균만 보지 않고 구간·기준일별 승패·상위 적중을 함께 본다. 놓친 정답 1위 원인은 '신호 없음'이라 "
            "([놓친 팀 분석](missed_analysis.md)) 특징을 다듬어도 그 팀들은 잡을 수 없다 — 이 실험은 '순위 낮음'만 겨냥한다."]
    return out


def _coarse(res: dict) -> List[str]:
    coarse = res["coarse"]
    lines = ["", f"## 4. 1차 격자 (미리 정한 {_fw(GRID)}점) 결과", "",
             "| 특징 | 평균 AUC (교차) | 차이 | 오른·내린 기준일 | 상위 20 / 50 / 100 | 기준일마다 고른 가중치 |", "|---|---|---|---|---|---|"]
    for f in sorted(coarse, key=lambda k: coarse[k]["cv_mean"] - coarse[k]["base_mean"], reverse=True):
        r = coarse[f]
        lines.append(f"| {NAMES[f]} | {_fa(r['cv_mean'])} | {r['cv_mean'] - r['base_mean']:+.3f} | {r['wins']} / {r['losses']} | "
                     f"{_hits(r['cv_hits'])} | {_fw(r['picks'].values())} |")
    lines += ["", "1차 격자에서는 채택 기준을 넘는 특징이 하나도 없었다 — 가장 작은 크기(0.5점)도 v2 순위를 크게 흔들어 손해였다."]
    return lines


def app_ties_by_recency() -> bool:
    """앱 후보 목록이 동점을 최근 신호 순으로 정렬하는가 (candidates.sql 을 읽어 확인)."""
    try:
        return "last_seen DESC" in lab_sql.read_sql("candidates.sql")
    except OSError:
        return False


def render(res: dict) -> str:
    return "\n".join(_header(res) + _results(res) + interpret(res) + _coarse(res)) + "\n"


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="점수 새 특징 실험 → docs/feature_lab.md")
    ap.add_argument("--data-dir", type=Path, default=lab_sql.DATA_DIR, help="랩 CSV 폴더 (기본 docs/lab/data)")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    res = run(args.data_dir)
    args.out.write_text(render(res), encoding="utf-8")
    print(f"✅ → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
