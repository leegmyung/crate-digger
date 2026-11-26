"""일일 기록(daily_note.py) 테스트."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import daily_note as dn  # noqa: E402

BOARD = {
    "steps": [{"no": "0", "name": "후보 풀", "status": "done"}, {"no": "1", "name": "원본 수집", "status": "now"}],
    "decisions": [{"q": "신인 기준", "state": "2년 이내"}, {"q": "공증 등급", "state": "결정 필요"}],
}
RUNS = [
    {"date": "2026-11-26", "source": "poclanos", "table": "raw_kr_release", "rows": 16, "file_ok": True},
    {"date": "2026-11-26", "source": "indiego", "table": "raw_kr_gig", "rows": 200, "file_ok": False},
    {"date": "2026-11-25", "source": "poclanos", "table": "raw_kr_release", "rows": 3, "file_ok": True},
]
COMMITS = ["aabf2f8 feat: 포크라노스 수집기", "4f91eb5 feat: 선정 명단 테이블"]


class NoteTest(unittest.TestCase):
    def test_note_has_step_commits_runs_and_open_decisions(self):
        md = dn.render_note("2026-11-26", COMMITS, RUNS, BOARD)
        self.assertIn("# 2026-11-26 작업 기록", md)
        self.assertIn("단계 1 원본 수집", md)
        self.assertIn("aabf2f8 feat: 포크라노스 수집기", md)
        self.assertIn("poclanos", md)
        self.assertIn("16", md)
        self.assertIn("❌", md)                 # 검사 실패 표시
        self.assertNotIn("2026-11-25", md)      # 다른 날 수집은 빼기
        self.assertIn("공증 등급", md)
        self.assertNotIn("신인 기준", md)        # 이미 정한 것은 빼기

    def test_empty_day(self):
        md = dn.render_note("2026-11-27", [], [], BOARD)
        self.assertIn("커밋 없음", md)
        self.assertIn("수집 기록 없음", md)

    def test_auto_worklog_entry(self):
        entry = dn.auto_entry("2026-11-26", COMMITS, RUNS)
        row = entry["작업기록"][0]
        self.assertEqual(entry["date"], "2026-11-26")
        self.assertEqual(row["파이프라인 단계"], "자동 (매일 저녁)")
        self.assertIn("poclanos 16줄", row["한 일"])
        self.assertIn("검사 실패", row["찾은 빈틈·보완"])
        self.assertEqual(row["커밋"], "aabf2f8, 4f91eb5")


if __name__ == "__main__":
    unittest.main()
