"""venue_profiles: 앱 공연장 상세(Chartmetric 공연장 페이지처럼)에 쓸 공연장 프로필 만들기."""
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import venue_profiles as vp  # noqa: E402

AS_OF = date(2026, 11, 27)
CFG = {"tiers": [{"tier": "S", "max": 150}, {"tier": "M", "max": 400}, {"tier": "L", "max": 1000},
                 {"tier": "XL", "max": None}],
       "venues": {"큰홀": {"capacity": 450, "tier": "L", "source": "u"},
                  "작은클럽": {"capacity": None, "tier": None},
                  "축제": {"capacity": None, "tier": None, "not_venue": True}}}
TEAMS = {"a": "에이", "b": "비", "c": "씨", "w": "우승팀", "x": "엑스"}


def _gigs():
    return [
        ("w", date(2024, 3, 1), "작은클럽"), ("w", date(2024, 9, 1), "큰홀"),     # 정답(2025-01-01) 전에 큰홀
        ("x", date(2025, 6, 1), "큰홀"),                                           # 정답(2025-01-01) 뒤에야 큰홀 → 아님
        ("a", date(2026, 3, 1), "큰홀"),                                           # a 의 첫 공연 = 큰홀 (첫 출연)
        ("b", date(2025, 1, 1), "작은클럽"), ("b", date(2026, 5, 1), "큰홀"),       # b 는 작은클럽이 첫 무대
        ("c", date(2026, 5, 1), "큰홀"),
        ("c", date(2027, 1, 2), "큰홀"),                                           # 예정 공연 → 날짜 수엔 안 셈
        ("a", date(2026, 6, 1), "축제"),                                           # 공연장 아님
    ]


OUTCOMES = [{"team_key": "w", "announced_date": date(2025, 1, 1), "counted": True, "program_label": "올해의 헬로루키",
             "grade": "S"},
            {"team_key": "x", "announced_date": date(2025, 1, 1), "counted": True, "program_label": "튠업", "grade": "S"},
            {"team_key": "b", "announced_date": date(2026, 1, 1), "counted": False, "program_label": "한대음 후보",
             "grade": "B"}]
SNAPSHOT = {"c": (1, 9.5), "a": (3, 7.0), "b": (40, 2.0)}


class ProfilesTest(unittest.TestCase):
    def setUp(self):
        self.p = vp.build_profiles(_gigs(), TEAMS, OUTCOMES, SNAPSHOT, CFG, {"큰홀": "서울"}, AS_OF)

    def test_capacity_tier_city(self):
        big = self.p["큰홀"]
        self.assertEqual((big["tier"], big["capacity"], big["city"]), ("L", 450, "서울"))
        self.assertEqual((self.p["작은클럽"]["tier"], self.p["작은클럽"]["city"]), (None, ""))
        self.assertNotIn("축제", self.p)

    def test_monthly_nights_exclude_future_and_upcoming_counted(self):
        big = self.p["큰홀"]
        self.assertEqual(big["monthly"]["2026-05"], 1)            # b·c 같은 날 = 공연 날짜 1
        self.assertNotIn("2027-01", big["monthly"])
        self.assertEqual(big["nights"], 4)                        # w·x·a·(b,c)
        self.assertEqual(big["upcoming_nights"], 1)

    def test_teams_last_year_and_first_timers(self):
        big = self.p["큰홀"]
        self.assertEqual(big["teams_1y"], 3)                      # a·b·c (2025-11-27 이후)
        self.assertEqual(big["first_timers_1y"], 2)               # a·c 는 우리 데이터 첫 공연이 여기
        self.assertAlmostEqual(big["first_timer_share_1y"], 2 / 3, places=3)

    def test_later_winners_only_if_played_before_outcome(self):
        winners = self.p["큰홀"]["later_winners"]
        self.assertEqual([w["team_key"] for w in winners], ["w"])
        self.assertEqual(winners[0]["first_here"], "2024-09-01")
        self.assertEqual(winners[0]["outcome"], "올해의 헬로루키")
        self.assertEqual(winners[0]["lead_months"], 4)
        self.assertEqual(self.p["큰홀"]["later_winners_total"], 1)
        self.assertEqual([w["team_key"] for w in self.p["작은클럽"]["later_winners"]], ["w"])   # 미집계 정답(b)은 안 셈

    def test_top_candidates_by_current_rank(self):
        top = self.p["큰홀"]["top_candidates"]
        self.assertEqual([t["team_key"] for t in top], ["c", "a", "b"])
        self.assertEqual(top[0], {"team_key": "c", "name": "씨", "rank": 1, "score": 9.5, "last_here": "2026-05-01"})

    def test_journey_before_after(self):
        big = self.p["큰홀"]
        self.assertEqual(big["before"], [["작은클럽", 1]])        # w 만 (b 는 1년 넘게 전)
        self.assertEqual(self.p["작은클럽"]["after"], [["큰홀", 1]])


