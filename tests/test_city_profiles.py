"""city_profiles: 도시 층 — 도시별 프로필, 팀별 활동 도시, 지방 → 서울 흐름, 교차 검증용 특징."""
import csv
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import city_profiles as cp  # noqa: E402

AS_OF = date(2026, 11, 27)
CITY = {"홍대A": "서울", "홍대B": "서울", "부산C": "부산", "대구D": "대구"}
MASTER = [{"name": "홍대A", "city": "서울", "in_our_data": True}, {"name": "홍대B", "city": "서울", "in_our_data": True},
          {"name": "서울없음", "city": "서울", "in_our_data": False}, {"name": "부산C", "city": "부산", "in_our_data": True},
          {"name": "대구D", "city": "대구", "in_our_data": True}]
TEAMS = {"p": "부산팀", "s": "서울팀", "d": "대구팀", "w": "우승팀"}


def _gigs():
    return [
        ("p", date(2024, 1, 10), "부산C"), ("p", date(2024, 2, 1), "부산C"), ("p", date(2024, 7, 10), "홍대A"),
        ("s", date(2026, 3, 1), "홍대A"), ("s", date(2026, 3, 1), "홍대B"),
        ("d", date(2026, 6, 1), "대구D"),
        ("w", date(2023, 5, 1), "부산C"), ("w", date(2023, 9, 1), "홍대B"),          # 정답(2024-01-01) 전에 부산·서울
        ("s", date(2027, 1, 5), "홍대A"),                                            # 예정 공연
        ("x", date(2026, 1, 1), "모르는곳"),                                         # 도시 모름
    ]


OUTCOMES = [{"team_key": "w", "announced_date": date(2024, 1, 1), "counted": True, "program_label": "헬로루키", "grade": "S"}]
SNAP = {"s": (2, 8.0), "p": (5, 6.0), "d": (9, 3.0)}


class CityOfTest(unittest.TestCase):
    def test_unknown_venue_gets_unknown_city(self):
        self.assertEqual(cp.city_for("모르는곳", CITY), cp.UNKNOWN_CITY)
        self.assertEqual(cp.city_for("부산C", CITY), "부산")


class TeamCitiesTest(unittest.TestCase):
    def setUp(self):
        self.rows = {r["team_key"]: r for r in cp.team_cities(_gigs(), CITY, AS_OF)}

    def test_home_city_is_most_nights_and_counts_cities(self):
        p = self.rows["p"]
        self.assertEqual((p["home_city"], p["cities"], p["nights"]), ("부산", 2, 3))
        self.assertEqual(self.rows["s"]["cities"], 1)
        self.assertEqual(self.rows["s"]["nights"], 2)                 # 예정 공연 제외, 같은 날 두 곳 = 2

    def test_local_to_seoul_months(self):
        p = self.rows["p"]
        self.assertEqual((p["first_city"], p["first_date"], p["seoul_first_date"]), ("부산", "2024-01-10", "2024-07-10"))
        self.assertEqual(p["months_to_seoul"], 6)
        self.assertEqual(self.rows["s"]["months_to_seoul"], "")      # 서울에서 시작한 팀
        self.assertEqual(self.rows["d"]["seoul_first_date"], "")     # 아직 서울 공연 없음

    def test_unknown_city_only_team_has_blank_home(self):
        self.assertEqual(self.rows["x"]["home_city"], "")
        self.assertEqual(self.rows["x"]["cities"], 0)

    def test_csv_columns(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "team_cities.csv"
            cp.write_team_cities(list(self.rows.values()), path)
            with open(path, encoding="utf-8") as f:
                header = next(csv.reader(f))
        self.assertEqual(header, list(cp.TEAM_CITY_FIELDS))


class CityProfilesTest(unittest.TestCase):
    def setUp(self):
        self.p = cp.build_city_profiles(_gigs(), TEAMS, OUTCOMES, SNAP, CITY, MASTER, AS_OF)

    def test_venue_counts_master_vs_ours(self):
        seoul = self.p["서울"]
        self.assertEqual((seoul["venues_master"], seoul["venues_master_in_data"], seoul["venues_with_gigs"]), (3, 2, 2))

    def test_nights_monthly_and_upcoming(self):
        seoul = self.p["서울"]
        self.assertEqual(seoul["nights"], 4)                         # (2024-07-10 A) (2026-03-01 A) (2026-03-01 B) (2023-09-01 B)
        self.assertEqual(seoul["monthly"]["2026-03"], 2)
        self.assertEqual(seoul["upcoming_nights"], 1)

    def test_teams_last_year_and_first_stage_city(self):
        self.assertEqual(self.p["서울"]["teams_1y"], 1)              # s
        self.assertEqual(self.p["부산"]["first_stage_teams"], 2)     # p, w 의 첫 무대 도시
        self.assertEqual(self.p["서울"]["first_stage_teams"], 1)     # s
        self.assertEqual(self.p["대구"]["first_stage_teams_1y"], 1)

    def test_later_winners_played_city_before_outcome(self):
        self.assertEqual([w["team_key"] for w in self.p["부산"]["later_winners"]], ["w"])
        self.assertEqual(self.p["부산"]["later_winners"][0]["first_here"], "2023-05-01")
        self.assertEqual(self.p["서울"]["later_winners_total"], 1)

    def test_top_candidates_and_top_venues(self):
        self.assertEqual([t["team_key"] for t in self.p["서울"]["top_candidates"]], ["s", "p"])
        self.assertEqual(self.p["서울"]["top_venues"][0], ["홍대A", 2])
        self.assertNotIn(cp.UNKNOWN_CITY, self.p)                     # 도시 모름은 프로필로 만들지 않음


class FlowTest(unittest.TestCase):
    def test_local_to_seoul_summary(self):
        rows = cp.team_cities(_gigs(), CITY, AS_OF)
        flow = cp.seoul_flow(rows)
        self.assertEqual(flow["local_start"], 3)                      # p·w(부산), d(대구)
        self.assertEqual(flow["reached_seoul"], 2)                    # p, w
        self.assertEqual(flow["by_first_city"]["부산"], {"teams": 2, "reached": 2, "median_months": 5})


class ArgsTest(unittest.TestCase):
    def test_data_only_skips_doc_and_eval(self):
        args = cp.parse_args(["--data-only"])
        self.assertTrue(args.no_eval)
        self.assertIsNone(args.doc)

    def test_default_writes_doc(self):
        self.assertEqual(cp.parse_args([]).doc, cp.DOC)


class FeaturesTest(unittest.TestCase):
    def test_features_use_only_gigs_before_cutoff(self):
        f = cp.city_features(_gigs(), CITY, date(2024, 3, 1), lookback_years=3)
        self.assertEqual(f["p"]["came_to_seoul"], 0.0)               # 서울 공연(2024-07)은 기준일 뒤
        self.assertEqual(f["p"]["non_seoul_base"], 1.0)
        self.assertEqual(f["w"]["came_to_seoul"], 1.0)
        self.assertEqual(f["w"]["city_count"], 1.0)                   # 부산·서울 = 2곳 → 1
        self.assertEqual(f["w"]["recent_seoul_arrival"], 1.0)         # 서울 첫 공연 2023-09 (기준일 전 1년 안)
        self.assertNotIn("s", f)

    def test_seoul_start_is_not_arrival(self):
        f = cp.city_features(_gigs(), CITY, AS_OF, lookback_years=3)
        self.assertEqual(f["s"], {"came_to_seoul": 0.0, "non_seoul_base": 0.0, "city_count": 0.0,
                                  "recent_seoul_arrival": 0.0})


if __name__ == "__main__":
    unittest.main()
