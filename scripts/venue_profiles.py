"""공연장 프로필 — 앱 공연장 상세(Chartmetric 공연장 페이지처럼)에 쓸 데이터 → docs/lab/data/venue_profiles.json

공연장마다: 대표 이름·체급·수용 인원·도시, 월별 공연 날짜 수, 최근 1년 선 팀 수, 첫 출연 팀 수(신인 비율),
그 공연장에 섰던 팀 중 나중에 정답 받은 팀('정답 전에 섰던'만), 지금 후보 상위 팀, 전후 공연장 흐름 상위 5.

- 입력(읽기만): 랩 데이터(docs/lab/data/signals.csv·teams.csv·outcomes.csv·snapshots/·meta.json),
  config/venue_capacity.json(체급), config/venues_kr.json(도시 — 없으면 빈칸), 전후 흐름은 venue_ladder 와 같은 계산.
- 시점: 기준 날짜(meta.json data_end) 뒤의 공연은 '예정 공연'으로만 세고 나머지 숫자에는 넣지 않는다.
  '나중에 정답 받은 팀' = 센 정답(counted)의 첫 발표일보다 '엄격하게 앞서' 그 공연장에 선 팀.
- 공개 데이터만: 팀 키·이름, 공연장 이름, 숫자 (주소·연락처 없음).

실행: .venv/bin/python scripts/venue_profiles.py [--data-dir 폴더] [--out 경로]   (21~23시엔 docs/lab/data 에 쓰지 말 것)
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab_sql  # noqa: E402
import venue_ladder as vl  # noqa: E402

OUT = lab_sql.DATA_DIR / "venue_profiles.json"
CITIES = lab_sql.ROOT / "config" / "venues_kr.json"
YEAR = timedelta(days=365)
CANDIDATE_LOOKBACK_YEARS = 3   # '지금 후보 상위 팀' = 최근 3년 안에 이 공연장에 선 후보 (점수 v2 신호 창과 같게)
TOP_CANDIDATES = 5
TOP_WINNERS = 10
TOP_FLOW = 5
SKIP = {"", "공연장 미정"}

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


def build_profiles(gigs: Sequence[Gig], teams: Dict[str, str], outcomes: Sequence[dict],
                   snapshot: Dict[str, Tuple[int, float]], cfg: dict, cities: Dict[str, str],
                   as_of: date) -> Dict[str, dict]:
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
    out = {}
    for v, items in by_venue.items():
        out[v] = _profile(v, items, caps.get(v, {}), cities.get(v, ""), first_gig, first_out, snapshot, teams,
                          journey.get(v, {"before": [], "after": []}), upcoming.get(v, 0), as_of)
    return out


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
    }


def payload(profiles: Dict[str, dict], as_of: date) -> dict:
    order = sorted(profiles, key=lambda v: (-profiles[v]["nights"], v))
    return {"as_of": as_of.isoformat(),
            "notes": {"nights": "공연 날짜 수(같은 날·같은 공연장 = 1), 기준 날짜까지",
                      "later_winners": "센 정답 첫 발표일보다 먼저 이 공연장에 선 팀",
                      "first_timers_1y": "최근 1년 이 공연장에 선 팀 중 우리 데이터의 첫 공연이 여기였던 팀",
                      "top_candidates": f"최근 {CANDIDATE_LOOKBACK_YEARS}년 이 공연장에 선 팀 중 최신 점수 순위 상위",
                      "before_after": "이 공연장에 처음 선 팀들이 그 전 1년에 선 곳 / 그 뒤 1년에 처음 선 곳 (팀 수, 페스티벌 제외)"},
            "venues": {v: profiles[v] for v in order}}


def summary(profiles: Dict[str, dict]) -> str:
    n = len(profiles)
    with_tier = sum(1 for p in profiles.values() if p["tier"])
    with_city = sum(1 for p in profiles.values() if p["city"])
    with_win = sum(1 for p in profiles.values() if p["later_winners_total"])
    top = sorted(profiles.items(), key=lambda kv: -kv[1]["later_winners_total"])[:5]
    return (f"공연장 {n}곳 · 체급 있음 {with_tier} · 도시 있음 {with_city} · 나중 정답 팀이 선 곳 {with_win}\n"
            "나중 정답 팀 많은 곳: " + ", ".join(f"{v} {p['later_winners_total']}" for v, p in top))


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="공연장 프로필 → docs/lab/data/venue_profiles.json")
    ap.add_argument("--data-dir", type=Path, default=lab_sql.DATA_DIR)
    ap.add_argument("--config", type=Path, default=vl.CONFIG)
    ap.add_argument("--cities", type=Path, default=CITIES)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    gigs, teams, outcomes, snap, as_of = load_lab(args.data_dir)
    prof = build_profiles(gigs, teams, outcomes, snap, vl.load_config(args.config), load_cities(args.cities), as_of)
    args.out.write_text(json.dumps(payload(prof, as_of), ensure_ascii=False, separators=(",", ":")) + "\n",
                        encoding="utf-8")
    print(summary(prof))
    print(f"✅ → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
