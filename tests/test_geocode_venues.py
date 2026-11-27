"""geocode_venues: 공연장 마스터 목록(config/venues_kr.json)에 지도용 좌표(lat·lon)·확실도 붙이기."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import geocode_venues as gv  # noqa: E402


def _hit(lat, lon, rank, display="서울특별시 마포구 와우산로", addresstype="building"):
    return {"lat": str(lat), "lon": str(lon), "place_rank": rank, "display_name": display,
            "addresstype": addresstype}


class AddressQueryTest(unittest.TestCase):
    def test_strips_floor_and_paren(self):
        self.assertEqual(gv.address_query("서울 마포구 와우산로 156 지하1층"), "서울 마포구 와우산로 156")
        self.assertEqual(gv.address_query("서울 마포구 와우산로14길 4 지층1"), "서울 마포구 와우산로14길 4")
        self.assertEqual(gv.address_query("서울 종로구 성균관로 87 1층"), "서울 종로구 성균관로 87")
        self.assertEqual(gv.address_query("서울 마포구 와우산로 53 지하"), "서울 마포구 와우산로 53")
        self.assertEqual(gv.address_query("부산 중구 광복로 1 2F (광복동"), "부산 중구 광복로 1")
        self.assertEqual(gv.address_query("서울 마포구 어울마당로 35, B1"), "서울 마포구 어울마당로 35")

    def test_cuts_building_name_after_road_number(self):
        self.assertEqual(gv.address_query("서울 서대문구 연희로 14 준영빌딩 지하 1층"), "서울 서대문구 연희로 14")
        self.assertEqual(gv.address_query("서울 마포구 잔다리로 35 서원빌딩 B1 사운드시티"), "서울 마포구 잔다리로 35")
        self.assertEqual(gv.address_query("서울특별시 마포구 성미산로 22길 16, 지하 1,2층"), "서울특별시 마포구 성미산로 22길 16")
        self.assertEqual(gv.address_query("서울 마포구 와우산로17길 19-22 DO빌딩 지하 1층"), "서울 마포구 와우산로17길 19-22")
        self.assertEqual(gv.address_query("강원특별자치도 춘천시 스포츠타운길399번길 25"), "강원특별자치도 춘천시 스포츠타운길399번길 25")
        self.assertEqual(gv.address_query("서울 중구 신당동 140-30 지하"), "서울 중구 신당동 140-30")   # 지번은 그대로

    def test_empty_address(self):
        self.assertEqual(gv.address_query(""), "")
        self.assertEqual(gv.address_query(None), "")


class PickTest(unittest.TestCase):
    def test_building_level_address_is_high(self):
        got = gv.pick([_hit(37.55, 126.92, 30)], method="address", city="서울")
        self.assertEqual(got, {"lat": 37.55, "lon": 126.92, "geo_confidence": "high", "geo_method": "address"})

    def test_road_level_address_is_medium(self):
        got = gv.pick([_hit(37.55, 126.92, 26, addresstype="road")], method="address", city="서울")
        self.assertEqual(got["geo_confidence"], "medium")

    def test_district_level_is_rejected(self):
        self.assertIsNone(gv.pick([_hit(37.55, 126.92, 18, addresstype="city_district")], method="address",
                                  city="서울"))

    def test_name_hit_is_low_and_must_be_in_city(self):
        ok = gv.pick([_hit(35.1, 129.0, 30, display="오방가르드, 부산광역시 중구")], method="name", city="부산")
        self.assertEqual(ok["geo_confidence"], "low")
        self.assertIsNone(gv.pick([_hit(37.5, 127.0, 30, display="오방가르드, 서울특별시")], method="name",
                                  city="부산"))

    def test_outside_korea_is_rejected(self):
        self.assertIsNone(gv.pick([_hit(48.8, 2.3, 30)], method="address", city="서울"))

    def test_no_results(self):
        self.assertIsNone(gv.pick([], method="address", city="서울"))


class GeocodeEntryTest(unittest.TestCase):
    def test_uses_cache_and_falls_back_to_name(self):
        calls = []

        def fetch(q):
            calls.append(q)
            return [_hit(35.1, 129.03, 30, display="오방가르드, 부산광역시 중구")] if "오방가르드" in q else []

        cache = {}
        e = {"name": "오방가르드", "city": "부산", "province": "부산", "address": "부산 중구 광복로 1 지하1층"}
        got = gv.geocode_entry(e, cache, fetch)
        self.assertEqual(got["geo_method"], "name")
        self.assertEqual(calls, ["부산 중구 광복로 1", "오방가르드 부산"])
        # 두 번째는 캐시에서 — 다시 묻지 않음
        gv.geocode_entry(e, cache, fetch)
        self.assertEqual(len(calls), 2)

    def test_road_level_address_upgraded_by_matching_name_hit(self):
        def fetch(q):
            if q == "서울 마포구 동교로22길 14":
                return [_hit(37.555, 126.919, 26, display="동교로22길, 서교동, 마포구, 서울특별시", addresstype="road")]
            return [_hit(37.5551, 126.9191, 30, display="클럽A, 14, 동교로22길, 서교동, 마포구, 서울특별시")]

        e = {"name": "클럽A", "city": "서울", "address": "서울 마포구 동교로22길 14 지하1층"}
        got = gv.geocode_entry(e, {}, fetch)
        self.assertEqual((got["geo_confidence"], got["geo_method"], got["lat"]), ("high", "name+address", 37.5551))

    def test_road_level_address_kept_when_name_hit_elsewhere(self):
        def fetch(q):
            if "동교로" in q:
                return [_hit(37.555, 126.919, 26, display="동교로22길, 마포구, 서울특별시", addresstype="road")]
            return [_hit(37.50, 127.02, 30, display="클럽A, 강남대로, 서울특별시")]

        got = gv.geocode_entry({"name": "클럽A", "city": "서울", "address": "서울 마포구 동교로22길 14"}, {}, fetch)
        self.assertEqual((got["geo_confidence"], got["geo_method"]), ("medium", "address"))

    def test_road_name(self):
        self.assertEqual(gv.road_name("서울 마포구 와우산로14길 4"), "와우산로14길")
        self.assertEqual(gv.road_name("서울 마포구 동교로 63"), "동교로")
        self.assertEqual(gv.road_name(""), "")

    def test_not_found_stays_empty(self):
        got = gv.geocode_entry({"name": "없는곳", "city": "서울", "address": ""}, {}, lambda q: [])
        self.assertIsNone(got)


class ApplyTest(unittest.TestCase):
    def test_apply_sets_and_clears_fields(self):
        cfg = {"venues": [{"name": "A", "city": "서울"}, {"name": "B", "city": "서울", "lat": 1.0, "lon": 2.0,
                                                          "geo_confidence": "low", "geo_method": "name"}]}
        out = gv.apply(cfg, {"A": {"lat": 37.5, "lon": 127.0, "geo_confidence": "high", "geo_method": "address"},
                             "B": None}, checked="2026-11-27")
        a, b = out["venues"]
        self.assertEqual((a["lat"], a["lon"], a["geo_confidence"], a["geo_checked"]), (37.5, 127.0, "high",
                                                                                       "2026-11-27"))
        self.assertNotIn("lat", b)
        self.assertEqual(b["geo_checked"], "2026-11-27")
        self.assertNotIn("lat", cfg["venues"][0])     # 원본은 그대로 (새 사본을 돌려줌)

    def test_cache_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.json"
            gv.save_cache(p, {"q": []})
            self.assertEqual(gv.load_cache(p), {"q": []})
            self.assertEqual(gv.load_cache(Path(d) / "none.json"), {})


if __name__ == "__main__":
    unittest.main()
