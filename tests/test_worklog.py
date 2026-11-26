"""작업 기록 엑셀(worklog.py) 테스트."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import worklog  # noqa: E402
from openpyxl import load_workbook  # noqa: E402

ENTRY = {
    "date": "2026-11-26",
    "작업기록": [{"파이프라인 단계": "1 원본 수집", "한 일": "포크라노스 수집기", "결정한 것": "",
               "찾은 빈틈·보완": "콜라보 중복", "다음 할 일": "공연 수집", "커밋": "aabf2f8"}],
    "결정사항": [{"주제": "신인 기준", "결정": "2년 이내 & 5개 이하", "이유": "싱글 위주 신인도 포함"}],
    "지침": [{"분류": "도구", "지침 내용": "웹 확인·수집은 aside"}],
}


class WorklogTest(unittest.TestCase):
    def test_creates_workbook_with_all_sheets_and_rows(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "log.xlsx"
            added = worklog.append_entry(path, ENTRY)
            wb = load_workbook(path)
        self.assertEqual(wb.sheetnames, list(worklog.SHEETS))
        self.assertEqual(added, {"작업기록": 1, "결정사항": 1, "지침": 1, "직무참고": 0})
        ws = wb["작업기록"]
        self.assertEqual([c.value for c in ws[1]], ["날짜"] + worklog.SHEETS["작업기록"])
        self.assertEqual(ws.cell(row=2, column=1).value, "2026-11-26")
        self.assertEqual(ws.cell(row=2, column=3).value, "포크라노스 수집기")

    def test_running_twice_does_not_duplicate(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "log.xlsx"
            worklog.append_entry(path, ENTRY)
            added = worklog.append_entry(path, ENTRY)
            wb = load_workbook(path)
        self.assertEqual(sum(added.values()), 0)
        self.assertEqual(wb["결정사항"].max_row, 2)

    def test_unknown_column_is_rejected(self):
        bad = {"date": "2026-11-26", "지침": [{"분류": "x", "없는칸": "y"}]}
        with tempfile.TemporaryDirectory() as d, self.assertRaises(ValueError):
            worklog.append_entry(Path(d) / "log.xlsx", bad)

    def test_cli_reads_json_file(self):
        with tempfile.TemporaryDirectory() as d:
            entry_path = Path(d) / "e.json"
            entry_path.write_text(json.dumps(ENTRY, ensure_ascii=False), encoding="utf-8")
            code = worklog.main([str(entry_path), "--xlsx", str(Path(d) / "log.xlsx")])
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
