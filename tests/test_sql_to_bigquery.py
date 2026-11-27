"""sql_to_bigquery: PostgreSQL 분석·검증 SQL을 BigQuery 문법으로 자동 변환·검사."""
import sys
import tempfile
import unittest
from pathlib import Path

try:
    import sqlglot  # noqa: F401
except ImportError:
    sqlglot = None

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
if sqlglot is not None:
    import sql_to_bigquery as sb  # noqa: E402


@unittest.skipIf(sqlglot is None, "sqlglot 없음 (.venv/bin/pip install sqlglot)")
class ConvertTest(unittest.TestCase):
    def test_postgres_only_syntax_is_rewritten(self):
        out = sb.convert("SELECT DISTINCT ON (a) a, x::int, count(*) FILTER (WHERE y) AS n, d - INTERVAL '3 years' "
                         "FROM raw.t GROUP BY a, x, d ORDER BY a")
        self.assertNotIn("DISTINCT ON", out)
        self.assertIn("ROW_NUMBER()", out)
        self.assertIn("CAST(x AS INT64)", out)
        self.assertIn("COUNTIF(y)", out)
        self.assertNotIn("::", out)

    def test_header_comments_are_kept(self):
        out = sb.convert_file_text("-- 질문: 무엇을 보나\n-- 읽는 법: 이렇게\nSELECT 1")
        self.assertTrue(out.startswith("-- 질문: 무엇을 보나"))
        self.assertIn("BigQuery", out.splitlines()[2])

    def test_check_reports_parse_errors(self):
        self.assertEqual(sb.check("SELECT 1"), [])
        self.assertTrue(sb.check("SELECT FROM WHERE ("))

    def test_build_writes_one_file_per_source(self):
        with tempfile.TemporaryDirectory() as d:
            src, dst = Path(d) / "kr", Path(d) / "bq"
            (src / "analysis").mkdir(parents=True)
            (src / "analysis" / "a.sql").write_text("-- 질문: x\nSELECT a::text FROM raw.t", encoding="utf-8")
            report = sb.build(src, dst)
            self.assertTrue((dst / "analysis" / "a.sql").exists())
            self.assertEqual(report, {"converted": 1, "failed": []})

    def test_repo_sql_all_convert(self):   # 저장소의 분석·검증 SQL이 모두 BigQuery로 바뀌어야 한다
        with tempfile.TemporaryDirectory() as d:
            report = sb.build(sb.SRC_DIR, Path(d))
        self.assertEqual(report["failed"], [])
        self.assertGreaterEqual(report["converted"], 17)
        self.assertTrue(any("00_core_views" in x for x in report.get("skipped", [])))   # 절차형 블록은 사람이

    def test_nulls_ordering_inside_string_agg_is_noted_not_failed(self):
        notes = []
        out = sb.convert("SELECT string_agg(n, ',' ORDER BY n NULLS LAST) FROM t", notes)
        self.assertIn("STRING_AGG", out.upper())
        self.assertTrue(notes)


if __name__ == "__main__":
    unittest.main()
