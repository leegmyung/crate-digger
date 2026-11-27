"""rule_leakage: 유명 팀 제외·신인 규칙이 '기준일 당시 알 수 없던 정보'를 쓰는지 — 대안 규칙 비교."""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import rule_leakage as rl  # noqa: E402

C = date(2025, 1, 1)


def team(**kw):
    base = {"profile_status": "unknown", "first_release": None, "first_seen": date(2024, 1, 1), "fan_count": None,
            "signals_before": 0, "prior_any_outcome": False, "prior_festival": False}
    return {**base, **kw}


class FameTest(unittest.TestCase):
    def test_current_and_off(self):
        self.assertTrue(rl.FAME["current"](team(profile_status="famous"), C))
        self.assertFalse(rl.FAME["off"](team(profile_status="famous"), C))

    def test_tenure_and_signals_at_cutoff(self):
        old_busy = team(first_release=date(2018, 1, 1), signals_before=rl.TENURE_MIN_SIGNALS)
        old_quiet = team(first_release=date(2018, 1, 1), signals_before=1)
        young_busy = team(first_release=date(2023, 1, 1), signals_before=50)
        self.assertTrue(rl.FAME["tenure_signals"](old_busy, C))
        self.assertFalse(rl.FAME["tenure_signals"](old_quiet, C))
        self.assertFalse(rl.FAME["tenure_signals"](young_busy, C))
        self.assertFalse(rl.FAME["tenure_signals"](team(signals_before=99), C))   # 첫 발매 모르면 제외 안 함

    def test_prior_outcome_or_festival(self):
        self.assertTrue(rl.FAME["prior_record"](team(prior_any_outcome=True), C))
        self.assertTrue(rl.FAME["prior_record"](team(prior_festival=True), C))
        self.assertFalse(rl.FAME["prior_record"](team(profile_status="famous"), C))  # 지금 팬 수는 안 봄


class NewcomerTest(unittest.TestCase):
    def test_years_and_modes(self):
        t = team(first_release=date(2021, 6, 1), first_seen=date(2023, 3, 1))
        self.assertFalse(rl.newcomer_ok(t, C, 3, "release_first"))     # 첫 발매 2021-06 → 3년 넘음
        self.assertTrue(rl.newcomer_ok(t, C, 4, "release_first"))
        self.assertTrue(rl.newcomer_ok(t, C, 3, "signal_first"))       # 첫 신호 2023-03 → 3년 이내
        self.assertTrue(rl.newcomer_ok(team(first_release=date(1999, 1, 1)), C, 3, "none"))
        self.assertTrue(rl.newcomer_ok(team(first_release=None, first_seen=date(2022, 2, 1)), C, 3, "release_first"))

    def test_years_before(self):
        self.assertEqual(rl.years_before(date(2025, 1, 1), 3), date(2022, 1, 1))
        self.assertEqual(rl.years_before(date(2024, 2, 29), 1), date(2023, 2, 28))


class ApplyTest(unittest.TestCase):
    def test_filter_rows_by_variant(self):
        rows = [{"team_key": "a"}, {"team_key": "b"}, {"team_key": "c"}]
        attrs = {"a": team(profile_status="famous"), "b": team(first_release=date(2015, 1, 1)), "c": team()}
        v = {"fame": "current", "new_years": 3, "new_mode": "release_first"}
        self.assertEqual([r["team_key"] for r in rl.apply_variant(rows, attrs, C, v)], ["c"])
        v_off = {"fame": "off", "new_years": 3, "new_mode": "none"}
        self.assertEqual(len(rl.apply_variant(rows, attrs, C, v_off)), 3)

    def test_top_change(self):
        base = ["a", "b", "c", "d"]
        alt = ["b", "x", "a", "y"]
        self.assertEqual(rl.top_change(base, alt, 3), {"kept": 2, "entered": ["x"], "left": ["c"]})


if __name__ == "__main__":
    unittest.main()
