"""데이터 대시보드 JSON 만들기 테스트 — DB 대신 가짜 실행 함수로."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_dashboard_data as bd  # noqa: E402


class RecordsTest(unittest.TestCase):
    def test_csv_to_records_with_numbers(self):
        recs = bd.records("branch,rows,rate,label\n공연,14933,0.087,\n")
        self.assertEqual(recs, [{"branch": "공연", "rows": 14933, "rate": 0.087, "label": None}])

    def test_empty(self):
        self.assertEqual(bd.records(""), [])


class BuildTest(unittest.TestCase):
    def test_every_section_filled_from_runner(self):
        fake = lambda sql: "n\n1\n"
        data = bd.build(run=fake)
        self.assertEqual(set(data["sections"]), set(bd.QUERIES))
        self.assertEqual(data["sections"]["collection"], [{"n": 1}])
        self.assertIn("generated", data)

    def test_failed_section_reported_not_fatal(self):
        def run(sql):
            if "v_outcome" in sql:
                raise RuntimeError("boom")
            return "n\n1\n"
        data = bd.build(run=run)
        self.assertTrue(data["errors"])
        self.assertEqual(data["sections"]["collection"], [{"n": 1}])


if __name__ == "__main__":
    unittest.main()
