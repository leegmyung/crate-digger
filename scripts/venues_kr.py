"""한국 공연장·도시 마스터 목록(config/venues_kr.json) → 도시별 공연장 수·우리 커버리지·출처 공백 (docs/venues_kr.md).

    python3 scripts/venues_kr.py                  # docs/venues_kr.md 다시 만들기 (+ 형식 검사)
    python3 scripts/venues_kr.py --update-config  # 위 + 마스터 목록의 '우리 데이터에 있음'(in_our_data·our_venue) 갱신
    python3 scripts/venues_kr.py --seed EXTRA.json  # 처음 한 번: 우리 공연 데이터·공연장 인스타·인디고 공연장 페이지
                                                    #  + 웹 조사 목록(EXTRA)을 합쳐 마스터 목록을 만들거나 빈칸을 채움

왜: Chartmetric 의 '공연장(Venue)'·'도시(City)'처럼 공연장마다 도시·종류·크기·운영 여부를 알고,
우리 공연 데이터가 서울(홍대)에 얼마나 몰려 있는지, 지방 공연장 중 어디가 비어 있는지(= 출처 공백) 보려고.

읽는 것: config/venues_kr.json(마스터), docs/lab/data/signals.csv(공연 신호, 공연장 = venue_xref 대표 이름),
data/raw/raw_kr_gig_*.csv(괄호 속 주소 — 마스터에 없는 공연장의 도시를 정할 때), config/venue_capacity.json(옛 표기·수용 인원).
쓰는 것: docs/venues_kr.md (PostgreSQL·랩 데이터는 건드리지 않음).
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

import venue_xref as vx

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "venues_kr.json"
CAPACITY = ROOT / "config" / "venue_capacity.json"
SIGNALS = ROOT / "docs" / "lab" / "data" / "signals.csv"
OUT = ROOT / "docs" / "venues_kr.md"
REVIEW_DIR = ROOT / "data" / "raw" / "review"

TYPES = {"live_club": "라이브클럽", "hall": "홀·공연장", "theater": "소극장", "creation_center": "창작소·지원 시설",
         "cafe": "카페·바", "festival": "페스티벌·야외"}
TYPE_UNKNOWN = "미정"           # type 이 빈칸 = 공개 근거로 종류를 못 정함 (scripts/venue_types.py)
STATUSES = {"open": "운영", "paused": "휴업", "closed": "폐업", "unknown": "확인 필요"}
SEOUL = "서울"
UNKNOWN_CITY = "(도시 모름)"
NON_VENUE_CITY = "(공연장 미상: 기획·레이블·행사 계정)"   # 공연장이 아닌 인스타 계정의 라인업 글 — 어느 공연장인지 모름
NON_VENUE_ROLES = ("promoter_showcase", "label_showcase", "event_showcase")
INSTA_ACCOUNTS = ROOT / "config" / "insta_accounts.json"
GAP_MIN_DAYS = 3            # 우리 공연 날짜가 이보다 적으면 '거의 없음'
RECENT_DAYS = 365           # 우리 데이터 마지막 공연이 1년 안이면 '운영'으로 봄
NOT_VENUE = {"", "공연장 미정"}

SIDO = {
    "서울": "서울", "서울시": "서울", "서울특별시": "서울", "부산": "부산", "부산시": "부산", "부산광역시": "부산",
    "대구": "대구", "대구시": "대구", "대구광역시": "대구", "인천": "인천", "인천시": "인천", "인천광역시": "인천",
    "광주": "광주", "광주시": "광주", "광주광역시": "광주", "대전": "대전", "대전시": "대전", "대전광역시": "대전",
    "울산": "울산", "울산시": "울산", "울산광역시": "울산", "세종": "세종", "세종시": "세종", "세종특별자치시": "세종",
    "경기": "경기", "경기도": "경기", "강원": "강원", "강원도": "강원", "강원특별자치도": "강원",
    "충북": "충북", "충청북도": "충북", "충남": "충남", "충청남도": "충남",
    "전북": "전북", "전라북도": "전북", "전북특별자치도": "전북", "전남": "전남", "전라남도": "전남",
    "경북": "경북", "경상북도": "경북", "경남": "경남", "경상남도": "경남",
    "제주": "제주", "제주도": "제주", "제주특별자치도": "제주",
}
METRO = {"서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종"}
GWANGJU_GU = {"동구", "서구", "남구", "북구", "광산구"}
MERGED_GJ = "전남광주통합특별시"
EMPTY_REGION = {"province": "", "city": "", "district": ""}


# ---------- 지역·종류 ----------

def parse_region(address: str) -> Dict[str, str]:
    """주소 → {province: 시·도, city: 도시, district: 구·군}. 광역시는 도시 = 시·도, 도는 도시 = '…시'에서 '시'를 뗀 이름."""
    words = (address or "").replace(",", " ").split()
    if not words:
        return dict(EMPTY_REGION)
    head, rest = words[0], words[1:]
    if head == MERGED_GJ:                         # 2026 광주·전남 통합 이름: 광주 5개 구면 광주, 아니면 전남
        if rest and rest[0] in GWANGJU_GU:
            return {"province": "광주", "city": "광주", "district": rest[0]}
        head = "전남"
    province = SIDO.get(head)
    if not province:
        return dict(EMPTY_REGION)
    if province in METRO:
        gu = rest[0] if rest and re.search(r"[구군]$", rest[0]) else ""
        return {"province": province, "city": province, "district": gu}
    si = rest[0] if rest and re.search(r"[시군]$", rest[0]) else ""
    gu = rest[1] if si and len(rest) > 1 and re.search(r"구$", rest[1]) else ""
    city = re.sub(r"시$", "", si) if si.endswith("시") else si
    return {"province": province, "city": city or province, "district": gu}


def guess_type(name: str) -> str:
    """이름으로 종류 짐작 (마스터 목록에 type 이 있으면 그것을 씀)."""
    n = name.replace(" ", "")
    if re.search(r"창작소|창작지원|진흥센터|뮤지스탕스|문화재단", n):
        return "creation_center"
    if re.search(r"야외|페스티벌|축제|공원|광장", n):
        return "festival"
    if re.search(r"카페|cafe|다방|라운지|바$|살롱|펍|pub", n, re.I):
        return "cafe"
    if re.search(r"소극장|씨어터|시어터|theat(er|re)", n, re.I):
        return "theater"
    if re.search(r"홀|hall|아트센터|극장|소극장|예술의전당|문화회관|회관|센터", n, re.I):
        return "hall"
    return "live_club"


# ---------- 우리 공연 데이터 ----------

def gig_stats(rows: Iterable[dict], skip: Iterable[str] = ()) -> Dict[str, dict]:
    """공연 신호 → {공연장: {gig_days, teams(집합), first, last, sources(Counter)}}. 공연 날짜 = 같은 공연장·같은 날 1건.
    skip = 공연장이 아닌 이름(config/venue_capacity.json 의 not_venue, 예: '축제')."""
    skip_set = NOT_VENUE | set(skip)
    days: Dict[str, set] = defaultdict(set)
    teams: Dict[str, set] = defaultdict(set)
    sources: Dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        v = (r.get("venue") or "").strip()
        if r.get("branch") != "공연" or v in skip_set:
            continue
        d = r.get("signal_date", "")
        if d not in days[v]:
            sources[v][r.get("source", "")] += 1
        days[v].add(d)
        teams[v].add(r.get("team_key", ""))
    return {v: {"gig_days": len(ds), "teams": teams[v], "first": min(ds), "last": max(ds), "sources": sources[v]}
            for v, ds in days.items()}


def _keys(entry: dict) -> set:
    names = [entry["name"], *entry.get("aliases", [])]
    return {vx.venue_key(n) for n in names if n and not vx.is_generic(n)}


INSTA_URL = re.compile(r"instagram\.com/([A-Za-z0-9_.]+)")


def instagram_index(master: Sequence[dict]) -> Dict[str, int]:
    """{인스타 계정(소문자): 마스터 번호} — instagram 칸이 먼저, 다음 근거 링크의 instagram.com/<계정>."""
    out: Dict[str, int] = {}
    for i, e in enumerate(master):
        if e.get("instagram"):
            out.setdefault(e["instagram"].lower(), i)
    for i, e in enumerate(master):
        for s in e.get("sources", []):
            m = INSTA_URL.search(s.get("url", ""))
            if m and m.group(1).lower() not in ("p", "explore"):
                out.setdefault(m.group(1).lower(), i)
    return out


def match_our_venues(master: Sequence[dict], our_names: Iterable[str]) -> Dict[str, int]:
    """우리 공연장 이름(대표 이름) → 마스터 목록 번호. our_names(옛 표기) 정확히 → '@계정'은 인스타 계정 → 이름·별칭의 정규화 키 순.
    '라이브홀'처럼 지점 없는 일반 이름은 our_names 에 적힌 경우만 짝짓는다."""
    exact = {n: i for i, e in enumerate(master) for n in e.get("our_names", [])}
    by_key = {k: i for i, e in enumerate(master) for k in _keys(e)}
    by_handle = instagram_index(master)
    out: Dict[str, int] = {}
    for n in our_names:
        if n in exact:
            out[n] = exact[n]
        elif n.startswith("@") and n[1:].lower() in by_handle:
            out[n] = by_handle[n[1:].lower()]
        elif not vx.is_generic(n) and vx.venue_key(n) in by_key:
            out[n] = by_key[vx.venue_key(n)]
    return out


def city_kind(city: str) -> str:
    """도시 → 서울 / 지방 / 모름 (공연장 미상 계정도 '모름')."""
    if city == SEOUL:
        return SEOUL
    return UNKNOWN_CITY if city in (UNKNOWN_CITY, NON_VENUE_CITY, "") else "지방"


def venue_city(stats: Dict[str, dict], match: Dict[str, int], master: Sequence[dict],
               addresses: Dict[str, str], non_venue_handles: Iterable[str] = ()) -> Dict[str, str]:
    """우리 공연장 → 도시 (마스터 목록 → 공연 원본 주소 → 모름). 공연장이 아닌 인스타 계정('@계정')은 NON_VENUE_CITY."""
    skip = {h.lower() for h in non_venue_handles}
    out = {}
    for v in stats:
        if v.startswith("@") and v[1:].lower() in skip and v not in match:
            out[v] = NON_VENUE_CITY
        elif v in match and master[match[v]].get("city"):
            out[v] = master[match[v]]["city"]
        else:
            out[v] = parse_region(addresses.get(v, ""))["city"] or UNKNOWN_CITY
    return out


def city_distribution(stats: Dict[str, dict], city_of: Dict[str, str]) -> List[dict]:
    """도시별 공연장 수·공연 날짜·팀 수 (공연 날짜 많은 순)."""
    agg: Dict[str, dict] = defaultdict(lambda: {"venues": 0, "gig_days": 0, "teams": set()})
    for v, s in stats.items():
        a = agg[city_of.get(v, UNKNOWN_CITY)]
        a["venues"] += 1
        a["gig_days"] += s["gig_days"]
        a["teams"] |= s["teams"]
    rows = [{"city": c, "venues": a["venues"], "gig_days": a["gig_days"], "teams": len(a["teams"])}
            for c, a in agg.items()]
    return sorted(rows, key=lambda r: (-r["gig_days"], r["city"]))


def _matched_by_entry(match: Dict[str, int]) -> Dict[int, List[str]]:
    out: Dict[int, List[str]] = defaultdict(list)
    for name, i in match.items():
        out[i].append(name)
    return out


def entry_days(i: int, by_entry: Dict[int, List[str]], stats: Dict[str, dict]) -> int:
    return sum(stats[n]["gig_days"] for n in by_entry.get(i, []) if n in stats)


def coverage_by_city(master: Sequence[dict], match: Dict[str, int], stats: Dict[str, dict]) -> List[dict]:
    """도시별 마스터 공연장 수(운영·확인 필요) · 폐업·휴업 · 그중 우리 데이터에 있는 곳."""
    by_entry = _matched_by_entry(match)
    agg: Dict[str, dict] = defaultdict(lambda: {"venues": 0, "closed": 0, "in_data": 0, "gig_days": 0, "province": ""})
    for i, e in enumerate(master):
        a = agg[e.get("city") or UNKNOWN_CITY]
        a["province"] = a["province"] or e.get("province", "")
        if e.get("status") in ("closed", "paused"):
            a["closed"] += 1
            continue
        a["venues"] += 1
        d = entry_days(i, by_entry, stats)
        a["in_data"] += 1 if d else 0
        a["gig_days"] += d
    rows = [{"city": c, **a} for c, a in agg.items()]
    return sorted(rows, key=lambda r: (r["city"] != SEOUL, -r["venues"], r["city"]))


def source_gaps(master: Sequence[dict], match: Dict[str, int], stats: Dict[str, dict],
                min_days: int = GAP_MIN_DAYS) -> List[dict]:
    """서울 밖 · 폐업 아님 · 우리 공연 날짜 < min_days 인 공연장 (다른 곳 공연 기록이 많은 순)."""
    by_entry = _matched_by_entry(match)
    out = []
    for i, e in enumerate(master):
        if e.get("city") in ("", SEOUL) or e.get("status") in ("closed", "paused") or e.get("mainstream"):
            continue
        d = entry_days(i, by_entry, stats)
        if d < min_days:
            out.append({**e, "our_days": d})
    return sorted(out, key=lambda e: (-(e.get("indiego_past") or 0), -int(bool(e.get("instagram"))),
                                      e["city"], e["name"]))


OUR_DATA_NOTE = "우리 공연 데이터"


def external_coverage(master: Sequence[dict], match: Dict[str, int], stats: Dict[str, dict]) -> Dict[str, int]:
    """우리 데이터가 아닌 근거(기사·인스타·인디고·위키)가 하나라도 있는 공연장(폐업·휴업 뺌) 중 우리 데이터에 있는 곳.
    마스터 목록 일부가 우리 데이터에서 왔으므로, 바깥 근거만으로 센 커버리지가 덜 부풀려진 값이다."""
    by_entry = _matched_by_entry(match)
    out = {"external": 0, "in_data": 0, "seoul": 0, "seoul_in_data": 0}
    for i, e in enumerate(master):
        if e.get("status") in ("closed", "paused"):
            continue
        if not any(OUR_DATA_NOTE not in (s.get("note") or "") for s in e.get("sources", [])):
            continue
        hit = 1 if entry_days(i, by_entry, stats) else 0
        seoul = 1 if e.get("city") == SEOUL else 0
        out["external"] += 1
        out["in_data"] += hit
        out["seoul"] += seoul
        out["seoul_in_data"] += hit * seoul
    return out


def same_address_groups(master: Sequence[dict]) -> List[List[str]]:
    """도로명+건물번호가 같은 항목 묶음 — 같은 공연장의 다른 이름일 수 있어 사람이 확인."""
    groups: Dict[str, List[str]] = defaultdict(list)
    for e in master:
        k = vx.address_key(e.get("address", ""))
        if k:
            groups[k].append(e["name"])
    return sorted(sorted(g) for g in groups.values() if len(g) > 1)


# ---------- 검사·갱신 ----------

REQUIRED = ("name", "city", "province", "status", "checked")   # type 은 빈칸 허용(근거 없으면 '미정')


def validate(cfg: dict) -> List[str]:
    problems = []
    seen = Counter(e.get("name") for e in cfg.get("venues", []))
    for name, n in seen.items():
        if n > 1:
            problems.append(f"{name}: 같은 이름이 {n}번")
    for e in cfg.get("venues", []):
        name = e.get("name") or "(이름 없음)"
        missing = [k for k in REQUIRED if not e.get(k)]
        if missing:
            problems.append(f"{name}: 빈칸 {', '.join(missing)}")
        if e.get("type") and e["type"] not in TYPES:
            problems.append(f"{name}: 모르는 종류 {e['type']}")
        if e.get("status") and e["status"] not in STATUSES:
            problems.append(f"{name}: 모르는 운영 상태 {e['status']}")
        if not any(s.get("url") for s in e.get("sources", [])):
            problems.append(f"{name}: 근거 링크 없음")
        cap = e.get("capacity")
        if cap is not None and (not isinstance(cap, int) or cap <= 0):
            problems.append(f"{name}: 수용 인원이 양의 정수가 아님 ({cap})")
    return problems


def update_in_data(cfg: dict, stats: Dict[str, dict]) -> dict:
    """마스터 목록에 our_venue(우리 대표 이름, 공연 날짜 많은 것)·in_our_data 를 채운 새 설정을 돌려준다.
    '@계정'(인스타 라인업 글)은 대표 이름으로 쓰지 않는다 — venue_xref 가 our_venue 를 그 계정의 공연장 이름으로 쓰므로,
    '@계정'만 있으면 마스터 이름을 쓴다(연결표가 '@계정' → 마스터 이름으로 묶음)."""
    master = cfg["venues"]
    by_entry = _matched_by_entry(match_our_venues(master, stats))
    venues = []
    for i, e in enumerate(master):
        names = sorted(by_entry.get(i, []), key=lambda n: -stats[n]["gig_days"])
        plain = [n for n in names if not n.startswith("@")]
        our = plain[0] if plain else (e["name"] if names else None)
        venues.append({**e, "our_venue": our, "in_our_data": bool(names)})
    return {**cfg, "venues": venues}


# ---------- 읽기 ----------

def load_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def non_venue_handles(path: Path = INSTA_ACCOUNTS) -> set:
    """공연장이 아닌 라인업 계정(기획·레이블·행사, config/insta_accounts.json role)."""
    accounts = (load_json(path, {}) or {}).get("accounts", [])
    return {a["handle"].lower() for a in accounts if a.get("role") in NON_VENUE_ROLES and a.get("handle")}


def not_venue_names(path: Path = CAPACITY) -> set:
    return {n for n, v in ((load_json(path, {}) or {}).get("venues", {})).items() if v.get("not_venue")}


def load_signals(path: Path = SIGNALS) -> List[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def our_addresses() -> Dict[str, str]:
    """{우리 대표 이름: 공연 원본 주소} — 연결표(venue_xref.json)로 표기를 대표 이름에 모은다."""
    mapping = load_json(vx.XREF_PATH, {}) or {}
    out: Dict[str, str] = {}
    for name, addr in vx.collect_addresses().items():
        out.setdefault(mapping.get(name, name), addr)
        out.setdefault(name, addr)
    return out


# ---------- 문서 ----------

def _pct(a: float, b: float) -> str:
    return f"{a / b * 100:.1f}%" if b else "—"


def _src_label(e: dict) -> str:
    bits = []
    if e.get("instagram"):
        bits.append(f"인스타 @{e['instagram']}")
    if e.get("indiego_url"):
        bits.append(f"[인디고]({e['indiego_url']})" + (f" 지난 공연 {e['indiego_past']}" if e.get("indiego_past") else ""))
    return " · ".join(bits) or "—"


def _summary(master: Sequence[dict], match: Dict[str, int], stats: Dict[str, dict], dist: List[dict]) -> List[str]:
    alive = [e for e in master if e.get("status") not in ("closed", "paused")]
    seoul = [e for e in alive if e.get("city") == SEOUL]
    by_entry = _matched_by_entry(match)
    in_data = {i for i in by_entry if entry_days(i, by_entry, stats)}
    alive_idx = [i for i, e in enumerate(master) if e.get("status") not in ("closed", "paused")]
    seoul_in = sum(1 for i in alive_idx if master[i].get("city") == SEOUL and i in in_data)
    local_in = sum(1 for i in alive_idx if master[i].get("city") not in ("", SEOUL) and i in in_data)
    total_days = sum(d["gig_days"] for d in dist)
    seoul_days = sum(d["gig_days"] for d in dist if d["city"] == SEOUL)
    unknown_days = sum(d["gig_days"] for d in dist if city_kind(d["city"]) == UNKNOWN_CITY)
    nonvenue_days = sum(d["gig_days"] for d in dist if d["city"] == NON_VENUE_CITY)
    known_days = total_days - unknown_days
    status = Counter(e.get("status") for e in master)
    ext = external_coverage(master, match, stats)
    ext_local, ext_local_in = ext["external"] - ext["seoul"], ext["in_data"] - ext["seoul_in_data"]
    return [
        f"- 마스터 목록 **{len(master)}곳** — 운영 {status['open']} · 확인 필요 {status['unknown']} · "
        f"휴업 {status['paused']} · 폐업 {status['closed']}.",
        f"- 폐업·휴업을 뺀 {len(alive)}곳 중 **서울 {len(seoul)}곳 · 지방 {len(alive) - len(seoul)}곳**.",
        f"- 우리 공연 데이터에 나오는 곳: 서울 {seoul_in}/{len(seoul)} ({_pct(seoul_in, len(seoul))}) · "
        f"지방 {local_in}/{len(alive) - len(seoul)} ({_pct(local_in, len(alive) - len(seoul))}).",
        f"- 다만 목록 일부를 우리 데이터에서 만들었으므로 위 비율은 부풀려져 있습니다. **바깥 근거(기사·인스타·인디고·위키)가 있는 "
        f"{ext['external']}곳만 보면** 서울 {ext['seoul_in_data']}/{ext['seoul']} ({_pct(ext['seoul_in_data'], ext['seoul'])}) · "
        f"지방 {ext_local_in}/{ext_local} ({_pct(ext_local_in, ext_local)}).",
        f"- 우리 공연 날짜 {total_days:,}건 중 **서울 {seoul_days:,}건 ({_pct(seoul_days, total_days)})**. "
        f"도시를 아는 {known_days:,}건만 보면 서울 {_pct(seoul_days, known_days)} "
        f"(도시 모름 {unknown_days:,}건 — 그중 공연장이 아닌 기획·레이블·행사 계정 라인업 {nonvenue_days:,}건).",
    ]


def _coverage_section(cov: List[dict]) -> List[str]:
    lines = ["| 도시 | 시·도 | 공연장 (폐업·휴업 뺌) | 폐업·휴업 | 우리 데이터에 있음 | 커버리지 | 우리 공연 날짜 |",
             "|---|---|---|---|---|---|---|"]
    for c in cov:
        lines.append(f"| {c['city']} | {c['province'] or '—'} | {c['venues']} | {c['closed']} | {c['in_data']} | "
                     f"{_pct(c['in_data'], c['venues'])} | {c['gig_days']:,} |")
    return lines


def _distribution_section(dist: List[dict], stats: Dict[str, dict], city_of: Dict[str, str],
                          all_teams: int) -> List[str]:
    total_days = sum(d["gig_days"] for d in dist) or 1
    lines = ["| 도시 | 공연장 | 공연 날짜 | 비율 | 공연한 팀 | 팀 비율 |", "|---|---|---|---|---|---|"]
    for d in dist:
        lines.append(f"| {d['city']} | {d['venues']} | {d['gig_days']:,} | {_pct(d['gig_days'], total_days)} | "
                     f"{d['teams']:,} | {_pct(d['teams'], all_teams)} |")
    lines += ["", f"팀 비율의 분모는 공연한 팀 전체 {all_teams:,}팀입니다(여러 도시에서 공연한 팀은 도시마다 셈).", "",
              "**출처별 서울 비율** (공연 날짜, 같은 공연장·같은 날을 처음 올린 출처 기준)", "",
              "| 출처 | 공연 날짜 | 서울 | 지방 | 도시 모름 |", "|---|---|---|---|---|"]
    by_src: Dict[str, Counter] = defaultdict(Counter)
    for v, s in stats.items():
        c = city_of.get(v, UNKNOWN_CITY)
        kind = city_kind(c)
        for src, n in s["sources"].items():
            by_src[src][kind] += n
    for src, c in sorted(by_src.items(), key=lambda kv: -sum(kv[1].values())):
        t = sum(c.values())
        lines.append(f"| {src} | {t:,} | {c[SEOUL]:,} ({_pct(c[SEOUL], t)}) | {c['지방']:,} ({_pct(c['지방'], t)}) | "
                     f"{c[UNKNOWN_CITY]:,} |")
    return lines


def _year_section(rows: Sequence[dict], city_of: Dict[str, str]) -> List[str]:
    per: Dict[str, Counter] = defaultdict(Counter)
    seen = set()
    for r in rows:
        v = (r.get("venue") or "").strip()
        if r.get("branch") != "공연" or v in NOT_VENUE or (v, r["signal_date"]) in seen:
            continue
        seen.add((v, r["signal_date"]))
        c = city_of.get(v, UNKNOWN_CITY)
        per[r["signal_date"][:4]][city_kind(c)] += 1
    lines = ["| 연도 | 공연 날짜 | 서울 비율 | 지방 | 도시 모름 |", "|---|---|---|---|---|"]
    for y in sorted(per):
        c = per[y]
        t = sum(c.values())
        lines.append(f"| {y} | {t:,} | {_pct(c[SEOUL], t)} | {c['지방']:,} | {c[UNKNOWN_CITY]:,} |")
    return lines


def _gap_section(gaps: List[dict], limit: int = 60) -> List[str]:
    per_city = Counter(g["city"] for g in gaps)
    lines = ["**도시별 공백 공연장 수:** " + " · ".join(f"{c} {n}" for c, n in per_city.most_common()), "",
             f"| 도시 | 공연장 | 종류 | 우리 공연 날짜 | 운영 | 가져올 곳 |", "|---|---|---|---|---|---|"]
    for g in gaps[:limit]:
        lines.append(f"| {g['city']} | {g['name']} | {TYPES.get(g.get('type'), g.get('type')) or TYPE_UNKNOWN} | {g['our_days']} | "
                     f"{STATUSES.get(g.get('status'), '')} | {_src_label(g)} |")
    if len(gaps) > limit:
        lines.append(f"\n(나머지 {len(gaps) - limit}곳은 `config/venues_kr.json`에서 `in_our_data: false`로 찾을 수 있습니다.)")
    return lines


def _unmatched_section(stats: Dict[str, dict], match: Dict[str, int], city_of: Dict[str, str]) -> List[str]:
    rest = sorted((v for v in stats if v not in match), key=lambda v: -stats[v]["gig_days"])
    if not rest:
        return ["없음."]
    lines = ["| 우리 공연장 이름 | 도시(주소로 짐작) | 공연 날짜 |", "|---|---|---|"]
    lines += [f"| {v} | {city_of.get(v, UNKNOWN_CITY)} | {stats[v]['gig_days']} |" for v in rest[:30]]
    if len(rest) > 30:
        lines.append(f"\n(그 밖 {len(rest) - 30}곳)")
    return lines


def _candidates_section(gaps: List[dict]) -> List[str]:
    insta = [g for g in gaps if g.get("instagram")]
    indiego = [g for g in gaps if g.get("indiego_past")]
    return [
        f"1. **인디고 과거 공연 되짚기** — 공백 공연장 중 {len(indiego)}곳은 인디고에 지난 공연 기록이 있습니다"
        f"(공연장 페이지 '지난 공연' 수). 이미 쓰는 출처이고 robots가 허용하므로 가장 싼 길입니다"
        f"([지방 출처 조사](research_2026-11-27_regional_gigs.md) 후보 ①).",
        f"2. **지방 공연장 인스타그램** — 공백 공연장 중 {len(insta)}곳은 공식 계정을 압니다: "
        + ", ".join(f"@{g['instagram']}({g['city']})" for g in insta[:25])
        + (" …" if len(insta) > 25 else "") + ". `config/insta_accounts.json`에 공연장 계정으로 넣으면 기존 "
        "`collect_insta.py`로 라인업 글을 받습니다(역할은 '검증 대기'로 시작).",
        "3. **KOPIS 공연예술통합전산망 오픈 API** — 공연시설 목록(`/openApi/restful/prfplc`, 시·도·구군 코드로 거름)과 "
        "공연 목록(장르 '대중음악')이 있습니다. 예매처를 거친 유료 공연은 지역과 상관없이 잡혀 광주·대전·전주·제주 같은 "
        "빈 곳을 채울 수 있습니다. **인증키가 필요합니다 — 사용자께 `KOPIS_API_KEY` 발급을 요청합니다**(무료, 사용자 계정으로 신청 → `.env`).",
        "4. **라랄라온(2026 소규모 대중음악 공연 활성화 지원, 한국음악레이블산업협회·문체부)** — 전국 소공연장 23곳 "
        "라인업 공지에 공연장·날짜·팀이 함께 나옵니다. 한 해 1번 aside로 읽기.",
        "5. **지역 음악창작소·지원 무대** — 광주·대전·부산·대구 음악창작소의 공연·선정 공지(선정·지원 갈래).",
    ]


def render(cfg: dict, stats: Dict[str, dict], match: Dict[str, int], addresses: Dict[str, str],
           rows: Optional[Sequence[dict]] = None, non_venue_handles: Iterable[str] = ()) -> str:
    master = cfg["venues"]
    city_of = venue_city(stats, match, master, addresses, non_venue_handles)
    dist = city_distribution(stats, city_of)
    all_teams = len(set().union(*(s["teams"] for s in stats.values()))) if stats else 0
    gaps = source_gaps(master, match, stats)
    lines = [
        "# 한국 공연장·도시 — 마스터 목록과 우리 커버리지",
        "",
        "_자동 생성: `python3 scripts/venues_kr.py` · 마스터 목록 [`config/venues_kr.json`](../config/venues_kr.json) · "
        f"확인일 {cfg.get('checked', '')}_",
        "",
        "Chartmetric의 '공연장(Venue)'·'도시(City)' 화면처럼, 공연장마다 도시·종류·크기·운영 여부를 정리하고 "
        "우리 공연 데이터가 어느 도시에 몰려 있는지, 지방 공연장 중 어디가 비어 있는지(= **출처 공백**) 봅니다. "
        "수용 인원·체급은 [공연장 사다리](venue_ladder.md)와 같은 값을 씁니다.",
        "",
        "## 1. 요약",
        "",
        *_summary(master, match, stats, dist),
        "",
        "## 2. 도시별 공연장 수와 우리 커버리지",
        "",
        "커버리지 = 마스터 목록 공연장(폐업·휴업 뺌) 중 우리 공연 데이터(인디스트릿·상상마당·인디고·공연장 인스타)에 "
        "한 번이라도 나온 곳의 비율.",
        "",
        *_coverage_section(coverage_by_city(master, match, stats)),
        "",
        "## 3. 우리 공연 데이터의 도시 분포",
        "",
        "공연 날짜 = 같은 공연장·같은 날 1건. 도시는 마스터 목록 → 공연 원본 주소 순으로 정했습니다.",
        "",
        *_distribution_section(dist, stats, city_of, all_teams),
        "",
    ]
    if rows is not None:
        lines += ["**연도별 서울 비율**", "", *_year_section(rows, city_of), ""]
    lines += [
        "## 4. 출처 공백 — 지방 공연장인데 우리 데이터에 거의 없는 곳",
        "",
        f"서울 밖 · 폐업·휴업 아님 · 우리 공연 날짜 {GAP_MIN_DAYS}일 미만. 인디고 지난 공연이 많은 곳(= 공연이 실제로 "
        "자주 열리는데 우리가 못 받는 곳)부터.",
        "",
        *_gap_section(gaps),
        "",
        "## 5. 수집 후보 출처 (공백을 채우는 순서 제안)",
        "",
        *_candidates_section(gaps),
        "",
        "## 6. 우리 데이터에 있지만 마스터 목록과 짝이 안 된 공연장",
        "",
        "이름이 달라 짝을 못 지었거나 마스터 목록에 아직 없는 곳입니다. 같은 곳이면 마스터 항목의 `aliases`나 "
        "`our_names`에 넣습니다.",
        "",
        *_unmatched_section(stats, match, city_of),
        "",
        "## 7. 같은 주소를 쓰는 항목 (같은 곳인지 확인 필요)",
        "",
        "건물 하나에 공연장이 여럿인 곳(예: 상상마당)과 이름만 다른 같은 곳이 섞여 있습니다. 같은 곳이면 하나로 합치고 "
        "다른 이름은 `aliases`에 넣습니다.",
        "",
        *([f"- {' · '.join(g)}" for g in same_address_groups(master)] or ["없음."]),
        "",
        "## 8. 한계",
        "",
        "- 마스터 목록은 우리 공연 데이터·공연장 인스타·인디고 공연장 페이지·기사(Korea Times 'Finding the Scene', "
        "Gwangju News, 디에디트, 라랄라온 보도)를 합친 것이라, **기사·예매처에 안 나오는 작은 지방 클럽은 빠져 있을 수 있습니다.**",
        "- 인디고 공연장 목록에는 공공 공연장(예술의전당·문예회관)도 섞여 있습니다(종류 '홀·공연장').",
        "- 운영 여부: 우리 데이터·인디고에 1년 안 공연이 있으면 '운영', 기사로 폐업·휴업을 확인한 곳만 '폐업'·'휴업', "
        "나머지는 '확인 필요'입니다.",
        "- 우리 공연 데이터는 인디스트릿(2024-01~)·상상마당(2010~) 위주라 연도별 비율은 출처가 바뀐 영향을 받습니다.",
        "",
    ]
    return "\n".join(lines)


# ---------- 처음 만들기(seed) ----------

CHAIN_REGION = {"홍대": ("서울", "서울", "마포구"), "대치": ("서울", "서울", "강남구"),
                "부산": ("부산", "부산", "부산진구"), "춘천": ("강원", "춘천", "")}
ADDR_IN_TEXT = re.compile(r"(" + "|".join(sorted(SIDO, key=len, reverse=True)) + r"|" + MERGED_GJ + r")\s+\S+[^\n|·]*")


def _address_from_text(text: str) -> str:
    m = ADDR_IN_TEXT.search(text or "")
    return m.group(0).strip() if m else ""


def _region_for(name: str, address: str) -> Dict[str, str]:
    reg = parse_region(address)
    if reg["city"]:
        return reg
    if "상상마당" in name:
        for k, (p, c, d) in CHAIN_REGION.items():
            if k in name:
                return {"province": p, "city": c, "district": d}
    return reg


def _merge(base: dict, extra: dict) -> dict:
    """base 의 빈칸만 extra 로 채운 새 항목 (별칭·근거는 합침)."""
    out = dict(base)
    for k, v in extra.items():
        if k in ("aliases", "our_names"):
            out[k] = sorted({*out.get(k, []), *v} - {out.get("name")})
        elif k == "sources":
            urls = {s["url"] for s in out.get("sources", [])}
            out[k] = [*out.get("sources", []), *[s for s in v if s["url"] not in urls]]
        elif out.get(k) in (None, "", [], "unknown") and v not in (None, "", []):
            out[k] = v
    return out


def seed(existing: Sequence[dict], candidates: Sequence[dict]) -> List[dict]:
    """앞쪽(기존 → 웹 조사 → 우리 데이터 → 인스타 → 인디고) 값을 우선해 정규화 키로 합친다."""
    merged: List[dict] = []
    index: Dict[str, int] = {}
    for c in [*existing, *candidates]:
        hit = next((index[k] for k in _keys(c) if k in index), None)
        if hit is None:
            merged.append(dict(c))
            hit = len(merged) - 1
        else:
            merged[hit] = _merge(merged[hit], c)
        for k in _keys(merged[hit]):
            index.setdefault(k, hit)
    return merged


def clean_address(address: str) -> str:
    """짝이 안 맞는 괄호 꼬리('… 지하1층 (서교동')와 앞뒤 공백을 정리."""
    a = (address or "").strip()
    if a.count("(") > a.count(")"):
        a = a[: a.rfind("(")].strip()
    return a


def _entry(name: str, address: str = "", **kw) -> dict:
    address = clean_address(address)
    reg = _region_for(name, address)
    return {"name": name, "aliases": [], **reg, "address": address, "type": guess_type(name),
            "capacity": None, "status": "unknown", "sources": [], **{k: v for k, v in kw.items() if v is not None}}


def candidates_from_our_data(stats: Dict[str, dict], addresses: Dict[str, str], as_of: date,
                             capacity_cfg: dict, gig_urls: Dict[str, str]) -> List[dict]:
    cap = capacity_cfg.get("venues", {})
    renamed = {}
    for old, v in cap.items():
        m = re.search(r"'([^']+)'로 묶임", v.get("note", "") or "")
        if m:
            renamed[old] = m.group(1)
    skip = {n for n, v in cap.items() if v.get("not_venue")}
    out = []
    recent = (as_of - timedelta(days=RECENT_DAYS)).isoformat()
    for v, s in sorted(stats.items(), key=lambda kv: -kv[1]["gig_days"]):
        if v in skip or vx.is_generic(v) and v not in renamed:
            continue
        name = renamed.get(v, v)
        c = cap.get(v, {}) or cap.get(name, {})
        src = [{"url": gig_urls[v], "note": "우리 공연 데이터 원본 공연 페이지(공연장·주소)"}] if v in gig_urls else []
        if c.get("source"):
            src.append({"url": c["source"], "note": "수용 인원 근거 (config/venue_capacity.json)"})
        out.append(_entry(name, addresses.get(v, ""), our_names=[v] if v != name else [],
                          capacity=c.get("capacity"), status="open" if s["last"] >= recent else "unknown",
                          status_note=f"우리 공연 데이터 마지막 공연 {s['last']}", sources=src))
    return out


def candidates_from_insta(items: Sequence[dict]) -> List[dict]:
    out = []
    for it in items:
        if not it.get("handle") or it.get("confidence") == "low":
            continue
        out.append(_entry(it["venue"], _address_from_text(it.get("bio", "")), instagram=it["handle"],
                          sources=[{"url": it["url"], "note": "공연장 공식 인스타그램"}]))
    return out


ADDRESS_LIKE = re.compile(r"(로|길)\d*\s*\d+(-\d+)?$")


def candidates_from_indiego(items: Sequence[dict], as_of: date) -> List[dict]:
    out = []
    for it in items:
        name = (it.get("name") or "").strip()
        if not name or it.get("error") or ADDRESS_LIKE.search(name):
            continue
        addr = "" if it.get("address") in (None, "", "주소 미입력") else it["address"]
        out.append(_entry(name, addr, indiego_url=it["url"], indiego_past=it.get("past"),
                          status="open" if (it.get("upcoming") or 0) > 0 else None,
                          status_note="인디고에 예정 공연 있음" if (it.get("upcoming") or 0) > 0 else None,
                          sources=[{"url": it["url"], "note": "인디고 공연장 페이지"}]))
    return out


def sample_gig_urls() -> Dict[str, str]:
    """{우리 대표 이름: 그 공연장 공연 페이지 하나}."""
    mapping = load_json(vx.XREF_PATH, {}) or {}
    out: Dict[str, str] = {}
    for path in sorted(vx.RAW_DIR.glob("raw_kr_gig_*.csv")):
        with open(path, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                d = vx.gig_detail(r.get("venue_text", ""))
                if r.get("gig_url"):
                    out.setdefault(mapping.get(d, d), r["gig_url"])
    return out


META = {
    "_설명": "한국 대중음악 공연장 마스터 목록 (scripts/venues_kr.py 가 읽어 docs/venues_kr.md 를 만듦). "
             "name = 대표 이름, aliases = 다른 표기(영문·옛 이름), our_names = 우리 공연 데이터(venue_xref 대표 이름) 중 "
             "규칙으로 못 잇는 이름('라이브홀' 같은 지점 없는 이름·건물 안 작은 공간), province/city/district = 시·도/도시/구·군, "
             "type = live_club·hall·theater·creation_center·cafe·festival(빈칸 = 공개 근거 없어 미정), "
             "type_basis = 종류를 정한 근거(이름·확인된 수용 인원·근거 메모, '수동:'으로 시작하면 사람이 정한 것 — scripts/venue_types.py), capacity = 스탠딩 최대(없으면 좌석, 모르면 null — "
             "venue_capacity.json 과 같은 기준), status = open(1년 안 공연 확인)·unknown(확인 필요)·paused(휴업)·closed(폐업), "
             "sources = 근거 링크, checked = 확인일, mainstream = 대형·공공 공연장(출처 공백 목록에서 뺌), "
             "instagram·indiego_url·indiego_past = 공연장 계정·인디고 공연장 페이지·인디고 지난 공연 수, "
             "merge_note = 두 항목을 하나로 합친 근거, genre_focus = 특정 장르 위주 공연장(예: hiphop), our_venue·in_our_data = 우리 공연 데이터와 짝(--update-config 가 갱신).",
    "types": TYPES,
    "statuses": STATUSES,
}


def run_seed(extra_path: Path, as_of: date) -> dict:
    cfg = load_json(CONFIG, {}) or {}
    stats = gig_stats(load_signals(), not_venue_names())
    extra = load_json(extra_path, []) or []
    insta = (load_json(REVIEW_DIR / "instagram_venues.json", {}) or {}).get("items", [])
    indiego_files = sorted(REVIEW_DIR.glob("indiego_venues_*.json"))
    indiego = (load_json(indiego_files[-1], {}) or {}).get("items", []) if indiego_files else []
    cands = [*extra,
             *candidates_from_our_data(stats, our_addresses(), as_of, load_json(CAPACITY, {}) or {}, sample_gig_urls()),
             *candidates_from_insta(insta), *candidates_from_indiego(indiego, as_of)]
    venues = seed(cfg.get("venues", []), cands)
    today = as_of.isoformat()
    venues = [{**e, "checked": e.get("checked") or today,
               "type": e.get("type") if "type_basis" in e else (e.get("type") or guess_type(e["name"])),
               "status": e.get("status") or "unknown"}
              for e in venues if e.get("city")]           # 도시를 모르는 곳은 빼고 문서 6절(짝 안 됨)에 남김
    return update_in_data({**META, **cfg, "checked": today, "venues": sorted(venues, key=lambda e: (e["city"] != SEOUL, e["province"],
                                                                        e["city"], e["name"]))}, stats)


def main() -> None:
    ap = argparse.ArgumentParser(description="한국 공연장·도시 마스터 목록 → docs/venues_kr.md")
    ap.add_argument("--update-config", action="store_true", help="마스터 목록의 in_our_data·our_venue 갱신")
    ap.add_argument("--seed", type=Path, help="웹 조사 목록 JSON 으로 마스터 목록 만들기/빈칸 채우기")
    ap.add_argument("--as-of", default=date.today().isoformat())
    args = ap.parse_args()
    as_of = date.fromisoformat(args.as_of)
    if args.seed:
        cfg = run_seed(args.seed, as_of)
        CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"마스터 목록 {len(cfg['venues'])}곳 → {CONFIG.relative_to(ROOT)}")
    cfg = load_json(CONFIG)
    if not cfg:
        raise SystemExit(f"{CONFIG} 이 없거나 읽을 수 없음 — 먼저 --seed")
    rows = load_signals()
    stats = gig_stats(rows, not_venue_names())
    if args.update_config:
        cfg = update_in_data(cfg, stats)
        CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for p in validate(cfg):
        print("형식 문제:", p)
    match = match_our_venues(cfg["venues"], stats)
    OUT.write_text(render(cfg, stats, match, our_addresses(), rows, non_venue_handles()), encoding="utf-8")
    print(f"공연장 {len(cfg['venues'])}곳 · 우리 공연장 {len(stats)}곳 중 짝 {len(match)}곳 → {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
