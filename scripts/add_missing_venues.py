"""공연 기록엔 있는데 마스터 목록(config/venues_kr.json)에 없어 도시·좌표가 빈 공연장 → 마스터 목록 항목을 만든다.

    python3 scripts/add_missing_venues.py --dry-run   # 무엇을 넣을지 보기만
    python3 scripts/add_missing_venues.py             # 좌표까지 찾아 config 에 붙이기

대상: docs/lab/data/venue_profiles.json 에서 도시도 좌표도 없는 공연장('@계정' 제외).
- 주소·근거 링크: 공연 원본(data/raw/raw_kr_gig_*.csv)의 괄호 속 주소와 그 공연장의 가장 최근 공연 페이지.
- 도시: 주소에서(scripts/venues_kr.parse_region). 주소가 도로명뿐이면 지오코딩 결과 주소에서.
- 좌표: scripts/geocode_venues.py 와 같은 방법(OpenStreetMap Nominatim, 1.1초에 1건, 일반 User-Agent, 캐시).
- 운영 상태: 최근 1년 안 공연 = open, 아니면 unknown(확인 필요). 폐업·이전은 공개 근거가 있을 때만(KNOWN).
  같은 주소에 다른 이름의 마스터 항목이 있으면 '이름이 바뀌었거나 문을 닫았을 수 있음'을 적는다.
- 온라인 중계('공식 유튜브'·'공식 인스타그램')는 공연장이 아니라 넣지 않는다. 주소가 없는 곳도 넣지 않는다.
- 기존 공연장의 다른 표기(EXTRA_OUR_NAMES)는 새 항목 대신 그 항목의 our_names 에 더한다.
config 는 쓰기 직전에 다시 읽어(다른 작업이 고쳤을 수 있음) 이미 있는 이름·별칭은 건너뛴다.
"""
from __future__ import annotations

import argparse
import copy
import csv
import glob
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import geocode_venues as gv  # noqa: E402
import venue_xref as vx  # noqa: E402
import venues_kr as vk  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROFILES = ROOT / "docs" / "lab" / "data" / "venue_profiles.json"
RAW_DIR = ROOT / "data" / "raw"
OPEN_WITHIN_DAYS = 365
SOURCE_NOTE = "우리 공연 데이터 원본 공연 페이지(공연장·주소)"
ADDED_BY = "scripts/add_missing_venues.py"  # 이 스크립트가 만든 항목 표시
_ONLINE = re.compile(r"공식\s*(유튜브|인스타그램)")

EXTRA_OUR_NAMES = {
    "KT&G 상상마당 홍대 안녕바다": "KT&G 상상마당 홍대 라이브홀",  # 공연 제목의 팀 이름이 공연장 칸에 붙은 표기
    "문화정원아트홀 1층 정원": "문화정원아트홀",                     # 같은 건물 같은 주소의 1층 공간
}
KNOWN = {
    "LG아트센터": {
        "status": "closed", "moved_to": "LG아트센터 서울",
        "status_note": "역삼동 LG아트센터는 2022년 2월까지 운영, 2022년 10월 마곡으로 옮겨 'LG아트센터 서울'로 개관"
                       " (옛 건물은 2025년 GS아트센터로 다시 엶)",
        "extra_sources": [
            {"url": "https://www.khan.co.kr/article/202210161056001", "note": "마곡 이전 개관 보도(경향신문 2022-10-16)"},
            {"url": "https://www.hankyung.com/article/202502117369i", "note": "옛 역삼 건물 GS아트센터 개관 보도"},
        ],
    },
}


def is_online(name: str) -> bool:
    return bool(_ONLINE.search(name or ""))


def region_from_display(display: str) -> Dict[str, str]:
    """Nominatim display_name('번호, 도로, 동, 구, 서울특별시, 우편번호, 대한민국') → 시·도/도시/구."""
    parts = [p.strip() for p in (display or "").split(",") if p.strip()]
    parts = [p for p in parts if p != "대한민국" and not p.isdigit()]
    return vk.parse_region(" ".join(reversed(parts)))


