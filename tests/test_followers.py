"""scripts/followers.py — 쌓인 팔로워 기록 → docs/lab/data/followers.csv (21~35일 전 기록과 비교)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import followers as fl  # noqa: E402


class HistoryTest(unittest.TestCase):
    def test_profile_rows_to_history_by_team_last_value_per_day(self):
        rows = [{"artist_source_id": "aa", "collected_at": "2026-11-01T10:00:00+09:00", "fan_count": "1,200"},
                {"artist_source_id": "aa", "collected_at": "2026-11-01T22:00:00+09:00", "fan_count": "1300"},
                {"artist_source_id": "zz", "collected_at": "2026-11-01T10:00:00+09:00", "fan_count": "5"},     # 팀 모름
                {"artist_source_id": "aa", "collected_at": "2026-11-02T10:00:00+09:00", "fan_count": ""}]      # 값 없음
        hist = fl.history(rows, "instagram", {"aa": "팀A"})
        self.assertEqual(hist, {("팀A", "instagram"): {"2026-11-01": 1300}})

    def test_spotify_log_lines(self):
        lines = ['{"team_key": "팀A", "spotify_id": "x", "date": "2026-11-01", "followers": 10}', "깨진 줄", ""]
        self.assertEqual(fl.spotify_history(lines), {("팀A", "spotify"): {"2026-11-01": 10}})


class CompareTest(unittest.TestCase):
    def test_picks_base_21_to_35_days_before_latest_closest_to_30(self):
        hist = {("팀A", "instagram"): {"2026-10-01": 900, "2026-10-26": 1000, "2026-11-05": 1100, "2026-11-28": 1500},
                ("팀B", "melon"): {"2026-11-20": 50, "2026-11-28": 60}}          # 8일 간격 → 30일 변화 아님, 안 씀
        rows = fl.compare(hist)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual((r["team_key"], r["platform"], r["latest_date"], r["latest"]), ("팀A", "instagram", "2026-11-28", 1500))
        self.assertEqual((r["base_date"], r["base"], r["change"]), ("2026-10-26", 1000, 500))   # 33일 전이 30일에 가장 가까움
        self.assertAlmostEqual(r["change_pct"], 50.0)

    def test_zero_base_has_no_percent(self):
        rows = fl.compare({("팀C", "instagram"): {"2026-10-29": 0, "2026-11-28": 10}})
        self.assertEqual(rows[0]["change"], 10)
        self.assertIsNone(rows[0]["change_pct"])


if __name__ == "__main__":
    unittest.main()
