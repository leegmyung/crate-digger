"""매일 알림 → docs/data/alerts.json — 경쟁 서비스(Soundcharts·Songstats·Viberate) 공통 기본 기능인 '알림'의 데이터 쪽.

랩 데이터(docs/lab/data: signals·outcomes·teams·programs, 점수 스냅샷 snapshots/)와 발굴 단계(docs/lab/sql/discovery_stage.sql)로
'오늘 새로 생긴 일'을 찾는다. '새로' = 지난 실행 때 본 상태(data/raw/state/alerts_state.json, 커밋 안 함)에 없던 것.
상태 파일이 없으면(첫 실행) 기준일 7일 전까지를 이미 본 것으로 친다. 같은 날 두 번 돌려도 같은 알림이 나오게 그날의 기준선을 남긴다.

알림 종류: 단계 상승 · 새 정답 · 새 선정·지원 · 백지 신인 첫 언급 · 순위 급상승(지난주 스냅샷 대비) · 큰 공연장 첫 출연
(config/venue_capacity.json 이 있을 때만) · 같은 무대 수상 팀(새 연결) · 새 공연(앱이 관심 목록 팀만 걸러 보임).
각 알림 = 종류·팀 키·이름·날짜(그 일이 일어난/일어날 날 — 선정은 기간 끝날이라 미래일 수 있음)·알게 된 날(found_on)·
한 줄 설명·근거(신호 출처)·중요도. 종류별 상한, 중요도 순. 공개 데이터라 팀 이름까지만 쓴다.

실행: .venv/bin/python scripts/build_alerts.py [--as-of YYYY-MM-DD] [--no-state] [--out 파일]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parent.parent
LAB_DATA = ROOT / "docs" / "lab" / "data"
OUT = ROOT / "docs" / "data" / "alerts.json"
STATE = ROOT / "data" / "raw" / "state" / "alerts_state.json"
CAPACITY = ROOT / "config" / "venue_capacity.json"

WINDOW_DAYS = 7                 # 상태 파일이 없을 때: 기준일 7일 전까지는 이미 본 것
SNAP_GAP_DAYS = 7               # 순위 비교: 지난주 스냅샷
RANK_JUMP_MIN = 50              # 이만큼 이상 오르면 급상승
RANK_TOP = 100                  # 이 순위 안에 든 팀만 급상승·새 진입 알림
BIG_TIERS = ("L", "XL")         # 큰 공연장 = 401명 이상 (config/venue_capacity.json tiers)
UNKNOWN_VENUES = ("", "공연장 미정")
DEFAULT_CAP = 20
CAPS = {"new_gig": 300}         # 새 공연은 앱이 관심 목록 팀만 걸러 보므로 넉넉히
CANDIDATE_TOP = 300             # 오늘 후보 상위 300(스냅샷)에 있으면 중요도 가점
EVIDENCE_MAX = 3

STAGE_LABELS = {0: "백지", 1: "첫 신호", 2: "여러 갈래", 3: "선정·중간 정답", 4: "졸업"}
SELECTION_STAGE = {0: "응모", 1: "서류 통과", 2: "라인업·쇼케이스", 3: "선정", 4: "최종"}
GRADE_POINTS = {"S": 30, "A": 20, "B": 10}
TYPES = {   # 종류 → (이름, 기본 중요도)
    "new_outcome": ("새 정답", 100),
    "new_selection": ("새 선정·지원", 70),
    "blank_first_mention": ("백지 신인 첫 언급", 65),
    "stage_up": ("단계 상승", 50),
    "big_venue_first": ("큰 공연장 첫 출연", 55),
    "peer_winner": ("같은 무대 수상 팀", 45),
    "rank_jump": ("순위 급상승", 40),
    "new_gig": ("새 공연", 10),
}
BASE = {k: v[1] for k, v in TYPES.items()}

Signal = Dict[str, object]
Alert = Dict[str, object]


# ---------- 작은 도우미 ----------

def signal_key(s: Signal) -> str:
    """신호 한 줄의 짧은 지문 (팀·갈래·출처·프로그램·날짜·공연장)."""
    raw = "|".join(str(s.get(k) or "") for k in ("team_key", "branch", "source", "program", "signal_date", "venue"))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def outcome_key(o: Dict[str, object]) -> str:
    return "|".join(str(o.get(k) or "") for k in ("team_key", "program", "announced_date"))


def _truthy(v) -> bool:
    return v is True or str(v).lower() == "true"


def _mention(s: Signal) -> bool:
    """남의 언급(발굴 단계와 같은 정의): 자기 발매 아님, 제외 출처·DMZ 아님."""
    return s.get("branch") != "발매" and s.get("role") != "excluded" and s.get("program") != "dmz_lineup"


def _evidence(rows: Iterable[Signal]) -> List[Dict[str, str]]:
    out = []
    for s in list(rows)[:EVIDENCE_MAX]:
        e = {"branch": s.get("branch"), "source": s.get("source"), "program": s.get("program"),
             "date": s.get("signal_date"), "venue": s.get("venue")}
        out.append({k: v for k, v in e.items() if v})
    return out


def _alert(kind: str, team: str, teams: Dict[str, str], day: str, text: str,
           evidence: Optional[List[Dict[str, str]]] = None, bonus: float = 0, **extra) -> Alert:
    return {"type": kind, "type_label": TYPES[kind][0], "team_key": team, "name": teams.get(team, team),
            "date": day, "text": text, "evidence": evidence or [], "importance": BASE[kind] + bonus, **extra}


def _by_team(rows: Iterable[Signal]) -> Dict[str, List[Signal]]:
    out: Dict[str, List[Signal]] = defaultdict(list)
    for s in rows:
        out[str(s["team_key"])].append(s)
    return out


# ---------- 알림 찾기 ----------

def detect_stage_up(now: Dict[str, int], before: Dict[str, int], teams: Dict[str, str], as_of: str,
                    new_signals: Sequence[Signal] = ()) -> List[Alert]:
    """발굴 단계가 오른 팀. 졸업(4)은 새 정답 알림과 겹치고 유명 판정 시작일에 몰려서 뺀다."""
    new_by = _by_team(s for s in new_signals if _mention(s))
    out = []
    for team in sorted(now):
        s, b = int(now[team]), int(before.get(team, 0))
        if b < s < 4 and s >= 1:
            text = f"{STAGE_LABELS[b]} → {STAGE_LABELS[s]}" if team in before else f"새로 나타난 팀 — 바로 {STAGE_LABELS[s]}"
            out.append(_alert("stage_up", team, teams, as_of, text,
                              _evidence(new_by.get(team, [])), bonus=5 * s, stage=s))
    return out


def detect_new_selection(new_signals: Sequence[Signal], teams: Dict[str, str], programs: Dict[str, str]) -> List[Alert]:
    seen: Set[Tuple[str, str]] = set()
    out = []
    for s in new_signals:
        if s.get("branch") != "선정·지원" or not _mention(s):
            continue
        team, prog = str(s["team_key"]), str(s.get("program") or s.get("source") or "")
        if (team, prog) in seen:
            continue
        seen.add((team, prog))
        rank = int(s["stage_rank"]) if s.get("stage_rank") not in (None, "") else None
        step = SELECTION_STAGE.get(rank, "") if rank is not None else ""
        text = f"{programs.get(prog, prog)} {step}".strip()
        out.append(_alert("new_selection", team, teams, str(s.get("signal_date") or ""), text, _evidence([s]),
                          bonus=5 * (rank or 0)))
    return out


def detect_new_outcomes(outcomes: Sequence[Dict[str, object]], known: Set[str], teams: Dict[str, str]) -> List[Alert]:
    out = []
    for o in outcomes:
        if not _truthy(o.get("counted")) or outcome_key(o) in known:
            continue
        grade = str(o.get("grade") or "")
        label = o.get("program_label") or o.get("program")
        out.append(_alert("new_outcome", str(o["team_key"]), teams, str(o.get("announced_date") or ""),
                          f"{label} ({grade}등급)" if grade else str(label),
                          [{"program": str(o.get("program") or ""), "date": str(o.get("announced_date") or "")}],
                          bonus=GRADE_POINTS.get(grade, 0)))
    return out


def detect_blank_first_mention(new_signals: Sequence[Signal], before: Dict[str, int], teams: Dict[str, str],
                               programs: Dict[str, str]) -> List[Alert]:
    """지난번에 백지(0단계)였던 신인이 처음 남에게 언급됨. 선정·지원이면 더 중요."""
    out = []
    for team, rows in sorted(_by_team(s for s in new_signals if _mention(s)).items()):
        if before.get(team) != 0:
            continue
        sel = [s for s in rows if s.get("branch") == "선정·지원"]
        first = (sel or rows)[0]
        where = programs.get(str(first.get("program") or ""), "") or first.get("program") or first.get("source")
        out.append(_alert("blank_first_mention", team, teams, str(first.get("signal_date") or ""),
                          f"백지 신인 첫 언급 — {first.get('branch')}: {where}", _evidence(sel + rows),
                          bonus=15 if sel else 0))
    return out


def detect_rank_jump(now: Dict[str, int], before: Dict[str, int], teams: Dict[str, str], as_of: str,
                     before_date: str, min_jump: int = RANK_JUMP_MIN, top: int = RANK_TOP) -> List[Alert]:
    """지난주 스냅샷 대비 순위 급상승 또는 상위권 새 진입 (스냅샷은 상위 300팀만 기록)."""
    out = []
    for team, r in sorted(now.items(), key=lambda kv: kv[1]):
        if r > top:
            continue
        b = before.get(team)
        ev = [{"source": "점수 스냅샷", "date": before_date}]
        if b is None:
            out.append(_alert("rank_jump", team, teams, as_of, f"상위 {top} 새 진입 ({r}위, {before_date}엔 300위 밖)", ev,
                              bonus=10, rank_before=None, rank_now=r))
        elif b - r >= min_jump:
            out.append(_alert("rank_jump", team, teams, as_of, f"{b}위 → {r}위 (+{b - r})", ev,
                              bonus=min((b - r) // 10, 20), rank_before=b, rank_now=r))
    return out


def detect_new_gigs(new_signals: Sequence[Signal], teams: Dict[str, str], as_of: str) -> List[Alert]:
    """새로 잡힌 '다가오는' 공연 (기준일 이후, 팀·날짜·공연장마다 한 건). 늦게 수집된 지난 공연은 팀 상세에서 보면 돼서 뺀다."""
    groups: Dict[Tuple[str, str, str], List[Signal]] = defaultdict(list)
    for s in new_signals:
        if s.get("branch") == "공연" and s.get("role") != "excluded" and str(s.get("signal_date") or "") >= as_of:
            groups[(str(s["team_key"]), str(s.get("signal_date") or ""), str(s.get("venue") or ""))].append(s)
    out = []
    for (team, day, venue), rows in sorted(groups.items()):
        upcoming = day >= as_of
        text = f"{'예정 공연' if upcoming else '공연'} {day} {venue or '공연장 미정'}"
        out.append(_alert("new_gig", team, teams, day, text, _evidence(rows), bonus=5 if upcoming else 0, upcoming=upcoming))
    return out


def venue_tiers(capacity: Optional[dict]) -> Dict[str, str]:
    if not capacity:
        return {}
    return {v: str(info.get("tier")) for v, info in (capacity.get("venues") or {}).items()
            if isinstance(info, dict) and info.get("tier")}


def detect_big_venue(new_signals: Sequence[Signal], all_signals: Sequence[Signal], capacity: Optional[dict],
                     teams: Dict[str, str]) -> List[Alert]:
    """처음으로 큰 공연장(L·XL)에 선(서는) 팀. 체급 파일이 없으면 건너뜀."""
    tiers = venue_tiers(capacity)
    if not tiers:
        return []
    new_keys = {signal_key(s) for s in new_signals}

    def big(s: Signal) -> bool:
        return s.get("branch") == "공연" and s.get("role") != "excluded" and tiers.get(str(s.get("venue") or "")) in BIG_TIERS
    had_big = {str(s["team_key"]) for s in all_signals if big(s) and signal_key(s) not in new_keys}
    out = []
    for team, rows in sorted(_by_team(s for s in new_signals if big(s)).items()):
        if team in had_big:
            continue
        first = min(rows, key=lambda s: str(s.get("signal_date")))
        venue = str(first.get("venue"))
        out.append(_alert("big_venue_first", team, teams, str(first.get("signal_date") or ""),
                          f"큰 공연장 첫 출연 — {venue} ({tiers[venue]}급)", _evidence([first])))
    return out


def peer_winner_pairs(signals: Sequence[Signal], outcomes: Sequence[Dict[str, object]]) -> Dict[str, Tuple[str, str, str, str]]:
    """같은 날·같은 공연장에 '그날 이미 센 정답을 받은 팀'과 선 팀 → {지문: (팀, 수상 팀, 날짜, 공연장)} (features.sql peer_winner 와 같은 뜻)."""
    first_win: Dict[str, str] = {}
    for o in outcomes:
        if _truthy(o.get("counted")):
            t, d = str(o["team_key"]), str(o.get("announced_date") or "")
            if d and (t not in first_win or d < first_win[t]):
                first_win[t] = d
    nights: Dict[Tuple[str, str], Set[str]] = defaultdict(set)
    for s in signals:
        if s.get("branch") == "공연" and s.get("role") != "excluded" and str(s.get("venue") or "") not in UNKNOWN_VENUES:
            nights[(str(s.get("signal_date")), str(s["venue"]))].add(str(s["team_key"]))
    pairs = {}
    for (day, venue), teams in nights.items():
        for w in teams:
            if w not in first_win or first_win[w] > day:
                continue
            for a in teams - {w}:
                if a in first_win and first_win[a] <= day:      # 이미 정답 받은 팀끼리는 알림 대상 아님
                    continue
                pairs[f"{a}|{w}|{day}|{venue}"] = (a, w, day, venue)
    return pairs


def detect_new_peer_winner(pairs: Dict[str, Tuple[str, str, str, str]], known: Set[str], teams: Dict[str, str]) -> List[Alert]:
    """새로 생긴 '수상 팀과 같은 무대' 연결 — 팀마다 한 건(수상 팀 이름을 모아서, 가장 최근 무대 날짜)."""
    by_team: Dict[str, List[Tuple[str, str, str]]] = defaultdict(list)
    for key, (a, w, day, venue) in pairs.items():
        if key not in known:
            by_team[a].append((day, w, venue))
    out = []
    for a, rows in sorted(by_team.items()):
        rows.sort(reverse=True)
        winners = list(dict.fromkeys(teams.get(w, w) for _, w, _ in rows))
        shown = ", ".join(winners[:3]) + (f" 외 {len(winners) - 3}팀" if len(winners) > 3 else "")
        out.append(_alert("peer_winner", a, teams, rows[0][0], f"같은 무대에 선 수상 팀: {shown}",
                          [{"branch": "공연", "date": d, "venue": v} for d, _, v in rows[:EVIDENCE_MAX]],
                          bonus=min(len(winners) - 1, 3) * 5, winners=[w for w in dict.fromkeys(w for _, w, _ in rows)]))
    return out


# ---------- 정렬·상한 ----------

def boost_candidates(alerts: Sequence[Alert], ranks: Dict[str, int]) -> List[Alert]:
    """오늘 후보 상위 300에 든 팀은 중요도 +15, 상위 50이면 +25. 원본은 바꾸지 않는다."""
    out = []
    for a in alerts:
        r = ranks.get(str(a["team_key"]))
        bonus = 0 if r is None or r > CANDIDATE_TOP else (25 if r <= 50 else 15)
        out.append({**a, "importance": a["importance"] + bonus, "rank": r})
    return out


def rank_and_cap(alerts: Sequence[Alert], caps: Optional[Dict[str, int]] = None, default_cap: int = DEFAULT_CAP) -> List[Alert]:
    caps = caps if caps is not None else CAPS
    ordered = sorted(alerts, key=lambda a: str(a.get("date") or ""), reverse=True)
    ordered = sorted(ordered, key=lambda a: -float(a["importance"]))
    used: Dict[str, int] = defaultdict(int)
    out = []
    for a in ordered:
        if used[a["type"]] < caps.get(a["type"], default_cap):
            used[a["type"]] += 1
            out.append(a)
    return out


# ---------- 기준선 ----------

def baseline_from_state(state: Optional[dict], as_of: str) -> Optional[dict]:
    """지난 실행 상태 → 오늘의 기준선. 같은 날 다시 돌리면 그날 처음 쓴 기준선을 그대로 쓴다."""
    if not state or not state.get("as_of"):
        return None
    if state["as_of"] == as_of:
        return state.get("baseline")
    if state["as_of"] < as_of:
        return state.get("current")
    return None


def _shift(day: str, days: int) -> str:
    return (date.fromisoformat(day) + timedelta(days=days)).isoformat()


def window_baseline(signals: Sequence[Signal], outcomes: Sequence[Dict[str, object]], as_of: str,
                    days: int = WINDOW_DAYS) -> dict:
    """상태가 없을 때: 기준일 − days 전 날짜의 신호·정답·같은 무대 연결을 이미 본 것으로."""
    cut = _shift(as_of, -days)
    old_sigs = [s for s in signals if str(s.get("signal_date") or "") < cut]
    old_outs = [o for o in outcomes if str(o.get("announced_date") or "") < cut]
    return {"signals": sorted(signal_key(s) for s in old_sigs), "outcomes": sorted(outcome_key(o) for o in old_outs),
            "pairs": sorted(peer_winner_pairs(old_sigs, old_outs))}


# ---------- 조립 ----------

def build(data: dict, stages_now: Dict[str, int], stages_before: Dict[str, int], baseline: Optional[dict],
          as_of: str) -> Tuple[dict, dict]:
    """알림 문서와 다음 실행용 상태."""
    signals, outcomes, teams = data["signals"], data["outcomes"], data["teams"]
    kind = "state" if baseline else "window"
    base = baseline or window_baseline(signals, outcomes, as_of)
    before = base.get("stages") or stages_before
    known_sig, known_out, known_pairs = set(base.get("signals", [])), set(base.get("outcomes", [])), set(base.get("pairs", []))
    new_sigs = [s for s in signals if signal_key(s) not in known_sig]
    pairs = peer_winner_pairs(signals, outcomes)

    blank = detect_blank_first_mention(new_sigs, before, teams, data.get("programs", {}))
    blank_teams = {a["team_key"] for a in blank}
    found = (detect_new_outcomes(outcomes, known_out, teams)
             + detect_new_selection(new_sigs, teams, data.get("programs", {}))
             + blank
             + [a for a in detect_stage_up(stages_now, before, teams, as_of, new_sigs)
                if not (a["team_key"] in blank_teams and int(before.get(a["team_key"], 0)) == 0)]
             + detect_big_venue(new_sigs, signals, data.get("capacity"), teams)
             + detect_new_peer_winner(pairs, known_pairs, teams)
             + detect_new_gigs(new_sigs, teams, as_of))
    snap_now, snap_before = data.get("snap_now") or {}, data.get("snap_before") or {}
    dates = data.get("snap_dates") or (None, None)
    if snap_now and snap_before and dates[1]:
        found += detect_rank_jump(snap_now, snap_before, teams, as_of, dates[1])
    counts = defaultdict(int)
    for a in found:
        counts[a["type"]] += 1
    alerts = [{**a, "found_on": as_of} for a in rank_and_cap(boost_candidates(found, snap_now))]
    doc = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "as_of": as_of,
        "baseline": {"kind": kind, "since": base.get("as_of") or _shift(as_of, -WINDOW_DAYS),
                     "note": "지난 실행 상태와 비교" if kind == "state" else f"상태 파일이 없어 기준일 {WINDOW_DAYS}일 전까지를 이미 본 것으로 침"},
        "snapshots": {"now": dates[0], "before": dates[1]},
        "types": {k: v[0] for k, v in TYPES.items()},
        "caps": {k: CAPS.get(k, DEFAULT_CAP) for k in TYPES},
        "counts_found": dict(counts),
        "counts_shown": {k: sum(1 for a in alerts if a["type"] == k) for k in TYPES if any(a["type"] == k for a in alerts)},
        "alerts": alerts,
    }
    current = {"as_of": as_of, "signals": sorted(signal_key(s) for s in signals),
               "outcomes": sorted(outcome_key(o) for o in outcomes), "pairs": sorted(pairs), "stages": dict(stages_now)}
    state = {"as_of": as_of, "current": current, "baseline": {**base, "stages": before}}
    return doc, state


# ---------- 읽기·실행 ----------

def _read_csv(path: Path) -> List[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _stage_rank(v) -> Optional[int]:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def read_snapshot(path: Path) -> Dict[str, int]:
    return {r["team_key"]: int(r["rank"]) for r in _read_csv(path)} if path.exists() else {}


def pick_snapshots(snap_dir: Path, as_of: str, gap: int = SNAP_GAP_DAYS) -> Tuple[Optional[str], Optional[str]]:
    """(오늘 쪽 스냅샷, 지난주 쪽 스냅샷) 날짜. 지난주 쪽은 gap일 이상 앞선 가장 최근 것, 없으면 더 이른 것 중 가장 최근."""
    days = sorted(p.stem for p in snap_dir.glob("*.csv") if p.stem <= as_of)
    if not days:
        return None, None
    now = days[-1]
    older = [d for d in days if d < now]
    far = [d for d in older if d <= _shift(now, -gap)]
    return now, (far[-1] if far else (older[-1] if older else None))


def load_data(data_dir: Path = LAB_DATA, as_of: Optional[str] = None, capacity_path: Path = CAPACITY) -> Tuple[dict, str]:
    meta = json.loads((data_dir / "meta.json").read_text(encoding="utf-8"))
    as_of = as_of or meta["data_end"]
    signals = [{**r, "stage_rank": _stage_rank(r.get("stage_rank"))} for r in _read_csv(data_dir / "signals.csv")]
    teams = {r["team_key"]: r.get("display_name") or r["team_key"] for r in _read_csv(data_dir / "teams.csv")}
    programs = {r["program"]: r.get("label") or r["program"] for r in _read_csv(data_dir / "programs.csv")}
    try:
        capacity = json.loads(capacity_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        capacity = None
    now, before = pick_snapshots(data_dir / "snapshots", as_of)
    data = {"signals": signals, "outcomes": _read_csv(data_dir / "outcomes.csv"), "teams": teams, "programs": programs,
            "capacity": capacity, "snap_dates": (now, before),
            "snap_now": read_snapshot(data_dir / "snapshots" / f"{now}.csv") if now else {},
            "snap_before": read_snapshot(data_dir / "snapshots" / f"{before}.csv") if before else {}}
    return data, as_of


def stages_at(con, day: str) -> Dict[str, int]:
    import lab_sql
    return {r["team_key"]: int(r["stage"]) for r in lab_sql.query(con, "discovery_stage.sql", as_of=f"'{day}'")}


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="매일 알림 만들기 → docs/data/alerts.json")
    ap.add_argument("--data-dir", type=Path, default=LAB_DATA)
    ap.add_argument("--as-of", default=None, help="기준일 (기본: 랩 데이터 meta.json 의 data_end)")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--state", type=Path, default=STATE)
    ap.add_argument("--no-state", action="store_true", help="상태 파일을 읽지도 쓰지도 않음(시험용, 7일 창으로 비교)")
    args = ap.parse_args(argv)
    import lab_sql

    data, as_of = load_data(args.data_dir, args.as_of)
    state = None
    if not args.no_state:
        try:
            state = json.loads(args.state.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            state = None
    baseline = baseline_from_state(state, as_of)
    con = lab_sql.connect(args.data_dir)
    stages_now = stages_at(con, as_of)
    stages_before = {} if baseline and baseline.get("stages") else stages_at(con, _shift(as_of, -WINDOW_DAYS))
    doc, new_state = build(data, stages_now, stages_before, baseline, as_of)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if not args.no_state:
        args.state.parent.mkdir(parents=True, exist_ok=True)
        args.state.write_text(json.dumps(new_state, ensure_ascii=False), encoding="utf-8")
    found = ", ".join(f"{TYPES[k][0]} {v}" for k, v in sorted(doc["counts_found"].items(), key=lambda kv: -kv[1]))
    print(f"✅ 알림 {len(doc['alerts'])}건 (찾은 것: {found or '없음'}, 비교: {doc['baseline']['note']}) → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
