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
        self.assertGreaterEqual(report["converted"], 18)                                # 기본 뷰도 펼쳐서 변환

    def test_core_views_do_blocks_are_flattened(self):
        flat = sb.flatten_core_views("CREATE SCHEMA IF NOT EXISTS core;\nDO $$ BEGIN x; END $$;\n"
                                     "DO $$ BEGIN y; END $$;\nCREATE VIEW core.a AS SELECT 1;\n")
        self.assertNotIn("DO $$", flat)
        self.assertNotIn("CREATE SCHEMA", flat)
        self.assertIn("core.v_team_map", flat)
        self.assertIn("core.v_venue_map", flat)
        self.assertIn("core.a", flat)

    def test_core_views_ref_tables_are_not_created_in_bigquery(self):
        # 뷰 파일이 만드는 빈 ref 표(없을 때 대비)는 BigQuery 에서는 운영 방식대로 따로 — 변환 결과에서 뺀다
        flat = sb.flatten_core_views("-- 2) 설명 주석\nCREATE TABLE IF NOT EXISTS ref.blocked_profile_ids (source text, artist_source_id text);\n"
                                     "CREATE VIEW core.a AS SELECT 1;\n")
        self.assertNotIn("CREATE TABLE", flat)
        self.assertIn("core.a", flat)
        self.assertIn("-- 2) 설명 주석", flat)                     # 건너뛴 문장 앞 주석은 다음 문장에 붙여 남김

    def test_core_views_header_comments_kept(self):
        flat = sb.flatten_core_views("-- 머리 주석\nCREATE SCHEMA IF NOT EXISTS core;\nCREATE VIEW core.a AS SELECT 1;   -- 끝 주석\n"
                                     "CREATE VIEW core.b AS SELECT 2;\n")
        self.assertTrue(flat.startswith("-- 머리 주석"))
        self.assertNotIn("CREATE SCHEMA", flat)
        self.assertIn("core.b", flat)

    def test_nulls_ordering_inside_string_agg_is_noted_not_failed(self):
        notes = []
        out = sb.convert("SELECT string_agg(n, ',' ORDER BY n NULLS LAST) FROM t", notes)
        self.assertIn("STRING_AGG", out.upper())
        self.assertTrue(notes)


if __name__ == "__main__":
    unittest.main()
