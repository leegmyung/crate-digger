"""spotify_budget: 스포티파이 단계들이 하루 요청 예산을 나눠 쓰고, 오래 기다리라는 429를 받으면 그날 남은 단계는 요청 없이 건너뛴다."""
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import collect_spotify as cs  # noqa: E402
import spotify_budget as sb  # noqa: E402

KST = timezone(timedelta(hours=9))
T0 = datetime(2026, 11, 27, 22, 0, tzinfo=KST)


class FakeHttp:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def __call__(self, method, url, headers=None, data=None):
        self.calls += 1
        return self.responses.pop(0) if self.responses else (200, {}, {})


class BudgetTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "spotify_budget.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_shared_daily_budget_across_stages(self):
        a = sb.BudgetedHttp(FakeHttp([]), path=self.path, budget=3, now=lambda: T0)
        a("GET", "u"), a("GET", "u")
        b = sb.BudgetedHttp(FakeHttp([]), path=self.path, budget=3, now=lambda: T0)   # 다음 단계 = 새 객체
        b("GET", "u")
        with self.assertRaises(sb.DailyBudgetExhausted):
            b("GET", "u")
        self.assertTrue(issubclass(sb.DailyBudgetExhausted, cs.RateLimited))          # 기존 '멈추고 저장' 처리 그대로

    def test_new_day_resets_used(self):
        a = sb.BudgetedHttp(FakeHttp([]), path=self.path, budget=1, now=lambda: T0)
        a("GET", "u")
        b = sb.BudgetedHttp(FakeHttp([]), path=self.path, budget=1, now=lambda: T0 + timedelta(days=1))
        b("GET", "u")                                                                  # 예외 없음

    def test_long_429_blocks_rest_of_day_without_requests(self):
        http = FakeHttp([(429, {"Retry-After": "86373"}, {})])
        a = sb.BudgetedHttp(http, path=self.path, budget=100, now=lambda: T0)
        status, _, _ = a("GET", "u")
        self.assertEqual(status, 429)                                                  # 응답은 그대로 돌려줌 (클라이언트가 멈춤)
        http2 = FakeHttp([])
        b = sb.BudgetedHttp(http2, path=self.path, budget=100, now=lambda: T0 + timedelta(hours=2))
        with self.assertRaises(sb.SpotifyBlocked):
            b("GET", "u")
        self.assertEqual(http2.calls, 0)                                               # 막힌 동안엔 요청을 아예 안 보냄
        self.assertIn("건너뜀", sb.skip_message(self.path, T0 + timedelta(hours=2)))
        later = T0 + timedelta(seconds=86373 + 60)
        self.assertIsNone(sb.skip_message(self.path, later))                           # 기다리라는 시간이 지나면 풀림

    def test_short_429_does_not_block(self):
        a = sb.BudgetedHttp(FakeHttp([(429, {"Retry-After": "2"}, {})]), path=self.path, budget=100, now=lambda: T0)
        a("GET", "u")
        self.assertIsNone(sb.skip_message(self.path, T0))

    def test_block_lasts_at_least_until_end_of_day(self):
        a = sb.BudgetedHttp(FakeHttp([(429, {"Retry-After": "600"}, {})]), path=self.path, budget=100, now=lambda: T0)
        a("GET", "u")
        self.assertIsNotNone(sb.skip_message(self.path, T0 + timedelta(hours=1)))      # 10분이 지나도 그날은 쉼
        self.assertIsNone(sb.skip_message(self.path, datetime(2026, 11, 28, 0, 1, tzinfo=KST)))


if __name__ == "__main__":
    unittest.main()
