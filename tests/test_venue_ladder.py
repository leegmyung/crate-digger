"""venue_ladder: 공연장 체급(수용 인원)으로 팀별 '공연장 사다리'와 공연장 전후 흐름 만들기."""
import json
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import venue_ladder as vl  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TIERS = [{"tier": "S", "max": 150}, {"tier": "M", "max": 400}, {"tier": "L", "max": 1000}, {"tier": "XL", "max": None}]
VT = {"작은클럽": "S", "중간홀": "M", "큰홀": "L", "아레나": "XL"}
C = date(2025, 1, 1)


def _cfg(venues):
    return {"tiers": TIERS, "venues": venues}


class TierTest(unittest.TestCase):
    def test_tier_bounds_are_inclusive_upper(self):
        self.assertEqual(vl.tier_of(150, TIERS), "S")
        self.assertEqual(vl.tier_of(151, TIERS), "M")
        self.assertEqual(vl.tier_of(400, TIERS), "M")
        self.assertEqual(vl.tier_of(1000, TIERS), "L")
        self.assertEqual(vl.tier_of(5000, TIERS), "XL")
        self.assertIsNone(vl.tier_of(None, TIERS))

    def test_venue_tiers_skips_unknown_and_not_venue(self):
        cfg = _cfg({"A": {"capacity": 100, "tier": "S", "source": "u"}, "B": {"capacity": None, "tier": None},
                    "축제": {"capacity": None, "tier": None, "not_venue": True}})
        self.assertEqual(vl.venue_tiers(cfg), {"A": "S"})
        self.assertEqual(vl.not_venues(cfg), {"축제"})


class ValidateTest(unittest.TestCase):
    def test_flags_tier_mismatch_missing_source_and_bad_capacity(self):
        cfg = _cfg({"A": {"capacity": 300, "tier": "S", "source": "u"},
                    "B": {"capacity": 100, "tier": "S"},
                    "C": {"capacity": 0, "tier": "S", "source": "u"},
                    "D": {"capacity": None, "tier": "M"}})
        problems = " ".join(vl.validate(cfg))
        for name in ("A", "B", "C", "D"):
            self.assertIn(name, problems)

    def test_tier_only_entry_needs_flag_and_source(self):
        ok = _cfg({"작은클럽": {"capacity": None, "tier": "S", "tier_only": True, "source": "u", "confidence": "low"}})
        self.assertEqual(vl.validate(ok), [])
        self.assertEqual(vl.venue_tiers(ok), {"작은클럽": "S"})
        no_src = _cfg({"작은클럽": {"capacity": None, "tier": "S", "tier_only": True}})
        self.assertTrue(any("작은클럽" in p for p in vl.validate(no_src)))

    def test_confidence_must_be_known_word(self):
        bad = _cfg({"A": {"capacity": 120, "tier": "S", "source": "u", "confidence": "medium"}})
        self.assertTrue(any("confidence" in p for p in vl.validate(bad)))

    def test_strict_config_drops_low_confidence(self):
        cfg = _cfg({"A": {"capacity": 120, "tier": "S", "source": "u", "confidence": "high"},
                    "B": {"capacity": 300, "tier": "M", "source": "u", "confidence": "low"},
                    "C": {"capacity": None, "tier": "S", "tier_only": True, "source": "u", "confidence": "low"},
                    "축제": {"capacity": None, "tier": None, "not_venue": True}})
        strict = vl.strict_config(cfg)
        self.assertEqual(vl.venue_tiers(strict), {"A": "S"})
        self.assertEqual(vl.not_venues(strict), {"축제"})
        self.assertEqual(vl.venue_tiers(cfg), {"A": "S", "B": "M", "C": "S"})   # 원본은 그대로

    def test_ok_config_has_no_problems(self):
        self.assertEqual(vl.validate(_cfg({"A": {"capacity": 120, "tier": "S", "source": "u"},
                                           "B": {"capacity": None, "tier": None}})), [])

    def test_repo_config_is_valid(self):
        cfg = json.loads((ROOT / "config" / "venue_capacity.json").read_text(encoding="utf-8"))
        self.assertEqual(vl.validate(cfg), [])


