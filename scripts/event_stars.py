"""사건 별점 — 신호 중 '사건'에 1~5별을 매기고 사건 전후 28일 공연·언급 수를 센다 → docs/lab/data/event_stars.csv

Chartmetric 마일스톤 별점("플레이리스트·차트 크기와 순위 같은 요소로 계산하고 경력 단계에 맞게 조정")을 우리 데이터로 옮긴 것.
같은 사건이라도 **그때 작은 팀일수록 별이 높다** — 그 시점 발굴 단계(discovery_stage.sql 과 같은 규칙)와 공연장 체급이 재료.
점수(lab_scored)에는 넣지 않는 화면용(팀 상세 '사건 기록'·알림 정렬)이다.

사건 종류 (기본 별 → 그때 단계로 조정, 1~5로 자름):
  outcome          센 정답 (S 5 · A 4 · B 3)
  selection        선정·지원 단계 2 이상 (라인업·쇼케이스 2 · 선정 3 · 최종 4) — DMZ·제외 출처 빼고
  big_venue_first  처음으로 큰 공연장(L 3 · XL 4) — 그 전 가장 큰 무대가 S급뿐이면 '체급 점프' +1,
                   우리 기록의 첫 공연이 곧 큰 무대면(내한·기성 팀일 수 있음) 작은 팀 가산을 주지 않음
  first_seoul_gig  지방 공연이 먼저 있던 팀의 첫 서울 공연 3 (같은 날 큰 공연장 첫 출연이면 그쪽에 합침)
  magazine         매체(출처)마다 첫 소개 — 발굴 출처 2 · 맥락·검증 대기 1
  first_mention    처음 남에게 언급됨(첫 공연·첫 소개·첫 선정 중 가장 이른 것) 1 — 거의 모든 팀에 있어 낮게
그때 단계 조정: 백지 +2 · 첫 신호 +1 · 여러 갈래 0 · 선정·중간 정답 −1 · 졸업 −2.
'그때 단계' = 사건 날짜 '전' 정보만(같은 날 신호는 안 셈). 유명 판정(지금 팬 수)은 과거 사건에 쓰지 않는다(미래 정보).
전후 28일: 공연 = 서로 다른 공연 날짜 수, 언급 = 공연·발매가 아닌 남의 언급(큐레이션·선정) 수(같은 날·같은 출처는 한 번).
사건 당일은 앞뒤 어디에도 안 넣는다. 뒤쪽은 기준일(meta.json data_end)까지만 — after_window_days 가 28보다 작으면 아직 덜 찬 것.

실행: .venv/bin/python scripts/event_stars.py [--data-dir 폴더] [--out 경로] [--as-of YYYY-MM-DD]
     (scripts/build_app_extras.sh 의 한 단계. 손으로 돌릴 땐 매일 21~23시 자동 실행과 겹치지 않게 — 그 시간엔 --out 으로 다른 곳에)
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
LAB_DATA = ROOT / "docs" / "lab" / "data"
OUT = LAB_DATA / "event_stars.csv"
CAPACITY = ROOT / "config" / "venue_capacity.json"
VENUES_KR = ROOT / "config" / "venues_kr.json"

WINDOW = 28
SEOUL = "서울"
TIER_ORDER = ["S", "M", "L", "XL"]
BIG_TIERS = {"L": 3, "XL": 4}
SMALL_TIER = "S"
OUTCOME_BASE = {"S": 5, "A": 4, "B": 3}
SELECTION_BASE = {2: 2, 3: 3, 4: 4}
FIRST_MENTION_BASE = 1          # 거의 모든 팀에 한 번씩 있는 일이라 낮게 (백지일 때 3별)
STAGE_ADJ = {0: 2, 1: 1, 2: 0, 3: -1, 4: -2}
STAGE_LABELS = {0: "백지", 1: "첫 신호", 2: "여러 갈래", 3: "선정·중간 정답", 4: "졸업"}
SELECTION_LABELS = {2: "라인업·쇼케이스", 3: "선정", 4: "최종"}
KINDS = ("first_mention", "magazine", "first_seoul_gig", "big_venue_first", "selection", "outcome")
KIND_LABELS = {"first_mention": "첫 언급", "magazine": "매체 첫 소개", "first_seoul_gig": "처음 서울 공연",
               "big_venue_first": "큰 공연장 첫 출연", "selection": "선정·지원", "outcome": "정답"}
COLUMNS = ["team_key", "date", "kind", "stars", "reason", "kind_label", "stage_at", "detail",
           "gigs_before_28", "gigs_after_28", "mentions_before_28", "mentions_after_28", "after_window_days"]

Row = Dict[str, object]


# ---------- 작은 도우미 ----------

def _truthy(v) -> bool:
    return v is True or str(v).lower() == "true"


def _rank(v) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _day(s: Row) -> str:
    return str(s.get("signal_date") or "")


def is_mention(s: Row) -> bool:
    """남의 언급 (discovery_stage.sql 과 같은 정의): 자기 발매 아님, 제외 출처·DMZ 라인업 아님."""
    return s.get("branch") != "발매" and s.get("role") != "excluded" and s.get("program") != "dmz_lineup"


def _shift(day: str, days: int) -> str:
    return (date.fromisoformat(day) + timedelta(days=days)).isoformat()


def _group(rows: Iterable[Row]) -> Dict[str, List[Row]]:
    out: Dict[str, List[Row]] = defaultdict(list)
    for r in rows:
        out[str(r["team_key"])].append(r)
    return out


# ---------- 그때 단계 ----------

def stage_before(rows: Sequence[Row], outcomes: Sequence[Row], day: str) -> int:
    """사건 날짜 '전' 신호·정답으로 본 발굴 단계 (0 백지 ~ 4 졸업)."""
    best = 0
    for o in outcomes:
        if _truthy(o.get("counted")) and str(o.get("announced_date") or "") < day:
            best = max(best, 4 if o.get("grade") in ("S", "A") else 3)
    if best == 4:
        return 4
    prior = [s for s in rows if _day(s) < day and is_mention(s)]
    if any(s.get("branch") == "선정·지원" and _rank(s.get("stage_rank")) >= 3 for s in prior):
        best = max(best, 3)
    if best:
        return best
    branches = {s.get("branch") for s in prior}
    return 2 if len(branches) >= 2 else (1 if branches else 0)


# ---------- 사건 찾기 ----------

def _event(team: str, day: str, kind: str, base: int, detail: str, **extra) -> Row:
    return {"team_key": team, "date": day, "kind": kind, "base": base, "detail": detail, **extra}


def _mention_events(team: str, rows: List[Row]) -> List[Row]:
    """첫 언급 · 매체별 첫 소개 · 선정 단계 2 이상. rows = 기준일까지의 남의 언급(날짜순)."""
    if not rows:
        return []
    first = rows[0]
    where = first.get("venue") or first.get("program") or first.get("source") or ""
    out = [_event(team, _day(first), "first_mention", FIRST_MENTION_BASE, f"{first.get('branch')}: {where}")]
    seen_outlets = set()
    for s in rows:
        if s.get("branch") == "큐레이션":
            outlet = str(s.get("source") or "")
            if outlet in seen_outlets:
                continue
            seen_outlets.add(outlet)
            if s is not first:
                out.append(_event(team, _day(s), "magazine", 2 if s.get("role") == "discovery" else 1, f"{outlet} 첫 소개"))
        elif s.get("branch") == "선정·지원" and _rank(s.get("stage_rank")) >= 2:
            r = min(_rank(s.get("stage_rank")), 4)
            prog = s.get("program") or s.get("source") or ""
            out.append(_event(team, _day(s), "selection", SELECTION_BASE[r], f"{prog} {SELECTION_LABELS[r]}"))
    return out


def _gig_events(team: str, rows: List[Row], tiers: Dict[str, str], city: Dict[str, str]) -> List[Row]:
    """큰 공연장 첫 출연 · (지방 공연 뒤) 처음 서울 공연."""
    by_day: Dict[str, List[str]] = defaultdict(list)
    for s in rows:
        if s.get("branch") == "공연":
            by_day[_day(s)].append(str(s.get("venue") or ""))
    out: List[Row] = []
    had_big = had_regional = had_seoul = False
    max_tier: Optional[str] = None
    first_gig_day = min(by_day) if by_day else ""
    for day in sorted(by_day):
        venues = by_day[day]
        big = [v for v in venues if tiers.get(v) in BIG_TIERS]
        if big and not had_big:
            v = max(big, key=lambda x: BIG_TIERS[tiers[x]])
            out.append(_event(team, day, "big_venue_first", BIG_TIERS[tiers[v]], f"{v} ({tiers[v]}급)",
                              tier_jump=max_tier == SMALL_TIER, no_history=day == first_gig_day))
            had_big = True
        seoul = [v for v in venues if city.get(v) == SEOUL]
        if seoul and not had_seoul and had_regional:
            out.append(_event(team, day, "first_seoul_gig", 3, f"{seoul[0]} (그 전엔 지방 무대)"))
        had_seoul = had_seoul or bool(seoul)
        had_regional = had_regional or any(city.get(v) not in (None, "", SEOUL) for v in venues)
        for v in venues:
            t = tiers.get(v)
            if t in TIER_ORDER and (max_tier is None or TIER_ORDER.index(t) > TIER_ORDER.index(max_tier)):
                max_tier = t
    return out


def _outcome_events(team: str, outcomes: Sequence[Row], as_of: str) -> List[Row]:
    out = []
    for o in outcomes:
        day = str(o.get("announced_date") or "")
        if _truthy(o.get("counted")) and day and day <= as_of:
            grade = str(o.get("grade") or "")
            label = o.get("program_label") or o.get("program") or ""
            out.append(_event(team, day, "outcome", OUTCOME_BASE.get(grade, 3), f"{label} ({grade})" if grade else str(label)))
    return out


def _dedupe(events: List[Row]) -> List[Row]:
    """같은 팀·날짜·종류는 한 건(기본 별 높은 쪽). 같은 날 큰 공연장 첫 출연이 있으면 처음 서울 공연은 그쪽 설명에 합친다."""
    by_key: Dict[Tuple[str, str, str], Row] = {}
    for e in events:
        k = (str(e["team_key"]), str(e["date"]), str(e["kind"]))
        if k not in by_key or int(e["base"]) > int(by_key[k]["base"]):
            by_key[k] = e
    for (team, day, kind) in [k for k in by_key if k[2] == "first_seoul_gig"]:
        big = by_key.get((team, day, "big_venue_first"))
        if big:
            by_key[(team, day, "big_venue_first")] = {**big, "detail": f"{big['detail']} · 처음 서울 무대"}
            del by_key[(team, day, kind)]
    return list(by_key.values())


def detect_events(signals: Sequence[Row], outcomes: Sequence[Row], tiers: Dict[str, str], city: Dict[str, str],
                  as_of: str) -> List[Row]:
    by_team, outs = _group(signals), _group(outcomes)
    events: List[Row] = []
    for team in sorted(set(by_team) | set(outs)):
        rows = sorted((s for s in by_team.get(team, []) if _day(s) and _day(s) <= as_of and is_mention(s)), key=_day)
        events += _dedupe(_mention_events(team, rows) + _gig_events(team, rows, tiers, city)
                          + _outcome_events(team, outs.get(team, []), as_of))
    return events


# ---------- 별점 ----------

def score_event(event: Row, stage: int) -> Tuple[int, str]:
    """(별 1~5, 이유 문장). 같은 사건이라도 그때 작은 팀일수록 높다."""
    base = int(event["base"])
    adj = STAGE_ADJ.get(stage, 0)
    if event.get("no_history"):          # 우리 기록의 첫 공연이 큰 무대 = 이미 큰 팀일 수 있음(내한·기성 팀) → 작은 팀 가산 없음
        adj = min(adj, 0)
    bonus = 1 if event.get("tier_jump") else 0
    stars = max(1, min(5, base + adj + bonus))
    parts = [f"{KIND_LABELS.get(str(event['kind']), event['kind'])} — {event.get('detail', '')}", f"기본 {base}",
             f"그때 '{STAGE_LABELS.get(stage, stage)}' {adj:+d}"]
    if event.get("no_history"):
        parts.append("우리 기록의 첫 공연이라 그 전 체급 모름(작은 팀 가산 없음)")
    if bonus:
        parts.append("체급 점프(그 전엔 S급 무대뿐) +1")
    return stars, " · ".join(parts) + f" → {stars}"


# ---------- 전후 28일 ----------

def window_counts(rows: Sequence[Row], day: str, as_of: str, days: int = WINDOW) -> Dict[str, int]:
    start, end = _shift(day, -days), _shift(day, days)
    observed = max(0, min(days, (date.fromisoformat(as_of) - date.fromisoformat(day)).days))
    gigs_b, gigs_a, men_b, men_a = set(), set(), set(), set()
    for s in rows:
        d = _day(s)
        if not d or d == day or d > as_of or not is_mention(s):
            continue
        before, after = start <= d < day, day < d <= end
        if not (before or after):
            continue
        if s.get("branch") == "공연":
            (gigs_b if before else gigs_a).add(d)
        else:
            (men_b if before else men_a).add((d, s.get("source"), s.get("program")))
    return {"gigs_before_28": len(gigs_b), "gigs_after_28": len(gigs_a), "mentions_before_28": len(men_b),
            "mentions_after_28": len(men_a), "after_window_days": observed}


# ---------- 조립 ----------

def build_rows(data: dict, as_of: str) -> List[Row]:
    signals, outcomes = data["signals"], data["outcomes"]
    by_team, outs = _group(signals), _group(outcomes)
    rows: List[Row] = []
    for e in detect_events(signals, outcomes, data["tiers"], data["venue_city"], as_of):
        team = str(e["team_key"])
        stage = stage_before(by_team.get(team, []), outs.get(team, []), str(e["date"]))
        stars, reason = score_event(e, stage)
        rows.append({"team_key": team, "date": e["date"], "kind": e["kind"], "stars": stars, "reason": reason,
                     "kind_label": KIND_LABELS[str(e["kind"])], "stage_at": stage, "detail": e["detail"],
                     **window_counts(by_team.get(team, []), str(e["date"]), as_of)})
    rows.sort(key=lambda r: (str(r["team_key"]), str(r["date"]), KINDS.index(str(r["kind"]))))
    return rows


def write_csv(rows: Iterable[Row], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in COLUMNS})


def tier_map(capacity: Optional[dict]) -> Dict[str, str]:
    return {v: str(info["tier"]) for v, info in ((capacity or {}).get("venues") or {}).items()
            if isinstance(info, dict) and info.get("tier")}


def venue_city_map(cfg: Optional[dict]) -> Dict[str, str]:
    """공연장 이름(대표·별칭·우리 데이터 이름) → 도시 (config/venues_kr.json)."""
    out: Dict[str, str] = {}
    for e in (cfg or {}).get("venues", []):
        c = e.get("city")
        if not c:
            continue
        for n in [e.get("name"), e.get("our_venue"), *(e.get("aliases") or []), *(e.get("our_names") or [])]:
            if n:
                out.setdefault(str(n), str(c))
    return out


def _read_csv(path: Path) -> List[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _read_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_data(data_dir: Path, capacity_path: Path = CAPACITY, venues_path: Path = VENUES_KR) -> Tuple[dict, str]:
    meta = json.loads((data_dir / "meta.json").read_text(encoding="utf-8"))
    return ({"signals": _read_csv(data_dir / "signals.csv"), "outcomes": _read_csv(data_dir / "outcomes.csv"),
             "tiers": tier_map(_read_json(capacity_path)), "venue_city": venue_city_map(_read_json(venues_path))},
            meta["data_end"])


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="사건 별점 → docs/lab/data/event_stars.csv")
    ap.add_argument("--data-dir", type=Path, default=LAB_DATA)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--as-of", default=None, help="기준일 (기본: meta.json data_end)")
    args = ap.parse_args(argv)
    data, data_end = load_data(args.data_dir)
    rows = build_rows(data, args.as_of or data_end)
    write_csv(rows, args.out)
    by_kind: Dict[str, int] = defaultdict(int)
    for r in rows:
        by_kind[str(r["kind_label"])] += 1
    five = sum(1 for r in rows if r["stars"] == 5)
    print(f"✅ 사건 {len(rows)}건 (5별 {five}) · " + ", ".join(f"{k} {v}" for k, v in by_kind.items()) + f" → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
