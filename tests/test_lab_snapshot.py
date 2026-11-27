"""lab_snapshot: 매일 점수 상위 팀을 기록해 앱이 '새로 들어온 팀·순위 상승'을 비교할 수 있게 한다."""
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import lab_snapshot as snap  # noqa: E402

ROWS = [{"team_key": "b", "score": 3.5}, {"team_key": "a", "score": 7.25}, {"team_key": "c", "score": 3.5}]


class WriteSnapshotTest(unittest.TestCase):
    def test_ranks_by_score_and_writes_csv(self):
        with tempfile.TemporaryDirectory() as d:
            path = snap.write_snapshot(ROWS, Path(d), "2026-11-27")
            with open(path, encoding="utf-8") as f:
                got = list(csv.DictReader(f))
            self.assertEqual([r["team_key"] for r in got], ["a", "b", "c"])
            self.assertEqual([r["rank"] for r in got], ["1", "2", "3"])
            self.assertEqual(got[0]["score"], "7.25")

    def test_index_lists_dates_newest_first_without_duplicates(self):
        with tempfile.TemporaryDirectory() as d:
            for day in ("2026-11-25", "2026-11-27", "2026-11-26", "2026-11-27"):
                snap.write_snapshot(ROWS, Path(d), day)
            index = json.loads((Path(d) / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(index["dates"], ["2026-11-27", "2026-11-26", "2026-11-25"])

    def test_keeps_only_recent_snapshots(self):
        with tempfile.TemporaryDirectory() as d:
            for i in range(1, 6):
                snap.write_snapshot(ROWS, Path(d), f"2026-11-0{i}", keep=3)
            files = sorted(p.name for p in Path(d).glob("*.csv"))
            self.assertEqual(files, ["2026-11-03.csv", "2026-11-04.csv", "2026-11-05.csv"])

    def test_reconstructed_dates_are_marked(self):
        with tempfile.TemporaryDirectory() as d:
            snap.write_snapshot(ROWS, Path(d), "2026-11-20", reconstructed=True)
            snap.write_snapshot(ROWS, Path(d), "2026-11-27")
            index = json.loads((Path(d) / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(index["reconstructed"], ["2026-11-20"])


if __name__ == "__main__":
    unittest.main()
