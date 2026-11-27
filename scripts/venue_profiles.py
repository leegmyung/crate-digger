"""공연장 프로필 — 앱 공연장 상세(Chartmetric 공연장 페이지처럼)에 쓸 데이터 → docs/lab/data/venue_profiles.json

공연장마다: 대표 이름·체급·수용 인원·도시, 월별 공연 날짜 수, 최근 1년 선 팀 수, 첫 출연 팀 수(신인 비율),
그 공연장에 섰던 팀 중 나중에 정답 받은 팀('정답 전에 섰던'만), 지금 후보 상위 팀, 전후 공연장 흐름 상위 5.
발굴 주목도(discovery: 최근 12개월 공연일 × 첫 출연 신인 비율 × 정답 전 출연 비율 → 0~100, 정렬용·점수 미반영,
정의는 docs/methods.md '공연장 발굴 주목도'), 지도용 좌표(lat·lon·geo_confidence, config/venues_kr.json 에서 복사).

- 입력(읽기만): 랩 데이터(docs/lab/data/signals.csv·teams.csv·outcomes.csv·snapshots/·meta.json),
  config/venue_capacity.json(체급·수용 인원 출처), config/venues_kr.json(도시·종류·별칭 — 없으면 빈칸),
  config/venue_aliases.json(묶인 표기·묶지 않음 근거), 전후 흐름은 venue_ladder 와 같은 계산.
- 시점: 기준 날짜(meta.json data_end) 뒤의 공연은 '예정 공연'으로만 세고 나머지 숫자에는 넣지 않는다.
  '나중에 정답 받은 팀' = 센 정답(counted)의 첫 발표일보다 '엄격하게 앞서' 그 공연장에 선 팀.
- 공개 데이터만: 팀 키·이름, 공연장 이름, 숫자 (주소·연락처 없음).

실행: .venv/bin/python scripts/venue_profiles.py [--data-dir 폴더] [--out 경로]   (21~23시엔 docs/lab/data 에 쓰지 말 것)
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab_sql  # noqa: E402
import venue_ladder as vl  # noqa: E402
import venues_kr as vk  # noqa: E402

OUT = lab_sql.DATA_DIR / "venue_profiles.json"
CITIES = lab_sql.ROOT / "config" / "venues_kr.json"
ALIASES = lab_sql.ROOT / "config" / "venue_aliases.json"
YEAR = timedelta(days=365)
CANDIDATE_LOOKBACK_YEARS = 3   # '지금 후보 상위 팀' = 최근 3년 안에 이 공연장에 선 후보 (점수 v2 신호 창과 같게)
TOP_CANDIDATES = 5
TOP_WINNERS = 10
TOP_FLOW = 5
SKIP = {"", "공연장 미정"}
# 발굴 주목도 (정렬용, 후보 점수엔 안 씀 — docs/methods.md '공연장 발굴 주목도')
DISCOVERY_PRIOR_TEAMS = 10      # 팀 수가 적은 공연장의 비율을 전체 평균 쪽으로 당기는 세기(팀 10명분)
DISCOVERY_FULL_NIGHTS = 365     # 최근 12개월 매일 공연 = 활동 만점 (로그 눈금)
DISCOVERY_FULL_WINNER = 0.10    # 처음 선 팀의 10% 이상이 나중에 정답 = 정답 만점
WINNER_MIN_AGE = YEAR           # 정답 전 출연 비율은 '처음 선 지 1년 넘은 팀'만 센다(정답 받을 시간)

Gig = Tuple[str, date, str]


# ---------- 읽기 ----------

def load_cities(path: Path = CITIES) -> Dict[str, str]:
    """config/venues_kr.json → {공연장: 도시}. 파일이 없거나 모양이 다르면 빈 표(도시 칸은 빈칸).
    받는 모양: {"venues": {이름: {"city"|"region": …}}}, {이름: {…}}, {이름: "도시"}, {"venues": [{"venue": 이름, "city": …}]}."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    body = raw.get("venues", raw) if isinstance(raw, dict) else raw
    items: Iterable[Tuple[str, object]]
    if isinstance(body, list):
        items = ((d.get("venue") or d.get("name") or "", d) for d in body if isinstance(d, dict))
    elif isinstance(body, dict):
        items = ((k, v) for k, v in body.items() if not k.startswith("_"))
    else:
        return {}
    out = {}
    for name, val in items:
        city = val if isinstance(val, str) else (val.get("city") or val.get("region") or "") if isinstance(val, dict) else ""
        if name and city:
            out[name] = city
    return out


