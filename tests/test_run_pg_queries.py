"""SQL 결과 문서 만들기(run_pg_queries)의 순수 함수 테스트 — DB 없이."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import run_pg_queries as rq  # noqa: E402

SQL = """-- 질문: 선정 프로그램별 이후 수상 비율은?
-- 왜 중요한가: 어떤 신호가 진짜인지 본다
-- 읽는 법: 비율이 높을수록 좋은 신호

WITH x AS (SELECT 1)
SELECT * FROM x;
"""


class HeaderTest(unittest.TestCase):
    def test_header_comment_and_body_split(self):
        head, body = rq.split_header(SQL)
        self.assertEqual(head, ["질문: 선정 프로그램별 이후 수상 비율은?", "왜 중요한가: 어떤 신호가 진짜인지 본다",
                                "읽는 법: 비율이 높을수록 좋은 신호"])
        self.assertTrue(body.startswith("WITH x AS"))


class TableTest(unittest.TestCase):
    def test_csv_to_markdown_with_limit_and_pipes(self):
        csv_text = "프로그램,비율\nband_discovery,0.087\na|b,0.05\nc,0.01\n"
        md, n = rq.csv_to_markdown(csv_text, limit=2)
        self.assertEqual(n, 3)
        self.assertIn("| 프로그램 | 비율 |", md)
        self.assertIn("| a\\|b | 0.05 |", md)
        self.assertNotIn("| c |", md)
        self.assertIn("3행 중 2행", md)

    def test_empty_result(self):
        md, n = rq.csv_to_markdown("a,b\n", limit=5)
        self.assertEqual(n, 0)
        self.assertIn("결과 없음", md)


if __name__ == "__main__":
    unittest.main()
