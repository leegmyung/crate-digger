"""공연장 사다리 — 공연장 체급(수용 인원)으로 팀의 '체급 흐름'과 공연장 전후 흐름을 본다 → docs/venue_ladder.md

Chartmetric 'Venue Journey'(이 공연장 전·후에 선 공연장)의 국내 인디판(docs/research_2026-11-27_competitor_logic.md D2).
1. 체급: config/venue_capacity.json (스탠딩 최대, 없으면 좌석) → S ~150 · M ~400 · L ~1,000 · XL 1,001~.
2. 팀별 사다리: 기준일 전 공연(발굴 출처, 기준일 전 3년)의 처음 체급 → 최근 체급, 최고 체급, 체급 상승 여부·속도.
3. 검증: 체급 상승이 정답을 미리 알려 주는지 — 점수 v2에 특징으로 하나씩 더해 기준일 6개 교차 검증
   (feature_lab 과 같은 방법·같은 채택 기준. 점수·계산식은 바꾸지 않음, 제안만).
4. 공연장 전후 흐름: 공연장마다 '처음 선 팀들이 그 전 1년에 선 곳 / 그 뒤 1년에 처음 선 곳' 상위.

누수 금지: 사다리는 기준일 '전' 공연만. 수용 인원은 '지금' 값(공연장 이전·확장은 반영 못 함 — 문서에 적음).
페스티벌: 한 공연(같은 날·같은 공연장)에 12팀 넘게 서면 빼서, 큰 무대 한 번이 '체급 상승'으로 잡히지 않게 한다.

실행: .venv/bin/python scripts/venue_ladder.py [--data-dir 폴더] [--no-eval]   → docs/venue_ladder.md
읽기만 한다(랩 CSV·config). PostgreSQL·랩 데이터는 쓰지 않는다.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab_sql  # noqa: E402

CONFIG = lab_sql.ROOT / "config" / "venue_capacity.json"
OUT = lab_sql.ROOT / "docs" / "venue_ladder.md"
LOOKBACK_YEARS = 3          # 점수 v2 신호 창과 같게
MAX_EVENT_TEAMS = 12        # 이보다 많은 팀이 선 공연은 페스티벌로 보고 뺀다 (docs/scene_map.md 와 같은 기준)
RECENT_DAYS = 365           # '최근 체급 상승' = 기준일 전 1년 안에 처음으로 더 큰 체급에 섬
JOURNEY_DAYS = 365          # 공연장 전후 흐름 창
JOURNEY_MIN_TEAMS = 15      # 처음 선 팀이 이만큼 이상인 공연장만 표로
JOURNEY_TOP = 3
JOURNEY_ROWS = 30

Gig = Tuple[str, date, str]   # (팀, 날짜, 공연장)

# (특징 키, 이름, 정의)
FEATURES: Tuple[Tuple[str, str, str], ...] = (
    ("tier_rise", "체급 상승 칸 수", "기준일 전 3년 공연에서 최고 체급 − 처음 체급 (0~3칸, 수용 인원을 아는 공연장만)"),
    ("max_tier", "최고 체급", "기준일 전 3년 공연 중 가장 큰 체급 (없음 0 · S 1 · M 2 · L 3 · XL 4)"),
    ("recent_rise", "최근 1년 체급 상승", "기준일 전 1년 안에 처음으로 더 큰 체급 공연장에 섬 (1/0)"),
    ("tier_rise_assume_small", "체급 상승 (모르는 공연장 = S 가정)",
     "수용 인원을 모르는 공연장을 모두 S(~150)로 보고 센 체급 상승 칸 수 — 민감도 확인용"),
)
NAMES = {k: n for k, n, _ in FEATURES}
DEFAULT_ORDER = ("S", "M", "L", "XL")


# ---------- 체급 ----------

def tier_of(capacity: Optional[float], tiers: Sequence[dict]) -> Optional[str]:
    """capacity 가 max 이하인 첫 체급 (max=None 은 끝까지)."""
    if capacity is None:
        return None
    for t in tiers:
        if t.get("max") is None or capacity <= t["max"]:
            return t["tier"]
    return None


def load_config(path: Path = CONFIG) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def tier_order(cfg: dict) -> List[str]:
    return [t["tier"] for t in cfg["tiers"]]


def venue_tiers(cfg: dict) -> Dict[str, str]:
    """수용 인원을 아는 공연장 → 체급."""
    return {v: d["tier"] for v, d in cfg["venues"].items() if d.get("capacity") and d.get("tier")}


def not_venues(cfg: dict) -> Set[str]:
    """공연장이 아닌 표기(예: '축제') — 체급 판정에서 아예 뺀다."""
    return {v for v, d in cfg["venues"].items() if d.get("not_venue")}


def validate(cfg: dict) -> List[str]:
    """설정 점검: 수용 인원이 양수인지, 적힌 체급이 기준과 맞는지, 수용 인원이 있으면 근거 링크가 있는지."""
    problems = []
    for v, d in cfg["venues"].items():
        cap, tier = d.get("capacity"), d.get("tier")
        if cap is None:
            if tier is not None:
                problems.append(f"{v}: 수용 인원 없이 체급 {tier}")
            continue
        if not isinstance(cap, (int, float)) or cap <= 0:
            problems.append(f"{v}: 수용 인원이 양수가 아님 ({cap})")
            continue
        if tier != tier_of(cap, cfg["tiers"]):
            problems.append(f"{v}: 체급 {tier} ≠ 기준상 {tier_of(cap, cfg['tiers'])} (수용 {cap})")
        if not d.get("source"):
            problems.append(f"{v}: 근거 링크(source) 없음")
    return problems


# ---------- 팀별 사다리 ----------

@dataclass(frozen=True)
class Ladder:
    first_tier: Optional[str]
    last_tier: Optional[str]
    max_tier: Optional[str]
    known_gigs: int                  # 체급을 아는 공연 수
    rise_steps: int                  # 최고 − 처음 (칸)
    first_rise_date: Optional[date]  # 처음 체급보다 큰 공연장에 처음 선 날
    days_to_rise: Optional[int]      # 첫 공연(체급 아는) → 첫 상승까지 일수
    recent_rise: bool                # 최고 체급에 처음 오른 날이 기준일 전 1년 안 (그리고 상승이 있음)


EMPTY = Ladder(None, None, None, 0, 0, None, None, False)


def festival_nights(gigs: Iterable[Gig], max_event_teams: int = MAX_EVENT_TEAMS) -> Set[Tuple[date, str]]:
    teams: Dict[Tuple[date, str], Set[str]] = defaultdict(set)
    for t, d, v in gigs:
        teams[(d, v)].add(t)
    return {k for k, s in teams.items() if len(s) > max_event_teams}


def _in_window(d: date, cutoff: date, lookback_years: Optional[int]) -> bool:
    if d >= cutoff:
        return False
    if lookback_years is None:
        return True
    return d >= date(cutoff.year - lookback_years, cutoff.month, cutoff.day)


def _ladder(items: Sequence[Tuple[date, str]], idx: Dict[str, int], recent_from: date) -> Ladder:
    """체급 아는 공연(날짜순)으로 사다리 한 줄."""
    first_d, first = items[0]
    best, best_from, rise_d = first, first_d, None
    for d, tr in items[1:]:
        if rise_d is None and idx[tr] > idx[first]:
            rise_d = d
        if idx[tr] > idx[best]:
            best, best_from = tr, d
    steps = idx[best] - idx[first]
    return Ladder(first, items[-1][1], best, len(items), steps, rise_d,
                  (rise_d - first_d).days if rise_d else None, steps > 0 and best_from >= recent_from)


def team_ladders(gigs: Iterable[Gig], venue_tier: Dict[str, str], cutoff: date,
                 lookback_years: Optional[int] = LOOKBACK_YEARS, max_event_teams: int = MAX_EVENT_TEAMS,
                 unknown_tier: Optional[str] = None, order: Sequence[str] = DEFAULT_ORDER,
                 skip_venues: Iterable[str] = ()) -> Dict[str, Ladder]:
    """기준일 전(lookback_years 년 안) 공연으로 팀마다 체급 흐름. 페스티벌(팀 수 초과) 공연은 뺀다.
    unknown_tier 를 주면 수용 인원을 모르는 공연장을 그 체급으로 본다(민감도 확인용)."""
    skip = set(skip_venues)
    rows = [g for g in gigs if _in_window(g[1], cutoff, lookback_years) and g[2] not in skip]
    fest = festival_nights(rows, max_event_teams)
    idx = {t: i for i, t in enumerate(order)}
    by_team: Dict[str, List[Tuple[date, Optional[str]]]] = defaultdict(list)
    for t, d, v in rows:
        if (d, v) not in fest:
            by_team[t].append((d, venue_tier.get(v, unknown_tier)))
    recent_from = cutoff - timedelta(days=RECENT_DAYS)
    out = {}
    for t, items in by_team.items():
        known = sorted((d, tr) for d, tr in items if tr is not None)
        out[t] = _ladder(known, idx, recent_from) if known else EMPTY
    return out


def ladder_features(ladders: Dict[str, Ladder], order: Sequence[str] = DEFAULT_ORDER) -> Dict[str, Dict[str, float]]:
    idx = {t: i for i, t in enumerate(order)}
    return {t: {"tier_rise": float(lad.rise_steps),
                "max_tier": float(idx[lad.max_tier] + 1) if lad.max_tier else 0.0,
                "recent_rise": 1.0 if lad.recent_rise else 0.0} for t, lad in ladders.items()}


def tier_transitions(ladders: Dict[str, Ladder]) -> Counter:
    """(처음 체급, 최근 체급) 쌍의 팀 수."""
    return Counter((lad.first_tier, lad.last_tier) for lad in ladders.values() if lad.first_tier)


# ---------- 공연장 전후 흐름 (Venue Journey) ----------

def venue_journey(gigs: Iterable[Gig], window_days: int = JOURNEY_DAYS, min_teams: int = JOURNEY_MIN_TEAMS,
                  max_event_teams: int = MAX_EVENT_TEAMS, skip_venues: Iterable[str] = ()) -> Dict[str, dict]:
    """공연장 V마다: V에 처음 선 팀 수, 그 팀들이 그 전 window 안에 선 공연장(팀당 1번), 그 뒤 window 안에
    '처음' 선 공연장(팀당 1번, 이미 가 본 곳 제외). 페스티벌 공연은 뺀다."""
    skip = set(skip_venues)
    rows = [g for g in gigs if g[2] not in skip]
    fest = festival_nights(rows, max_event_teams)
    by_team: Dict[str, List[Tuple[date, str]]] = defaultdict(list)
    for t, d, v in rows:
        if (d, v) not in fest:
            by_team[t].append((d, v))
    win = timedelta(days=window_days)
    teams_at: Counter = Counter()
    before: Dict[str, Counter] = defaultdict(Counter)
    after: Dict[str, Counter] = defaultdict(Counter)
    for items in by_team.values():
        items.sort()
        first_at: Dict[str, date] = {}
        for d, v in items:
            first_at.setdefault(v, d)
        for v, d0 in first_at.items():
            teams_at[v] += 1
            before[v].update({u for d, u in items if d0 - win <= d < d0 and u != v})
            after[v].update({u for u, du in first_at.items() if d0 < du <= d0 + win})
    return {v: {"teams": n, "before": before[v].most_common(), "after": after[v].most_common()}
            for v, n in teams_at.items() if n >= min_teams}


# ---------- 검증 (feature_lab 과 같은 방법) ----------

def extra_features(sigs: Sequence[dict], rows: Sequence[dict], cutoff: date, cfg: dict) -> Dict[str, Dict[str, float]]:
    """후보 팀(rows)마다 사다리 특징. 기준일 전 3년 발굴 공연만."""
    import feature_lab as fl

    gig_rows = fl.gigs(fl.window(sigs, cutoff, LOOKBACK_YEARS, ("discovery",)))
    vt, skip, order = venue_tiers(cfg), not_venues(cfg), tier_order(cfg)
    known = ladder_features(team_ladders(gig_rows, vt, cutoff, order=order, skip_venues=skip), order)
    small = team_ladders(gig_rows, vt, cutoff, unknown_tier=order[0], order=order, skip_venues=skip)
    zero = {"tier_rise": 0.0, "max_tier": 0.0, "recent_rise": 0.0}
    out = {}
    for r in rows:
        t = r["team_key"]
        out[t] = {**known.get(t, zero), "tier_rise_assume_small": float(small[t].rise_steps) if t in small else 0.0}
    return out


def evaluate(data_dir: Path = lab_sql.DATA_DIR, cfg: Optional[dict] = None) -> dict:
    import feature_lab as fl
    import score_tune as st

    cfg = cfg or load_config()
    con = lab_sql.connect(data_dir)
    data = {c: st.features(con, c) for c in st.CUTOFFS}
    sigs, _ = fl.load_events(con)
    extra = {c: extra_features(sigs, data[c], date.fromisoformat(c), cfg) for c in st.CUTOFFS}
    res = {}
    for f, _, _ in FEATURES:
        r = fl.evaluate_feature(data, extra, f, fl.GRID_FINE)
        r["coarse"] = fl.evaluate_feature(data, extra, f, fl.GRID)
        r["boot"] = fl.bootstrap_diff(data, r)
        r["desc"] = fl.describe(data, extra, f)
        res[f] = r
    return {"singles": res}


def verdict(r: dict) -> str:
    """feature_lab 과 같은 채택 기준."""
    import feature_lab as fl

    gain = r["cv_mean"] - r["base_mean"]
    keeps = r["cv_hits"]["hits50"] >= r["base_hits"]["hits50"]
    if gain >= fl.ADOPT_MIN_GAIN and r["boot"][1] > 0 and keeps:
        return "채택 후보"
    if gain > 0 and keeps:
        return "지켜볼 것"
    return "효과 없음"


# ---------- 설명 숫자 ----------

def until(gigs: Iterable[Gig], end: date) -> List[Gig]:
    """end 이후(예정 공연)는 뺀다 — 아직 열리지 않은 공연은 '선 곳'이 아니다."""
    return [g for g in gigs if g[1] <= end]


def data_end(data_dir: Path) -> date:
    """랩 데이터의 기준 날짜(meta.json data_end). 없으면 오늘."""
    try:
        return date.fromisoformat(json.loads((data_dir / "meta.json").read_text(encoding="utf-8"))["data_end"])
    except (OSError, KeyError, ValueError):
        return date.today()


def all_gigs(data_dir: Path) -> Tuple[List[Gig], date]:
    """데이터 끝 날짜까지의 전체 발굴 공연(기간 제한 없음)과 그 날짜."""
    import feature_lab as fl

    sigs, _ = fl.load_events(lab_sql.connect(data_dir))
    end = data_end(data_dir)
    return until(fl.gigs([s for s in sigs if s["role"] == "discovery"]), end), end


def export(ladders: Dict[str, Ladder], journey: Dict[str, dict], vt: Dict[str, str], as_of: date) -> dict:
    """앱 화면용 JSON(팀 상세 '공연장 사다리', 공연장 상세 '전후 흐름'). 체급을 아는 팀만."""
    teams = {t: {"first": lad.first_tier, "last": lad.last_tier, "max": lad.max_tier, "steps": lad.rise_steps,
                 "rise_date": lad.first_rise_date.isoformat() if lad.first_rise_date else None,
                 "days_to_rise": lad.days_to_rise}
             for t, lad in sorted(ladders.items()) if lad.first_tier}
    venues = {v: {"tier": vt.get(v), "teams": j["teams"],
                  "before": [[u, c] for u, c in j["before"][:5]], "after": [[u, c] for u, c in j["after"][:5]]}
              for v, j in sorted(journey.items())}
    return {"as_of": as_of.isoformat(), "teams": teams, "venues": venues}


def coverage(gigs: Sequence[Gig], cfg: dict) -> dict:
    vt, skip = venue_tiers(cfg), not_venues(cfg)
    nights = {(d, v) for _, d, v in gigs if v not in skip}
    known_n = {(d, v) for d, v in nights if v in vt}
    return {"nights": len(nights), "known_nights": len(known_n),
            "teams": len({t for t, _, v in gigs if v not in skip}),
            "teams_known": len({t for t, _, v in gigs if v in vt}),
            "by_tier": Counter(vt[v] for _, v in known_n), "venues_known": len(vt)}


# ---------- 문서 ----------

def _fa(v: Optional[float]) -> str:
    return "—" if v is None else f"{v:.3f}"


def _pct(a: int, b: int) -> str:
    return f"{a / b:.1%}" if b else "—"


def _vname(v: str, vt: Dict[str, str]) -> str:
    return f"{v} ({vt[v]})" if v in vt else v


def _tier_section(cfg: dict, cov: dict) -> List[str]:
    vt, tiers = venue_tiers(cfg), cfg["tiers"]
    lines = ["## 1. 체급 기준과 수용 인원", "",
             "| 체급 | 수용 인원(스탠딩 최대, 없으면 좌석) | 확인한 공연장 (예) |", "|---|---|---|"]
    prev = 0
    for t in tiers:
        rng = f"{prev + 1:,}명~" if t["max"] is None else f"{prev + 1:,}~{t['max']:,}명"
        ex = ", ".join(sorted(v for v, tr in vt.items() if tr == t["tier"])[:7])
        lines.append(f"| {t['tier']} | {rng} | {ex or '—'} |")
        prev = t["max"] or prev
    lines += [
        "",
        "- **제안 이유:** 150명 이하는 클럽·카페·소극장, 151~400명은 웨스트브릿지·프리즘홀·상상마당 홍대 같은 소형 라이브홀, "
        "401~1,000명은 롤링홀·무신사 개러지·원더로크홀처럼 '단독 공연이 의미 있는' 중형 라이브홀, 1,001명 이상은 대형입니다. "
        "상상마당 홍대(스탠딩 400)와 롤링홀(450)이 400 경계에 걸려 있어, 경계를 옮기면 결과가 달라질 수 있습니다"
        "(설정 파일의 `tiers`만 고치면 됨).",
        "- **근거:** 대부분 나무위키 '공연장' 문서의 1,000석 미만 표(2026-11-25 편집본), 일부 방문강남·헤이팝. "
        "공연장마다 링크·확인일·확실도(high/medium)를 적었습니다.",
        f"- **수용 인원을 확인한 공연장 {cov['venues_known']}곳** (공연 횟수 상위 100곳 기준). 작은 클럽(Club 빵·Club FF·"
        "언플러그드·오방가르드·Club Victim 등)은 공식 사이트·대관 안내·위키·기사에 숫자가 없어 비웠습니다.",
        f"- **덮는 비율:** 발굴 출처 공연 날짜(같은 날·같은 공연장 = 1건) {cov['nights']:,}건 중 체급 아는 공연장 "
        f"{cov['known_nights']:,}건({_pct(cov['known_nights'], cov['nights'])}), 공연한 팀 {cov['teams']:,}팀 중 체급 아는 공연장에 "
        f"선 팀 {cov['teams_known']:,}팀({_pct(cov['teams_known'], cov['teams'])}). 체급별 공연 날짜: "
        + " · ".join(f"{t['tier']} {cov['by_tier'].get(t['tier'], 0):,}" for t in tiers) + ".",
        "- ⚠️ **공연장 연결표 문제 발견:** 상상마당 공연 원본은 '라이브홀 (KT&G 상상마당 홍대)'처럼 지점이 괄호에 있는데, "
        "연결표(`scripts/venue_xref.py`)가 끝 괄호를 떼어 대표 이름이 '라이브홀'·'3층 라이브홀'·'사운드홀'·'아트홀'이 됩니다. "
        "그래서 '라이브홀'(= 상상마당 홍대, 공연 317일)과 'KT&G 상상마당 홍대 라이브홀'(50일)이 다른 공연장으로 갈라져 있습니다"
        "('같은 무대' 점수·씬 지도에도 영향). 설정 파일에는 원본을 확인해 같은 수용 인원을 넣었고, 연결표에 묶는 줄을 넣자고 제안합니다.",
        "- 수용 인원은 **지금** 값입니다. 공연장이 이전·확장했으면 과거 공연의 체급이 다를 수 있습니다.", ""]
    return lines


def _ladder_section(cfg: dict, ladders_now: Dict[str, Ladder], end: date) -> List[str]:
    tiers = cfg["tiers"]
    with_tier = [lad for lad in ladders_now.values() if lad.first_tier]
    rise = [lad for lad in with_tier if lad.rise_steps > 0]
    days = sorted(lad.days_to_rise for lad in rise if lad.days_to_rise is not None)
    lines = [f"## 2. 팀별 사다리 (데이터 끝 {end}까지 — 예정 공연 제외, 전체 기간 발굴 출처 공연, 페스티벌 제외)", "",
             f"- 체급 아는 공연장에 선 팀 {len(with_tier):,}팀 중 **체급이 한 칸 이상 오른 팀 {len(rise):,}팀**"
             f"({_pct(len(rise), len(with_tier))})."]
    if days:
        mid = days[len(days) // 2]
        lines.append(f"- 오른 팀의 '체급 아는 첫 공연 → 첫 상승' 기간 중앙값 **{mid}일**(약 {mid / 30.4:.0f}개월), "
                     f"25%·75% 지점 {days[len(days) // 4]}일·{days[(3 * len(days)) // 4]}일.")
    lines += ["", "**처음 체급 → 최근 체급 (팀 수)**", "",
              "| 처음 \\ 최근 | " + " | ".join(t["tier"] for t in tiers) + " |", "|---|" + "---|" * len(tiers)]
    tr = tier_transitions(ladders_now)
    for a in tiers:
        lines.append(f"| {a['tier']} | " + " | ".join(f"{tr.get((a['tier'], b['tier']), 0):,}" for b in tiers) + " |")
    lines += ["", "읽는 법: 대각선은 같은 체급에 머문 팀, 오른쪽 위는 올라간 팀, 왼쪽 아래는 큰 곳에 선 뒤 작은 곳에서도 공연한 팀입니다. "
              "작은 클럽 대부분이 '체급 모름'이라 S에서 시작한 팀이 적게 잡힙니다 — 실제 '작은 클럽 → 라이브홀' 상승은 이 표보다 많습니다.", ""]
    return lines


def _eval_section(ev: dict) -> List[str]:
    import feature_lab as fl
    import score_tune as st

    singles = ev["singles"]
    base = next(iter(singles.values()))
    bh = base["base_hits"]
    defs = {k: d for k, _, d in FEATURES}
    lines = ["## 3. 체급 상승이 정답을 미리 알려 주나 — 점수 v2에 더해 교차 검증", "",
             f"[점수 새 특징 실험](feature_lab.md)과 같은 방법입니다. 기준일 6개({', '.join(st.CUTOFFS)}), 관찰 "
             f"{st.HORIZON_MONTHS}개월, 정답 등급 가중 AUC. 특징을 표준편차 1로 맞추고 가중치 후보 0(= v2 그대로)·"
             f"{', '.join(f'{g:g}' for g in fl.GRID_FINE)}점 중 기준일 하나를 뺀 나머지로 고른 뒤 뺀 기준일에서 채점했습니다. "
             f"채택 기준(미리 정함, feature_lab과 같음): 평균 AUC +{fl.ADOPT_MIN_GAIN} 이상, 95% 구간 하한 > 0, 상위 50 적중이 줄지 않음.", "",
             f"v2 그대로: 평균 AUC **{_fa(base['base_mean'])}**, 상위 20 / 50 / 100 적중 합계 "
             f"{bh['hits20']} / {bh['hits50']} / {bh['hits100']}.", "",
             "| 특징 | 정의 | 평균 AUC (교차) | 차이 | 95% 구간 | 오른·내린 기준일 | 상위 20 / 50 / 100 | 고른 가중치 | "
             "0 아닌 후보 | 평균: 정답 / 아닌 팀 | 판정 |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for f, r in singles.items():
        b, h = r["boot"], r["cv_hits"]
        picks = ", ".join(sorted({f"{w:g}" for w in r["picks"].values()}))
        lines.append(f"| {NAMES[f]} | {defs[f]} | {_fa(r['cv_mean'])} | {r['cv_mean'] - r['base_mean']:+.3f} | "
                     f"{b[1]:+.3f} ~ {b[2]:+.3f} | {r['wins']} / {r['losses']} | {h['hits20']} / {h['hits50']} / {h['hits100']} | "
                     f"{picks} | {r['desc']['nonzero']:.1%} | {r['desc']['hit_mean']:.2f} / {r['desc']['non_mean']:.2f} | {verdict(r)} |")
    lines += ["", "1차 격자(미리 정한 " + ", ".join(f"{g:g}" for g in fl.GRID) + "점)로 잰 차이: " + " · ".join(
        f"{NAMES[f]} {r['coarse']['cv_mean'] - r['coarse']['base_mean']:+.3f}" for f, r in singles.items()) + ".", "",
              "(평균 정답 / 아닌 팀은 표준화 전 값, 기준일 6개 합침 — 라벨을 보는 참고용이고 가중치 고르기에는 안 썼습니다.)", ""]
    rise_nz = singles["tier_rise"]["desc"]["nonzero"]
    mt = singles["max_tier"]["desc"]
    lines += [f"**읽는 법:** 체급 상승이 잡힌 후보는 {rise_nz:.1%}뿐이라(대부분 체급 모르는 작은 클럽에서 공연) 이 특징은 거의 재지 못한 것과 같습니다. "
              f"'최고 체급'은 정답 팀 평균이 {mt['hit_mean']:.2f}로 아닌 팀({mt['non_mean']:.2f})보다 높지만, 더하면 오히려 내려갑니다 — "
              "큰 공연장 기록 대부분이 상상마당 공연(이미 점수에 들어간 발굴 출처)이라 새 정보가 없다는 뜻입니다.", ""]
    adopt = [f for f, r in singles.items() if verdict(r) == "채택 후보"]
    if adopt:
        lines.append("**요청(코디네이터):** " + ", ".join(NAMES[f] for f in adopt) + " — 채택 기준을 넘었습니다. "
                     "`docs/lab/sql/features.sql`의 `lab_scored`에 기본 0인 인자(예: `w_" + adopt[0] + " := 0`)로 넣고, "
                     "체급 표를 랩 데이터로 내보낸 뒤 `score_tune.GRID`에 넣어 다시 고르는 것을 요청합니다(앱 기본값은 사용자 확인 뒤).")
    else:
        lines.append("**결론:** 채택 기준을 넘는 특징이 없습니다. 체급 상승은 **점수에 넣지 않고 화면 정보로만** 씁니다"
                     "(팀 상세의 '공연장 사다리', 공연장 상세의 '전후 흐름'). 작은 클럽 수용 인원이 채워지거나 공연 기록이 1년 더 쌓이면 다시 잽니다.")
    return lines + [""]


def _tier_flow(journey: Dict[str, dict], vt: Dict[str, str], tiers: Sequence[dict]) -> List[str]:
    flow: Dict[str, Counter] = defaultdict(Counter)
    for v, j in journey.items():
        if v in vt:
            for u, c in j["after"]:
                if u in vt:
                    flow[vt[v]][vt[u]] += c
    names = [t["tier"] for t in tiers]
    out = ["| 처음 선 공연장 체급 \\ 그 뒤 처음 선 공연장 체급 | " + " | ".join(names) + " | 합 |",
           "|---|" + "---|" * (len(names) + 1)]
    for a in names:
        tot = sum(flow[a].values())
        if tot:
            out.append(f"| {a} | " + " | ".join(f"{flow[a][b]} ({flow[a][b] / tot:.0%})" for b in names) + f" | {tot} |")
    return out if len(out) > 2 else ["(체급 아는 공연장끼리 이어진 흐름이 없음)"]


def _journey_section(journey: Dict[str, dict], cfg: dict) -> List[str]:
    vt = venue_tiers(cfg)
    lines = [f"## 4. 공연장 전후 흐름 (Venue Journey) — 처음 선 팀 {JOURNEY_MIN_TEAMS}팀 이상인 공연장 상위 {JOURNEY_ROWS}곳", "",
             f"공연장마다 그곳에 **처음** 선 팀들이 그 전 1년 안에 선 공연장, 그 뒤 1년 안에 **처음** 선 공연장 상위 {JOURNEY_TOP}곳"
             "(팀 수·비율). 괄호는 체급(모르면 없음). 전체 기간 발굴 출처 공연, 페스티벌 제외.", "",
             "| 공연장 | 처음 선 팀 | 그 전 1년에 선 곳 | 그 뒤 1년에 처음 선 곳 |", "|---|---|---|---|"]
    for v, j in sorted(journey.items(), key=lambda kv: (-kv[1]["teams"], kv[0]))[:JOURNEY_ROWS]:
        n = j["teams"]

        def fmt(pairs: Sequence[Tuple[str, int]]) -> str:
            return " · ".join(f"{_vname(u, vt)} {c}({c / n:.0%})" for u, c in pairs[:JOURNEY_TOP]) or "—"
        lines.append(f"| {_vname(v, vt)} | {n:,} | {fmt(j['before'])} | {fmt(j['after'])} |")
    lines += ["", "**체급으로 묶어 보기** — 체급 아는 공연장끼리, '이 체급 공연장에 처음 선 팀이 그 뒤 1년에 처음 선 공연장'의 체급 분포"
              f"(위 표 기준 {JOURNEY_MIN_TEAMS}팀 이상 공연장만):", ""]
    return lines + _tier_flow(journey, vt, cfg["tiers"])


LIMITS = ["", "## 5. 화면에 쓰는 법 (제안)", "",
          "- **팀 상세 → 공연장 사다리:** 처음 체급 → 최고 체급 → 최근 체급과 첫 상승 날짜(예: 'M 상상마당 홍대 → L 롤링홀, 2025-03 상승'). "
          "점수 구성과 따로, '참고' 표시로.",
          "- **공연장 상세 → 전후 흐름:** 위 4절 표처럼 '여기 처음 선 팀들이 그 전에 선 곳 / 그 뒤 처음 선 곳' 상위 5곳과 체급.",
          "- 데이터: `.venv/bin/python scripts/venue_ladder.py --json docs/lab/data/venue_ladder.json` (팀별 사다리 + 공연장별 전후 흐름, "
          "체급 아는 팀만). 매일 실행에 넣을지는 코디네이터가 정함.", "",
          "## 6. 한계", "",
          "- 체급을 아는 공연장이 적고 작은 클럽이 거의 다 비어 있어 '작은 클럽 → 라이브홀' 상승을 대부분 놓칩니다. "
          "'모르는 공연장 = S' 가정으로 민감도를 함께 쟀습니다.",
          "- 공연 기록이 인디스트릿(2024-01~)·상상마당(2010~) 위주라, 2023년 기준일에는 상상마당 공연장(M·L)만 보입니다.",
          "- 상상마당 공연은 그 자체가 발굴 출처(성적이 좋은 출처)라, '상상마당 공연장에 섰다'와 '체급이 올랐다'가 겹칩니다.",
          "- 수용 인원은 지금 값이고, 공연이 그 공연장의 큰 방인지 작은 방인지(로비·루프탑 등)는 이름으로만 구분합니다."]


def render(cfg: dict, cov: dict, ladders_now: Dict[str, Ladder], journey: Dict[str, dict],
           ev: Optional[dict], end: date) -> str:
    head = ["# 공연장 사다리 — 공연장 체급으로 본 팀의 흐름", "",
            "_자동 생성: `.venv/bin/python scripts/venue_ladder.py` · 체급 원본 "
            "[`config/venue_capacity.json`](../config/venue_capacity.json)_", "",
            "Chartmetric의 'Venue Journey'(이 공연장에 선 팀들이 그 전·후 어느 공연장에 섰나)를 우리 공연 데이터로 만든 것입니다"
            "([경쟁 서비스 조사 D2](research_2026-11-27_competitor_logic.md)). 공연장 크기(수용 인원)로 **체급**을 나누고, "
            "팀이 작은 곳에서 큰 곳으로 올라가는지 봅니다.", ""]
    body = _tier_section(cfg, cov) + _ladder_section(cfg, ladders_now, end)
    body += _eval_section(ev) if ev else ["## 3. 교차 검증", "", "(`--no-eval` 로 건너뜀)", ""]
    return "\n".join(head + body + _journey_section(journey, cfg) + LIMITS) + "\n"


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="공연장 사다리 → docs/venue_ladder.md")
    ap.add_argument("--data-dir", type=Path, default=lab_sql.DATA_DIR)
    ap.add_argument("--config", type=Path, default=CONFIG)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--no-eval", action="store_true", help="교차 검증은 건너뛰고 설명 숫자만")
    ap.add_argument("--json", type=Path, default=None,
                    help="앱 화면용 JSON도 쓴다 (예: docs/lab/data/venue_ladder.json — 21~23시엔 쓰지 말 것)")
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    problems = validate(cfg)
    if problems:
        print("⚠️ 설정 문제:\n- " + "\n- ".join(problems))
        return 1
    gigs, end = all_gigs(args.data_dir)
    skip = not_venues(cfg)
    ladders_now = team_ladders(gigs, venue_tiers(cfg), end + timedelta(days=1), lookback_years=None,
                               order=tier_order(cfg), skip_venues=skip)
    journey = venue_journey(gigs, skip_venues=skip)
    ev = None if args.no_eval else evaluate(args.data_dir, cfg)
    args.out.write_text(render(cfg, coverage(gigs, cfg), ladders_now, journey, ev, end), encoding="utf-8")
    print(f"✅ → {args.out}")
    if args.json:
        payload = export(ladders_now, journey, venue_tiers(cfg), end)
        args.json.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        print(f"✅ → {args.json} (팀 {len(payload['teams']):,} · 공연장 {len(payload['venues']):,})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
