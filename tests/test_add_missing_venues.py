"""add_missing_venues: 공연 기록엔 있는데 마스터 목록에 없어 도시·좌표가 빈 공연장 → 마스터 목록 항목 만들기."""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import add_missing_venues as amv  # noqa: E402

AS_OF = date(2026, 11, 28)
URL = "https://www.indiego.co.kr/events/1"


class OnlineTest(unittest.TestCase):
    def test_online_broadcast_names(self):
        self.assertTrue(amv.is_online("KT&G 상상마당 부산 공식 인스타그램 LIVE"))
        self.assertTrue(amv.is_online("KT&G 상상마당 홍대 공식 유튜브 채널"))
        self.assertFalse(amv.is_online("GBN LIVEHOUSE"))
        self.assertFalse(amv.is_online("롤링홀"))


class BuildEntryTest(unittest.TestCase):
    def test_region_status_and_source_from_gig_data(self):
        e = amv.build_entry("작은물", "서울 중구 을지로16길 6 3층", URL, "2022-07-02", AS_OF, {})
        self.assertEqual((e["province"], e["city"], e["district"]), ("서울", "서울", "중구"))
        self.assertEqual(e["status"], "unknown")  # 1년 넘게 공연 기록 없음 → 확인 필요(폐업이라고 단정하지 않음)
        self.assertIn("2022-07-02", e["status_note"])
        self.assertEqual(e["sources"][0]["url"], URL)
        self.assertEqual(e["checked"], "2026-11-28")
        self.assertEqual(e["type"], "")

    def test_recent_gig_is_open(self):
        e = amv.build_entry("새곳", "부산 수영구 수영로 429", URL, "2026-10-01", AS_OF, {})
        self.assertEqual(e["status"], "open")

    def test_same_address_as_master_entry_is_noted(self):
        e = amv.build_entry("네스트나다", "서울 마포구 와우산로29길 15 2층", URL, "2023-06-30", AS_OF,
                            {"와우산로29길15": "언플러그드 라운지"})
        self.assertIn("언플러그드 라운지", e["status_note"])
        self.assertEqual(e["status"], "unknown")

    def test_known_move_is_closed_with_extra_source(self):
        e = amv.build_entry("LG아트센터", "서울 강남구 논현로 508", URL, "2021-06-12", AS_OF, {})
        self.assertEqual(e["status"], "closed")
        self.assertEqual(e["moved_to"], "LG아트센터 서울")
        self.assertGreaterEqual(len(e["sources"]), 2)

    def test_no_region_returns_none(self):
        self.assertIsNone(amv.build_entry("어딘가", "아차산로5길 24-14", URL, "2026-11-28", AS_OF, {}))
        self.assertIsNone(amv.build_entry("주소없음", "", URL, "2026-11-28", AS_OF, {}))


class RegionFromDisplayTest(unittest.TestCase):
    def test_nominatim_display_name(self):
        d = "24-14, 아차산로5길, 성수동2가, 성동구, 서울특별시, 04793, 대한민국"
        self.assertEqual(amv.region_from_display(d), {"province": "서울", "city": "서울", "district": "성동구"})
        self.assertEqual(amv.region_from_display(""), {"province": "", "city": "", "district": ""})


class PlanMergeTest(unittest.TestCase):
    def setUp(self):
        self.missing = [("작은물", "2022-07-02"), ("KT&G 상상마당 홍대 공식 유튜브 채널", "2021-11-02"),
                        ("KT&G 상상마당 홍대 안녕바다", "2019-06-02"), ("GBN LIVEHOUSE", "2019-02-15")]
        self.addresses = {"작은물": "서울 중구 을지로16길 6 3층", "KT&G 상상마당 홍대 안녕바다": "KT&G 상상마당 홍대"}
        self.urls = {"작은물": URL}

    def test_plan_sorts_into_new_alias_and_skipped(self):
        entries, our_names, skipped, no_region = amv.plan(self.missing, self.addresses, self.urls, AS_OF, [])
        self.assertEqual([e["name"] for e in entries], ["작은물"])
        self.assertEqual(our_names, {"KT&G 상상마당 홍대 라이브홀": ["KT&G 상상마당 홍대 안녕바다"]})
        self.assertEqual({n for n, _ in skipped}, {"KT&G 상상마당 홍대 공식 유튜브 채널", "GBN LIVEHOUSE"})
        self.assertEqual(no_region, [])

    def test_merge_appends_without_duplicates_and_keeps_others(self):
        cfg = {"checked": "x", "venues": [
            {"name": "KT&G 상상마당 홍대 라이브홀", "our_names": ["라이브홀"]},
            {"name": "다른 작업자가 넣은 곳", "aliases": ["작은물"]},
        ]}
        new = [{"name": "작은물", "city": "서울"}, {"name": "진짜 새곳", "city": "부산"}]
        out, added, dup = amv.merge(cfg, new, {"KT&G 상상마당 홍대 라이브홀": ["KT&G 상상마당 홍대 안녕바다"]})
        names = [e["name"] for e in out["venues"]]
        self.assertEqual(names, ["KT&G 상상마당 홍대 라이브홀", "다른 작업자가 넣은 곳", "진짜 새곳"])
        self.assertEqual(out["venues"][0]["our_names"], ["라이브홀", "KT&G 상상마당 홍대 안녕바다"])
        self.assertEqual((added, dup), (["진짜 새곳"], ["작은물"]))
        self.assertEqual(cfg["venues"][0]["our_names"], ["라이브홀"])  # 원본은 그대로