class DiscoveryTest(unittest.TestCase):
    """발굴 주목도: 최근 12개월 공연일 × 첫 출연 신인 비율 × 정답 전 출연 비율 → 0~100 (정렬용)."""

    def setUp(self):
        self.p = vp.build_profiles(_gigs(), TEAMS, OUTCOMES, SNAPSHOT, CFG, {"큰홀": "서울"}, AS_OF)

    def test_raw_counts(self):
        d = self.p["큰홀"]["discovery"]
        self.assertEqual(d["nights_12m"], 2)                      # 2026-03-01 · 2026-05-01 (예정 공연 뺌)
        self.assertEqual(d["winner_base"], 2)                     # 1년 넘게 전에 처음 선 팀: w · x
        self.assertEqual(d["winner_hits"], 1)                     # 그중 정답 전에 선 팀: w
        self.assertAlmostEqual(d["winner_share"], 0.5)
        self.assertAlmostEqual(d["newcomer_share"], 2 / 3, places=3)

    def test_no_recent_nights_means_no_score(self):
        d = self.p["작은클럽"]["discovery"]
        self.assertEqual(d["nights_12m"], 0)
        self.assertIsNone(d["score"])
        self.assertEqual((d["winner_base"], d["winner_hits"]), (2, 1))   # w(정답 전) · b(미집계 정답 → 아님)

    def test_score_in_range(self):
        s = self.p["큰홀"]["discovery"]["score"]
        self.assertTrue(0 < s <= 100, s)

    def test_block_formula_with_shrinkage(self):
        raw = {"nights_12m": 365, "teams_1y": 10, "first_timers_1y": 10, "winner_base": 10, "winner_hits": 10}
        d = vp.discovery_block(raw, prior_new=0.5, prior_win=0.05)
        self.assertAlmostEqual(d["activity"], 1.0)
        self.assertAlmostEqual(d["newcomer_adj"], 0.75)           # (10 + 10×0.5) / (10 + 10)
        self.assertAlmostEqual(d["winner_adj"], 0.525)            # (10 + 10×0.05) / (10 + 10)
        self.assertAlmostEqual(d["winner_norm"], 1.0)             # 10% 이상이면 만점
        self.assertAlmostEqual(d["score"], round(100 * 0.75 ** (1 / 3), 1))

    def test_small_venue_pulled_toward_average(self):
        small = vp.discovery_block({"nights_12m": 12, "teams_1y": 1, "first_timers_1y": 1, "winner_base": 1,
                                    "winner_hits": 1}, prior_new=0.3, prior_win=0.02)
        self.assertLess(small["newcomer_adj"], 0.5)               # 1팀 중 1팀(100%)이어도 평균 쪽으로
        self.assertLess(small["winner_adj"], 0.2)

    def test_more_newcomers_scores_higher(self):
        base = {"nights_12m": 50, "teams_1y": 40, "winner_base": 40, "winner_hits": 2}
        lo = vp.discovery_block({**base, "first_timers_1y": 5}, prior_new=0.3, prior_win=0.02)
        hi = vp.discovery_block({**base, "first_timers_1y": 30}, prior_new=0.3, prior_win=0.02)
        self.assertGreater(hi["score"], lo["score"])

    def test_priors_are_pooled(self):
        profs = {"A": {"teams_1y": 10, "first_timers_1y": 5, "discovery": {"winner_base": 20, "winner_hits": 1}},
                 "B": {"teams_1y": 30, "first_timers_1y": 5, "discovery": {"winner_base": 80, "winner_hits": 4}}}
        self.assertEqual(vp.discovery_priors(profs), (10 / 40, 5 / 100))


