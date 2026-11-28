"""멜론 프로필 고른 큐(profile_queue): 정답 여부를 보지 않고 팀 키 해시 순으로, 받은 팀·재검색 대기 팀은 빼기."""
import inspect
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import profile_queue as pq  # noqa: E402

TEAMS = {k: {"team_key": k, "display_name": n, "profile_status": s} for k, n, s in [
    ("a", "에이", "unknown"), ("b", "비", "newcomer"), ("c", "씨", "unknown"), ("d", "디", "unknown"),
    ("e", "이", "unknown"), ("f", "", "unknown")]}


def build(pool=("a", "b", "c", "d", "e", "f"), **kw):
    args = dict(teams=TEAMS, matches={}, attempts={}, misses={}, profiled=set(), today="2026-11-28")
    args.update(kw)
    return pq.build_queue(pool, **args)


class OrderTest(unittest.TestCase):
    def test_hash_order_is_stable_and_not_alphabetical(self):
        keys = [f"팀{i}" for i in range(50)]
        order = pq.hash_order(keys)
        self.assertEqual(order, pq.hash_order(list(reversed(keys))))   # 입력 순서와 무관
        self.assertEqual(sorted(order), sorted(keys))
        self.assertNotEqual(order, sorted(keys))

    def test_queue_follows_hash_order(self):
        names, _ = build()
        expect = [TEAMS[k]["display_name"] for k in pq.hash_order(["a", "c", "d", "e"])]
        self.assertEqual(names, expect)

    def test_no_outcome_input(self):
        # 정답 정보를 받는 자리가 없어야 한다 (정답 팀만 먼저 받는 일이 다시 생기지 않게)
        params = inspect.signature(pq.build_queue).parameters
        self.assertFalse({"outcomes", "winners", "is_hit"} & set(params))


class FilterTest(unittest.TestCase):
    def test_skips_known_profile_and_blank_name(self):
        names, stats = build()
        self.assertNotIn("비", names)          # 이미 프로필(newcomer)
        self.assertEqual(stats["pool"], 6)
        self.assertEqual(stats["has_profile"], 1)
        self.assertEqual(stats["no_name"], 1)

    def test_skips_team_not_in_teams(self):
        names, stats = build(pool=("a", "zz"))
        self.assertEqual(names, ["에이"])
        self.assertEqual(stats["no_name"], 1)

    def test_skips_profiled_match_even_if_teams_csv_stale(self):
        names, stats = build(matches={"에이": {"id": "123456"}}, profiled={"123456"})
        self.assertNotIn("에이", names)
        self.assertEqual(stats["has_profile"], 2)

    def test_keeps_matched_but_not_fetched(self):
        names, stats = build(matches={"에이": {"id": "123456"}})
        self.assertIn("에이", names)
        self.assertEqual(stats["fetch_only"], 1)

    def test_miss_waits_retry_days(self):
        m = {"씨": None, "디": None}
        att = {"씨": "2026-11-20", "디": "2026-10-01"}
        mis = {"씨": {"kind": "mismatch"}, "디": {"kind": "mismatch"}}
        names, stats = build(matches=m, attempts=att, misses=mis)
        self.assertNotIn("씨", names)          # 8일 전 불일치 → 30일 대기
        self.assertIn("디", names)             # 58일 전 → 다시
        self.assertEqual(stats["miss_waiting"], 1)

    def test_duplicate_display_names_once(self):
        teams = dict(TEAMS, g={"team_key": "g", "display_name": "에이", "profile_status": "unknown"})
        names, _ = build(pool=("a", "g"), teams=teams)
        self.assertEqual(names, ["에이"])


class WriteTest(unittest.TestCase):
    def test_write_queue(self):
        with tempfile.TemporaryDirectory() as d:
            p = pq.write_queue(Path(d) / "state" / "profile_queue.txt", ["에이", "씨"])
            self.assertEqual(p.read_text(encoding="utf-8"), "에이\n씨\n")


class ProgressTest(unittest.TestCase):
    def test_progress_counts_profiled_share(self):
        teams = {"a": {"profile_status": "unknown"}, "b": {"profile_status": "newcomer"},
                 "c": {"profile_status": "famous"}, "d": {"profile_status": "unknown"}}
        self.assertEqual(pq.progress(["a", "b", "c", "d", "x"], teams), {"pool": 5, "profiled": 2, "share": 0.4})


if __name__ == "__main__":
    unittest.main()
