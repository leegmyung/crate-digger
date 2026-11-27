"""venues_kr: 한국 공연장·도시 마스터 목록(config/venues_kr.json)과 우리 공연 데이터의 도시 분포·출처 공백."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import venues_kr as vk  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _v(name, city="서울", province=None, **kw):
    base = {"name": name, "aliases": [], "province": province or city, "city": city, "district": "",
            "type": "live_club", "status": "open", "sources": [{"url": "https://example.com"}],
            "checked": "2026-11-27"}
    base.update(kw)
    return base


def _sig(team, date, venue, source="indistreet"):
    return {"team_key": team, "branch": "공연", "source": source, "signal_date": date, "venue": venue}


class RegionTest(unittest.TestCase):
    def test_metro_city_uses_sido_and_gu(self):
        self.assertEqual(vk.parse_region("서울 마포구 와우산로29길 12"),
                         {"province": "서울", "city": "서울", "district": "마포구"})
        self.assertEqual(vk.parse_region("부산광역시 수영구 광안해변로 1"),
                         {"province": "부산", "city": "부산", "district": "수영구"})
        self.assertEqual(vk.parse_region("서울특별시 용산구 이태원로 1")["city"], "서울")

    def test_province_uses_si_without_suffix(self):
        self.assertEqual(vk.parse_region("강원특별자치도 춘천시 서부대성로 1"),
                         {"province": "강원", "city": "춘천", "district": ""})
        self.assertEqual(vk.parse_region("경기 수원시 팔달구 정조로 1"),
                         {"province": "경기", "city": "수원", "district": "팔달구"})
        self.assertEqual(vk.parse_region("제주특별자치도 서귀포시 남원읍 한신로 515")["city"], "서귀포")
        self.assertEqual(vk.parse_region("전북특별자치도 전주시 완산구 1")["city"], "전주")

    def test_merged_gwangju_jeonnam_name(self):
        self.assertEqual(vk.parse_region("전남광주통합특별시 동구 문화전당로 43")["city"], "광주")
        self.assertEqual(vk.parse_region("전남광주통합특별시 목포시 1")["city"], "목포")

    def test_clean_address_drops_unbalanced_paren_tail(self):
        self.assertEqual(vk.clean_address("서울 마포구 와우산로 156 지하1층 (서교동"), "서울 마포구 와우산로 156 지하1층")
        self.assertEqual(vk.clean_address("서울 종로구 사직로 8 (교북동)"), "서울 종로구 사직로 8 (교북동)")

    def test_unknown_or_empty_address(self):
        self.assertEqual(vk.parse_region(""), {"province": "", "city": "", "district": ""})
        self.assertEqual(vk.parse_region("주소 미입력")["city"], "")
        self.assertEqual(vk.parse_region("양화로 1")["city"], "")


class TypeTest(unittest.TestCase):
    def test_guess_type_from_name(self):
        self.assertEqual(vk.guess_type("부산음악창작소"), "creation_center")
        self.assertEqual(vk.guess_type("카페 언플러그드 홍대점"), "cafe")
        self.assertEqual(vk.guess_type("롤링홀"), "hall")
        self.assertEqual(vk.guess_type("KT&G 상상마당 춘천 야외공연장"), "festival")
        self.assertEqual(vk.guess_type("Club 빵"), "live_club")


class StatsTest(unittest.TestCase):
    def test_gig_stats_skips_extra_not_venue_names(self):
        st = vk.gig_stats([_sig("a", "2025-01-01", "축제"), _sig("a", "2025-01-01", "X")], skip={"축제"})
        self.assertEqual(set(st), {"X"})

    def test_gig_stats_counts_days_and_teams_and_skips_non_venue(self):
        rows = [_sig("a", "2025-01-01", "X"), _sig("b", "2025-01-01", "X"), _sig("a", "2025-02-01", "X"),
                _sig("c", "2025-03-01", "공연장 미정"), _sig("d", "2025-03-01", ""),
                {"team_key": "e", "branch": "큐레이션", "source": "s", "signal_date": "2025-01-01", "venue": "X"}]
        st = vk.gig_stats(rows)
        self.assertEqual(set(st), {"X"})
        self.assertEqual(st["X"]["gig_days"], 2)
        self.assertEqual(st["X"]["teams"], {"a", "b"})
        self.assertEqual((st["X"]["first"], st["X"]["last"]), ("2025-01-01", "2025-02-01"))


class MatchTest(unittest.TestCase):
    def test_match_by_name_alias_key_and_our_names(self):
        master = [_v("Club 빵", aliases=["클럽빵"]),
                  _v("KT&G 상상마당 홍대 라이브홀", our_names=["라이브홀"]),
                  _v("HQ광안", city="부산")]
        got = vk.match_our_venues(master, ["클럽 빵", "라이브홀", "HQ 광안", "어딘가"])
        self.assertEqual(got, {"클럽 빵": 0, "라이브홀": 1, "HQ 광안": 2})

    def test_instagram_handle_venue_matches_by_account(self):
        # 인스타 라인업 글은 공연장 칸에 계정 이름('@handle')이 들어옴
        master = [_v("언플러그드 라운지", instagram="unplugged.lounge"),
                  _v("퍼플홀", city="안양", sources=[{"url": "https://www.instagram.com/purple_hall/", "note": "인스타"}])]
        got = vk.match_our_venues(master, ["@Unplugged.Lounge", "@purple_hall", "@unbornsounds"])
        self.assertEqual(got, {"@Unplugged.Lounge": 0, "@purple_hall": 1})

    def test_generic_name_does_not_match_without_our_names(self):
        master = [_v("KT&G 상상마당 부산 3층 라이브홀", city="부산")]
        self.assertEqual(vk.match_our_venues(master, ["라이브홀"]), {})


class DistributionTest(unittest.TestCase):
    def setUp(self):
        self.master = [_v("A"), _v("B", city="부산"), _v("C", city="광주"), _v("D", city="광주", status="closed")]
        rows = [_sig("t1", "2025-01-01", "A"), _sig("t2", "2025-01-01", "A"), _sig("t1", "2025-01-02", "A"),
                _sig("t3", "2025-01-05", "B"), _sig("t9", "2025-01-06", "모르는곳")]
        self.stats = vk.gig_stats(rows)
        self.match = vk.match_our_venues(self.master, list(self.stats))

    def test_city_distribution_counts_and_unknown(self):
        city_of = vk.venue_city(self.stats, self.match, self.master, {})
        dist = {d["city"]: d for d in vk.city_distribution(self.stats, city_of)}
        self.assertEqual(dist["서울"]["gig_days"], 2)
        self.assertEqual(dist["서울"]["teams"], 2)
        self.assertEqual(dist["부산"]["gig_days"], 1)
        self.assertEqual(dist["(도시 모름)"]["venues"], 1)

    def test_venue_city_falls_back_to_address(self):
        city_of = vk.venue_city(self.stats, self.match, self.master, {"모르는곳": "대전 중구 중교로 40"})
        self.assertEqual(city_of["모르는곳"], "대전")

    def test_non_venue_account_handles_get_their_own_label_not_regional(self):
        rows = [_sig("t1", "2025-01-01", "A"), _sig("t5", "2025-01-03", "@somecrew"), _sig("t6", "2025-01-04", "@realclub")]
        stats = vk.gig_stats(rows)
        match = vk.match_our_venues(self.master, list(stats))
        city_of = vk.venue_city(stats, match, self.master, {}, non_venue_handles={"somecrew"})
        self.assertEqual(city_of["@somecrew"], vk.NON_VENUE_CITY)
        self.assertEqual(city_of["@realclub"], vk.UNKNOWN_CITY)
        self.assertEqual(vk.city_kind(vk.NON_VENUE_CITY), vk.UNKNOWN_CITY)   # 지방으로 세지 않음
        self.assertEqual(vk.city_kind("부산"), "지방")
        self.assertEqual(vk.city_kind(vk.SEOUL), vk.SEOUL)

    def test_coverage_by_city_counts_open_and_in_data(self):
        cov = {c["city"]: c for c in vk.coverage_by_city(self.master, self.match, self.stats)}
        self.assertEqual((cov["서울"]["venues"], cov["서울"]["in_data"]), (1, 1))
        self.assertEqual((cov["광주"]["venues"], cov["광주"]["in_data"], cov["광주"]["closed"]), (1, 0, 1))

    def test_gaps_are_open_non_seoul_venues_with_few_gig_days(self):
        gaps = vk.source_gaps(self.master, self.match, self.stats, min_days=3)
        names = [g["name"] for g in gaps]
        self.assertIn("B", names)          # 우리 데이터에 1일뿐
        self.assertIn("C", names)          # 없음
        self.assertNotIn("A", names)       # 서울
        self.assertNotIn("D", names)       # 폐업

    def test_gaps_skip_mainstream_big_venues(self):
        master = [*self.master, _v("KINTEX", city="고양", province="경기", mainstream=True)]
        names = [g["name"] for g in vk.source_gaps(master, self.match, self.stats)]
        self.assertNotIn("KINTEX", names)


class ExternalCoverageTest(unittest.TestCase):
    def test_counts_only_entries_with_outside_sources(self):
        ours = [{"url": "https://indistreet.com/gigs/1", "note": "우리 공연 데이터 원본 공연 페이지"}]
        master = [_v("A", sources=ours), _v("B"), _v("C", city="부산"), _v("D", status="closed")]
        stats = vk.gig_stats([_sig("t", "2025-01-01", "A"), _sig("t", "2025-01-01", "B")])
        got = vk.external_coverage(master, vk.match_our_venues(master, stats), stats)
        self.assertEqual(got, {"external": 2, "in_data": 1, "seoul": 1, "seoul_in_data": 1})


class UpdateInDataTest(unittest.TestCase):
    def test_our_venue_is_never_an_instagram_handle(self):
        # venue_xref 가 our_venue 를 '@계정'의 대표 이름으로 쓰므로, '@계정'이면 공연장 이름으로 안 바뀜
        cfg = {"venues": [_v("BOLERO", instagram="boleroseoul"), _v("록집", instagram="rock._.zip"), _v("없음")]}
        stats = vk.gig_stats([_sig("a", "2025-01-01", "@boleroseoul"), _sig("a", "2025-01-02", "@boleroseoul"),
                              _sig("b", "2025-01-01", "@rock._.zip"), _sig("b", "2025-01-01", "록집"),
                              _sig("b", "2025-01-02", "@rock._.zip")])
        got = {e["name"]: (e["our_venue"], e["in_our_data"]) for e in vk.update_in_data(cfg, stats)["venues"]}
        self.assertEqual(got, {"BOLERO": ("BOLERO", True), "록집": ("록집", True), "없음": (None, False)})


class SameAddressTest(unittest.TestCase):
    def test_groups_entries_sharing_road_address(self):
        master = [_v("001 클럽", address="서울 마포구 와우산로18길 20"),
                  _v("공공일클럽", address="서울 마포구 와우산로18길 20 지하"),
                  _v("다른곳", address="서울 마포구 와우산로29길 12"), _v("주소없음")]
        self.assertEqual(vk.same_address_groups(master), [["001 클럽", "공공일클럽"]])


class ValidateTest(unittest.TestCase):
    def test_flags_missing_fields_bad_type_and_duplicates(self):
        cfg = {"venues": [_v("A"), _v("A"), _v("B", type="stadium"), _v("C", sources=[]), _v("E", city="")]}
        problems = " ".join(vk.validate(cfg))
        for word in ("A", "B", "C", "E"):
            self.assertIn(word, problems)

    def test_repo_config_is_valid(self):
        path = ROOT / "config" / "venues_kr.json"
        cfg = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(vk.validate(cfg), [])


class RenderTest(unittest.TestCase):
    def test_render_has_sections(self):
        master = [_v("A"), _v("B", city="부산", instagram="b_club")]
        rows = [_sig("t1", "2025-01-01", "A")]
        st = vk.gig_stats(rows)
        m = vk.match_our_venues(master, list(st))
        md = vk.render({"venues": master, "checked": "2026-11-27"}, st, m, {})
        self.assertIn("2026-11-27", md)
        for word in ("도시별 공연장", "우리 공연 데이터의 도시 분포", "출처 공백", "수집 후보", "@b_club"):
            self.assertIn(word, md)


if __name__ == "__main__":
    unittest.main()
