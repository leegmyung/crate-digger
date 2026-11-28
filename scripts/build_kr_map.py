"""한국 시·도 경계 지도 자료 만들기 → docs/app/data/kr_sido.json (앱 지도 components/region_map.js 가 읽음).

원본: Natural Earth 1:10m admin-1 (퍼블릭 도메인, https://www.naturalearthdata.com/about/terms-of-use/)
  ne_10m_admin_1_states_provinces.geojson 을 받아(커밋 안 함) 경로를 넘긴다:
  python3 scripts/build_kr_map.py <받은 geojson> [docs/app/data/kr_sido.json]
줄이는 방법: 좌표 소수점 셋째 자리(약 100m)로 반올림 · 이어진 같은 점 빼기 · 아주 작은 섬(약 3㎢ 미만) 빼기.
이웃 시·도의 경계 점이 원본에서 같으니 반올림해도 틈이 생기지 않는다.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "docs" / "app" / "data" / "kr_sido.json"
DECIMALS = 3
MIN_ISLAND_AREA = 0.0003  # 제곱 도(°²) — 약 3㎢. 시·도의 가장 큰 땅은 크기와 상관없이 남긴다.
SOURCE = "Natural Earth 1:10m admin-1 states/provinces (퍼블릭 도메인)"

SHORT_NAMES = {
    "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천",
    "광주광역시": "광주", "대전광역시": "대전", "울산광역시": "울산", "세종특별자치시": "세종",
    "경기도": "경기", "강원도": "강원", "충청북도": "충북", "충청남도": "충남",
    "전라북도": "전북", "전라남도": "전남", "경상북도": "경북", "경상남도": "경남",
    "제주특별자치도": "제주",
}


def short_name(full: str) -> str:
    return SHORT_NAMES.get(full, full)


def round_ring(ring: list) -> list:
    """좌표 반올림 + 이어진 같은 점 빼기 (새 목록을 돌려준다)."""
    out: list = []
    for x, y in ring:
        pt = [round(x, DECIMALS), round(y, DECIMALS)]
        if not out or out[-1] != pt:
            out.append(pt)
    return out


def ring_area(ring: list) -> float:
    """신발끈 공식 넓이(절댓값, 제곱 도)."""
    s = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        s += x1 * y2 - x2 * y1
    return abs(s) / 2


def _polygons(geometry: dict) -> list:
    if geometry["type"] == "Polygon":
        return [geometry["coordinates"]]
    return geometry["coordinates"]


def _region(feature: dict) -> dict:
    props = feature["properties"]
    polys = [[round_ring(r) for r in poly] for poly in _polygons(feature["geometry"])]
    polys = [p for p in polys if len(p[0]) >= 4]
    largest = max(ring_area(p[0]) for p in polys)
    kept = [p for p in polys if ring_area(p[0]) >= MIN_ISLAND_AREA or ring_area(p[0]) == largest]
    rings = [r for p in kept for r in p if len(r) >= 4]
    xs = [x for r in rings for x, _ in r]
    ys = [y for r in rings for _, y in r]
    full = props["name_ko"]
    return {
        "code": props["iso_3166_2"], "name": short_name(full), "full": full,
        "bbox": [min(xs), min(ys), max(xs), max(ys)], "rings": rings,
    }


def build_regions(features: list) -> list:
    kor = [f for f in features if f["properties"].get("adm0_a3") == "KOR"]
    return sorted((_region(f) for f in kor), key=lambda r: r["code"])


def main(argv: list) -> None:
    if not argv:
        sys.exit("사용법: python3 scripts/build_kr_map.py <ne_10m_admin_1_states_provinces.geojson> [출력 경로]")
    src = Path(argv[0])
    out = Path(argv[1]) if len(argv) > 1 else DEFAULT_OUT
    features = json.loads(src.read_text(encoding="utf-8"))["features"]
    regions = build_regions(features)
    data = {"source": SOURCE, "decimals": DECIMALS, "regions": regions}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    pts = sum(len(r) for g in regions for r in g["rings"])
    print(f"{out.name}: 시·도 {len(regions)}곳 · 점 {pts:,}개 · {out.stat().st_size:,}바이트")


if __name__ == "__main__":
    main(sys.argv[1:])
