"""국내 페스티벌 프로필 — Chartmetric 페스티벌 화면처럼(점수 대신 신인 비율·라인업 흐름) → docs/lab/data/festival_profiles.json

페스티벌 회차(연도)마다: 라인업 팀 수, 이 페스티벌에 처음 선 팀 비율(Chartmetric '신규 아티스트 비율'),
우리 데이터에서 첫 페스티벌이 이 무대였던 팀 비율(신인 비율), 우리가 다른 신호로 먼저 본 팀 비율,
그 뒤 처음 정답 받은 팀(기준일 규칙), 지금 후보 상위 팀. 페스티벌끼리 겹치는 팀과 이동 흐름(먼저 선 곳 → 뒤에 선 곳).

페스티벌로 보는 출처 (우리 데이터에 있는 것만, 2026-11-27 조사 — docs/festival_profiles.md 1절):
  부산국제록페스티벌 본무대 = 정답 outcomes 'burock_main'(B등급) · 부산록페 루키즈 = 신호 'burock_rookies'
  펜타포트 슈퍼루키 = 정답 'penta_superrookie'(A등급, 무대에 선 selected·winner 만 — finalist 는 결선까지만)
  DMZ 피스트레인 = 신호 'dmz_lineup' · 라이브클럽데이 = 공연장 인스타 '@liveclubday'
  (인디스트릿·인디고의 '축제'는 공연장 이름 표기라 페스티벌이 아님. 빌 순서(포스터 순서)는 원본에 없어 null.)
'같은 집안': 정답 프로그램과 같은 행사(부산록페 본무대·루키즈 ↔ 정답 burock_main, 펜타 슈퍼루키 ↔ 정답
penta_superrookie)는 표시하고, '그 뒤 정답'을 셀 때 그 정답 프로그램을 뺀다(행사가 자기 정답을 맞힌 것으로 세지 않게).

시점 규칙: 기준 날짜(meta.json data_end) 뒤 회차는 'upcoming'(라인업만, 정답 세지 않음).
'그 뒤 정답' = 같은 집안을 뺀 센 정답(counted) 중 팀의 첫 정답이 그 회차 날짜보다 '엄격하게 뒤'이고 기준 날짜 이하.
(이미 다른 정답을 받은 팀은 세지 않음 — venue_profiles 의 '나중에 정답 받은 팀'과 같은 규칙.)

실행: .venv/bin/python scripts/festival_profiles.py [--data-dir 폴더] [--out 경로] [--doc 경로|--no-doc]
      (21~23시엔 docs/lab/data 에 쓰지 말 것 — --out 으로 다른 곳에)
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Dict, Iterable, List, NamedTuple, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab_sql  # noqa: E402
import venue_ladder as vl  # noqa: E402
import venue_profiles as vp  # noqa: E402

OUT = lab_sql.DATA_DIR / "festival_profiles.json"
DOC = lab_sql.ROOT / "docs" / "festival_profiles.md"
TOP_CANDIDATES = 5
TOP_WINNERS = 10


@dataclass(frozen=True)
class Festival:
    key: str
    label: str
    kind: str                        # 'outcome'(정답 표에서) | 'signal'(신호 표에서)
    program: str                     # outcomes.program 또는 signals.program
    results: Tuple[str, ...] = ()    # outcome 일 때 라인업으로 볼 result (빈칸 = 전부)
    same_house: Tuple[str, ...] = ()  # 같은 행사의 정답 프로그램
    lineup: str = ""                 # config/festival_lineups.json 의 페스티벌 키 (라인업 표로 출연 보탬, 국내 팀만)


FESTIVALS: Tuple[Festival, ...] = (
    Festival("burock_main", "부산국제록페스티벌 본무대", "outcome", "burock_main", (), ("burock_main",), "burock"),
    Festival("burock_rookies", "부산록페 루키즈", "signal", "burock_rookies", (), ("burock_main",)),
    Festival("penta_superrookie", "펜타포트 슈퍼루키", "outcome", "penta_superrookie", ("selected", "winner"),
             ("penta_superrookie",)),
    Festival("dmz", "DMZ 피스트레인", "signal", "dmz_lineup", lineup="dmz"),
    Festival("liveclubday", "라이브클럽데이", "signal", "@liveclubday"),
    # 라인업 표만으로 보는 페스티벌 (config/festival_lineups.json, 2026-11-28 — 나무위키 연도별 라인업 표 옮김)
    Festival("penta_main", "인천 펜타포트 락 페스티벌", "lineup", "", (), ("penta_superrookie",), "penta"),
    Festival("gmf", "그랜드 민트 페스티벌", "lineup", "", lineup="gmf"),
    Festival("bml", "뷰티풀 민트 라이프", "lineup", "", lineup="bml"),
)
LINEUPS = lab_sql.ROOT / "config" / "festival_lineups.json"
XREF = lab_sql.ROOT / "data" / "raw" / "state" / "artist_xref.json"
BY_KEY = {f.key: f for f in FESTIVALS}


class Appearance(NamedTuple):
    festival: str
    team: str
    day: date
    role: str


# ---------- 모으기 ----------

def _day(v) -> Optional[date]:
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v or "")[:10])
    except ValueError:
        return None


def collect_appearances(signals: Iterable[dict], outcomes: Iterable[dict],
                        festivals: Sequence[Festival] = FESTIVALS, lineups: Optional[dict] = None,
                        key_of: Optional[Callable[[str], str]] = None) -> List[Appearance]:
    """신호·정답 표 (+ 라인업 표) → 페스티벌 출연 목록 (같은 페스티벌·팀·날짜는 1번).
    라인업 표(config/festival_lineups.json)는 korean=true 팀만 — 해외 팀은 팀 목록·비율 계산에 넣지 않는다."""
    by_sig = {f.program: f for f in festivals if f.kind == "signal"}
    by_out = {f.program: f for f in festivals if f.kind == "outcome"}
    seen = {}
    for r in signals:
        f = by_sig.get(r.get("program", ""))
        d = _day(r.get("signal_date"))
        if f and d and r.get("team_key"):
            seen.setdefault((f.key, r["team_key"], d), r.get("role") or "lineup")
    for o in outcomes:
        f = by_out.get(o.get("program", ""))
        d = _day(o.get("announced_date"))
        if f and d and o.get("team_key") and (not f.results or o.get("result") in f.results):
            key = (f.key, o["team_key"], d)
            if seen.get(key) != "winner":
                seen[key] = o.get("result") or "lineup"
    if lineups:
        key_of = key_of or (lambda n: n)
        by_line = {f.lineup: f for f in festivals if f.lineup}
        have = {(k[0], k[1], k[2].year) for k in seen}     # 같은 해 이미 다른 표로 잡힌 팀은 날짜만 다른 중복이라 뺌
        for lk, lf in lineups.get("festivals", {}).items():
            f = by_line.get(lk)
            if not f:
                continue
            for e in lf.get("editions", {}).values():
                for a in e.get("acts", []):
                    d = _day(a.get("day"))
                    team = key_of(a.get("name", ""))
                    if a.get("rookie_stage"):          # 부산록페 히든 스테이지 신인 경연 — 본무대 아님(정답 규칙과 같게)
                        continue
                    if a.get("korean") and d and team and (f.key, team, d.year) not in have:
                        seen.setdefault((f.key, team, d), "lineup")
    return sorted(Appearance(k[0], k[1], k[2], role) for k, role in seen.items())


def official_totals(lineups: Optional[dict], festivals: Sequence[Festival] = FESTIVALS) -> Dict[Tuple[str, str], int]:
    """(페스티벌 키, 연도) → 공식 라인업 전체 팀 수(해외 팀 포함, 라인업 표 기준)."""
    by_line = {f.lineup: f.key for f in festivals if f.lineup}
    out = {}
    for lk, lf in (lineups or {}).get("festivals", {}).items():
        for y, e in lf.get("editions", {}).items():
            if lk in by_line and e.get("official_total"):
                out[(by_line[lk], y)] = e["official_total"]
    return out


# 페스티벌라이프 목록 이름 → 라인업 페스티벌 키 (이름에 이 낱말이 들어 있으면 같은 페스티벌)
CATALOG_MATCH = (("펜타포트", "penta_main"), ("부산국제록", "burock_main"), ("부산국제락", "burock_main"),
                 ("그랜드민트", "gmf"), ("뷰티풀민트", "bml"), ("피스트레인", "dmz"), ("라이브클럽데이", "liveclubday"))
CATALOG = lab_sql.ROOT / "config" / "festival_catalog.json"


def _best_post(posts: List[dict]) -> str:
    """근거 글: '최종' 글 우선, 없으면 목록 첫 글(가장 최근)."""
    best = next((p for p in posts if "최종" in (p.get("kind") or "")), posts[0] if posts else {})
    return best.get("url", "")


def catalog_entries(catalog: Optional[dict]) -> List[dict]:
    """페스티벌라이프 목록(config/festival_catalog.json) → 화면용 [{name, festival(라인업 페스티벌 키|None), editions}].
    라인업은 포스터 그림이라 없음 — 회차마다 날짜·장소·근거 글(가장 최근 글) 주소만."""
    out = []
    for key, f in sorted((catalog or {}).get("festivals", {}).items()):
        squashed = key.replace(" ", "")
        match = next((fk for word, fk in CATALOG_MATCH if word in squashed), None)
        eds = {y: {"dates": e.get("dates") or [], "venue": e.get("venue") or "",
                   "url": _best_post(e.get("posts") or [])}
               for y, e in sorted(f.get("editions", {}).items())}
        if eds:
            out.append({"name": f.get("name") or key, "festival": match, "editions": eds})
    # 라인업 페스티벌과 연결된 곳 → 회차 많은 곳 → 최근 회차 순
    out.sort(key=lambda r: (r["festival"] is None, -len(r["editions"]), -int(max(r["editions"])), r["name"]))
    return out


def make_key_of(xref_path: Path = XREF) -> Callable[[str], str]:
    """이름 → 팀 키 (공연 원본이 팀 키를 만드는 것과 같은 규칙: 이름 키 → artist_xref 대표 키, 없으면 이름 키)."""
    import normalize as nz
    key2team: Dict[str, str] = {}
    if xref_path.exists():
        for e in json.loads(xref_path.read_text(encoding="utf-8")):
            for k in [*e.get("keys", []), e["artist_key"]]:
                key2team.setdefault(k, e["artist_key"])
    return lambda name: key2team.get(nz.artist_key(name), nz.artist_key(name))


def _first_signal_days(signals: Iterable[dict], festivals: Sequence[Festival]) -> Dict[str, date]:
    """페스티벌이 아닌 신호(공연·큐레이션·선정·발매)로 팀을 처음 본 날."""
    fest_programs = {f.program for f in festivals if f.kind == "signal"}
    first: Dict[str, date] = {}
    for r in signals:
        d = _day(r.get("signal_date"))
        if d and r.get("team_key") and r.get("program", "") not in fest_programs and r.get("role") != "excluded":
            t = r["team_key"]
            first[t] = min(first.get(t, d), d)
    return first


def _first_outcome(outcomes: Iterable[dict], exclude: Iterable[str], as_of: date) -> Dict[str, dict]:
    """팀마다 센 정답 중 가장 이른 것 (exclude 프로그램은 뺌, 기준일 이하만)."""
    ex = set(exclude)
    first: Dict[str, dict] = {}
    for o in sorted((o for o in outcomes if o.get("counted") and o.get("program") not in ex
                     and (d := _day(o.get("announced_date"))) and d <= as_of),
                    key=lambda o: _day(o["announced_date"])):
        first.setdefault(o["team_key"], o)
    return first


# ---------- 계산 ----------

def _share(n: int, d: int) -> Optional[float]:
    return round(n / d, 4) if d else None


def _months(a: date, b: date) -> int:
    return (b.year - a.year) * 12 + (b.month - a.month)


def build_profiles(apps: Sequence[Appearance], signals: Sequence[dict], outcomes: Sequence[dict],
                   teams: Dict[str, str], snapshot: Dict[str, Tuple[int, float]], as_of: date,
                   festivals: Sequence[Festival] = FESTIVALS) -> Dict[str, dict]:
    first_any = {}                                           # 팀의 첫 페스티벌 출연일
    for a in apps:
        first_any[a.team] = min(first_any.get(a.team, a.day), a.day)
    seen_from = _first_signal_days(signals, festivals)
    out = {}
    for f in festivals:
        mine = [a for a in apps if a.festival == f.key]
        if not mine:
            continue
        first_out = _first_outcome(outcomes, f.same_house, as_of)
        first_out_all = _first_outcome(outcomes, (), as_of)
        by_year: Dict[int, List[Appearance]] = defaultdict(list)
        for a in mine:
            by_year[a.day.year].append(a)
        editions = {}
        seen_here: set = set()
        for y in sorted(by_year):
            editions[str(y)] = _edition(by_year[y], seen_here, first_any, seen_from, first_out, first_out_all,
                                        teams, snapshot, as_of)
            seen_here |= {a.team for a in by_year[y]}
        out[f.key] = {
            "label": f.label, "kind": f.kind, "program": f.program,
            "same_house": ({"outcome_programs": list(f.same_house), "is_outcome": f.kind == "outcome",
                            "note": "정답 프로그램과 같은 행사 — '그 뒤 정답'에서 이 정답 프로그램을 뺐음"}
                           if f.same_house else None),
            "editions": editions,
            "teams_total": len({a.team for a in mine}),
            "overlaps": _overlaps(f.key, apps),
        }
    return out


def _edition(rows: List[Appearance], seen_here: set, first_any: Dict[str, date], seen_from: Dict[str, date],
             first_out: Dict[str, dict], first_out_all: Dict[str, dict], teams: Dict[str, str],
             snapshot: Dict[str, Tuple[int, float]], as_of: date) -> dict:
    day0 = min(a.day for a in rows)
    lineup = sorted({a.team for a in rows})
    team_day = {}
    for a in rows:
        team_day[a.team] = min(team_day.get(a.team, a.day), a.day)
    upcoming = day0 > as_of
    new_here = [t for t in lineup if t not in seen_here]
    first_fest = [t for t in lineup if first_any[t] == team_day[t]]
    seen_before = [t for t in lineup if t in seen_from and seen_from[t] < team_day[t]]
    winners, incl = [], 0
    if not upcoming:
        for t in lineup:
            o = first_out.get(t)
            if o and _day(o["announced_date"]) > team_day[t]:
                od = _day(o["announced_date"])
                winners.append({"team_key": t, "name": teams.get(t, t), "outcome": o.get("program_label", ""),
                                "grade": o.get("grade", ""), "outcome_date": od.isoformat(),
                                "lead_months": _months(team_day[t], od)})
            oa = first_out_all.get(t)
            if oa and _day(oa["announced_date"]) > team_day[t]:
                incl += 1
    winners.sort(key=lambda w: (w["outcome_date"], w["team_key"]))
    cands = sorted((t for t in lineup if t in snapshot), key=lambda t: snapshot[t][0])
    roles = {a.team: a.role for a in rows}
    return {
        "date": day0.isoformat(), "upcoming": upcoming, "lineup": len(lineup),
        "teams": [{"team_key": t, "name": teams.get(t, t), "role": roles[t], "bill_order": None} for t in lineup],
        "new_to_festival": len(new_here), "new_to_festival_share": _share(len(new_here), len(lineup)),
        "first_festival": len(first_fest), "first_festival_share": _share(len(first_fest), len(lineup)),
        "seen_before": len(seen_before), "seen_before_share": _share(len(seen_before), len(lineup)),
        "later_winners_total": len(winners), "later_winners": winners[:TOP_WINNERS],
        "later_winners_incl_same_house": incl,
        "top_candidates": [{"team_key": t, "name": teams.get(t, t), "rank": snapshot[t][0],
                            "score": snapshot[t][1]} for t in cands[:TOP_CANDIDATES]],
    }


def _first_by_festival(apps: Iterable[Appearance]) -> Dict[str, Dict[str, date]]:
    first: Dict[str, Dict[str, date]] = defaultdict(dict)
    for a in apps:
        cur = first[a.festival].get(a.team)
        first[a.festival][a.team] = a.day if cur is None else min(cur, a.day)
    return first


def _overlaps(key: str, apps: Sequence[Appearance]) -> List[dict]:
    first = _first_by_festival(apps)
    mine = first.get(key, {})
    rows = []
    for other, teams in first.items():
        if other == key:
            continue
        both = set(mine) & set(teams)
        if not both:
            continue
        rows.append({"festival": other, "label": BY_KEY[other].label if other in BY_KEY else other,
                     "teams": len(both),
                     "this_first": sum(1 for t in both if mine[t] < teams[t]),
                     "other_first": sum(1 for t in both if teams[t] < mine[t]),
                     "same_day": sum(1 for t in both if teams[t] == mine[t])})
    return sorted(rows, key=lambda r: (-r["teams"], r["festival"]))


def festival_flows(apps: Sequence[Appearance]) -> List[dict]:
    """페스티벌 A 에 먼저 서고 B 에 나중에 처음 선 팀 수(A→B), 걸린 개월 중앙값."""
    first = _first_by_festival(apps)
    flows: Dict[Tuple[str, str], List[int]] = defaultdict(list)
    for a_key, a_teams in first.items():
        for b_key, b_teams in first.items():
            if a_key == b_key:
                continue
            for t in set(a_teams) & set(b_teams):
                if a_teams[t] < b_teams[t]:
                    flows[(a_key, b_key)].append(_months(a_teams[t], b_teams[t]))
    return sorted(({"from": a, "to": b, "teams": len(m), "median_months": statistics.median(m)}
                   for (a, b), m in flows.items()), key=lambda r: (-r["teams"], r["from"], r["to"]))


# ---------- 결과물 ----------

def payload(profiles: Dict[str, dict], flows: List[dict], as_of: date) -> dict:
    return {
        "as_of": as_of.isoformat(),
        "notes": {
            "new_to_festival": "이 회차 라인업 중 이 페스티벌의 앞선 회차(우리 데이터)에 없던 팀 — Chartmetric '신규 아티스트 비율'",
            "first_festival": "우리 데이터의 첫 페스티벌 출연이 이 회차였던 팀 (신인 비율)",
            "seen_before": "이 회차 전에 우리 다른 신호(공연·큐레이션·선정·발매)로 먼저 본 팀",
            "later_winners": "같은 집안 정답을 뺀 첫 센 정답이 회차 날짜보다 뒤·기준일 이하인 팀",
            "later_winners_incl_same_house": "같은 집안을 빼지 않고 센 수 (비교용)",
            "bill_order": "포스터 순서 — 원본에 없어 null",
            "upcoming": "회차 날짜가 기준일 뒤 (정답 세지 않음)",
            "official_lineup": "공식 라인업 전체 팀 수(해외 팀 포함, config/festival_lineups.json 라인업 표) — lineup 은 그중 국내 팀만",
            "date": "회차 날짜 = 그 해 라인업 행 중 가장 이른 날짜(정답 표는 발표일, 신호 표는 공연·발표일)",
        },
        "festivals": profiles,
        "flows": flows,
    }


def _pct(v: Optional[float]) -> str:
    return "—" if v is None else f"{v * 100:.0f}%"


def render_doc(data: dict) -> str:
    fest = data["festivals"]
    lines = [
        "# 국내 페스티벌 프로필 — 회차별 라인업·신인 비율·페스티벌 간 흐름", "",
        "_자동 생성: `.venv/bin/python scripts/festival_profiles.py` · 앱 데이터 `docs/lab/data/festival_profiles.json`_", "",
        "Chartmetric 페스티벌 화면([안쪽 ②](research_2026-11-27_chartmetric_live.md) 2-4절)의 '주요 정보'(라인업 수·"
        "**신규 아티스트 비율**)와 라인업 표를 우리 데이터로 만든 것입니다. 그들에게 없는 칸 — **우리가 먼저 본 팀**, "
        "**그 뒤 정답 받은 팀**, 페스티벌 간 이동 — 을 더했습니다. 점수에는 넣지 않습니다.", "",
        f"기준 날짜 {data['as_of']}.", "",
        "## 1. 우리 데이터에 있는 페스티벌 (2026-11-27 조사)", "",
        "| 페스티벌 | 우리 데이터의 출처 | 회차 | 팀 | 같은 집안 |",
        "|---|---|---|---|---|",
    ]
    for k, f in fest.items():
        src = f"정답 표 `{f['program']}`" if f["kind"] == "outcome" else f"신호 표 `{f['program']}`"
        sh = "⚠️ " + ", ".join(f["same_house"]["outcome_programs"]) if f["same_house"] else "—"
        lines.append(f"| {f['label']} | {src} | {', '.join(f['editions'])} | {f['teams_total']} | {sh} |")
    lines += [
        "",
        "- 출처 역할(`config/source_roles.json`): DMZ 피스트레인 라인업은 '제외'(적중 0/103팀 — 이미 알려진 팀이 많음), 부산록페 루키즈는 '검증 대기'(2026년 명단만). 이 화면은 점수와 상관없는 설명 데이터입니다.",
        "- 페스티벌이 아닌 것: 인디스트릿·인디고의 공연장 칸 '축제'는 공연장 이름 표기(여러 곳)라 뺐습니다. 뮤콘·슈퍼루키챌린지는 쇼케이스·경연이라 뺐습니다.",
        "- **빌 순서(포스터 순서)** 는 원본에 없어 비웠습니다(`bill_order: null`). 펜타 슈퍼루키는 역할(winner·selected)만 있습니다.",
        "- **⚠️ 같은 집안:** 부산록페 본무대는 그 자체가 정답(B등급), 루키즈는 같은 행사, 펜타 슈퍼루키도 그 자체가 정답(A등급)입니다. "
        "'그 뒤 정답'을 셀 때 같은 행사의 정답은 뺐습니다(행사가 자기 무대를 정답으로 맞힌 것으로 세지 않게).",
        "- 정답 표의 부산록페는 지금 랩 데이터에 들어간 회차만 보입니다. 2021~2025 수기 보강분은 다음 랩 데이터 내보내기 뒤 자동으로 늘어납니다.",
        "", "## 2. 회차별 프로필", "",
        "| 페스티벌 | 회차 | 날짜 | 라인업 | 이 페스티벌 처음 | 첫 페스티벌(신인) | 우리가 먼저 봄 | 그 뒤 정답 | 지금 후보 상위 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for f in fest.values():
        for y, e in f["editions"].items():
            win = "예정" if e["upcoming"] else str(e["later_winners_total"])
            cands = ", ".join(f"{c['name']}({c['rank']})" for c in e["top_candidates"][:3]) or "—"
            lines.append(f"| {f['label']} | {y} | {e['date']} | {e['lineup']} | {_pct(e['new_to_festival_share'])} | "
                         f"{_pct(e['first_festival_share'])} | {_pct(e['seen_before_share'])} | {win} | {cands} |")
    lines += ["", "읽는 법: '이 페스티벌 처음' = Chartmetric 신규 아티스트 비율(앞선 회차에 없던 팀). "
              "'첫 페스티벌' = 우리 데이터에서 이 무대가 그 팀의 첫 페스티벌. '우리가 먼저 봄' = 회차 전에 공연·큐레이션·선정·발매 신호가 있던 팀. "
              "첫 회차는 '이 페스티벌 처음'이 100%가 됩니다(그 전 회차 기록 없음).", ""]
    winners = [(f["label"], y, w) for f in fest.values() for y, e in f["editions"].items() for w in e["later_winners"]]
    lines += ["## 3. 페스티벌 무대 뒤 처음 정답 받은 팀", ""]
    if winners:
        lines += ["| 페스티벌 | 회차 | 팀 | 정답 | 등급 | 정답 날짜 | 몇 달 뒤 |", "|---|---|---|---|---|---|---|"]
        lines += [f"| {lab} | {y} | {w['name']} | {w['outcome']} | {w['grade']} | {w['outcome_date']} | {w['lead_months']} |"
                  for lab, y, w in winners]
    else:
        lines.append("- 아직 없음.")
    lines += ["", "## 4. 페스티벌 간 이동 (먼저 선 곳 → 뒤에 처음 선 곳)", ""]
    if data["flows"]:
        lines += ["| 먼저 | 뒤에 | 팀 | 걸린 개월(중앙값) |", "|---|---|---|---|"]
        lines += [f"| {BY_KEY[r['from']].label} | {BY_KEY[r['to']].label} | {r['teams']} | {r['median_months']} |"
                  for r in data["flows"]]
    else:
        lines.append("- 두 페스티벌에 모두 선 팀이 없음.")
    lines += ["", "## 5. 화면에 쓰는 법 (제안)", "",
              "- 공연장·씬 메뉴에 '페스티벌' 탭: 페스티벌 카드(회차 칩) → 회차 화면 = 주요 정보 숫자 칸(라인업 · 이 페스티벌 처음 · 첫 페스티벌 · 우리가 먼저 봄 · 그 뒤 정답) + 라인업 표(팀 · 역할 · 발굴 단계 · 점수 · 첫 신호 날짜) + '다른 페스티벌과 겹치는 팀'.",
              "- 같은 집안 페스티벌은 회차 화면 머리에 ⚠️ 배지와 설명.",
              "- 한계: 라인업 출처가 4~5곳뿐이고(그랜드민트·펜타포트 본무대·서울재즈 등 없음), 빌 순서·무대 이름이 없습니다. 큰 페스티벌 라인업을 모으면 '작은 페스티벌 → 큰 페스티벌' 흐름을 다시 잽니다.", ""]
    return "\n".join(lines)


# ---------- 실행 ----------

def load(data_dir: Path) -> Tuple[List[dict], List[dict], Dict[str, str], Dict[str, Tuple[int, float]], date]:
    signals = vp._read_csv(data_dir / "signals.csv")
    outcomes = [{**r, "announced_date": _day(r["announced_date"]), "counted": r.get("counted") == "true"}
                for r in vp._read_csv(data_dir / "outcomes.csv") if _day(r.get("announced_date"))]
    _, teams, _, snap, as_of = vp.load_lab(data_dir)
    return signals, outcomes, teams, snap, as_of


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="국내 페스티벌 프로필 → docs/lab/data/festival_profiles.json")
    ap.add_argument("--data-dir", type=Path, default=lab_sql.DATA_DIR)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--doc", type=Path, default=DOC)
    ap.add_argument("--no-doc", action="store_true")
    args = ap.parse_args(argv)
    signals, outcomes, teams, snap, as_of = load(args.data_dir)
    lineups = json.loads(LINEUPS.read_text(encoding="utf-8")) if LINEUPS.exists() else None
    apps = collect_appearances(signals, outcomes, lineups=lineups, key_of=make_key_of())
    prof = build_profiles(apps, signals, outcomes, teams, snap, as_of)
    for (fk, y), n in official_totals(lineups).items():          # 회차마다 공식 라인업 전체 수(해외 포함)
        if y in prof.get(fk, {}).get("editions", {}):
            prof[fk]["editions"][y]["official_lineup"] = n
    data = payload(prof, festival_flows(apps), as_of)
    catalog = json.loads(CATALOG.read_text(encoding="utf-8")) if CATALOG.exists() else None
    data["catalog"] = catalog_entries(catalog)                     # 날짜·장소만 있는 페스티벌·회차 (페스티벌라이프)
    args.out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    if not args.no_doc:
        args.doc.write_text(render_doc(data), encoding="utf-8")
    n_ed = sum(len(f["editions"]) for f in prof.values())
    print(f"페스티벌 {len(prof)}곳 · 회차 {n_ed} · 출연 {len(apps)}건 · 흐름 {len(data['flows'])}개")
    print(f"✅ → {args.out}" + ("" if args.no_doc else f" · {args.doc}"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
