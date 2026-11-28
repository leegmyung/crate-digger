"""newcomer_audit — 상위 후보 중 데뷔 5년 넘어 보이는 기성 팀 찾기 (2026-11-28)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import newcomer_audit as na  # noqa: E402


class NormDateTest(unittest.TestCase):
    def test_year_month_and_full_dates(self):
        self.assertEqual(na.norm_date("2015"), "2015-01-01")
        self.assertEqual(na.norm_date("2015.03"), "2015-03-01")
        self.assertEqual(na.norm_date("2015-03-07T00:00:00+09:00"), "2015-03-07")
        self.assertIsNone(na.norm_date(""))
        self.assertIsNone(na.norm_date("미상"))


class EarliestBySourceTest(unittest.TestCase):
    def test_keeps_earliest_date_per_team_and_source(self):
        ev = na.earliest_by_source([
            ("a", "2020-05-01", "spotify", "x"), ("a", "2012", "spotify", "y"),
            ("a", "2024-01-01", "signal", "z"), ("b", "", "itunes", "bad"),
        ])
        self.assertEqual(ev["a"]["spotify"], ("2012-01-01", "y"))
        self.assertEqual(ev["a"]["signal"], ("2024-01-01", "z"))
        self.assertNotIn("b", ev)


class FlagOldTest(unittest.TestCase):
    def test_two_old_sources_is_sure(self):
        f = na.flag_old({"spotify": ("2012-01-01", ""), "itunes": ("2013-01-01", ""), "signal": ("2024-01-01", "")}, "2026-11-28")
        self.assertEqual(f["earliest"], "2012-01-01")
        self.assertEqual(f["old_sources"], ["spotify", "itunes"])
        self.assertTrue(f["sure"])

    def test_one_old_source_is_not_sure(self):
        f = na.flag_old({"spotify": ("2019-01-01", ""), "signal": ("2024-01-01", "")}, "2026-11-28")
        self.assertFalse(f["sure"])

    def test_recent_team_not_flagged(self):
        self.assertIsNone(na.flag_old({"spotify": ("2022-01-01", ""), "signal": ("2024-01-01", "")}, "2026-11-28"))

    def test_cutoff_is_five_years_before(self):
        self.assertIsNone(na.flag_old({"x": ("2021-11-28", "")}, "2026-11-28"))
        self.assertIsNotNone(na.flag_old({"x": ("2021-11-27", "")}, "2026-11-28"))


if __name__ == "__main__":
    unittest.main()
