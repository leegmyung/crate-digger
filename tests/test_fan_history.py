"""fan_history: 멜론 프로필 파일들에서 아티스트별 팬 수 기록(날짜·팬 수)을 모은다 — 나중에 '기준일 당시 팬 수'로 유명 판정하려고."""
import csv
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import fan_history as fh  # noqa: E402

FIELDS = ["collected_at", "source", "artist_source_id", "artist_text", "fan_count", "artist_key"]


def write(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


class CollectTest(unittest.TestCase):
    def test_points_from_files_merge_and_dedupe(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            write(d / "raw_artist_profile_2026-11-26_melon.csv", [
                {"collected_at": "2026-11-26T21:00:00+09:00", "source": "melon", "artist_source_id": "1",
                 "artist_text": "에이", "fan_count": "1,200", "artist_key": "에이"},
                {"collected_at": "2026-11-26T21:00:00+09:00", "source": "melon", "artist_source_id": "2",
                 "artist_text": "비", "fan_count": "", "artist_key": "비"}])          # 팬 수 없음 → 건너뜀
            write(d / "raw_artist_profile_2026-12-03_melon_120000.csv", [
                {"collected_at": "2026-12-03T12:00:00+09:00", "source": "melon", "artist_source_id": "1",
                 "artist_text": "에이", "fan_count": "1500", "artist_key": "에이"}])
            write(d / "raw_artist_profile_2026-11-26_spotify.csv", [
                {"collected_at": "2026-11-26T21:00:00+09:00", "source": "spotify", "artist_source_id": "x",
                 "artist_text": "에이", "fan_count": "99", "artist_key": "에이"}])  # 멜론 파일만 읽음
            hist = fh.collect(d, {})
        self.assertEqual(list(hist), ["1"])
        self.assertEqual(hist["1"]["points"], [["2026-11-26", 1200], ["2026-12-03", 1500]])
        self.assertEqual(hist["1"]["artist_key"], "에이")

    def test_merge_keeps_old_points(self):
        old = {"1": {"artist_key": "에이", "points": [["2026-11-20", 1000]]}}
        new = {"1": {"artist_key": "에이", "points": [["2026-11-26", 1200], ["2026-11-20", 1000]]}}
        self.assertEqual(fh.merge(old, new)["1"]["points"], [["2026-11-20", 1000], ["2026-11-26", 1200]])


class LookupTest(unittest.TestCase):
    def test_fans_at_uses_last_known_on_or_before(self):
        pts = [["2026-11-26", 1200], ["2026-12-03", 1500]]
        self.assertIsNone(fh.fans_at(pts, date(2026, 11, 25)))            # 기록 전 = 모름
        self.assertEqual(fh.fans_at(pts, date(2026, 11, 30)), 1200)
        self.assertEqual(fh.fans_at(pts, date(2027, 1, 1)), 1500)


class SummaryTest(unittest.TestCase):
    def test_summary_numbers_only(self):
        hist = {"1": {"points": [["2026-11-26", 1000], ["2026-12-03", 1100]]},
                "2": {"points": [["2026-11-26", 500]]},
                "3": {"points": [["2026-11-27", 200], ["2026-12-04", 180]]}}
        s = fh.summarize(hist)
        self.assertEqual((s["artists"], s["multi"], s["dates"]), (3, 2, 4))
        self.assertEqual((s["first"], s["last"]), ("2026-11-26", "2026-12-04"))
        self.assertEqual((s["up"], s["down"], s["same"]), (1, 1, 0))
        self.assertAlmostEqual(s["pct_q"][1], 0.0)                        # +10%, −10% 의 중앙값


if __name__ == "__main__":
    unittest.main()
