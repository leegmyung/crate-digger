"""비슷한 팀(docs/lab/sql/similar_teams.sql) 성적 검증 — 유사도가 높은 팀끼리 실제로 '같은 길'을 갔나.

    .venv/bin/python scripts/similar_validate.py [--json 결과.json]

과거 기준일 6개마다 (그날까지의 신호만으로) 후보 풀의 팀마다 비슷한 팀을 계산하고, 그 뒤 18개월을 본다.
정답(outcomes)은 여기 '채점'에만 쓰고 유사도 계산식에는 들어가지 않는다 (similar_teams.sql 은 정답 표를 읽지 않음).

재는 것 (가중치 묶음 WEIGHTS 마다):
  A. 같이 뜬 비율 — X 가 관찰 기간 안에 정답을 받았을 때, X 의 비슷한 팀 상위 5(풀 안)도 정답을 받은 비율 ÷ 풀 전체 정답 비율(=lift).
     같은 계산을 정답이 아닌 신호 기반 '단계 상승' 두 가지로도 한다: 새 갈래(기준일 전에 없던 갈래의 신호를 받음 — 발굴 단계를 올리는 일),
     선정·지원 신호를 새로 받음(드물어 참고만). 무작위 이웃 5팀이 기준선(≈1).
  B. 먼저 뜬 비슷한 팀 — 기준일 전에 이미 정답을 받은 팀과의 최고 유사도가 X 의 다음 정답을 맞히나 (AUC, 40% 이상 있음/없음 적중률,
     점수 상위 100 안에서도 차이가 나나). 앱에 '비슷한 팀 중 먼저 뜬 팀' 근거 문장을 넣을지 판단용.
  C. 공정성 점검 (2026-11-28 첫 실행에서 찾은 새는 곳):
     - 확인된 장르(멜론 프로필·보도)는 주로 '나중에 상 받은 팀'에 대해 모았다 → 장르가 있다는 것 자체가 정답 신호.
       그래서 '확인된 장르가 있는 팀끼리만' 다시 잰다(hit_conf_genre).
     - 2025 부산록페 본무대(burock_main)는 부산 지역 팀을 많이 뽑았다 → 부산 클럽에서 같이 선 팀이 같이 뽑힌 한 번의 일.
       그래서 이 정답을 빼고도 잰다(hit_no_burock).
결과 해석: docs/similar_teams.md
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab_sql  # noqa: E402
from score_tune import auc  # noqa: E402

CUTOFFS = ("2024-01-01", "2024-04-01", "2024-07-01", "2024-10-01", "2025-01-01", "2025-04-01")
HORIZON_MONTHS = 18            # 마지막 기준일 2025-04-01 + 18개월 = 2026-10-01 < 데이터 끝(2026-11)
TOP_K = 5
PRIOR_SIM_THRESHOLD = 0.40     # '먼저 뜬 비슷한 팀이 있다' = 그 팀과 유사도 40% 이상
TOP_SCORE_N = 100              # 점수 상위 몇 팀 안에서도 차이가 나나
SEED = 20261128
FAIRNESS_EXCLUDE_PROGRAMS = ("burock_main",)   # 지역 라인업 한 번이 결과를 끌고 가는 정답 — 빼고도 잰다
ALL_ROWS = "100000"            # similar_teams.sql 행 수 제한을 사실상 없앰 (가중치를 바꿔 다시 줄 세우려고)

WEIGHTS: Dict[str, Dict[str, float]] = {
    "기본": {"stage": 0.40, "source": 0.25, "genre": 0.20, "level": 0.15},
    "같은 무대만": {"stage": 1.0, "source": 0.0, "genre": 0.0, "level": 0.0},
    "같은 출처만": {"stage": 0.0, "source": 1.0, "genre": 0.0, "level": 0.0},
    "같은 장르만": {"stage": 0.0, "source": 0.0, "genre": 1.0, "level": 0.0},
    "체급만": {"stage": 0.0, "source": 0.0, "genre": 0.0, "level": 1.0},
    "장르 빼기": {"stage": 0.50, "source": 0.30, "genre": 0.0, "level": 0.20},
    "무대 많이": {"stage": 0.60, "source": 0.20, "genre": 0.10, "level": 0.10},
    "출처 많이": {"stage": 0.25, "source": 0.45, "genre": 0.15, "level": 0.15},
    "고르게": {"stage": 0.25, "source": 0.25, "genre": 0.25, "level": 0.25},
}


# ---------- 순수 함수 (tests/test_similar_validate.py) ----------

def weighted_sim(row: dict, w: Dict[str, float]) -> float:
    return (w["stage"] * float(row.get("f_stage") or 0) + w["source"] * float(row.get("f_source") or 0)
            + w["genre"] * (1.0 if row.get("same_genre") else 0.0) + w["level"] * float(row.get("f_level") or 0))


def top_neighbors(rows: Iterable[dict], w: Dict[str, float], k: int, allowed: Set[str]) -> List[str]:
    """풀 안(allowed) 팀만, 가중 유사도 높은 순 k팀 (0점은 '비슷하지 않음'이라 뺌, 동점은 키 순)."""
    scored = [(weighted_sim(r, w), r["related_team"]) for r in rows if r["related_team"] in allowed]
    scored = [(s, key) for s, key in scored if s > 0]
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [key for _, key in scored[:k]]


def prior_winner_sim(rows: Iterable[dict], w: Dict[str, float], winners: Set[str]) -> float:
    """기준일 전에 정답을 받은 팀과의 최고 유사도 (없으면 0)."""
    return max((weighted_sim(r, w) for r in rows if r["related_team"] in winners), default=0.0)


def conditional_rate(pairs: Sequence[Tuple[str, str]], labels: Dict[str, int], base_keys: Sequence[str]) -> dict:
    """X 가 맞힌 쌍 중 Y 도 맞힌 비율, 풀 전체 비율(base), 그 비(lift)."""
    hit_pairs = [(x, y) for x, y in pairs if labels.get(x)]
    both = sum(1 for _, y in hit_pairs if labels.get(y))
    base = (sum(1 for k in base_keys if labels.get(k)) / len(base_keys)) if base_keys else None
    rate = both / len(hit_pairs) if hit_pairs else None
    lift = (rate / base) if (rate is not None and base) else None
    return {"n": len(hit_pairs), "both": both, "rate": rate, "base": base, "lift": lift}


def wilson(k: int, n: int, z: float = 1.96) -> Tuple[Optional[float], Optional[float]]:
    """비율의 95% 구간 (윌슨). 표본이 작을 때도 0~1 안에 머문다."""
    if n == 0:
        return (None, None)
    p = k / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, mid - half), min(1.0, mid + half))


def random_pairs(keys: Sequence[str], k: int, seed: int) -> List[Tuple[str, str]]:
    """팀마다 자기 말고 무작위 k팀 (기준선)."""
    rng = random.Random(seed)
    keys = list(keys)
    out = []
    for x in keys:
        others = [y for y in keys if y != x]
        for y in rng.sample(others, min(k, len(others))):
            out.append((x, y))
    return out


def branch_up(before: Dict[str, Set[str]], after: Dict[str, Set[str]], keys: Sequence[str]) -> Dict[str, int]:
    """기준일 전에 없던 갈래의 신호를 관찰 기간에 받았으면 1 (= 신호 갈래가 늘어남 → 발굴 단계가 오르는 일)."""
    return {k: int(bool(after.get(k, set()) - before.get(k, set()))) for k in keys}


def split_rate(feature: Sequence[float], labels: Sequence[int], threshold: float) -> dict:
    """특징이 기준 이상인 팀 / 아닌 팀의 적중률."""
    w = [y for f, y in zip(feature, labels) if f >= threshold]
    wo = [y for f, y in zip(feature, labels) if f < threshold]
    return {"with_n": len(w), "with_rate": (sum(w) / len(w)) if w else None,
            "without_n": len(wo), "without_rate": (sum(wo) / len(wo)) if wo else None}


# ---------- 데이터 (DuckDB) ----------

def pool_rows(con, cutoff: str) -> List[dict]:
    d = lab_sql.DEFAULTS
    q = (f"SELECT team_key, score, is_hit, had_outcome FROM lab_scored(DATE '{cutoff}', {d['lookback_years']}, "
         f"{d['newcomer_years']}, {d['exclude_famous']}, {d['outcome_tier']}, {HORIZON_MONTHS}, {d['genre']}, {d['branches']}, "
         f"{d['w_branch']}, {d['w_stage']}, {d['w_peer']}, {d['w_dmz']}, {d['w_gigs']}, {d['w_outlets']}, {d['outlet_cap']}, "
         f"w_recent := {d['w_recent']}, w_venues := {d['w_venues']}, w_winner := {d['w_winner']}, w_context := {d['w_context']})")
    cur = con.execute(q)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def selection_teams(con, cutoff: str) -> Set[str]:
    """관찰 기간 안에 선정·지원 신호를 새로 받은 팀 (정답 표가 아니라 신호 — '단계 상승' 쪽 채점)."""
    q = (f"SELECT DISTINCT team_key FROM signals WHERE branch = '선정·지원' AND COALESCE(role, '') <> 'excluded' "
         f"AND signal_date > DATE '{cutoff}' AND signal_date <= DATE '{cutoff}' + INTERVAL {HORIZON_MONTHS} MONTH")
    return {r[0] for r in con.execute(q).fetchall()}


def branch_sets(con, cutoff: str) -> Tuple[Dict[str, Set[str]], Dict[str, Set[str]]]:
    """팀별 갈래 묶음: 기준일까지 / 관찰 기간 안. 제외(excluded) 역할 신호는 안 셈."""
    q = (f"SELECT team_key, branch, signal_date <= DATE '{cutoff}' AS before FROM signals "
         f"WHERE COALESCE(role, '') <> 'excluded' AND signal_date <= DATE '{cutoff}' + INTERVAL {HORIZON_MONTHS} MONTH "
         f"GROUP BY 1, 2, 3")
    before: Dict[str, Set[str]] = {}
    after: Dict[str, Set[str]] = {}
    for team, branch, is_before in con.execute(q).fetchall():
        (before if is_before else after).setdefault(team, set()).add(branch)
    return before, after


def hits_excluding(con, cutoff: str, programs: Sequence[str]) -> Set[str]:
    """관찰 기간 안 정답(counted) 팀 — 주어진 프로그램 정답은 뺀다."""
    excl = ", ".join("'" + p.replace("'", "''") + "'" for p in programs) or "''"
    q = (f"SELECT DISTINCT team_key FROM outcomes WHERE counted AND program NOT IN ({excl}) "
         f"AND announced_date > DATE '{cutoff}' AND announced_date <= DATE '{cutoff}' + INTERVAL {HORIZON_MONTHS} MONTH")
    return {r[0] for r in con.execute(q).fetchall()}


def confirmed_genre_teams(con) -> Set[str]:
    """확인된 장르(멜론 프로필·보도)가 있는 팀 — similar_teams.sql 의 '같은 장르' 규칙과 같다."""
    q = ("SELECT team_key FROM teams WHERE COALESCE(primary_genre, '') NOT IN ('', '미분류') "
         "AND COALESCE(genre_confidence, '') IN ('', 'profile', 'press')")
    return {r[0] for r in con.execute(q).fetchall()}


def prior_winners(con, cutoff: str) -> Set[str]:
    q = f"SELECT DISTINCT team_key FROM outcomes WHERE counted AND announced_date <= DATE '{cutoff}'"
    return {r[0] for r in con.execute(q).fetchall()}


def neighbor_rows(con, sql: str, team: str, cutoff: str) -> List[dict]:
    filled = lab_sql.fill(sql, team_key="'" + team.replace("'", "''") + "'", as_of=f"DATE '{cutoff}'", sim_limit=ALL_ROWS)
    cur = con.execute(filled)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def gather(con) -> List[dict]:
    """기준일마다: 풀(정답 전 팀)·채점표·팀별 이웃 원재료."""
    sql = lab_sql.read_sql("similar_teams.sql")
    conf = confirmed_genre_teams(con)
    out = []
    for c in CUTOFFS:
        pool = [r for r in pool_rows(con, c) if not r["had_outcome"]]
        keys = [r["team_key"] for r in pool]
        out.append({
            "cutoff": c,
            "keys": keys,
            "hit": {r["team_key"]: int(bool(r["is_hit"])) for r in pool},
            "score": {r["team_key"]: float(r["score"] or 0) for r in pool},
            "sel": {k: int(k in sel) for sel in [selection_teams(con, c)] for k in keys},
            "up": branch_up(*branch_sets(con, c), keys),
            "hit_nob": {k: int(k in nob) for nob in [hits_excluding(con, c, FAIRNESS_EXCLUDE_PROGRAMS)] for k in keys},
            "conf": [k for k in keys if k in conf],
            "winners": prior_winners(con, c),
            "rows": {k: neighbor_rows(con, sql, k, c) for k in keys},
        })
        print(f"  {c}: 풀 {len(keys)}팀 · 정답 {sum(out[-1]['hit'].values())} · 새 갈래 {sum(out[-1]['up'].values())} "
              f"· 선정 새로 {sum(out[-1]['sel'].values())}", file=sys.stderr)
    return out


def _pooled(per_cut: List[dict]) -> dict:
    """기준일별 conditional_rate 를 합친다: lift = 같이 맞힌 수 ÷ 기대 수(기준일별 base × 쌍 수)."""
    n = sum(r["n"] for r in per_cut)
    both = sum(r["both"] for r in per_cut)
    expected = sum((r["base"] or 0) * r["n"] for r in per_cut)
    lo, hi = wilson(both, n)
    return {"n": n, "both": both, "rate": both / n if n else None, "expected_rate": expected / n if n else None,
            "lift": (both / expected) if expected else None, "rate_lo": lo, "rate_hi": hi}


def evaluate(data: List[dict], w: Dict[str, float]) -> dict:
    hit_parts, up_parts, sel_parts, feats, labels, top_feats, top_labels = [], [], [], [], [], [], []
    nob_parts, conf_parts, nob_labels, top_nob = [], [], [], []
    for d in data:
        allowed = set(d["keys"])
        pairs = [(x, y) for x in d["keys"] for y in top_neighbors(d["rows"][x], w, TOP_K, allowed)]
        hit_parts.append(conditional_rate(pairs, d["hit"], d["keys"]))
        up_parts.append(conditional_rate(pairs, d["up"], d["keys"]))
        sel_parts.append(conditional_rate(pairs, d["sel"], d["keys"]))
        nob_parts.append(conditional_rate(pairs, d["hit_nob"], d["keys"]))
        cset = set(d["conf"])
        cpairs = [(x, y) for x in d["conf"] for y in top_neighbors(d["rows"][x], w, TOP_K, cset)]
        conf_parts.append(conditional_rate(cpairs, d["hit"], d["conf"]))
        f = {x: prior_winner_sim(d["rows"][x], w, d["winners"]) for x in d["keys"]}
        feats += [f[x] for x in d["keys"]]
        labels += [d["hit"][x] for x in d["keys"]]
        nob_labels += [d["hit_nob"][x] for x in d["keys"]]
        top = sorted(d["keys"], key=lambda k: -d["score"][k])[:TOP_SCORE_N]
        top_feats += [f[x] for x in top]
        top_labels += [d["hit"][x] for x in top]
        top_nob += [d["hit_nob"][x] for x in top]
    return {
        "hit": _pooled(hit_parts),
        "up": _pooled(up_parts),
        "sel": _pooled(sel_parts),
        "prior_auc": auc(feats, labels),
        "prior_split": split_rate(feats, labels, PRIOR_SIM_THRESHOLD),
        "prior_split_top": split_rate(top_feats, top_labels, PRIOR_SIM_THRESHOLD),
        "pairs_hit_n": sum(p["n"] for p in hit_parts),
        "hit_no_burock": _pooled(nob_parts),
        "hit_conf_genre": _pooled(conf_parts),
        "prior_auc_no_burock": auc(feats, nob_labels),
        "prior_split_top_no_burock": split_rate(top_feats, top_nob, PRIOR_SIM_THRESHOLD),
    }


def random_baseline(data: List[dict]) -> dict:
    hit_parts, up_parts, sel_parts, nob_parts = [], [], [], []
    for i, d in enumerate(data):
        pairs = random_pairs(d["keys"], TOP_K, SEED + i)
        nob_parts.append(conditional_rate(pairs, d["hit_nob"], d["keys"]))
        hit_parts.append(conditional_rate(pairs, d["hit"], d["keys"]))
        up_parts.append(conditional_rate(pairs, d["up"], d["keys"]))
        sel_parts.append(conditional_rate(pairs, d["sel"], d["keys"]))
    return {"hit": _pooled(hit_parts), "up": _pooled(up_parts), "sel": _pooled(sel_parts), "hit_no_burock": _pooled(nob_parts)}


def per_cutoff(data: List[dict], w: Dict[str, float]) -> List[dict]:
    out = []
    for d in data:
        allowed = set(d["keys"])
        pairs = [(x, y) for x in d["keys"] for y in top_neighbors(d["rows"][x], w, TOP_K, allowed)]
        out.append({"cutoff": d["cutoff"], "pool": len(d["keys"]), "hits": sum(d["hit"].values()),
                    "hit": conditional_rate(pairs, d["hit"], d["keys"]), "up": conditional_rate(pairs, d["up"], d["keys"]),
                    "sel": conditional_rate(pairs, d["sel"], d["keys"])})
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="비슷한 팀 성적 검증")
    ap.add_argument("--json", help="결과를 JSON 으로 저장할 경로")
    args = ap.parse_args(argv)
    con = lab_sql.connect()
    data = gather(con)
    result = {
        "cutoffs": list(CUTOFFS), "horizon_months": HORIZON_MONTHS, "top_k": TOP_K,
        "random": random_baseline(data),
        "weights": {name: {"w": w, **evaluate(data, w)} for name, w in WEIGHTS.items()},
        "per_cutoff_base": per_cutoff(data, WEIGHTS["기본"]),
    }
    text = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    if args.json:
        Path(args.json).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