class GeoTest(unittest.TestCase):
    def test_geo_copied_from_master_via_matching(self):
        master = {"venues": [{"name": "큰 홀 서교", "our_names": ["큰홀"], "city": "서울", "lat": 37.55, "lon": 126.92,
                              "geo_confidence": "high"},
                             {"name": "작은클럽", "city": "부산"}]}
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "v.json"
            p.write_text(json.dumps(master, ensure_ascii=False), encoding="utf-8")
            geo = vp.load_geo(["큰홀", "작은클럽", "없는곳"], p)
        self.assertEqual(geo["큰홀"], {"lat": 37.55, "lon": 126.92, "geo_confidence": "high", "city": "서울"})
        self.assertEqual(geo["작은클럽"], {"lat": None, "lon": None, "geo_confidence": None, "city": "부산"})
        self.assertNotIn("없는곳", geo)

    def test_profile_carries_geo_and_city_fallback(self):
        geo = {"큰홀": {"lat": 37.55, "lon": 126.92, "geo_confidence": "high", "city": "서울"},
               "작은클럽": {"lat": None, "lon": None, "geo_confidence": None, "city": "부산"}}
        p = vp.build_profiles(_gigs(), TEAMS, OUTCOMES, SNAPSHOT, CFG, {}, AS_OF, geo=geo)
        self.assertEqual((p["큰홀"]["lat"], p["큰홀"]["lon"], p["큰홀"]["geo_confidence"]), (37.55, 126.92, "high"))
        self.assertEqual(p["작은클럽"]["city"], "부산")              # 도시 표에 없으면 마스터 목록 도시로
        self.assertIsNone(p["작은클럽"]["lat"])

    def test_missing_master_file(self):
        self.assertEqual(vp.load_geo(["큰홀"], Path("/nonexistent/v.json")), {})


class CitiesTest(unittest.TestCase):
    def test_missing_file_is_empty(self):
        self.assertEqual(vp.load_cities(Path("/nonexistent/venues_kr.json")), {})

    def test_accepts_common_shapes(self):
        shapes = [{"venues": {"A": {"city": "부산"}}}, {"A": {"city": "부산"}}, {"A": "부산"},
                  {"venues": [{"venue": "A", "city": "부산"}]}, {"A": {"region": "부산"}}]
        for shape in shapes:
            with tempfile.TemporaryDirectory() as d:
                p = Path(d) / "v.json"
                p.write_text(json.dumps(shape, ensure_ascii=False), encoding="utf-8")
                self.assertEqual(vp.load_cities(p), {"A": "부산"}, shape)


class PayloadTest(unittest.TestCase):
    def test_payload_shape(self):
        prof = vp.build_profiles(_gigs(), TEAMS, OUTCOMES, SNAPSHOT, CFG, {}, AS_OF)
        out = vp.payload(prof, AS_OF)
        self.assertEqual(out["as_of"], "2026-11-27")
        self.assertEqual(list(out["venues"])[0], "큰홀")          # 공연 날짜 많은 순
        json.dumps(out, ensure_ascii=False)                        # JSON 으로 쓸 수 있어야 함


if __name__ == "__main__":
    unittest.main()