def build_entry(name: str, address: str, gig_url: str, last_night: str, as_of: date,
                master_by_addr: Dict[str, str], region: Optional[Dict[str, str]] = None) -> Optional[dict]:
    """공연장 1곳의 마스터 항목. 도시를 못 정하면 None."""
    region = region or vk.parse_region(address)
    if not region.get("city"):
        return None
    last = date.fromisoformat(last_night) if last_night else None
    recent = bool(last) and (as_of - last).days <= OPEN_WITHIN_DAYS
    note = f"우리 공연 데이터 마지막 공연 {last_night or '모름'}"
    if not recent:
        note += " — 1년 넘게 기록 없음, 운영 여부 확인 필요"
    same = master_by_addr.get(vx.address_key(address))
    if same and same != name:
        note += f" · 같은 주소에 '{same}'가 있음(이름이 바뀌었거나 문을 닫았을 수 있음)"
    entry = {
        "name": name, "aliases": [], "province": region["province"], "city": region["city"],
        "district": region.get("district", ""), "address": address, "type": "", "capacity": None,
        "status": "open" if recent else "unknown",
        "sources": [{"url": gig_url, "note": SOURCE_NOTE}] if gig_url else [],
        "checked": as_of.isoformat(), "in_our_data": True, "status_note": note, "type_basis": "",
        "added_by": ADDED_BY,
    }
    known = KNOWN.get(name)
    if known:
        entry = {**entry, "status": known["status"], "moved_to": known.get("moved_to"),
                 "status_note": f"{known['status_note']} · {note}",
                 "sources": entry["sources"] + known.get("extra_sources", [])}
    return entry


