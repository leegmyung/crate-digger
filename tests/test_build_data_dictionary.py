"""데이터 사전(build_data_dictionary): 코드의 칸 정의에서 docs/data_dictionary.md 를 만든다.
칸이 바뀌면 설명 누락·문서 낡음이 테스트 실패로 드러난다 → python3 scripts/build_data_dictionary.py 로 다시 만든다."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_data_dictionary as dd  # noqa: E402


class CoverageTest(unittest.TestCase):
    def test_every_column_has_a_description(self):
        self.assertEqual(dd.missing_descriptions(), [],
                         "설명 없는 칸 — build_data_dictionary.COLUMN_DOC 에 추가해 주세요")

    def test_missing_detected_for_new_column(self):
        tables = [{"name": "t", "columns": ["team_key", "brand_new_col"]}]
        self.assertEqual(dd.missing_descriptions(tables), ["t.brand_new_col"])


class RenderTest(unittest.TestCase):
    def setUp(self):
        self.md = dd.render()

    def test_all_tables_and_columns_present(self):
        for t in dd.all_tables():
            self.assertIn(f"`{t['name']}`", self.md)
            for c in t["columns"]:
                self.assertIn(f"`{c}`", self.md)

    def test_raw_tables_marked_private_and_roles_listed(self):
        self.assertIn("비공개", self.md)
        self.assertIn("raw_kr_gig", self.md)
        for role in ("발굴", "맥락", "검증 대기", "제외"):
            self.assertIn(role, self.md)
        self.assertIn("공연:indistreet", self.md)

    def test_no_private_paths(self):
        self.assertNotIn("/Users/", self.md)

    def test_doc_file_is_up_to_date(self):
        path = ROOT / "docs" / "data_dictionary.md"
        self.assertTrue(path.exists(), "docs/data_dictionary.md 없음 — python3 scripts/build_data_dictionary.py")
        self.assertEqual(path.read_text(encoding="utf-8"), self.md,
                         "칸 정의가 바뀌었는데 문서가 낡음 — python3 scripts/build_data_dictionary.py 로 다시 만드세요")


if __name__ == "__main__":
    unittest.main()