class LadderTest(unittest.TestCase):
    def _gigs(self):
        return [("a", date(2023, 1, 10), "작은클럽"), ("a", date(2023, 6, 1), "모르는곳"),
                ("a", date(2024, 3, 1), "중간홀"), ("a", date(2024, 9, 1), "큰홀"),
                ("a", date(2025, 2, 1), "아레나"),      # 기준일 뒤 → 안 씀
                ("b", date(2024, 5, 1), "중간홀"), ("b", date(2024, 8, 1), "작은클럽"),
                ("c", date(2024, 5, 1), "모르는곳")]

    def test_first_last_max_and_rise_use_only_gigs_before_cutoff(self):
        lad = vl.team_ladders(self._gigs(), VT, C)
        a = lad["a"]
        self.assertEqual((a.first_tier, a.last_tier, a.max_tier), ("S", "L", "L"))
        self.assertEqual(a.rise_steps, 2)
        self.assertEqual(a.first_rise_date, date(2024, 3, 1))
        self.assertEqual(a.days_to_rise, (date(2024, 3, 1) - date(2023, 1, 10)).days)
        self.assertEqual(a.known_gigs, 3)
        self.assertTrue(a.recent_rise)   # 기준일 전 1년 안에 처음으로 더 큰 체급(L)에 섬

    def test_going_down_is_not_a_rise_and_unknown_only_has_no_tier(self):
        lad = vl.team_ladders(self._gigs(), VT, C)
        self.assertEqual(lad["b"].rise_steps, 0)
        self.assertEqual((lad["b"].first_tier, lad["b"].last_tier), ("M", "S"))
        self.assertIsNone(lad["c"].first_tier)
        self.assertEqual(lad["c"].known_gigs, 0)

    def test_assume_unknown_small_is_sensitivity_option(self):
        lad = vl.team_ladders(self._gigs(), VT, C, unknown_tier="S")
        self.assertEqual(lad["c"].first_tier, "S")
        self.assertEqual(lad["c"].known_gigs, 1)

    def test_lookback_window_drops_old_gigs(self):
        lad = vl.team_ladders(self._gigs(), VT, C, lookback_years=1)
        self.assertEqual(lad["a"].first_tier, "M")   # 2024-03-01 부터만

    def test_big_lineups_are_excluded_as_festivals(self):
        gigs = [(f"t{i}", date(2024, 6, 1), "아레나") for i in range(13)] + [("t0", date(2024, 1, 1), "작은클럽")]
        lad = vl.team_ladders(gigs, VT, C, max_event_teams=12)
        self.assertEqual(lad["t0"].max_tier, "S")
        self.assertNotIn("t5", lad)

    def test_features_from_ladders(self):
        lad = vl.team_ladders(self._gigs(), VT, C)
        f = vl.ladder_features(lad)
        self.assertEqual(f["a"], {"tier_rise": 2.0, "max_tier": 3.0, "recent_rise": 1.0})
        self.assertEqual(f["c"], {"tier_rise": 0.0, "max_tier": 0.0, "recent_rise": 0.0})

    def test_transitions_count_first_to_last(self):
        lad = vl.team_ladders(self._gigs(), VT, C)
        self.assertEqual(vl.tier_transitions(lad)[("S", "L")], 1)
        self.assertEqual(vl.tier_transitions(lad)[("M", "S")], 1)


class DataEndTest(unittest.TestCase):
    def test_future_scheduled_gigs_are_dropped(self):
        gigs = [("a", date(2026, 11, 1), "X"), ("a", date(2027, 1, 2), "Y")]
        self.assertEqual(vl.until(gigs, date(2026, 11, 27)), [("a", date(2026, 11, 1), "X")])


class ExportTest(unittest.TestCase):
    def test_export_shape_for_app(self):
        lad = vl.team_ladders([("a", date(2024, 1, 1), "작은클럽"), ("a", date(2024, 6, 1), "큰홀")], VT, C)
        journey = {"큰홀": {"teams": 20, "before": [("작은클럽", 5)], "after": []}}
        out = vl.export(lad, journey, VT, date(2024, 12, 31))
        self.assertEqual(out["as_of"], "2024-12-31")
        self.assertEqual(out["teams"]["a"], {"first": "S", "last": "L", "max": "L", "steps": 2,
                                             "rise_date": "2024-06-01", "days_to_rise": 152})
        self.assertEqual(out["venues"]["큰홀"]["tier"], "L")
        self.assertEqual(out["venues"]["큰홀"]["before"], [["작은클럽", 5]])

    def test_export_skips_teams_without_known_tier(self):
        lad = vl.team_ladders([("c", date(2024, 1, 1), "모르는곳")], VT, C)
        self.assertEqual(vl.export(lad, {}, VT, C)["teams"], {})


class ArgsTest(unittest.TestCase):
    def test_json_default_location_is_lab_data(self):
        args = vl.parse_args(["--json"])
        self.assertEqual(args.json, ROOT / "docs" / "lab" / "data" / "venue_ladder.json")
        self.assertIsNone(vl.parse_args([]).json)

    def test_json_only_implies_default_json(self):
        args = vl.parse_args(["--json-only"])
        self.assertTrue(args.json_only)
        self.assertEqual(args.json, vl.JSON_OUT)


class JourneyTest(unittest.TestCase):
    def test_before_and_after_venues_within_window(self):
        gigs = [("a", date(2024, 1, 1), "작은클럽"), ("a", date(2024, 3, 1), "중간홀"), ("a", date(2024, 6, 1), "큰홀"),
                ("a", date(2024, 7, 1), "작은클럽"),               # 이미 가 본 곳 → '다음' 아님
                ("b", date(2023, 1, 1), "작은클럽"), ("b", date(2024, 4, 1), "중간홀"),   # 1년 넘게 전 → '전' 아님
                ("b", date(2024, 4, 2), "중간홀"), ("b", date(2026, 1, 1), "큰홀")]      # 1년 넘게 뒤 → '다음' 아님
        j = vl.venue_journey(gigs, window_days=365, min_teams=1)["중간홀"]
        self.assertEqual(j["teams"], 2)
        self.assertEqual(dict(j["before"]), {"작은클럽": 1})
        self.assertEqual(dict(j["after"]), {"큰홀": 1})

    def test_min_teams_filters_small_venues(self):
        gigs = [("a", date(2024, 1, 1), "X")]
        self.assertEqual(vl.venue_journey(gigs, min_teams=2), {})


if __name__ == "__main__":
    unittest.main()
