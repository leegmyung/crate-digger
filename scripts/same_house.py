"""'같은 집안' 점검 → docs/same_house.md

신호 출처와 정답 프로그램이 같은 주최·같은 매체(같은 집안)이면, 그 출처가 '나중에 상 받을 팀을 먼저 짚었다'는 성적이
실력이 아니라 집안 효과일 수 있다(예: 힙합엘이는 한국힙합어워즈 공동 주최). 짝마다 잰다.
- 그 출처 적중 중 같은 집안 정답 비율, 같은 집안 정답을 빼면 적중률·배수가 얼마나 줄었나
  (후보군은 출처 성적표 docs/lab/sql/source_scorecard.sql 과 같은 정의, 기준일 2024-07·2025-01·2025-07, 관찰 24개월)
- 교차 검증 AUC에 주는 영향 (score_tune.features 후보군·같은 지표, 점수 v2 고정 + 가중치 교차 검증)
규칙: '그 팀이 짝 출처(기준일 전 3년 안)에 나왔으면, 짝 정답은 그 팀의 적중으로 세지 않는다' — SAME_PROGRAM 을 출처까지 넓힌 것.
config·features.sql 은 고치지 않고 이 스크립트 안에서만 정답 라벨을 다시 매겨 흉내 낸다.

실행: .venv/bin/python scripts/same_house.py   → docs/same_house.md
"""
from __future__ import annotations

import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab_sql  # noqa: E402
import score_model as sm  # noqa: E402
import score_tune as st  # noqa: E402

OUT = lab_sql.ROOT / "docs" / "same_house.md"
CARD_CUTOFFS = ("2024-07-01", "2025-01-01", "2025-07-01")   # 출처 성적표(docs/source_roles.md)와 같은 기준일
LOOKBACK_YEARS = 3
NONE_LABEL = "규칙 없음 (모든 정답)"
LAB_LABEL = "지금 랩 데이터 (2026-11-27 적용된 규칙)"
SCORED_LABEL = "점수에 쓰는 출처의 짝만 (음악취향Y·평론 웹진)"
ALL_LABEL = "짝 4개 모두 적용"
SRC_KEY = "branch || ':' || CASE WHEN branch = '선정·지원' THEN program ELSE source END"

# 잴 수 있는 짝: 신호 출처와 정답 프로그램이 둘 다 랩 데이터에 있음
PAIRS: List[dict] = [
    {"key": "hiphople_khha", "name": "힙합엘이 ↔ 한국힙합어워즈 신인", "sources": ["큐레이션:hiphople"],
     "outcomes": ["khha_rookie"], "relation": "공동 주최 (힙합엘이·힙합플레이야)", "strength": "강함"},
    {"key": "musicy_rookie", "name": "음악취향Y 큐레이션 ↔ 음악취향Y 올해의 신인", "sources": ["큐레이션:musicy"],
     "outcomes": ["musicy_rookie"], "relation": "같은 매체가 고름", "strength": "강함"},
    {"key": "burock", "name": "부산록페 루키즈 ↔ 부산록페 본무대", "sources": ["선정·지원:burock_rookies"],
     "outcomes": ["burock_main"], "relation": "같은 페스티벌 (루키즈 1~3위는 다음 해 본무대 기회)", "strength": "강함"},
    {"key": "critics_kma", "name": "평론 웹진 ↔ 한국대중음악상", "sources": ["큐레이션:rhythmer", "큐레이션:musicy",
                                                                           "큐레이션:weiv", "큐레이션:izm"],
     "outcomes": ["kma_rookie", "kma_genre"], "relation": "선정위원에 그 웹진 필진이 참여 (2011년 명단 기준)", "strength": "약함"},
]
# 짚어 봤지만 지금은 잴 수 없는 짝 (문서에만)
UNMEASURABLE: List[Tuple[str, str]] = [
    ("IZM 큐레이션 ↔ IZM 올해의 신인", "정답 정리(2026-11-27) 뒤 IZM 올해의 신인이 정답 목록에 없음"),
    ("리드머 큐레이션 ↔ 리드머 어워드", "리드머 어워드가 정답 목록에 없음"),
    ("헬로루키 월간 ↔ 올해의 헬로루키 (EBS)", "둘 다 '정답'이라 신호 출처가 아님. 이미 OUTCOME_SAME_FAMILY 로 2단계 규칙에서 서로 못 쓰게 막혀 있음"),
    ("뮤즈온 서류 통과 ↔ 뮤즈온 최종", "SAME_PROGRAM 에 있지만 서류 통과 신호가 랩 데이터에 없음"),
    ("펜타포트 슈퍼루키 ↔ 펜타 관련 신호", "펜타포트가 여는 신호 출처가 없음"),
    ("상상마당 공연·밴드 디스커버리 ↔ 상상마당 정답", "상상마당이 주는 정답 프로그램이 없음 (같은 집안 아님)"),
]


