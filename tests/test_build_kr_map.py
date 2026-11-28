"""시·도 경계 지도 자료 만들기(scripts/build_kr_map.py) 검사 — 가짜 경계로 반올림·작은 섬 빼기·이름 줄이기를 본다."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build_kr_map as bkm  # noqa: E402

OUT = ROOT / "docs" / "app" / "data" / "kr_sido.json"


def square(x, y, size):
    return [[x, y], [x + size, y], [x + size, y + size], [x, y + size], [x, y]]


def feature(name_ko, code, polys, adm0="KOR"):
    geom = ({"type": "MultiPolygon", "coordinates": polys} if len(polys) > 1
            else {"type": "Polygon", "coordinates": polys[0]})
    return {"type": "Feature", "properties": {"adm0_a3": adm0, "name_ko": name_ko, "iso_3166_2": code}, "geometry": geom}


class BuildKrMapTest(unittest.TestCase):
    def test_short_name(self):
        self.assertEqual(bkm.short_name("서울특별시"), "서울")
        self.assertEqual(bkm.short_name("충청남도"), "충남")
        self.assertEqual(bkm.short_name("제주특별자치도"), "제주")
        self.assertEqual(bkm.short_name("세종특별자치시"), "세종")
        self.assertEqual(len(bkm.SHORT_NAMES), 17)

    def test_round_ring_drops_repeated_points(self):
        ring = [[126.00001, 37.00001], [126.00004, 37.00002], [126.5, 37.0], [126.5, 37.5], [126.00001, 37.00001]]
        self.assertEqual(bkm.round_ring(ring), [[126.0, 37.0], [126.5, 37.0], [126.5, 37.5], [126.0, 37.0]])

    def test_ring_area(self):
        self.assertAlmostEqual(bkm.ring_area(square(0, 0, 2)), 4.0)

    def test_build_regions_keeps_largest_and_drops_tiny_islands(self):
        feats = [
            feature("서울특별시", "KR-11", [[square(126.8, 37.4, 0.3)]]),
            feature("전라남도", "KR-46", [[square(126.0, 34.5, 1.0)], [square(125.0, 34.0, 0.01)], [square(125.5, 34.2, 0.1)]]),
            feature("北", "KP-01", [[square(127, 39, 1)]], adm0="PRK"),
        ]
        regions = bkm.build_regions(feats)
        self.assertEqual([r["code"] for r in regions], ["KR-11", "KR-46"])  # 다른 나라는 뺌, 코드순
        self.assertEqual(regions[0]["name"], "서울")
        self.assertEqual(regions[0]["full"], "서울특별시")
        jn = regions[1]
        self.assertEqual(len(jn["rings"]), 2)  # 0.01도 섬(약 1㎢)은 뺌, 0.1도 섬은 남김
        self.assertEqual(jn["bbox"], [125.5, 34.2, 127.0, 35.5])

    def test_build_regions_keeps_holes(self):
        outer = square(126, 37, 1)
        hole = list(reversed(square(126.4, 37.4, 0.2)))
        regions = bkm.build_regions([feature("경기도", "KR-41", [[outer, hole]])])
        self.assertEqual(len(regions[0]["rings"]), 2)

    def test_add_dokdo_to_gyeongbuk(self):
        gb = {"code": "KR-47", "name": "경북", "full": "경상북도", "bbox": [128.0, 35.5, 130.9, 37.5],
              "rings": [square(128.0, 35.5, 1.0)]}
        other = {"code": "KR-11", "name": "서울", "full": "서울특별시", "bbox": [126.8, 37.4, 127.1, 37.7], "rings": []}
        regions, marks = bkm.add_dokdo([other, gb])
        out_gb = regions[1]
        self.assertEqual(len(out_gb["rings"]), 3)          # 동도·서도
        self.assertGreaterEqual(out_gb["bbox"][2], 131.86)
        self.assertEqual(marks, [{"name": "독도", "sido": "경북", "lon": bkm.DOKDO_LON, "lat": bkm.DOKDO_LAT}])
        self.assertEqual(len(gb["rings"]), 1)              # 원본은 그대로
        self.assertEqual(regions[0], other)

    @unittest.skipUnless(OUT.exists(), "지도 자료가 아직 없음")
    def test_built_file_is_small_and_complete(self):
        self.assertLess(OUT.stat().st_size, 120_000)
        data = json.loads(OUT.read_text(encoding="utf-8"))
        self.assertIn("Natural Earth", data["source"])
        self.assertEqual(len(data["regions"]), 17)
        self.assertEqual(sorted(r["name"] for r in data["regions"]), sorted(bkm.SHORT_NAMES.values()))
        gb = next(r for r in data["regions"] if r["code"] == "KR-47")
        self.assertGreaterEqual(gb["bbox"][2], 131.86)      # 독도 포함
        self.assertEqual([m["name"] for m in data["marks"]], ["독도"])

    def test_main_writes_json(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "in.geojson"
            out = Path(d) / "out.json"
            src.write_text(json.dumps({"features": [feature("부산광역시", "KR-26", [[square(129, 35, 0.2)]])]}),
                           encoding="utf-8")
            bkm.main([str(src), str(out)])
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(data["regions"][0]["name"], "부산")


if __name__ == "__main__":
    unittest.main()
