"""PostgreSQL 적재 스크립트의 순수 함수 테스트 — DB 없이."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import load_pg as lp  # noqa: E402


class TypeTest(unittest.TestCase):
    def test_kinds_to_postgres_types(self):
        self.assertEqual(lp.pg_type("date"), "date")
        self.assertEqual(lp.pg_type("datetime_tz"), "timestamptz")
        self.assertEqual(lp.pg_type("int_pos"), "integer")
        self.assertEqual(lp.pg_type("int0"), "integer")
        self.assertEqual(lp.pg_type("flag01"), "smallint")
        self.assertEqual(lp.pg_type("date_partial"), "text")   # '2024'·'2024-05'도 있어서 원문 보관 + 보조 칸
        self.assertEqual(lp.pg_type("code"), "text")


class DdlTest(unittest.TestCase):
    def test_create_table_has_schema_columns_plus_keys_and_source(self):
        sql = lp.ddl("raw_kr_selection")
        self.assertIn("CREATE TABLE raw.raw_kr_selection", sql)
        self.assertIn("announced_at text", sql)
        self.assertIn("announced_start date", sql)      # 기간 첫날 (정답 쪽 해석)
        self.assertIn("announced_end date", sql)        # 기간 마지막 날 (후보 쪽 해석)
        self.assertIn("artist_key text", sql)
        self.assertIn("alias_key text", sql)
        self.assertIn("source_file text", sql)

    def test_artist_key_not_duplicated_when_schema_has_it(self):
        sql = lp.ddl("raw_kr_release")
        self.assertEqual(sql.count("artist_key text"), 1)


class RowTest(unittest.TestCase):
    def test_normalized_row_fills_keys_dates_and_blanks(self):
        cols = lp.columns("raw_kr_selection")
        row = lp.normalize_row("raw_kr_selection", {
            "collected_at": "2026-11-26T20:00:00+09:00", "source": "yjh", "collector": "script",
            "program": "yoojaeha_finalist", "round": "36회", "stage": "selected", "announced_at": "2025",
            "artist_text": "OU:RE(아우리)", "url": "https://www.yjh.or.kr/History", "note": ""}, "f.csv")
        rec = dict(zip(cols, row))
        self.assertEqual((rec["announced_start"], rec["announced_end"]), ("2025-01-01", "2025-12-31"))
        self.assertEqual((rec["artist_key"], rec["alias_key"]), ("oure", "아우리"))
        self.assertEqual(rec["note"], None)            # 빈 칸은 NULL
        self.assertEqual(rec["source_file"], "f.csv")

    def test_missing_optional_columns_become_null(self):
        cols = lp.columns("raw_kr_release")
        rec = dict(zip(cols, lp.normalize_row("raw_kr_release", {
            "collected_at": "2026-11-26T15:00:00+09:00", "source": "poclanos", "collector": "script",
            "released_at": "2026-11-26", "artist_text": "결 (KYUL)", "title": "세탁", "release_url": "https://x"}, "p.csv")))
        self.assertEqual(rec["distributor_text"], None)
        self.assertEqual(rec["artist_key"], "결")        # 파일에 없으면 계산해서 채움


class HtmlEntityTest(unittest.TestCase):
    def test_html_entities_unescaped_before_keys(self):
        cols = lp.columns("raw_kr_gig")
        rec = dict(zip(cols, lp.normalize_row("raw_kr_gig", {
            "collected_at": "2026-11-26T18:00:00+09:00", "source": "indistreet", "collector": "aside", "gig_date": "2026-11-28",
            "title": "You&amp;apos;re mine", "artist_text": "팻햄스터&amp;amp;캉뉴", "gig_url": "https://x"}, "g.csv")))
        self.assertEqual(rec["artist_text"], "팻햄스터&캉뉴")
        self.assertEqual(rec["title"], "You're mine")
        self.assertEqual(rec["artist_key"], "팻햄스터캉뉴")


class RefTest(unittest.TestCase):
    def test_reference_tables_sql_from_schema(self):
        sql = lp.ref_sql()
        self.assertIn("CREATE TABLE ref.outcome_tier", sql)
        self.assertIn("('kma_rookie', 'final', false)", sql)
        self.assertIn("('burock_main', 'mid', true)", sql)
        self.assertIn("('final', 4)", sql)                      # ref.stage_rank
        self.assertIn("('hello_rookie', 'hello_rookie_year')", sql)   # ref.outcome_same_family
        self.assertIn("('burock_rookies', 'burock_main')", sql)       # ref.same_program


if __name__ == "__main__":
    unittest.main()