# ---------- 계산 (순수 함수) ----------

def plus_months(d: date, months: int) -> date:
    total = d.year * 12 + d.month - 1 + months
    return date(total // 12, total % 12 + 1, min(d.day, 28))


def _excluded(program: str, team_srcs: Set[str], pairs: Sequence[dict]) -> bool:
    return any(program in p["outcomes"] and team_srcs & set(p["sources"]) for p in pairs)


def label(team_outcomes: Sequence[Tuple[str, date, float]], team_srcs: Set[str], pairs: Sequence[dict],
          cutoff: date, horizon: int) -> Tuple[int, float]:
    """기준일 뒤 관찰 기간 안 정답 → (적중 여부, 가장 높은 등급 가중치). 짝 출처에 나온 팀의 짝 정답은 뺀다."""
    end = plus_months(cutoff, horizon)
    ws = [w for prog, d, w in team_outcomes
          if cutoff <= d < end and not _excluded(prog, team_srcs, pairs)]
    return (1, max(ws)) if ws else (0, 0)


def source_card(pool: Sequence[dict], outcomes: Dict[str, list], srcs: Dict[Tuple[date, str], Set[str]],
                pair: dict, horizon: int) -> dict:
    """짝 출처에 나온 후보 팀의 적중 — 그대로 vs 짝 정답을 뺀 뒤. 기준선(후보 전체 적중률)도 같은 규칙으로 다시 잰다."""
    orig, ex, mine_o, mine_e = [], [], [], []
    for r in pool:
        c, k = r["cutoff"], r["team_key"]
        s = srcs.get((c, k), set())
        o = label(outcomes.get(k, []), s, [], c, horizon)[0]
        e = label(outcomes.get(k, []), s, [pair], c, horizon)[0]
        orig.append(o)
        ex.append(e)
        if s & set(pair["sources"]):
            mine_o.append(o)
            mine_e.append(e)
    n, hits, hits_ex = len(mine_o), sum(mine_o), sum(mine_e)
    base, base_ex = (sum(orig) / len(orig) if orig else 0.0), (sum(ex) / len(ex) if ex else 0.0)
    rate, rate_ex = (hits / n if n else 0.0), (hits_ex / n if n else 0.0)
    return {"teams": n, "hits": hits, "hits_ex": hits_ex, "rate": rate, "rate_ex": rate_ex, "base": base,
            "base_ex": base_ex, "lift": rate / base if base else None, "lift_ex": rate_ex / base_ex if base_ex else None,
            "same_house_share": (hits - hits_ex) / hits if hits else None}


# ---------- 데이터 ----------

def load_outcomes(con) -> Dict[str, list]:
    out: Dict[str, list] = defaultdict(list)
    for k, prog, d, w in con.execute("SELECT team_key, program, announced_date, weight FROM outcomes WHERE counted").fetchall():
        out[k].append((prog, d, float(w or 0)))
    return out


def load_sources(con, cutoffs: Sequence[str]) -> Dict[Tuple[date, str], Set[str]]:
    """(기준일, 팀) → 기준일 전 3년 안에 나온 출처 (모든 역할 — 출처 성적표와 같음)."""
    out: Dict[Tuple[date, str], Set[str]] = defaultdict(set)
    for c in cutoffs:
        q = (f"SELECT DISTINCT team_key, {SRC_KEY} FROM signals WHERE signal_date < DATE '{c}' "
             f"AND signal_date >= DATE '{c}' - INTERVAL {LOOKBACK_YEARS} YEAR")
        cd = date.fromisoformat(c)
        for k, s in con.execute(q).fetchall():
            out[(cd, k)].add(s)
    return out


def card_pool(con, cutoffs: Sequence[str]) -> List[dict]:
    """출처 성적표(source_scorecard.sql)의 후보군: 기준일 전 3년 안 신호, 첫 등장 3년 이내, 유명 팀·이미 정답 팀 제외."""
    out = []
    for c in cutoffs:
        q = f"""SELECT DISTINCT t.team_key FROM signals s JOIN teams t USING (team_key)
                WHERE s.signal_date < DATE '{c}' AND s.signal_date >= DATE '{c}' - INTERVAL {LOOKBACK_YEARS} YEAR
                  AND t.first_seen >= DATE '{c}' - INTERVAL {LOOKBACK_YEARS} YEAR
                  AND (DATE '{c}' < fame_known_from() OR t.profile_status <> 'famous')
                  AND NOT EXISTS (SELECT 1 FROM outcomes b WHERE b.team_key = t.team_key AND b.counted
                                  AND b.announced_date < DATE '{c}')"""
        cd = date.fromisoformat(c)
        out += [{"cutoff": cd, "team_key": k} for (k,) in con.execute(q).fetchall()]
    return out


def relabel(data: Dict[str, List[dict]], outcomes: Dict[str, list], srcs: Dict[Tuple[date, str], Set[str]],
            pairs: Sequence[dict]) -> Dict[str, List[dict]]:
    out = {}
    for c, rows in data.items():
        cd = date.fromisoformat(c)
        new = []
        for r in rows:
            hit, w = label(outcomes.get(r["team_key"], []), srcs.get((cd, r["team_key"]), set()), pairs, cd, st.HORIZON_MONTHS)
            new.append({**r, "is_hit": hit, "hit_weight": w})
        out[c] = new
    return out


def auc_summary(data: Dict[str, List[dict]]) -> dict:
    """점수 v2 고정의 평균 AUC·상위50 적중 합, 그리고 가중치 교차 검증(뺀 기준일 안 보고 고름) 평균 AUC."""
    cutoffs = list(st.CUTOFFS)
    w2 = sm.v2_weights()
    v2 = {c: sm.metrics(data[c], sm.hand_scores(data[c], w2)) for c in cutoffs}
    grid, table = sm.grid_table(data)
    cv = []
    for held in cutoffs:
        w = grid[sm.pick_best(table, [c for c in cutoffs if c != held])]
        a = sm.metrics(data[held], sm.hand_scores(data[held], w))["auc"]
        if a is not None:
            cv.append(a)
    v2a = [m["auc"] for m in v2.values() if m["auc"] is not None]
    return {"v2_auc": float(np.mean(v2a)), "hits50": sum(m["hits50"] for m in v2.values()),
            "pos": sum(m["pos"] for m in v2.values()), "cv_auc": float(np.mean(cv))}


# ---------- 문서 ----------

def _p(v: Optional[float]) -> str:
    return "—" if v is None else f"{v * 100:.2f}%"


def _x(v: Optional[float]) -> str:
    return "—" if v is None else f"{v:.1f}"


def build(con) -> List[str]:
    outcomes = load_outcomes(con)
    roles = dict(con.execute(f"SELECT {SRC_KEY}, ANY_VALUE(role) FROM signals GROUP BY 1").fetchall())
    pool = card_pool(con, CARD_CUTOFFS)
    csrcs = load_sources(con, CARD_CUTOFFS)
    cards = {p["key"]: source_card(pool, outcomes, csrcs, p, st.HORIZON_MONTHS) for p in PAIRS}

    data = {c: st.features(con, c) for c in st.CUTOFFS}
    asrcs = load_sources(con, st.CUTOFFS)
    scored = [p for p in PAIRS if any(roles.get(x) in ("discovery", "context") for x in p["sources"])]
    # 같은 집안 규칙은 2026-11-27 랩 데이터에 적용됐다(outcomes.csv same_house_scored) → 비교 기준은 '규칙 없음(모든 정답)'으로 다시 매긴다
    applied = [p for p in scored if p["strength"] == "강함"]   # 랩에 적용된 것: 강한 짝 중 점수에 쓰는 출처의 짝
    rel_applied = relabel(data, outcomes, asrcs, applied)
    rows_all = [(a, b) for c in st.CUTOFFS for a, b in zip(data[c], rel_applied[c])]
    n_diff = sum(1 for a, b in rows_all if a["is_hit"] != b["is_hit"])
    variants = ([(NONE_LABEL, [])] + [(p["name"], [p]) for p in PAIRS]
                + [(SCORED_LABEL, scored), (ALL_LABEL, PAIRS), (LAB_LABEL, None)])
    aucs = [(name, auc_summary(data if prs is None else relabel(data, outcomes, asrcs, prs))) for name, prs in variants]

    lines = ["# 같은 집안 점검 — 신호 출처와 정답 프로그램이 같은 주최일 때", "",
             "_자동 생성: `.venv/bin/python scripts/same_house.py`_", "",
             "출처가 '나중에 상 받을 팀을 먼저 짚었다'는 성적이, 실은 **같은 주최·같은 매체가 신호와 정답을 둘 다 만든** 효과일 수 있다. "
             "힙합엘이가 공동 주최하는 한국힙합어워즈가 첫 사례였다([힙합·R&B 출처 조사](research_2026-11-27_hiphop_rnb_sources.md) 5절). "
             "이 문서는 그런 짝을 전부 찾아, 짝 정답을 빼면 성적이 얼마나 바뀌는지 잰다.", "",
             "**잰 방법**: 그 팀이 짝 출처에 (기준일 전 3년 안에) 나왔으면, 짝 정답은 그 팀의 적중으로 세지 않는다 — 선정 프로그램의 앞 단계와 "
             "다음 단계를 잇는 기존 규칙(`SAME_PROGRAM`)을 출처까지 넓힌 것. 설정·계산식(config, features.sql)은 고치지 않고 이 스크립트 안에서만 "
             "정답 라벨을 다시 매겼다. **이 규칙은 2026-11-27 랩 데이터에 적용됐다**(`outcomes.csv`의 `same_house_scored`, 점수에 쓰는 출처의 짝) — "
             f"점수 검증에 적용된 것은 강한 짝 중 점수에 쓰는 출처의 짝({', '.join(p['name'] for p in applied)})이고, 평론 웹진↔한대음은 표시만 한다. "
             f"그래서 아래 비교의 기준은 '규칙 없음(모든 정답)'이고, 이 스크립트로 같은 짝을 적용한 라벨은 랩 라벨과 {len(rows_all):,}행 중 "
             f"{len(rows_all) - n_diff:,}행에서 같다" + (f"(다른 {n_diff}행은 짝 출처를 보는 기간 차이 — 랩은 정답 전 아무 때나, 이 스크립트는 기준일 전 3년)." if n_diff else "."), "",
             "## 1. 짝 목록", "",
             "| 짝 | 신호 출처 (지금 역할) | 정답 프로그램 | 관계 | 강도 |", "|---|---|---|---|---|"]
    for p in PAIRS:
        srcs = ", ".join(f"{s} ({roles.get(s, '?')})" for s in p["sources"])
        lines.append(f"| {p['name']} | {srcs} | {', '.join(p['outcomes'])} | {p['relation']} | {p['strength']} |")
    lines += ["", "**짚어 봤지만 지금은 잴 수 없는 짝**", ""] + [f"- {a}: {b}" for a, b in UNMEASURABLE]
    lines += ["", f"## 2. 출처 성적표 — 짝 정답을 빼면 (기준일 {', '.join(CARD_CUTOFFS)} 합산, 관찰 {st.HORIZON_MONTHS}개월)", "",
              "후보군은 [출처 성적표](lab/sql/source_scorecard.sql)와 같다(모든 역할의 출처, 첫 등장 3년 이내, 유명 팀·이미 정답 팀 제외). "
              "'같은 집안 비율' = 그 출처 적중 중 짝 정답 때문에만 적중이던 비율. 기준선도 같은 규칙으로 다시 잰다.", "",
              "| 짝 | 출처에 나온 후보 | 적중 (그대로 → 짝 정답 빼고) | 같은 집안 비율 | 적중률 그대로 → 빼고 | 배수 그대로 → 빼고 |",
              "|---|---|---|---|---|---|"]
    for p in PAIRS:
        c = cards[p["key"]]
        lines.append(f"| {p['name']} | {c['teams']:,} | {c['hits']} → **{c['hits_ex']}** | {_p(c['same_house_share'])} | "
                     f"{_p(c['rate'])} → {_p(c['rate_ex'])} | {_x(c['lift'])} → **{_x(c['lift_ex'])}** |")
    base = next(iter(cards.values()))
    lines += ["", f"(기준선 그대로 {_p(base['base'])}. 짝마다 규칙을 적용한 기준선은 그 짝 출처 팀만 바뀌어 거의 같다.)", "",
              f"## 3. 교차 검증 AUC에 주는 영향 (기준일 {len(st.CUTOFFS)}개, 점수 후보군)", "",
              "점수 v2 고정과, 가중치를 뺀 기준일을 안 보고 고르는 교차 검증 평균 AUC(정답 등급 가중). 짝 정답을 빼면 정답 수도 줄어든다.", "",
              "| 정답 판정 | 정답 수 (6개 합) | v2 평균 AUC | v2 상위50 적중 합 | 교차 검증 평균 AUC |", "|---|---|---|---|---|"]
    for name, a in aucs:
        lines.append(f"| {name} | {a['pos']} | {a['v2_auc']:.3f} | {a['hits50']} | {a['cv_auc']:.3f} |")
    lines += [""] + interpret(cards, aucs, roles)
    return lines


def interpret(cards: Dict[str, dict], aucs: List[Tuple[str, dict]], roles: Dict[str, str]) -> List[str]:
    base = aucs[0][1]
    lines = ["## 4. 해석", ""]
    for p in PAIRS:
        c = cards[p["key"]]
        share = c["same_house_share"]
        used = [s for s in p["sources"] if roles.get(s) in ("discovery", "context")]
        auc = next(a for n, a in aucs if n == p["name"])
        if not c["teams"]:
            lines.append(f"- **{p['name']}**: 이 기준일들에서 짝 출처에 나온 후보가 없어 잴 수 없음.")
            continue
        tone = ("**대부분 집안 효과**" if share is not None and share >= 0.5 else
                "일부 집안 효과" if share else "집안 효과 거의 없음")
        lines.append(f"- **{p['name']}**: 적중 {c['hits']}팀 중 {c['hits'] - c['hits_ex']}팀이 짝 정답 때문 → {tone}. "
                     f"배수 {_x(c['lift'])} → {_x(c['lift_ex'])}. "
                     + (f"점수에 쓰는 출처라 교차 검증 AUC가 {base['cv_auc']:.3f} → {auc['cv_auc']:.3f}, v2 {base['v2_auc']:.3f} → {auc['v2_auc']:.3f}."
                        if used else "점수에 안 쓰는 출처(검증 대기)라 점수 AUC 변화는 정답 라벨 변화 몫뿐이다."))
    scv = next(a for n, a in aucs if n == SCORED_LABEL)
    allv = next(a for n, a in aucs if n == ALL_LABEL)
    up = scv["cv_auc"] > base["cv_auc"]
    lines += [f"- **점수 숫자는 집안 효과로 부풀지 않았다.** 점수에 쓰는 출처의 짝만 적용하면 교차 검증 AUC {base['cv_auc']:.3f} → {scv['cv_auc']:.3f}, "
              f"v2 {base['v2_auc']:.3f} → {scv['v2_auc']:.3f}, 정답 {base['pos']} → {scv['pos']}행"
              + (" — 오히려 **올라간다**. 빠지는 짝 정답 팀들이 점수로는 원래 평균보다 아래쪽에 있었다는 뜻이다. "
                 "정답을 빼서 AUC가 오르는 것은 '맞히기 어려운 정답을 뺀 효과'이지 점수가 좋아진 것이 아니므로, 규칙을 적용해도 성능 개선으로 발표하면 안 된다."
                 if up else " — 내려간다. 지금 점수 숫자의 일부가 집안 효과였다는 뜻이다."),
              f"- 짝 4개 모두(점수에 안 쓰는 힙합엘이·부산록페 루키즈 포함) 적용하면 교차 검증 AUC {allv['cv_auc']:.3f}, 정답 {allv['pos']}행. "
              "점수에 안 쓰는 출처의 짝 정답까지 빼는 것은 점수 평가에는 맞지 않는다(그 팀이 실제로 받은 상이고, 점수는 그 출처를 안 봤으므로). "
              "**점수 평가에는 '점수에 쓰는 출처의 짝'만, 출처 성적표에는 모든 짝을** 적용하는 것을 제안한다.",
              "- 부산록페 루키즈는 기록이 짧아(2025년 루키즈) 이 기준일들에서는 후보가 없다 — 짝은 등록해 두고 나중에 다시 잰다.", "",
              "## 5. 규칙 제안 (적용은 사용자 확인 뒤)", "",
              "1. **`config/same_house.json`에 짝 목록을 둔다** — `{\"sources\": [\"큐레이션:hiphople\"], \"outcomes\": [\"khha_rookie\"], "
              "\"relation\": \"공동 주최\", \"evidence\": \"…\"}`. 지금 `csv_schema.SAME_PROGRAM`(선정 프로그램 앞 단계 → 같은 프로그램 정답)을 "
              "출처 단위로 넓힌 것이다.",
              "2. **적용 범위**: 그 팀이 짝 출처에 나왔으면 짝 정답은 그 팀의 적중으로 세지 않는다. 출처 성적표와 출처 역할 판정에는 모든 짝을, "
              "점수 백테스트·교차 검증에는 점수에 쓰는 출처의 짝만 적용한다(위 4절). 숫자가 올라가도 '개선'이 아니라 '정답 정의 변경'으로 적는다.",
              "3. **강한 짝부터**: 공동 주최·같은 매체(힙합엘이↔한국힙합어워즈, 음악취향Y↔음악취향Y 올해의 신인, 부산록페 루키즈↔본무대)는 바로 적용을 권한다. "
              "평론 웹진↔한대음은 선정위원 명단이 해마다 바뀌고 근거가 2011년 명단이라 **표시만** 하고(성적표에 '짝 정답 빼면' 열을 같이 보여 주기), "
              "최신 명단을 확인한 뒤 정한다.",
              "4. **새 출처·새 정답을 넣을 때 확인 항목에 추가**: '이 출처를 만든 곳이 정답 프로그램도 여는가?' — 출처 역할 분류([source_roles.md](source_roles.md))의 체크리스트로.",
              "5. 부산록페 루키즈 짝은 이미 `SAME_PROGRAM`에 있지만, 랩 계산식(features.sql)은 이 규칙을 쓰지 않는다. 규칙을 넣을 때 랩 쪽에도 함께 반영해야 한다.", "",
              "## 근거", "",
              "- 한국힙합어워즈 공동 주최(힙합플레이야·힙합엘이): [스포츠경향 — 2024 한국힙합어워즈 후보 발표](https://sports.khan.co.kr/article/202401152305003)",
              "- 한국대중음악상 선정위원에 웹진 필진(리드머·음악취향Y·weiv 등) 참여 — 2011년 제8회 64인 명단: "
              "[뉴스와이어](https://www.newswire.co.kr/newsRead.php?no=523250). 최신 명단은 확인하지 못함(공식 사이트에서 확인 필요).",
              "- 부산록페 루키즈 → 다음 해 본무대: `scripts/csv_schema.py` SAME_PROGRAM 주석", ""]
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
