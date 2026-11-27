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
