"""백테스트 시점 누수(look-ahead) 방지 날짜 규칙 테스트."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import timing  # noqa: E402


class ConservativeDateTest(unittest.TestCase):
    def test_signal_takes_last_day_of_period(self):
        self.assertEqual(timing.signal_date("2024"), "2024-12-31")
        self.assertEqual(timing.signal_date("2024-02"), "2024-02-29")
        self.assertEqual(timing.signal_date("2024-05-07"), "2024-05-07")

    def test_outcome_takes_first_day_of_period(self):
        self.assertEqual(timing.outcome_date("2024"), "2024-01-01")
        self.assertEqual(timing.outcome_date("2024-05"), "2024-05-01")
        self.assertEqual(timing.outcome_date("2024-05-07"), "2024-05-07")

    def test_lead_days_never_inflated(self):
        # 같은 해 연도만 아는 후보와 정답 → 앞섰다고 볼 수 없음
        self.assertIsNone(timing.lead_days("2024", "2024"))
        self.assertEqual(timing.lead_days("2024-03", "2024-06"), 62)  # 3/31 → 6/1
        self.assertEqual(timing.lead_days("2023", "2024-01-15"), 15)
        self.assertIsNone(timing.lead_days("2024-06", "2024-03"))

    def test_bad_input(self):
        self.assertIsNone(timing.lead_days("", "2024"))
        self.assertEqual(timing.signal_date("미상"), "")


if __name__ == "__main__":
    unittest.main()
