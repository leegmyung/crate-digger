"""공연장 마스터 목록(config/venues_kr.json)에 지도용 좌표(lat·lon)와 확실도를 붙인다.

    python3 scripts/geocode_venues.py            # 아직 확인 안 한 곳만 묻고 config 갱신
    python3 scripts/geocode_venues.py --all      # 이미 확인한 곳도 다시 (캐시는 그대로 씀)
    python3 scripts/geocode_venues.py --dry-run  # config 는 안 바꾸고 결과만 출력

방법 (공개 지오코딩 OpenStreetMap Nominatim, 이용 정책 준수):
  1) 주소가 있으면 층·호수·괄호를 뗀 도로명 주소로 검색
  2) 못 찾으면 '공연장 이름 + 도시'로 검색 — 결과 주소에 그 도시 이름이 있어야 받음
  - 요청은 1.1초에 1건 이하, 일반 클라이언트 이름 User-Agent(개인정보 없음), 결과는
    data/raw/state/geocode_cache.json 에 캐시해 같은 질문을 다시 보내지 않는다(빈 결과도 캐시).
확실도(geo_confidence):
  high   = 주소 검색이 건물·번지 수준(place_rank ≥ 30)으로 맞음
  medium = 주소 검색이 도로 수준(place_rank 26~29)까지만 맞음 — 수백 m 오차 가능
  low    = 이름 검색으로 찾음 — 같은 도시 안이지만 다른 곳일 수 있음
  (구·동 수준까지만 맞으면 지도에 쓸 수 없어 비운다.)
  (주소가 도로 수준까지만 맞을 때 이름 검색 결과가 같은 도로의 건물이면 high, 방법은 name+address)
쓰는 칸: lat · lon · geo_confidence · geo_method(address|name|name+address) · geo_checked(확인일)
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
from typing import Callable, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "venues_kr.json"
CACHE = ROOT / "data" / "raw" / "state" / "geocode_cache.json"
ENDPOINT = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "venue-map-geocoder/1.0 (python-urllib)"
MIN_INTERVAL_SEC = 1.1          # Nominatim 정책: 초당 1건 이하
TIMEOUT_SEC = 20
RANK_BUILDING = 30              # 건물·번지
RANK_ROAD = 26                  # 도로
KOREA_LAT = (33.0, 39.0)
KOREA_LON = (124.0, 132.0)
GEO_FIELDS = ("lat", "lon", "geo_confidence", "geo_method")

Fetch = Callable[[str], List[dict]]

# 층·호수 같은 꼬리: '지하1층', '지층1', '1층', '2F', 'B1', '지하', '101호' …
_FLOOR = re.compile(r"(\s|,)+(지하\s*\d*\s*층?|지층\s*\d*|\d+\s*층|\d+\s*[Ff]|[Bb]\d+|\d+\s*호|\d+-\d+호).*$")


_ROAD_NUMBER = re.compile(r"^(.*?\S+(?:로|길)(?:\s*\d+번?길)?\s+\d+(?:-\d+)?)(?:\s|,|$)")


def address_query(address: Optional[str]) -> str:
    """주소 → 검색어: 짝 안 맞는 괄호 꼬리·괄호 안 동 이름·층/호수 꼬리를 뗀다."""
    a = (address or "").strip()
    if not a:
        return ""
    if a.count("(") > a.count(")"):
        a = a[: a.rfind("(")]
    a = re.sub(r"\([^)]*\)", "", a)
    road = _ROAD_NUMBER.match(a)          # 도로명 주소면 '도로 이름 + 건물 번호'까지만 (뒤의 건물 이름·층은 뗌)
    if road:
        a = road.group(1)
    prev = None
    while prev != a:                      # '… 87 1층 101호'처럼 꼬리가 여럿이어도
        prev = a
        a = _FLOOR.sub("", a).strip(" ,")
    return re.sub(r"\s+", " ", a).strip()


def _in_korea(lat: float, lon: float) -> bool:
    return KOREA_LAT[0] <= lat <= KOREA_LAT[1] and KOREA_LON[0] <= lon <= KOREA_LON[1]


def pick(results: List[dict], method: str, city: str) -> Optional[dict]:
    """Nominatim 결과 중 첫 번째 쓸 만한 것 → 좌표·확실도. 못 쓰면 None."""
    for r in results:
        try:
            lat, lon, rank = float(r["lat"]), float(r["lon"]), int(r.get("place_rank") or 0)
        except (KeyError, TypeError, ValueError):
            continue
        if not _in_korea(lat, lon):
            continue
        if method == "name":
            if city and city not in (r.get("display_name") or ""):
                continue
            if rank < RANK_ROAD:
                continue
            conf = "low"
        elif rank >= RANK_BUILDING:
            conf = "high"
        elif rank >= RANK_ROAD:
            conf = "medium"
        else:
            continue
        return {"lat": round(lat, 6), "lon": round(lon, 6), "geo_confidence": conf, "geo_method": method}
    return None


def _ask(query: str, cache: Dict[str, List[dict]], fetch: Fetch) -> List[dict]:
    if query not in cache:
        cache[query] = fetch(query)
    return cache[query]


def geocode_entry(entry: dict, cache: Dict[str, List[dict]], fetch: Fetch) -> Optional[dict]:
    """공연장 1곳: 주소 → (못 찾으면) 이름 + 도시 순으로 찾는다."""
    city = entry.get("city") or ""
    q = address_query(entry.get("address"))
    by_addr = pick(_ask(q, cache, fetch), "address", city) if q else None
    if by_addr and by_addr["geo_confidence"] == "high":
        return by_addr
    name = (entry.get("name") or "").strip()
    if not name:
        return by_addr
    results = _ask(f"{name} {city}".strip(), cache, fetch)
    by_name = pick(results, "name", city)
    if by_addr:                       # 주소는 도로까지만 — 이름 검색이 같은 도로의 건물을 찾으면 high
        road = road_name(q)
        same = [r for r in results if road and road in (r.get("display_name") or "")]
        hit = pick(same, "name", city) if same else None
        if hit and int(next(r for r in same).get("place_rank") or 0) >= RANK_BUILDING:
            return {**hit, "geo_confidence": "high", "geo_method": "name+address"}
        return by_addr
    return by_name


def road_name(query: str) -> str:
    """도로명 주소 검색어에서 도로 이름('와우산로14길'·'동교로')만."""
    m = re.search(r"(\S+(?:로|길))(?:\s|$)", query or "")
    return m.group(1) if m else ""


def apply(cfg: dict, found: Dict[str, Optional[dict]], checked: str) -> dict:
    """found = {공연장 이름: 좌표 dict 또는 None} → 새 config 사본 (None 이면 좌표 칸을 비움)."""
    out = copy.deepcopy(cfg)
    for e in out.get("venues", []):
        if e.get("name") not in found:
            continue
        for k in GEO_FIELDS:
            e.pop(k, None)
        hit = found[e["name"]]
        if hit:
            e.update(hit)
        e["geo_checked"] = checked
    return out


def load_cache(path: Path) -> Dict[str, List[dict]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_cache(path: Path, cache: Dict[str, List[dict]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


_KEEP = ("lat", "lon", "place_rank", "display_name", "addresstype", "class", "type")


class Nominatim:
    """요청 간격을 지키는 Nominatim 검색기 (캐시에 없는 질문만 여기로 옴)."""

    def __init__(self, interval: float = MIN_INTERVAL_SEC):
        self.interval = interval
        self._last = 0.0
        self.calls = 0

    def __call__(self, query: str) -> List[dict]:
        wait = self.interval - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        params = urllib.parse.urlencode({"q": query, "format": "jsonv2", "countrycodes": "kr", "limit": 3,
                                         "accept-language": "ko"})
        req = urllib.request.Request(f"{ENDPOINT}?{params}", headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        finally:
            self._last = time.monotonic()
            self.calls += 1
        return [{k: r.get(k) for k in _KEEP} for r in data if isinstance(r, dict)]


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="공연장 마스터 목록에 지도용 좌표 붙이기 (OpenStreetMap Nominatim)")
    ap.add_argument("--config", type=Path, default=CONFIG)
    ap.add_argument("--cache", type=Path, default=CACHE)
    ap.add_argument("--all", action="store_true", help="이미 확인한 곳도 다시")
    ap.add_argument("--dry-run", action="store_true", help="config 를 바꾸지 않음")
    args = ap.parse_args(argv)
    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    cache = load_cache(args.cache)
    fetch = Nominatim()
    found: Dict[str, Optional[dict]] = {}
    todo = [e for e in cfg.get("venues", []) if args.all or "geo_checked" not in e]
    try:
        for i, e in enumerate(todo, 1):
            try:
                found[e["name"]] = geocode_entry(e, cache, fetch)
            except OSError as err:                  # 네트워크 오류: 그 곳은 건너뛰고 다음 실행 때 다시
                print(f"  ⚠️ {e['name']}: {err}", file=sys.stderr)
                continue
            if i % 20 == 0:
                save_cache(args.cache, cache)
                print(f"  {i}/{len(todo)} (요청 {fetch.calls}건)", flush=True)
    finally:
        save_cache(args.cache, cache)
    conf = [v["geo_confidence"] for v in found.values() if v]
    print(f"확인 {len(found)}곳 · 좌표 찾음 {len(conf)} (high {conf.count('high')} · medium {conf.count('medium')}"
          f" · low {conf.count('low')}) · 못 찾음 {len(found) - len(conf)} · 새 요청 {fetch.calls}건")
    if not args.dry_run:
        fresh = json.loads(args.config.read_text(encoding="utf-8"))   # 도는 동안 다른 작업이 고쳤을 수 있어 다시 읽음
        out = apply(fresh, found, date.today().isoformat())
        args.config.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"✅ → {args.config}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
