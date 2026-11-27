"""도시 층 — 도시별 프로필·팀별 활동 도시·지방 → 서울 흐름 → docs/lab/data/city_profiles.json, team_cities.csv, docs/city_profiles.md

Chartmetric '도시(City)' 페이지처럼, 공연장을 도시로 묶어 본다(공연장 → 도시는 config/venues_kr.json).
- 도시마다: 공연장 수(마스터 목록 / 그중 우리 데이터에 있음 / 공연 기록이 있는 우리 공연장), 공연 날짜 수·월별,
  최근 1년 공연한 팀 수, 그 도시가 첫 무대였던 팀 수, 그 도시 공연 뒤 정답 받은 팀('정답 전에 섰던'만),
  지금 후보 상위 팀, 대표 공연장.
- 팀마다(team_cities.csv): 활동 도시(공연 날짜 가장 많은 도시)·도시 수·첫 무대 도시·서울 첫 공연·서울까지 개월.
- 지방 → 서울 흐름이 정답과 관련 있는지: 점수 v2에 특징으로 하나씩 더해 기준일 6개 교차 검증
  (feature_lab 과 같은 방법·채택 기준. 점수·계산식은 바꾸지 않음 — 효과 있으면 '요청'만).

시점: 기준 날짜(meta.json data_end) 뒤 공연은 '예정'으로만 센다. 교차 검증 특징은 기준일 전 3년 발굴 출처 공연만.
읽기만: 랩 CSV·config. 쓰기: 위 세 파일 (21~23시엔 docs/lab/data 에 쓰지 말 것 — --out-dir 로 다른 곳에).

실행: .venv/bin/python scripts/city_profiles.py [--out-dir 폴더] [--no-eval]
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab_sql  # noqa: E402
import venue_profiles as vp  # noqa: E402
import venues_kr as vk  # noqa: E402

UNKNOWN_CITY = vk.UNKNOWN_CITY
SEOUL = "서울"
DOC = lab_sql.ROOT / "docs" / "city_profiles.md"
YEAR = timedelta(days=365)
LOOKBACK_YEARS = 3
TOP_N = 5
TOP_WINNERS = 10
TEAM_CITY_FIELDS = ("team_key", "home_city", "cities", "first_city", "first_date", "seoul_first_date",
                    "months_to_seoul", "nights")
FEATURES: Tuple[Tuple[str, str, str], ...] = (
    ("came_to_seoul", "지방에서 시작해 서울 진출", "기준일 전 첫 무대 도시가 서울이 아니고, 기준일 전에 서울 공연이 있음 (1/0)"),
    ("non_seoul_base", "지방 활동 팀", "기준일 전 공연 날짜가 가장 많은 도시가 서울이 아님 (1/0)"),
    ("city_count", "공연 도시 수", "기준일 전 3년 공연한 서로 다른 도시 수 − 1"),
    ("recent_seoul_arrival", "최근 1년 서울 진출", "지방에서 시작했고 서울 첫 공연이 기준일 전 1년 안 (1/0)"),
)
NAMES = {k: n for k, n, _ in FEATURES}

Gig = Tuple[str, date, str]


# ---------- 공연장 → 도시 ----------

def city_for(venue: str, city_of: Dict[str, str]) -> str:
    return city_of.get(venue) or UNKNOWN_CITY


def load_city_map(venue_names: Iterable[str]) -> Tuple[Dict[str, str], List[dict]]:
    """우리 공연장 대표 이름 → 도시 (venues_kr 와 같은 짝짓기: 마스터 목록 → 공연 원본 주소). (도시 표, 마스터 목록)."""
    master = (vk.load_json(vk.CONFIG, {}) or {}).get("venues", [])
    names = sorted(set(venue_names))
    match = vk.match_our_venues(master, names)
    city = vk.venue_city({n: {} for n in names}, match, master, vk.our_addresses())
    return {n: c for n, c in city.items() if c and c != UNKNOWN_CITY}, master


# ---------- 팀별 활동 도시 ----------

def _months(a: date, b: date) -> int:
    return (b.year - a.year) * 12 + (b.month - a.month)


def team_cities(gigs: Iterable[Gig], city_of: Dict[str, str], as_of: date) -> List[dict]:
    """팀마다 활동 도시·도시 수·첫 무대 도시·서울 첫 공연·서울까지 개월 (기준 날짜까지 공연, 도시 모름은 셈에서 뺌)."""
    nights: Dict[str, set] = defaultdict(set)
    for t, d, v in gigs:
        if d <= as_of:
            nights[t].add((d, v))
    rows = []
    for t in sorted(nights):
        known = sorted((d, city_for(v, city_of)) for d, v in nights[t] if city_for(v, city_of) != UNKNOWN_CITY)
        per_city = Counter(c for _, c in known)
        first_d, first_c = known[0] if known else (None, "")
        seoul = next((d for d, c in known if c == SEOUL), None)
        home = min(per_city, key=lambda c: (-per_city[c], c)) if per_city else ""
        rows.append({"team_key": t, "home_city": home, "cities": len(per_city), "first_city": first_c,
                     "first_date": first_d.isoformat() if first_d else "",
                     "seoul_first_date": seoul.isoformat() if seoul else "",
                     "months_to_seoul": _months(first_d, seoul) if seoul and first_c and first_c != SEOUL else "",
                     "nights": len(nights[t])})
    return rows


def write_team_cities(rows: Sequence[dict], path: Path) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=TEAM_CITY_FIELDS)
        w.writeheader()
        w.writerows(rows)


def seoul_flow(rows: Sequence[dict]) -> dict:
    """지방에서 첫 무대를 연 팀 중 서울에 올라온 팀 수와 걸린 개월 (첫 무대 도시별)."""
    local = [r for r in rows if r["first_city"] and r["first_city"] != SEOUL]
    reached = [r for r in local if r["seoul_first_date"]]
    by_city: Dict[str, dict] = {}
    for c in sorted({r["first_city"] for r in local}):
        rs = [r for r in local if r["first_city"] == c]
        months = [r["months_to_seoul"] for r in rs if r["months_to_seoul"] != ""]
        by_city[c] = {"teams": len(rs), "reached": len(months),
                      "median_months": statistics.median(months) if months else None}
    all_months = [r["months_to_seoul"] for r in reached]
    return {"local_start": len(local), "reached_seoul": len(reached),
            "median_months": statistics.median(all_months) if all_months else None, "by_first_city": by_city}


# ---------- 도시 프로필 ----------

def build_city_profiles(gigs: Sequence[Gig], teams: Dict[str, str], outcomes: Sequence[dict],
                        snapshot: Dict[str, Tuple[int, float]], city_of: Dict[str, str],
                        master: Sequence[dict], as_of: date) -> Dict[str, dict]:
    rows = [(t, d, v, city_for(v, city_of)) for t, d, v in gigs]
    rows = [r for r in rows if r[3] != UNKNOWN_CITY]
    past = [r for r in rows if r[1] <= as_of]
    upcoming = Counter(c for _, _, c in {(d, v, c) for _, d, v, c in rows if d > as_of})   # 예정 공연 날짜 수
    first_city: Dict[str, Tuple[date, str]] = {}
    for t, d, v, c in sorted(past, key=lambda r: (r[1], r[2])):
        first_city.setdefault(t, (d, c))
    first_out = vp.first_counted_outcome(o for o in outcomes if o["announced_date"] <= as_of)
    by_city: Dict[str, list] = defaultdict(list)
    for t, d, v, c in past:
        by_city[c].append((t, d, v))
    master_n = Counter(e.get("city") for e in master)
    master_in = Counter(e.get("city") for e in master if e.get("in_our_data"))
    out = {}
    for c, items in by_city.items():
        out[c] = _city(c, items, first_city, first_out, snapshot, teams, as_of,
                       master_n.get(c, 0), master_in.get(c, 0), upcoming.get(c, 0))
    return out


def _city(c: str, items: List[Tuple[str, date, str]], first_city: Dict[str, Tuple[date, str]],
          first_out: Dict[str, dict], snapshot: Dict[str, Tuple[int, float]], teams: Dict[str, str], as_of: date,
          n_master: int, n_master_in: int, upcoming: int) -> dict:
    nights = {(d, v) for _, d, v in items}
    year_ago = as_of - YEAR
    first_here: Dict[str, date] = {}
    last_here: Dict[str, date] = {}
    for t, d, _ in sorted(items, key=lambda x: x[1]):
        first_here.setdefault(t, d)
        last_here[t] = d
    starters = [t for t, (d, fc) in first_city.items() if fc == c]
    winners = []
    for t, d0 in first_here.items():
        o = first_out.get(t)
        if o and d0 < o["announced_date"]:
            winners.append({"team_key": t, "name": teams.get(t, t), "first_here": d0.isoformat(),
                            "outcome": o["program_label"], "grade": o["grade"],
                            "outcome_date": o["announced_date"].isoformat(),
                            "lead_months": _months(d0, o["announced_date"])})
    winners.sort(key=lambda w: (w["outcome_date"], w["team_key"]), reverse=True)
    since = date(as_of.year - LOOKBACK_YEARS, as_of.month, as_of.day)
    cands = sorted((t for t in last_here if t in snapshot and last_here[t] >= since), key=lambda t: snapshot[t][0])
    venue_nights = Counter(v for _, v in nights)
    return {
        "venues_master": n_master, "venues_master_in_data": n_master_in, "venues_with_gigs": len(venue_nights),
        "nights": len(nights), "upcoming_nights": upcoming,
        "monthly": dict(sorted(Counter(d.strftime("%Y-%m") for d, _ in nights).items())),
        "teams_1y": len({t for t, d, _ in items if d > year_ago}),
        "first_stage_teams": len(starters),
        "first_stage_teams_1y": sum(1 for t in starters if first_city[t][0] > year_ago),
        "later_winners_total": len(winners), "later_winners": winners[:TOP_WINNERS],
        "top_candidates": [{"team_key": t, "name": teams.get(t, t), "rank": snapshot[t][0], "score": snapshot[t][1],
                            "last_here": last_here[t].isoformat()} for t in cands[:TOP_N]],
        "top_venues": [[v, n] for v, n in sorted(venue_nights.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP_N]],
    }


def payload(profiles: Dict[str, dict], flow: dict, as_of: date) -> dict:
    order = sorted(profiles, key=lambda c: (-profiles[c]["nights"], c))
    return {"as_of": as_of.isoformat(),
            "notes": {"venues_master": "config/venues_kr.json 의 그 도시 공연장 수 (venues_master_in_data = 그중 우리 공연 기록 있음)",
                      "nights": "공연 날짜 수(같은 날·같은 공연장 = 1), 기준 날짜까지",
                      "first_stage_teams": "우리 데이터의 첫 공연(도시 아는 것)이 이 도시였던 팀",
                      "later_winners": "센 정답 첫 발표일보다 먼저 이 도시에서 공연한 팀"},
            "seoul_flow": flow, "cities": {c: profiles[c] for c in order}}


# ---------- 교차 검증 특징 ----------

def city_features(gigs: Iterable[Gig], city_of: Dict[str, str], cutoff: date,
                  lookback_years: int = LOOKBACK_YEARS) -> Dict[str, Dict[str, float]]:
    """기준일 전(lookback 년 안) 공연만으로 팀마다 도시 특징. 도시 모름 공연은 뺀다."""
    start = date(cutoff.year - lookback_years, cutoff.month, cutoff.day)
    by_team: Dict[str, List[Tuple[date, str]]] = defaultdict(list)
    for t, d, v in gigs:
        c = city_for(v, city_of)
        if start <= d < cutoff and c != UNKNOWN_CITY:
            by_team[t].append((d, c))
    recent_from = cutoff - YEAR
    out = {}
    for t, items in by_team.items():
        items.sort()
        per_city = Counter(c for _, c in items)
        first_c = items[0][1]
        seoul = next((d for d, c in items if c == SEOUL), None)
        came = first_c != SEOUL and seoul is not None
        home = min(per_city, key=lambda c: (-per_city[c], c))
        out[t] = {"came_to_seoul": float(came), "non_seoul_base": float(home != SEOUL),
                  "city_count": float(len(per_city) - 1), "recent_seoul_arrival": float(came and seoul >= recent_from)}
    return out


def evaluate(data_dir: Path, city_of: Dict[str, str]) -> dict:
    import feature_lab as fl
    import score_tune as st

    con = lab_sql.connect(data_dir)
    data = {c: st.features(con, c) for c in st.CUTOFFS}
    sigs, _ = fl.load_events(con)
    disc = fl.gigs([s for s in sigs if s["role"] == "discovery"])
    zero = {f: 0.0 for f, _, _ in FEATURES}
    extra = {}
    for c in st.CUTOFFS:
        feats = city_features(disc, city_of, date.fromisoformat(c))
        extra[c] = {r["team_key"]: feats.get(r["team_key"], zero) for r in data[c]}
    res = {}
    for f, _, _ in FEATURES:
        r = fl.evaluate_feature(data, extra, f, fl.GRID_FINE)
        r["boot"] = fl.bootstrap_diff(data, r)
        r["desc"] = fl.describe(data, extra, f)
        res[f] = r
    return res


def verdict(r: dict) -> str:
    import venue_ladder as vl
    return vl.verdict(r)


# ---------- 문서 ----------

def _f(v: Optional[float]) -> str:
    return "—" if v is None else f"{v:.3f}"


def render(profiles: Dict[str, dict], flow: dict, team_rows: Sequence[dict], coverage: dict,
           ev: Optional[dict], as_of: date) -> str:
    order = sorted(profiles, key=lambda c: (-profiles[c]["nights"], c))
    total_n = sum(p["nights"] for p in profiles.values())
    lines = ["# 도시 층 — 도시별 프로필과 지방 → 서울 흐름", "",
             "_자동 생성: `.venv/bin/python scripts/city_profiles.py` · 공연장 → 도시: [`config/venues_kr.json`](../config/venues_kr.json)_", "",
             "Chartmetric의 '도시(City)' 페이지처럼 공연장을 도시로 묶어, 어느 도시에서 신인이 첫 무대를 열고 어느 도시를 거쳐 서울로 오는지 봅니다"
             "([경쟁 서비스 조사](research_2026-11-27_competitor_logic.md)). 앱 데이터: `docs/lab/data/city_profiles.json`(도시), "
             "`docs/lab/data/team_cities.csv`(팀별 활동 도시).", "",
             f"## 1. 덮는 비율 (기준 날짜 {as_of})", "",
             f"- 공연 기록이 있는 우리 공연장 {coverage['venues']:,}곳 중 도시를 아는 곳 {coverage['venues_known']:,}곳, "
             f"공연 날짜 {coverage['nights']:,}건 중 도시 아는 공연장 {coverage['nights_known']:,}건"
             f"({coverage['nights_known'] / coverage['nights']:.1%}).",
             f"- 도시를 아는 공연 날짜 중 **서울 {profiles.get(SEOUL, {}).get('nights', 0) / total_n:.0%}** — 우리 공연 출처(인디스트릿·상상마당)가 "
             "홍대 중심이라 지방 공연은 적게 잡힙니다(지방 공연장 공백은 [공연장·도시 목록](venues_kr.md) 참고).", "",
             "## 2. 도시별 프로필", "",
             "| 도시 | 공연장 (목록 / 우리 데이터) | 공연 날짜 | 최근 1년 공연 팀 | 첫 무대 팀 (최근 1년) | 나중 정답 팀 | 지금 후보 상위 | 대표 공연장 |",
             "|---|---|---|---|---|---|---|---|"]
    for c in order:
        p = profiles[c]
        cand = ", ".join(f"{t['name']}({t['rank']})" for t in p["top_candidates"][:3]) or "—"
        ven = ", ".join(f"{v} {n}" for v, n in p["top_venues"][:3])
        lines.append(f"| {c} | {p['venues_master']} / {p['venues_with_gigs']} | {p['nights']:,} | {p['teams_1y']:,} | "
                     f"{p['first_stage_teams']:,} ({p['first_stage_teams_1y']:,}) | {p['later_winners_total']} | {cand} | {ven} |")
    lines += ["", "읽는 법: '공연장 목록'은 마스터 목록의 그 도시 공연장 수, '우리 데이터'는 공연 기록이 있는 우리 공연장 수입니다. "
              "'첫 무대 팀'은 우리 데이터에서 첫 공연(도시 아는 것)이 그 도시였던 팀, '나중 정답 팀'은 정답 발표 전에 그 도시에서 공연한 팀입니다.", ""]
    lines += _flow_section(flow, team_rows)
    lines += _eval_section(ev) if ev else ["## 4. 교차 검증", "", "(`--no-eval` 로 건너뜀)", ""]
    lines += ["## 5. 한계", "",
              "- 공연 출처가 홍대 중심이라 지방 팀의 지방 공연이 적게 잡히고, 그래서 '첫 무대 도시'가 실제보다 서울로 쏠립니다.",
              "- '첫 무대'는 우리 데이터의 첫 공연이지 팀의 실제 첫 공연이 아닙니다(인디스트릿 공연 2024-01~, 상상마당 2010~).",
              "- 도시는 공연장 마스터 목록(234곳)과 공연 원본 주소로 정하므로, 둘 다 없는 공연장은 '도시 모름'으로 빠집니다."]
    return "\n".join(lines) + "\n"


def _flow_section(flow: dict, team_rows: Sequence[dict]) -> List[str]:
    lines = ["## 3. 지방 → 서울 흐름", "",
             f"- 우리 데이터에서 **지방에서 첫 무대를 연 팀 {flow['local_start']:,}팀** 중 서울에서도 공연한 팀 "
             f"{flow['reached_seoul']:,}팀({flow['reached_seoul'] / flow['local_start']:.0%})" if flow["local_start"] else "- 지방에서 첫 무대를 연 팀이 없습니다"]
    if flow["median_months"] is not None:
        lines[-1] += f", 첫 공연 → 서울 첫 공연 중앙값 **{flow['median_months']:g}개월**."
    lines += ["", "| 첫 무대 도시 | 팀 | 서울 진출 | 비율 | 걸린 개월(중앙값) |", "|---|---|---|---|---|"]
    for c, s in sorted(flow["by_first_city"].items(), key=lambda kv: -kv[1]["teams"])[:12]:
        mm = "—" if s["median_months"] is None else f"{s['median_months']:g}"
        lines.append(f"| {c} | {s['teams']:,} | {s['reached']:,} | {s['reached'] / s['teams']:.0%} | {mm} |")
    multi = sum(1 for r in team_rows if r["cities"] >= 2)
    known = sum(1 for r in team_rows if r["cities"] >= 1)
    lines += ["", f"- 도시를 아는 팀 {known:,}팀 중 두 도시 이상에서 공연한 팀 {multi:,}팀({multi / known:.1%})." if known else "", ""]
    return lines


def _reading(ev: dict) -> str:
    """방향(고른 가중치 부호)과 크기를 숫자에 맞춰 풀어 쓴다."""
    parts = []
    for f, r in ev.items():
        gain = r["cv_mean"] - r["base_mean"]
        picks = list(r["picks"].values())
        if gain <= 0.001:
            continue
        sign = "음수" if all(w < 0 for w in picks) else "양수" if all(w > 0 for w in picks) else "기준일마다 다른 부호"
        direction = ("이런 팀을 **조금 아래로** 둘 때 나아졌다는 뜻 — 이 특징이 있는 팀이 정답을 더 받는다는 근거가 아님"
                     if sign == "음수" else "이런 팀을 조금 위로 둘 때 나아졌다는 뜻" if sign == "양수" else "방향이 일정하지 않음")
        parts.append(f"'{NAMES[f]}'는 {gain:+.3f}(가중치 {sign}: {direction}; 정답 팀 평균 {r['desc']['hit_mean']:.2f} vs 아닌 팀 "
                     f"{r['desc']['non_mean']:.2f}, 해당 후보 {r['desc']['nonzero']:.1%})")
    if not parts:
        return "**읽는 법:** 모든 특징이 v2보다 낫지 않거나 차이가 0.001 이하입니다."
    return ("**읽는 법:** " + "; ".join(parts) + ". 차이가 0.001~0.002로 작고 해당 후보가 몇 %뿐이라, 대부분 v2 점수가 같은 팀끼리의 "
            "순서를 바꾼 효과입니다. 공연 도시 수가 많은 팀은 정답 비율이 높지만 그 정보는 이미 v2의 '공연장 다양성'에 들어 있습니다.")


def _eval_section(ev: dict) -> List[str]:
    import feature_lab as fl
    import score_tune as st

    base = next(iter(ev.values()))
    bh = base["base_hits"]
    defs = {k: d for k, _, d in FEATURES}
    lines = ["## 4. 지방 → 서울 흐름이 정답을 미리 알려 주나 — 점수 v2에 더해 교차 검증", "",
             f"[점수 새 특징 실험](feature_lab.md)·[공연장 사다리](venue_ladder.md)와 같은 방법(기준일 6개 {', '.join(st.CUTOFFS)}, "
             f"관찰 {st.HORIZON_MONTHS}개월, 정답 등급 가중 AUC, 가중치 후보 0·{', '.join(f'{g:g}' for g in fl.GRID_FINE)}점을 기준일 하나 빼고 고름). "
             f"채택 기준: 평균 AUC +{fl.ADOPT_MIN_GAIN} 이상, 95% 구간 하한 > 0, 상위 50 적중 유지. 특징은 기준일 전 3년 발굴 출처 공연만.", "",
             f"v2 그대로: 평균 AUC **{_f(base['base_mean'])}**, 상위 20 / 50 / 100 적중 {bh['hits20']} / {bh['hits50']} / {bh['hits100']}.", "",
             "| 특징 | 정의 | 평균 AUC (교차) | 차이 | 95% 구간 | 오른·내린 기준일 | 상위 20 / 50 / 100 | 고른 가중치 | 0 아닌 후보 | 평균: 정답 / 아닌 팀 | 판정 |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for f, r in ev.items():
        b, h = r["boot"], r["cv_hits"]
        picks = ", ".join(sorted({f"{w:g}" for w in r["picks"].values()}))
        lines.append(f"| {NAMES[f]} | {defs[f]} | {_f(r['cv_mean'])} | {r['cv_mean'] - r['base_mean']:+.3f} | "
                     f"{b[1]:+.3f} ~ {b[2]:+.3f} | {r['wins']} / {r['losses']} | {h['hits20']} / {h['hits50']} / {h['hits100']} | "
                     f"{picks} | {r['desc']['nonzero']:.1%} | {r['desc']['hit_mean']:.2f} / {r['desc']['non_mean']:.2f} | {verdict(r)} |")
    adopt = [f for f, r in ev.items() if verdict(r) == "채택 후보"]
    lines += ["", "(평균 정답 / 아닌 팀은 표준화 전 값, 기준일 6개 합침 — 라벨을 보는 참고용이고 가중치 고르기에는 안 썼습니다.)", "",
              _reading(ev), ""]
    if adopt:
        lines.append("**요청(코디네이터):** " + ", ".join(NAMES[f] for f in adopt) + " — 채택 기준을 넘었습니다. "
                     "`docs/lab/sql/features.sql`의 `lab_scored`에 기본 0인 인자로 넣고 공연장 → 도시 표를 랩 데이터로 내보낸 뒤 "
                     "`score_tune.GRID`에 넣어 다시 고르는 것을 요청합니다(앱 기본값은 사용자 확인 뒤).")
    else:
        lines.append("**결론:** 채택 기준을 넘는 특징이 없습니다. 도시 정보는 **점수에 넣지 않고 화면 정보로만** 씁니다"
                     "(도시 페이지, 팀 상세의 '활동 도시'). 지방 공연 출처가 늘면 다시 잽니다.")
    return lines + [""]


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="도시 층 → city_profiles.json · team_cities.csv · docs/city_profiles.md")
    ap.add_argument("--data-dir", type=Path, default=lab_sql.DATA_DIR)
    ap.add_argument("--out-dir", type=Path, default=lab_sql.DATA_DIR, help="JSON·CSV 쓸 폴더 (21~23시엔 다른 곳으로)")
    ap.add_argument("--doc", type=Path, default=DOC)
    ap.add_argument("--no-eval", action="store_true")
    args = ap.parse_args(argv)
    gigs, teams, outcomes, snap, as_of = vp.load_lab(args.data_dir)
    city_of, master = load_city_map(v for _, _, v in gigs)
    team_rows = team_cities(gigs, city_of, as_of)
    profiles = build_city_profiles(gigs, teams, outcomes, snap, city_of, master, as_of)
    flow = seoul_flow(team_rows)
    past = {(d, v) for _, d, v in gigs if d <= as_of}
    venues = {v for _, v in past}
    cov = {"venues": len(venues), "venues_known": sum(1 for v in venues if v in city_of),
           "nights": len(past), "nights_known": sum(1 for _, v in past if v in city_of)}
    ev = None if args.no_eval else evaluate(args.data_dir, city_of)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "city_profiles.json").write_text(
        json.dumps(payload(profiles, flow, as_of), ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    write_team_cities(team_rows, args.out_dir / "team_cities.csv")
    args.doc.write_text(render(profiles, flow, team_rows, cov, ev, as_of), encoding="utf-8")
    print(f"도시 {len(profiles)}곳 · 팀 {len(team_rows):,} · 도시 아는 공연 날짜 {cov['nights_known'] / cov['nights']:.1%}")
    print(f"✅ → {args.out_dir / 'city_profiles.json'}, {args.out_dir / 'team_cities.csv'}, {args.doc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