def _r(lat, lon, rank, display):
    return {"lat": str(lat), "lon": str(lon), "place_rank": rank, "display_name": display}


class NameHitCheckTest(unittest.TestCase):
    def test_name_hit_must_be_in_same_district(self):
        e = {"name": "공감", "city": "인천", "district": "중구", "lat": 37.6, "lon": 126.65, "geo_confidence": "low"}
        cache = {"공감 인천": [_r(37.6, 126.65, 30, "공감, 완정로117번길, 검단구, 인천광역시, 대한민국")]}
        self.assertFalse(amv.name_hit_ok(e, cache))
        ok = {**e, "name": "꿈빛극장", "city": "서울", "district": "성북구"}
        self.assertTrue(amv.name_hit_ok(ok, {"꿈빛극장 서울": [_r(37.6, 126.65, 30, "꿈빛극장, 20, 길음로, 성북구, 서울특별시")]}))

    def test_address_hits_are_not_rechecked(self):
        self.assertTrue(amv.name_hit_ok({"name": "x", "geo_confidence": "high", "lat": 1, "lon": 2}, {}))

    def test_name_variants(self):
        self.assertEqual(amv.name_variants("속초 칠성조선소", "속초"), ["속초 칠성조선소", "칠성조선소"])
        self.assertEqual(amv.name_variants("한국소리문화의전당 연지홀", "전주"), ["한국소리문화의전당 연지홀", "한국소리문화의전당"])
        self.assertEqual(amv.name_variants("난지한강공원", "서울"), ["난지한강공원"])
        self.assertEqual(amv.name_variants("세빛섬 예빛무대", "서울"), ["세빛섬 예빛무대", "세빛섬"])
        # 첫 낱말만 남기면 엉뚱한 곳(예: 'KT&G' → KT&G 강원본부, '홍대' → 동네 전체)이 걸려서 안 씀
        self.assertEqual(amv.name_variants("홍대 플렉스라운지", "서울"), ["홍대 플렉스라운지"])
        self.assertEqual(amv.name_variants("을지로 H.ai", "서울"), ["을지로 H.ai"])
        self.assertEqual(amv.name_variants("KT&G 상상마당 춘천 사운드홀", "춘천"),
                         ["KT&G 상상마당 춘천 사운드홀", "KT&G 상상마당 춘천"])
        self.assertEqual(amv.name_variants("KT&G 상상마당 춘천", "춘천"), ["KT&G 상상마당 춘천", "KT&G 상상마당"])

    def test_area_fallback_needs_name_and_place_match(self):
        e = {"name": "서피랑공원", "city": "통영", "district": ""}
        good = [_r(34.85, 128.42, 24, "서피랑공원, 중앙동, 통영시, 경상남도, 대한민국")]
        hit = amv.area_fallback(e, lambda q: good if q == "서피랑공원 통영" else [])
        self.assertEqual((hit["geo_confidence"], hit["geo_method"]), ("low", "name"))
        other = [_r(34.85, 128.42, 24, "다른공원, 중앙동, 통영시, 경상남도, 대한민국")]
        self.assertIsNone(amv.area_fallback(e, lambda q: other))
        far = [_r(35.1, 129.0, 24, "서피랑공원, 부산광역시, 대한민국")]
        self.assertIsNone(amv.area_fallback(e, lambda q: far))


class MadeHereTest(unittest.TestCase):
    def test_only_entries_this_script_made(self):
        mine = amv.build_entry("작은물", "서울 중구 을지로16길 6 3층", URL, "2022-07-02", AS_OF, {})
        self.assertTrue(amv.made_here(mine))
        self.assertTrue(amv.made_here(amv.build_entry("LG아트센터", "서울 강남구 논현로 508", URL, "2021-06-12", AS_OF, {})))
        older = {"name": "A.O.R", "in_our_data": True, "status_note": "우리 공연 데이터 마지막 공연 2026-11-26",
                 "sources": [{"url": URL, "note": amv.SOURCE_NOTE}, {"url": "https://www.instagram.com/x/", "note": "인스타"}]}
        self.assertFalse(amv.made_here(older))  # 다른 근거가 더 있는 기존 항목은 손대지 않음


if __name__ == "__main__":
    unittest.main()