def _master_by_address(master: Sequence[dict]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for e in master:
        k = vx.address_key(e.get("address", ""))
        if k:
            out.setdefault(k, e["name"])
    return out


def plan(missing: Sequence[Tuple[str, str]], addresses: Dict[str, str], gig_urls: Dict[str, str], as_of: date,
         master: Sequence[dict]):
    """→ (새 항목들, {기존 대표 이름: [더할 our_names]}, [(건너뛴 이름, 까닭)], [주소는 있는데 도시를 못 정한 (이름, 주소)])"""
    by_addr = _master_by_address(master)
    entries: List[dict] = []
    our_names: Dict[str, List[str]] = {}
    skipped: List[Tuple[str, str]] = []
    no_region: List[Tuple[str, str]] = []
    for name, last in missing:
        if name in EXTRA_OUR_NAMES:
            our_names.setdefault(EXTRA_OUR_NAMES[name], []).append(name)
            continue
        if is_online(name):
            skipped.append((name, "온라인 중계(공연장 아님)"))
            continue
        addr = addresses.get(name, "")
        if not addr:
            skipped.append((name, "공연 원본에 주소 없음·공개 주소 못 찾음"))
            continue
        e = build_entry(name, addr, gig_urls.get(name, ""), last, as_of, by_addr)
        if e:
            entries.append(e)
        else:
            no_region.append((name, addr))
    return entries, our_names, skipped, no_region


def _known_names(venues: Sequence[dict]) -> set:
    names = set()
    for e in venues:
        names.add(e.get("name"))
        names.update(e.get("aliases") or [])
        names.update(e.get("our_names") or [])
    return names


def merge(cfg: dict, entries: Sequence[dict], our_names: Dict[str, List[str]]):
    """새 config 사본 (원본은 안 바꿈) → (사본, 더한 이름, 이미 있어 건너뛴 이름). 기존 항목은 our_names 만 늘린다."""
    out = copy.deepcopy(cfg)
    venues = out.setdefault("venues", [])
    known = _known_names(venues)
    added, dup = [], []
    for e in entries:
        if e["name"] in known:
            dup.append(e["name"])
            continue
        venues.append(copy.deepcopy(e))
        known.add(e["name"])
        added.append(e["name"])
    for target, extra in our_names.items():
        hit = next((v for v in venues if v.get("name") == target), None)
        if hit is None:
            continue
        cur = list(hit.get("our_names") or [])
        hit["our_names"] = cur + [n for n in extra if n not in cur]
    return out, added, dup


def missing_from_profiles(path: Path = PROFILES) -> List[Tuple[str, str]]:
    venues = json.loads(path.read_text(encoding="utf-8")).get("venues", {})
    return sorted((n, v.get("last_night") or "") for n, v in venues.items()
                  if not n.startswith("@") and not v.get("city") and v.get("lat") is None)


def latest_gig_urls(raw_dir: Path = RAW_DIR) -> Dict[str, str]:
    """{우리 대표 이름: 가장 최근 공연 페이지} — 표기는 연결표(venue_xref)로 대표 이름에 모은다."""
    mapping = vk.load_json(vx.XREF_PATH, {}) or {}
    best: Dict[str, Tuple[str, str]] = {}
    for path in sorted(glob.glob(str(raw_dir / "raw_kr_gig_*.csv"))):
        with open(path, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                url = (r.get("gig_url") or "").strip()
                if not url.startswith("http"):
                    continue
                detail = vx.gig_detail(r.get("venue_text", ""))
                day = r.get("gig_date") or ""
                for key in {detail, mapping.get(detail, detail)}:
                    if key and day >= best.get(key, ("", ""))[0]:
                        best[key] = (day, url)
    return {k: u for k, (_, u) in best.items()}


AREA_MIN_RANK = 20  # 공원·시설 단지 같은 넓은 곳 — 이름과 구·시가 모두 맞을 때만 (확실도 low)


def _place_of(entry: dict) -> str:
    return entry.get("district") or entry.get("city") or ""


def name_hit_ok(entry: dict, cache: dict) -> bool:
    """이름 검색(low)으로 얻은 좌표가 그 공연장 주소의 구·군(없으면 도시) 안인지. 주소 검색 결과는 그대로 믿는다."""
    if entry.get("geo_confidence") != "low":
        return True
    results = cache.get(f"{entry.get('name', '')} {entry.get('city', '')}".strip(), [])
    for r in results:
        try:
            same = round(float(r["lat"]), 6) == entry.get("lat") and round(float(r["lon"]), 6) == entry.get("lon")
        except (KeyError, TypeError, ValueError):
            continue
        if same:
            return _place_of(entry) in (r.get("display_name") or "")
    return False


HALL_WORD = re.compile(r"(홀|무대|극장|정원|로비)$")  # 큰 시설 안의 방 이름 — 떼면 시설 이름이 남는다


def name_variants(name: str, city: str) -> List[str]:
    """이름 검색에 쓸 표기: 그대로 → 앞의 도시 이름을 뗀 것 / 끝의 방 이름('연지홀')·도시 이름을 뗀 것.
    첫 낱말만 남기지는 않는다('KT&G'·'홍대'처럼 엉뚱한 곳이나 동네 전체가 걸린다)."""
    words = (name or "").split()
    out = [name]
    if len(words) > 1:
        if words[0] == city:
            out.append(" ".join(words[1:]))
        elif HALL_WORD.search(words[-1]) or words[-1] == city:
            out.append(" ".join(words[:-1]))
    return list(dict.fromkeys(out))


def area_fallback(entry: dict, ask) -> Optional[dict]:
    """좌표를 못 찾은 곳: 표기를 바꿔 이름 검색 — 결과 이름이 그 표기로 시작하고 구·시가 맞으면 받는다(low)."""
    city = entry.get("city") or ""
    place = _place_of(entry)
    for v in name_variants(entry.get("name", ""), city):
        for r in ask(f"{v} {city}".strip()):
            disp = r.get("display_name") or ""
            try:
                lat, lon, rank = float(r["lat"]), float(r["lon"]), int(r.get("place_rank") or 0)
            except (KeyError, TypeError, ValueError):
                continue
            if disp.startswith(v) and place in disp and rank >= AREA_MIN_RANK and gv._in_korea(lat, lon):
                return {"lat": round(lat, 6), "lon": round(lon, 6), "geo_confidence": "low", "geo_method": "name"}
    return None


def refine(entry: dict, cache: dict, fetch) -> dict:
    """이름 검색 좌표가 다른 구면 지우고, 좌표가 없으면 표기를 바꿔 한 번 더 찾는다 (새 사본)."""
    e = dict(entry)
    if e.get("lat") is not None and not name_hit_ok(e, cache):
        for k in gv.GEO_FIELDS:
            e.pop(k, None)
        e["geo_note"] = "이름 검색 결과가 주소의 구·군과 달라 좌표를 비움"
    if e.get("lat") is None:
        hit = area_fallback(e, lambda q: gv._ask(q, cache, fetch))
        if hit:
            e.update(hit)
            e["geo_note"] = "이름 검색(넓은 곳·표기 바꿈) — 같은 구·시 안, 위치는 대략"
    return e


def _geocode(entries: List[dict], cache: dict, fetch, checked: str) -> List[dict]:
    out = []
    for e in entries:
        hit = gv.geocode_entry(e, cache, fetch)
        out.append(refine({**e, **(hit or {}), "geo_checked": checked}, cache, fetch))
    return out


def made_here(entry: dict) -> bool:
    """이 스크립트가 만든 항목인지 (added_by 표시로 — 다른 항목은 --refine-only 가 손대지 않는다)."""
    return entry.get("added_by") == ADDED_BY


def refine_config(path: Path, cache_path: Path) -> int:
    """이미 붙인 항목(이 스크립트가 만든 것)만 다시 다듬는다 — 다른 항목·칸은 그대로."""
    cache = gv.load_cache(cache_path)
    fetch = gv.Nominatim()
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
        targets = {e["name"]: refine(e, cache, fetch) for e in cfg["venues"] if made_here(e) and "geo_checked" in e}
    finally:
        gv.save_cache(cache_path, cache)
    fresh = json.loads(path.read_text(encoding="utf-8"))
    fresh["venues"] = [targets.get(e.get("name"), e) if made_here(e) else e for e in fresh["venues"]]
    path.write_text(json.dumps(fresh, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    geo = [e for e in fresh["venues"] if e.get("name") in targets]
    print(f"다듬음 {len(targets)}곳 · 좌표 있음 {sum(1 for e in geo if e.get('lat') is not None)} · 새 요청 {fetch.calls}건")
    return 0


def _resolve_no_region(no_region, gig_urls, last_by_name, as_of, master, cache, fetch) -> List[dict]:
    """도로명뿐인 주소: 지오코딩 결과 주소로 도시를 정한다."""
    out = []
    by_addr = _master_by_address(master)
    for name, addr in no_region:
        results = gv._ask(gv.address_query(addr), cache, fetch)
        region = region_from_display(results[0].get("display_name", "")) if results else {}
        if region.get("city"):
            e = build_entry(name, addr, gig_urls.get(name, ""), last_by_name.get(name, ""), as_of, by_addr, region)
            if e:
                out.append(e)
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="마스터 목록에 없는 우리 공연장 → 항목 만들기(도시·주소·좌표)")
    ap.add_argument("--config", type=Path, default=gv.CONFIG)
    ap.add_argument("--profiles", type=Path, default=PROFILES)
    ap.add_argument("--cache", type=Path, default=gv.CACHE)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--refine-only", action="store_true", help="이미 붙인 항목의 좌표만 다시 다듬기")
    args = ap.parse_args(argv)
    if args.refine_only:
        return refine_config(args.config, args.cache)
    as_of = date.today()
    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    missing = missing_from_profiles(args.profiles)
    gig_urls = latest_gig_urls()
    entries, our_names, skipped, no_region = plan(missing, vk.our_addresses(), gig_urls, as_of, cfg["venues"])
    print(f"대상 {len(missing)}곳 → 새 항목 {len(entries)} · 다른 표기 {sum(map(len, our_names.values()))}"
          f" · 도시 다시 찾기 {len(no_region)} · 건너뜀 {len(skipped)}")
    for n, why in skipped:
        print(f"  건너뜀: {n} ({why})")
    if args.dry_run:
        return 0
    cache = gv.load_cache(args.cache)
    fetch = gv.Nominatim()
    try:
        entries += _resolve_no_region(no_region, gig_urls, dict(missing), as_of, cfg["venues"], cache, fetch)
        entries = _geocode(entries, cache, fetch, as_of.isoformat())
    finally:
        gv.save_cache(args.cache, cache)
    conf = [e.get("geo_confidence") for e in entries if e.get("lat") is not None]
    print(f"좌표 찾음 {len(conf)}/{len(entries)} (high {conf.count('high')} · medium {conf.count('medium')}"
          f" · low {conf.count('low')}) · 새 요청 {fetch.calls}건")
    fresh = json.loads(args.config.read_text(encoding="utf-8"))   # 도는 동안 다른 작업이 고쳤을 수 있어 다시 읽음
    out, added, dup = merge(fresh, entries, our_names)
    problems = vk.validate(out)
    if problems:
        print("❌ 검사 실패 — config 를 안 바꿈:\n  " + "\n  ".join(problems[:20]), file=sys.stderr)
        return 1
    args.config.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"✅ {len(added)}곳 더함 · 이미 있어 건너뜀 {len(dup)} → {args.config}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