def load_geo(names: Iterable[str], path: Path = CITIES) -> Dict[str, dict]:
    """우리 공연장 이름 → 마스터 목록(config/venues_kr.json)의 좌표·확실도·도시. 짝짓기는 venues_kr 와 같은 규칙
    (our_names 정확히 → 이름·별칭 정규화 키). 짝이 없으면 빠지고, 짝은 있는데 좌표가 없으면 lat·lon = None."""
    master = (vk.load_json(path, {}) or {}).get("venues", [])
    if not isinstance(master, list):
        return {}
    match = vk.match_our_venues(master, list(names))
    return {n: {"lat": master[i].get("lat"), "lon": master[i].get("lon"),
                "geo_confidence": master[i].get("geo_confidence"), "city": master[i].get("city") or ""}
            for n, i in match.items()}


def _read_csv(path: Path) -> List[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _day(s: str) -> Optional[date]:
    try:
        return date.fromisoformat((s or "")[:10])
    except ValueError:
        return None


def load_lab(data_dir: Path = lab_sql.DATA_DIR):
    """(공연, 팀 이름, 정답, 최신 스냅샷 {팀: (순위, 점수)}, 기준 날짜)."""
    gigs = sorted({(r["team_key"], d, r["venue"].strip()) for r in _read_csv(data_dir / "signals.csv")
                   if r["branch"] == "공연" and r["venue"].strip() not in SKIP and (d := _day(r["signal_date"]))})
    teams = {r["team_key"]: r.get("display_name") or r["team_key"] for r in _read_csv(data_dir / "teams.csv")}
    outcomes = [{"team_key": r["team_key"], "announced_date": d, "counted": r.get("counted") == "true",
                 "program_label": r.get("program_label") or r.get("program", ""), "grade": r.get("grade", "")}
                for r in _read_csv(data_dir / "outcomes.csv") if (d := _day(r["announced_date"]))]
    snap: Dict[str, Tuple[int, float]] = {}
    try:
        latest = json.loads((data_dir / "snapshots" / "index.json").read_text(encoding="utf-8"))["dates"][0]
        snap = {r["team_key"]: (int(r["rank"]), float(r["score"]))
                for r in _read_csv(data_dir / "snapshots" / f"{latest}.csv")}
    except (OSError, ValueError, KeyError, IndexError):
        pass
    return gigs, teams, outcomes, snap, vl.data_end(data_dir)


# ---------- 계산 ----------

def _months_between(a: date, b: date) -> int:
    return (b.year - a.year) * 12 + (b.month - a.month)


def first_counted_outcome(outcomes: Iterable[dict]) -> Dict[str, dict]:
    """팀마다 센 정답(counted) 중 가장 이른 것."""
    first: Dict[str, dict] = {}
    for o in sorted((o for o in outcomes if o["counted"]), key=lambda o: o["announced_date"]):
        first.setdefault(o["team_key"], o)
    return first


def load_master_meta(names: Iterable[str], path: Path = CITIES) -> Dict[str, dict]:
    """우리 공연장 이름 → 마스터 목록의 종류(type·type_label·type_basis)·별칭(마스터 aliases + 우리 이름과 다른 대표 이름).
    짝짓기는 load_geo 와 같은 규칙. type 이 비면 None(= 앱 '유형 미정')."""
    raw = vk.load_json(path, {}) or {}
    master = raw.get("venues", [])
    if not isinstance(master, list):
        return {}
    labels = raw.get("types") if isinstance(raw.get("types"), dict) else {}
    out = {}
    for n, i in vk.match_our_venues(master, list(names)).items():
        e = master[i]
        code = str(e.get("type") or "").strip() or None
        alias = {a for a in (e.get("aliases") or []) if isinstance(a, str) and a.strip()}
        if e.get("name") and e["name"] != n:
            alias.add(e["name"])
        out[n] = {"type": code, "type_label": labels.get(code) if code else None,
                  "type_basis": e.get("type_basis") or None, "aliases": sorted(alias - {n})}
    return out


def load_alias_notes(path: Path = ALIASES) -> Dict[str, dict]:
    """config/venue_aliases.json → {대표 이름: {variants: 묶인 표기('@계정' 제외), not_merged: [{names, reason}]}}.
    '묶지 않음' 근거는 거기 이름이 나온 공연장마다 붙인다(앱 공연장 상세 접힌 칸)."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: Dict[str, dict] = defaultdict(lambda: {"variants": [], "not_merged": []})
    for rule in raw.get("aliases", []) or []:
        venue = rule.get("venue")
        if not venue:
            continue
        out[venue]["variants"].extend(v for v in rule.get("variants", []) if v and not str(v).startswith("@"))
    for rule in raw.get("_묶지_않음", []) or []:
        item = {"names": list(rule.get("names", [])), "reason": rule.get("reason", "")}
        for n in item["names"]:
            out[n]["not_merged"].append(item)
    return {k: {"variants": sorted(set(v["variants"])), "not_merged": v["not_merged"]} for k, v in out.items()}


def _extra_fields(v: str, cap: dict, meta: dict, notes: dict) -> dict:
    """종류·별칭·'묶지 않음'·수용 인원 출처 칸 (없으면 None·빈 목록)."""
    aliases = sorted((set(meta.get("aliases", [])) | set(notes.get("variants", []))) - {v})
    return {"type": meta.get("type"), "type_label": meta.get("type_label"), "type_basis": meta.get("type_basis"),
            "aliases": aliases, "not_merged": notes.get("not_merged", []),
            "capacity_source": cap.get("source") or None, "capacity_note": cap.get("source_note") or None,
            "capacity_confidence": cap.get("confidence") or None, "capacity_checked": cap.get("checked") or None}


def build_profiles(gigs: Sequence[Gig], teams: Dict[str, str], outcomes: Sequence[dict],
                   snapshot: Dict[str, Tuple[int, float]], cfg: dict, cities: Dict[str, str],
                   as_of: date, geo: Optional[Dict[str, dict]] = None,
                   meta: Optional[Dict[str, dict]] = None, alias_notes: Optional[Dict[str, dict]] = None
                   ) -> Dict[str, dict]:
    skip = vl.not_venues(cfg)
    rows = [g for g in gigs if g[2] not in skip and g[2] not in SKIP]
    past = [g for g in rows if g[1] <= as_of]
    upcoming = Counter(v for _, v in {(d, v) for _, d, v in rows if d > as_of})   # 예정 공연 날짜 수
    first_gig: Dict[str, Tuple[date, str]] = {}
    for t, d, v in sorted(past, key=lambda g: (g[1], g[2])):
        first_gig.setdefault(t, (d, v))
    first_out = first_counted_outcome(o for o in outcomes if o["announced_date"] <= as_of)
    journey = vl.venue_journey(past, min_teams=1)
    caps = cfg["venues"]
    by_venue: Dict[str, List[Tuple[str, date]]] = defaultdict(list)
    for t, d, v in past:
        by_venue[v].append((t, d))
    geo = geo or {}
    meta = meta or {}
    alias_notes = alias_notes or {}
    out = {}
    for v, items in by_venue.items():
        g = geo.get(v, {})
        prof = _profile(v, items, caps.get(v, {}), cities.get(v) or g.get("city", ""), first_gig, first_out,
                        snapshot, teams, journey.get(v, {"before": [], "after": []}), upcoming.get(v, 0), as_of)
        out[v] = {**prof, "lat": g.get("lat"), "lon": g.get("lon"), "geo_confidence": g.get("geo_confidence"),
                  **_extra_fields(v, caps.get(v, {}), meta.get(v, {}), alias_notes.get(v, {}))}
    prior_new, prior_win = discovery_priors(out)
    return {v: {**p, "discovery": discovery_block({**p, **p["discovery"]}, prior_new, prior_win)}
            for v, p in out.items()}


def discovery_priors(profiles: Dict[str, dict]) -> Tuple[float, float]:
    """전체 평균(모든 공연장을 합친 비율): (첫 출연 신인 / 최근 1년 팀, 정답 전 출연 / 처음 선 지 1년 넘은 팀)."""
    teams = sum(p["teams_1y"] for p in profiles.values())
    new = sum(p["first_timers_1y"] for p in profiles.values())
    base = sum(p["discovery"]["winner_base"] for p in profiles.values())
    hits = sum(p["discovery"]["winner_hits"] for p in profiles.values())
    return (new / teams if teams else 0.0), (hits / base if base else 0.0)


def discovery_block(raw: dict, prior_new: float, prior_win: float) -> dict:
    """발굴 주목도 0~100 = 100 × (활동 × 첫 출연 신인 비율 × 정답 만점 비율)^(1/3).
    세 값을 곱한 것과 순서가 같고(세제곱근은 순서를 안 바꿈) 0~100으로 읽기 쉽게 한 것.
    - 활동 = log(1 + 최근 12개월 공연일) / log(1 + 365), 1이 상한
    - 첫 출연 신인 비율 = (첫 출연 팀 + 10 × 전체 평균) / (최근 1년 팀 + 10)  ← 팀 적은 곳은 평균 쪽으로
    - 정답 전 출연 비율 = (정답 전에 선 팀 + 10 × 전체 평균) / (처음 선 지 1년 넘은 팀 + 10), 10%면 만점
    최근 12개월 공연이 없으면 점수 None(빈칸)."""
    k = DISCOVERY_PRIOR_TEAMS
    n12, teams, new = raw["nights_12m"], raw["teams_1y"], raw["first_timers_1y"]
    base, hits = raw["winner_base"], raw["winner_hits"]
    activity = min(1.0, math.log1p(n12) / math.log1p(DISCOVERY_FULL_NIGHTS))
    newcomer_adj = (new + k * prior_new) / (teams + k)
    winner_adj = (hits + k * prior_win) / (base + k)
    winner_norm = min(1.0, winner_adj / DISCOVERY_FULL_WINNER)
    score = round(100 * (activity * newcomer_adj * winner_norm) ** (1 / 3), 1) if n12 else None
    return {"score": score, "nights_12m": n12, "activity": round(activity, 4),
            "newcomer_share": round(new / teams, 4) if teams else None, "newcomer_adj": round(newcomer_adj, 4),
            "winner_base": base, "winner_hits": hits,
            "winner_share": round(hits / base, 4) if base else None, "winner_adj": round(winner_adj, 4),
            "winner_norm": round(winner_norm, 4)}


def _profile(v: str, items: List[Tuple[str, date]], cap: dict, city: str, first_gig: Dict[str, Tuple[date, str]],
             first_out: Dict[str, dict], snapshot: Dict[str, Tuple[int, float]], teams: Dict[str, str],
             journey: dict, upcoming: int, as_of: date) -> dict:
    nights = sorted({d for _, d in items})
    year_ago = as_of - YEAR
    teams_1y = {t for t, d in items if d > year_ago}
    first_timers = {t for t in teams_1y if first_gig[t][1] == v and first_gig[t][0] > year_ago}
    first_here: Dict[str, date] = {}
    last_here: Dict[str, date] = {}
    for t, d in sorted(items, key=lambda x: x[1]):
        first_here.setdefault(t, d)
        last_here[t] = d
    winners = []
    for t, d0 in first_here.items():
        o = first_out.get(t)
        if o and d0 < o["announced_date"]:
            winners.append({"team_key": t, "name": teams.get(t, t), "first_here": d0.isoformat(),
                            "outcome": o["program_label"], "grade": o["grade"],
                            "outcome_date": o["announced_date"].isoformat(),
                            "lead_months": _months_between(d0, o["announced_date"])})
    winners.sort(key=lambda w: (w["outcome_date"], w["team_key"]), reverse=True)
    old_enough = as_of - WINNER_MIN_AGE
    winner_base = {t for t, d0 in first_here.items() if d0 <= old_enough}
    winner_hits = {w["team_key"] for w in winners if w["team_key"] in winner_base}
    since = date(as_of.year - CANDIDATE_LOOKBACK_YEARS, as_of.month, as_of.day)
    cands = sorted((t for t in last_here if t in snapshot and last_here[t] >= since), key=lambda t: snapshot[t][0])
    return {
        "tier": cap.get("tier"), "capacity": cap.get("capacity"), "city": city,
        "nights": len(nights), "first_night": nights[0].isoformat(), "last_night": nights[-1].isoformat(),
        "upcoming_nights": upcoming,
        "monthly": dict(sorted(Counter(d.strftime("%Y-%m") for d in nights).items())),
        "teams_1y": len(teams_1y), "first_timers_1y": len(first_timers),
        "first_timer_share_1y": round(len(first_timers) / len(teams_1y), 4) if teams_1y else None,
        "later_winners_total": len(winners), "later_winners": winners[:TOP_WINNERS],
        "top_candidates": [{"team_key": t, "name": teams.get(t, t), "rank": snapshot[t][0], "score": snapshot[t][1],
                            "last_here": last_here[t].isoformat()} for t in cands[:TOP_CANDIDATES]],
        "before": [[u, c] for u, c in journey["before"][:TOP_FLOW]],
        "after": [[u, c] for u, c in journey["after"][:TOP_FLOW]],
        "discovery": {"nights_12m": sum(1 for d in nights if d > year_ago),
                      "winner_base": len(winner_base), "winner_hits": len(winner_hits)},
    }


def payload(profiles: Dict[str, dict], as_of: date) -> dict:
    order = sorted(profiles, key=lambda v: (-profiles[v]["nights"], v))
    return {"as_of": as_of.isoformat(),
            "notes": {"nights": "공연 날짜 수(같은 날·같은 공연장 = 1), 기준 날짜까지",
                      "later_winners": "센 정답 첫 발표일보다 먼저 이 공연장에 선 팀",
                      "first_timers_1y": "최근 1년 이 공연장에 선 팀 중 우리 데이터의 첫 공연이 여기였던 팀",
                      "top_candidates": f"최근 {CANDIDATE_LOOKBACK_YEARS}년 이 공연장에 선 팀 중 최신 점수 순위 상위",
                      "before_after": "이 공연장에 처음 선 팀들이 그 전 1년에 선 곳 / 그 뒤 1년에 처음 선 곳 (팀 수, 페스티벌 제외)",
                      "discovery": "발굴 주목도 0~100(정렬용, 후보 점수엔 안 씀) = 100 × (활동 × 첫 출연 신인 비율 × 정답 전 출연 "
                                   "비율 정규화)^(1/3). 활동 = log(1+최근 12개월 공연일)/log(366), 비율은 팀 10명분만큼 전체 평균 쪽으로 "
                                   "당김, 정답 전 출연은 처음 선 지 1년 넘은 팀 중 정답 발표 전에 선 팀(10%면 만점). "
                                   "최근 12개월 공연이 없으면 빈칸. docs/methods.md '공연장 발굴 주목도'",
                      "type": "type·type_label·type_basis = config/venues_kr.json 공연장 종류(라이브클럽·홀·소극장·창작소·카페·페스티벌)와 근거. "
                              "없으면 null(앱 '유형 미정')",
                      "aliases": "aliases = 마스터 목록 별칭·대표 이름 + config/venue_aliases.json 묶인 표기('@계정' 제외), "
                                 "not_merged = 묶지 않은 비슷한 이름과 근거",
                      "capacity_source": "capacity_source·note·confidence·checked = config/venue_capacity.json 수용 인원 출처·"
                                         "설명·확실도(high·medium·low)·확인일",
                      "geo": "lat·lon·geo_confidence = config/venues_kr.json 좌표(OpenStreetMap Nominatim, "
                             "high 건물 · medium 도로 · low 이름 검색). 없으면 null"},
            "venues": {v: profiles[v] for v in order}}


def summary(profiles: Dict[str, dict]) -> str:
    n = len(profiles)
    with_tier = sum(1 for p in profiles.values() if p["tier"])
    with_city = sum(1 for p in profiles.values() if p["city"])
    with_win = sum(1 for p in profiles.values() if p["later_winners_total"])
    with_geo = sum(1 for p in profiles.values() if p.get("lat") is not None)
    scored = sorted(((p["discovery"]["score"], v) for v, p in profiles.items() if p["discovery"]["score"] is not None),
                    reverse=True)
    top = sorted(profiles.items(), key=lambda kv: -kv[1]["later_winners_total"])[:5]
    return (f"공연장 {n}곳 · 체급 있음 {with_tier} · 도시 있음 {with_city} · 좌표 있음 {with_geo} · "
            f"나중 정답 팀이 선 곳 {with_win}\n"
            "나중 정답 팀 많은 곳: " + ", ".join(f"{v} {p['later_winners_total']}" for v, p in top) + "\n"
            f"발굴 주목도 (점수 있는 곳 {len(scored)}) 상위: " + ", ".join(f"{v} {s}" for s, v in scored[:8]))


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="공연장 프로필 → docs/lab/data/venue_profiles.json")
    ap.add_argument("--data-dir", type=Path, default=lab_sql.DATA_DIR)
    ap.add_argument("--config", type=Path, default=vl.CONFIG)
    ap.add_argument("--cities", type=Path, default=CITIES)
    ap.add_argument("--aliases", type=Path, default=ALIASES)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    gigs, teams, outcomes, snap, as_of = load_lab(args.data_dir)
    names = {v for _, _, v in gigs}
    geo = load_geo(names, args.cities)
    prof = build_profiles(gigs, teams, outcomes, snap, vl.load_config(args.config), load_cities(args.cities), as_of,
                          geo=geo, meta=load_master_meta(names, args.cities), alias_notes=load_alias_notes(args.aliases))
    args.out.write_text(json.dumps(payload(prof, as_of), ensure_ascii=False, separators=(",", ":")) + "\n",
                        encoding="utf-8")
    print(summary(prof))
    print(f"✅ → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
