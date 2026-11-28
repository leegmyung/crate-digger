"""scripts/daily_run.sh 순서 점검 — 장르 처음 확인한 날(genre_seen.py)이 랩 데이터 내보내기 뒤에 돌고 자동 커밋에 실리는지."""
import re
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "daily_run.sh"


class DailyRunGenreSeenTest(unittest.TestCase):
    def setUp(self):
        self.lines = SCRIPT.read_text(encoding="utf-8").splitlines()

    def _index(self, needle: str) -> int:
        hits = [i for i, line in enumerate(self.lines) if needle in line and not line.lstrip().startswith("#")]
        self.assertEqual(len(hits), 1, f"{needle} 줄이 정확히 한 번 있어야 함")
        return hits[0]

    def test_genre_seen_runs_after_lab_export_and_before_app_extras(self):
        seen = self._index("scripts/genre_seen.py")
        self.assertLess(self._index("scripts/export_lab_data.py"), seen)     # teams.csv·signals.csv 를 읽으니 내보내기 뒤
        self.assertLess(seen, self._index("scripts/build_app_extras.sh"))

    def test_genre_seen_failure_does_not_stop_the_run(self):
        line = self.lines[self._index("scripts/genre_seen.py")]
        self.assertRegex(line, r'\|\| echo "⚠️ ')

    def test_auto_commit_includes_lab_data_folder(self):
        add = next(line for line in self.lines if line.startswith("git add "))
        self.assertIn(" docs/lab/data ", f" {add} ")                         # docs/lab/data/genre_seen.csv 가 같이 실림
        self.assertIsNone(re.search(r"data/raw|records/", add))               # 원본·개인 기록은 커밋 안 함


if __name__ == "__main__":
    unittest.main()