class MasterMetaTest(unittest.TestCase):
    """공연장 종류(type·type_basis)·한/영 별칭·'묶지 않음' 근거·수용 인원 출처 칸 (앱 공연장 상세·목록 '유형' 필터)."""

    MASTER = {"types": {"live_club": "라이브클럽", "hall": "홀·공연장"},
              "venues": [{"name": "큰 홀 서교", "aliases": ["Big Hall"], "our_names": ["큰홀"], "type": "hall",
                          "type_basis": "수동: 공식 소개"},
                         {"name": "작은클럽", "aliases": [], "type": "", "instagram": "smallclub"},
                         {"name": "닫은클럽", "aliases": [], "type": "live_club", "status": "closed",
                          "status_note": "2021 영업 종료", "moved_to": None},
                         {"name": "옮긴곳", "aliases": [], "type": "cafe", "status": "unknown",
                          "status_note": "둔산점으로 옮긴 듯", "moved_to": "대전 서구 대덕대로 244"}],
              "statuses": {"open": "운영", "unknown": "확인 필요", "closed": "폐업", "paused": "휴업"}}
    ALIASES = {"aliases": [{"venue": "큰홀", "variants": ["큰 홀(BIG HALL)", "@bighall"], "reason": "같은 곳"}],
               "_묶지_않음": [{"names": ["큰홀", "큰홀 2관"], "reason": "주소가 다름"}]}

    def _write(self, d, name, obj):
        p = Path(d) / name
        p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
        return p

    def test_master_meta_type_label_and_aliases(self):
        with tempfile.TemporaryDirectory() as d:
            meta = vp.load_master_meta(["큰홀", "작은클럽", "없는곳"], self._write(d, "v.json", self.MASTER))
        self.assertEqual(meta["큰홀"]["type"], "hall")
        self.assertEqual(meta["큰홀"]["type_label"], "홀·공연장")
        self.assertEqual(meta["큰홀"]["type_basis"], "수동: 공식 소개")
        self.assertEqual(meta["큰홀"]["aliases"], ["Big Hall", "큰 홀 서교"])     # 마스터 대표 이름도 별칭(우리 이름과 다르면)
        self.assertIsNone(meta["작은클럽"]["type"])                                # 빈 type 은 None(유형 미정)
        self.assertIsNone(meta["작은클럽"]["type_label"])
        self.assertNotIn("없는곳", meta)

    def test_master_meta_carries_operating_status(self):
        # 앱 공연장 목록·상세에 '폐업'·'이전' 표시를 하려면 운영 상태가 앱 데이터까지 와야 한다
        with tempfile.TemporaryDirectory() as d:
            meta = vp.load_master_meta(["닫은클럽", "옮긴곳", "작은클럽"], self._write(d, "v.json", self.MASTER))
        self.assertEqual((meta["닫은클럽"]["status"], meta["닫은클럽"]["status_label"]), ("closed", "폐업"))
        self.assertEqual(meta["닫은클럽"]["status_note"], "2021 영업 종료")
        self.assertEqual(meta["옮긴곳"]["moved_to"], "대전 서구 대덕대로 244")
        self.assertIsNone(meta["작은클럽"]["status"])                              # 상태 칸이 없으면 None
        p = vp.build_profiles(_gigs(), TEAMS, OUTCOMES, SNAPSHOT, CFG, {}, AS_OF,
                              meta={"작은클럽": meta["닫은클럽"]}, alias_notes={})
        self.assertEqual((p["작은클럽"]["status"], p["작은클럽"]["status_label"]), ("closed", "폐업"))
        self.assertEqual(p["작은클럽"]["status_note"], "2021 영업 종료")

    def test_alias_notes_skip_insta_handles_and_keep_not_merged(self):
        with tempfile.TemporaryDirectory() as d:
            notes = vp.load_alias_notes(self._write(d, "a.json", self.ALIASES))
        self.assertEqual(notes["큰홀"]["variants"], ["큰 홀(BIG HALL)"])          # '@계정'은 별칭 칸에 안 씀
        self.assertEqual(notes["큰홀"]["not_merged"], [{"names": ["큰홀", "큰홀 2관"], "reason": "주소가 다름"}])
        self.assertEqual(notes["큰홀 2관"]["not_merged"][0]["reason"], "주소가 다름")

    def test_missing_files_are_empty(self):
        self.assertEqual(vp.load_master_meta(["큰홀"], Path("/nonexistent/v.json")), {})
        self.assertEqual(vp.load_alias_notes(Path("/nonexistent/a.json")), {})

    def test_profile_carries_type_aliases_and_capacity_source(self):
        cfg = {**CFG, "venues": {**CFG["venues"], "큰홀": {"capacity": 450, "tier": "L", "source": "https://x/cap",
                                                           "source_note": "공식 안내", "confidence": "high",
                                                           "checked": "2026-11-27"}}}
        meta = {"큰홀": {"type": "hall", "type_label": "홀·공연장", "type_basis": "수동", "aliases": ["Big Hall"]}}
        notes = {"큰홀": {"variants": ["큰 홀(BIG HALL)"], "not_merged": [{"names": ["큰홀", "큰홀 2관"], "reason": "r"}]}}
        p = vp.build_profiles(_gigs(), TEAMS, OUTCOMES, SNAPSHOT, cfg, {}, AS_OF, meta=meta, alias_notes=notes)
        big = p["큰홀"]
        self.assertEqual((big["type"], big["type_label"], big["type_basis"]), ("hall", "홀·공연장", "수동"))
        self.assertEqual(big["aliases"], ["Big Hall", "큰 홀(BIG HALL)"])
        self.assertEqual(big["not_merged"], [{"names": ["큰홀", "큰홀 2관"], "reason": "r"}])
        self.assertEqual(big["capacity_source"], "https://x/cap")
        self.assertEqual(big["capacity_note"], "공식 안내")
        self.assertEqual(big["capacity_confidence"], "high")
        self.assertEqual(big["capacity_checked"], "2026-11-27")
        small = p["작은클럽"]                                                       # 마스터·별칭·출처가 없으면 빈 값
        self.assertEqual((small["type"], small["aliases"], small["not_merged"]), (None, [], []))
        self.assertIsNone(small["capacity_source"])
