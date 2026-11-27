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


class VenueBranchTest(unittest.TestCase):
    def _venue(self, text):
        cols = lp.columns("raw_kr_gig")
        rec = dict(zip(cols, lp.normalize_row("raw_kr_gig", {
            "collected_at": "2026-11-26T18:00:00+09:00", "source": "sangsangmadang", "collector": "script",
            "gig_date": "2026-11-28", "artist_text": "몽니", "gig_url": "https://x", "venue_text": text}, "g.csv")))
        return rec["venue_text"]

    def test_branch_in_paren_moves_to_front_on_load(self):
        # SQL 이 split_part(venue_text, ' (', 1) 로 공연장을 자르므로, 지점 괄호는 적재 때 앞으로 옮긴다 (원본 CSV는 그대로)
        self.assertEqual(self._venue("라이브홀 (KT&amp;G 상상마당 홍대)"), "KT&G 상상마당 홍대 라이브홀")

    def test_address_paren_kept(self):
        self.assertEqual(self._venue("Club FF (서울 마포구 와우산로 1)"), "Club FF (서울 마포구 와우산로 1)")


class RefTest(unittest.TestCase):
    def test_reference_tables_sql_from_schema(self):
        sql = lp.ref_sql()
        self.assertIn("CREATE TABLE ref.outcome_tier", sql)
        self.assertIn("('kma_rookie', 'final', false)", sql)
        self.assertIn("('burock_main', 'mid', true)", sql)
        self.assertIn("('final', 4)", sql)                      # ref.stage_rank
        self.assertIn("('hello_rookie', 'hello_rookie_year')", sql)   # ref.outcome_same_family
        self.assertIn("('burock_rookies', 'burock_main')", sql)       # ref.same_program
        self.assertIn("('fame_fans', 10000)", sql)                    # 유명 팀 제외 기준
        self.assertIn("('fame_years', 5)", sql)
        self.assertIn("('newcomer_years', 3)", sql)


class DebutOverridesTest(unittest.TestCase):
    """사람이 확인한 데뷔일(config/debut_overrides.json)을 DB에도 — 랩 팀 표와 정답 '셈' 판정이 같아지게."""

    def test_ref_sql_builds_debut_override_table(self):
        sql = lp.ref_sql(debut_overrides={"안예은": {"debut": "2016-11-28"}, "it's": {"debut": "2015-01-01"}})
        self.assertIn("CREATE TABLE ref.debut_overrides", sql)
        self.assertIn("('안예은', DATE '2016-11-28')", sql)
        self.assertIn("('it''s', DATE '2015-01-01')", sql)       # 작은따옴표는 두 번
        self.assertIn("ref.debut_overrides", sql[sql.index("DROP TABLE"):sql.index(";", sql.index("DROP TABLE"))])

    def test_ref_sql_without_overrides_makes_empty_table(self):
        sql = lp.ref_sql(debut_overrides={})
        self.assertIn("CREATE TABLE ref.debut_overrides", sql)
        self.assertNotIn("INSERT INTO ref.debut_overrides", sql)

    def test_bad_debut_dates_are_skipped(self):
        sql = lp.ref_sql(debut_overrides={"a": {"debut": "2016"}, "b": {}, "c": {"debut": "2016-02-30x"}})
        self.assertNotIn("INSERT INTO ref.debut_overrides", sql)

    def test_default_reads_config_file(self):
        sql = lp.ref_sql()
        self.assertIn("('안예은', DATE '2016-11-28')", sql)

    def test_team_profile_view_takes_earlier_of_profile_and_override(self):
        sql = (ROOT / "sql" / "kr" / "00_core_views.sql").read_text(encoding="utf-8")
        view = sql[sql.index("CREATE VIEW core.v_team_profile"):sql.index("CREATE VIEW core.v_outcome ")]
        self.assertIn("ref.debut_overrides", view)
        self.assertIn("FULL JOIN", view)          # 프로필이 없는 팀(안예은)도 덮어쓴 데뷔일로
        self.assertIn("least(", view.lower())
        self.assertLess(sql.index("CREATE TABLE IF NOT EXISTS ref.debut_overrides"), sql.index("CREATE VIEW core.v_team_profile"))


class ArtistProfileOwnReleaseTest(unittest.TestCase):
    """v_artist_profile: 같은 출처·번호는 최신 행만(다시 받은 프로필이 옛 행의 이른 날짜를 덮게) · 첫 발매 = 본인 음반 기준
    (first_release_own)이 있으면 그것, 없으면 전체 앨범 기준 — 데뷔일과 이른 쪽 (2026-11-28, 성현: 2016 → 2025-10-22)."""

    def setUp(self):
        sql = (ROOT / "sql" / "kr" / "00_core_views.sql").read_text(encoding="utf-8")
        self.view = sql[sql.index("CREATE VIEW core.v_artist_profile"):sql.index("CREATE VIEW core.v_team_profile")]

    def test_latest_row_per_source_and_id(self):
        self.assertIn("DISTINCT ON (source, artist_source_id)", self.view)
        self.assertIn("ORDER BY source, artist_source_id, collected_at DESC", self.view)

    def test_first_release_prefers_own_albums(self):
        self.assertIn("coalesce(first_release_own_start, first_release_start)", self.view.lower())
        self.assertIn("least(", self.view.lower())
        self.assertIn("ref.blocked_profile_ids", self.view)

    def test_own_column_is_loaded(self):
        self.assertIn("first_release_own_start", lp.columns("raw_artist_profile"))


class ExpandRowsTest(unittest.TestCase):
    """원본은 그대로 두고, 적재할 때 오버톤의 '여러 팀 한 칸'을 팀별 행으로 나눈다."""

    def test_overtone_press_row_split(self):
        row = {"source": "overtone", "artist_text": "SUMIN, Slom", "url": "u"}
        self.assertEqual([r["artist_text"] for r in lp.expand_rows("raw_press", row)], ["SUMIN", "Slom"])

    def test_other_rows_untouched(self):
        row = {"source": "izm", "artist_text": "A, B", "url": "u"}
        self.assertEqual(lp.expand_rows("raw_press", row), [row])
        gig = {"artist_text": "A, B"}
        self.assertEqual(lp.expand_rows("raw_kr_gig", gig), [gig])

    def test_name_with_comma_one_row(self):
        row = {"source": "overtone", "artist_text": "Tyler, The Creator"}
        self.assertEqual(lp.expand_rows("raw_press", row), [row])


if __name__ == "__main__":
    unittest.main()
