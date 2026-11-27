"""docs/lab/sql/*.sql을 로컬 DuckDB로 돌려 본다 (브라우저의 DuckDB-WASM과 같은 문법).
duckdb가 없으면 건너뛴다: .venv/bin/pip install duckdb 후 .venv/bin/python -m unittest tests.test_lab_sql
"""
import math
import sys
import unittest
from pathlib import Path

try:
    import duckdb
except ImportError:  # 시스템 파이썬에는 없을 수 있음
    duckdb = None

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from lab_sql import COLLABS_DDL, DEFAULTS, SQL_DIR, V0_WEIGHTS, fill  # noqa: E402


def fixture_db():
    con = duckdb.connect()
    con.execute("""
        CREATE TABLE signals(team_key VARCHAR, branch VARCHAR, source VARCHAR, program VARCHAR,
                             stage_rank INTEGER, signal_date DATE, venue VARCHAR);
        INSERT INTO signals VALUES
          ('a','공연','x','',NULL,'2024-06-01','클럽1'),
          ('a','선정·지원','x','band_discovery',3,'2024-03-01',''),
          ('a','큐레이션','x','visla',NULL,'2024-07-01',''),
          ('b','공연','x','',NULL,'2024-06-01','클럽1'),
          ('c','공연','x','',NULL,'2024-05-01','클럽2'),
          ('d','공연','x','',NULL,'2010-05-01','클럽2'),
          ('d','공연','x','',NULL,'2024-05-01','클럽2'),
          ('e','선정·지원','x','dmz_lineup',2,'2024-08-01',''),
          ('f','공연','x','',NULL,'2024-02-01','클럽3'),
          ('g','선정·지원','x','band_discovery',2,'2026-05-01',''),
          ('g','공연','x','',NULL,'2026-06-01','클럽1'),
          ('g','공연','x','',NULL,'2026-07-01','클럽9');
        CREATE TABLE teams(team_key VARCHAR, display_name VARCHAR, first_seen DATE, first_release DATE,
                           fan_count INTEGER, album_count INTEGER, profile_status VARCHAR, primary_genre VARCHAR);
        INSERT INTO teams VALUES
          ('a','에이','2024-03-01',NULL,NULL,NULL,'unknown','록·밴드'),
          ('b','비','2024-06-01',NULL,NULL,NULL,'unknown',''),
          ('c','씨','2024-05-01',NULL,NULL,NULL,'famous',''),
          ('d','디','2010-05-01',NULL,NULL,NULL,'unknown',''),
          ('e','이','2024-08-01',NULL,NULL,NULL,'unknown',''),
          ('f','에프','2024-02-01',NULL,NULL,NULL,'unknown',''),
          ('g','지','2026-05-01',NULL,NULL,NULL,'unknown','');
        CREATE TABLE outcomes(team_key VARCHAR, program VARCHAR, program_label VARCHAR, tier VARCHAR,
                              announced_date DATE, counted BOOLEAN);
        INSERT INTO outcomes VALUES
          ('a','kma_rookie','한대음 신인','final','2025-03-01',true),
          ('b','museon_final','뮤즈온','mid','2025-04-01',true),
          ('f','kma_rookie','한대음 신인','final','2024-12-01',true);
        CREATE TABLE programs(program VARCHAR, label VARCHAR, kind VARCHAR);
        INSERT INTO programs VALUES ('band_discovery','상상마당 밴드 디스커버리','signal');
    """)
    con.execute("ALTER TABLE signals ADD COLUMN role VARCHAR DEFAULT 'discovery'")
    con.execute("UPDATE signals SET role = 'discovery'")
    con.execute("ALTER TABLE outcomes ADD COLUMN weight INTEGER DEFAULT 1")
    con.execute("UPDATE outcomes SET weight = CASE WHEN program = 'kma_rookie' THEN 3 ELSE 1 END")
    con.execute("ALTER TABLE outcomes ADD COLUMN grade VARCHAR")
    con.execute("UPDATE outcomes SET grade = CASE WHEN weight = 3 THEN 'S' ELSE 'B' END")
    con.execute("ALTER TABLE outcomes ADD COLUMN same_house_sources VARCHAR DEFAULT ''")
    con.execute("ALTER TABLE outcomes ADD COLUMN same_house_scored BOOLEAN DEFAULT false")
    con.execute(COLLABS_DDL)      # 협업 데이터가 없을 때와 같은 빈 표 (lab_sql.connect·앱과 같은 정의)
    con.execute("ALTER TABLE teams ADD COLUMN newcomer_check VARCHAR DEFAULT 'first_seen'")   # 신인 판정 확인 상태
    con.execute("UPDATE teams SET newcomer_check = CASE team_key WHEN 'b' THEN 'unverified' ELSE 'first_seen' END")
    con.execute((SQL_DIR / "features.sql").read_text(encoding="utf-8"))
    con.execute("CREATE OR REPLACE MACRO fame_known_from() AS DATE '2000-01-01'")   # 가짜 데이터: 유명 판정을 모든 기준일에 씀
    return con


def rows(con, name, **params):
    cur = con.execute(fill((SQL_DIR / name).read_text(encoding="utf-8"), **{**V0_WEIGHTS, **params}))
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


@unittest.skipIf(duckdb is None, "duckdb 없음")
class LabSqlTest(unittest.TestCase):
    def setUp(self):
        self.con = fixture_db()

    def scored(self, cutoff="2025-01-01", **p):
        q = ("SELECT * FROM lab_scored(DATE '{c}', {lookback_years}, {newcomer_years}, {exclude_famous}, "
             "{outcome_tier}, {horizon_months}, {genre}, {branches}, {w_branch}, {w_stage}, {w_peer}, {w_dmz}, "
             "{w_gigs}, {w_outlets}, {outlet_cap}, {w_recent}, {w_venues}, {w_winner}) ORDER BY team_key")
        args = {**DEFAULTS, **V0_WEIGHTS, **p}
        cur = self.con.execute(q.format(c=cutoff, **args))
        cols = [d[0] for d in cur.description]
        return {r[0]: dict(zip(cols, r)) for r in cur.fetchall()}

    def test_famous_and_old_teams_are_excluded_from_pool(self):
        pool = self.scored()
        self.assertNotIn("c", pool)       # 유명
        self.assertNotIn("d", pool)       # 2010년 첫 등장 → 신인 아님
        self.assertIn("c", self.scored(exclude_famous="false"))

    def test_famous_rule_is_not_used_before_fan_counts_were_collected(self):
        # 유명 판정은 '지금' 팬 수라, 팬 수를 모으기 시작한 날보다 이른 기준일에는 쓰지 않는다 (미래 정보 방지)
        self.con.execute("CREATE OR REPLACE MACRO fame_known_from() AS DATE '2025-06-01'")
        try:
            self.assertIn("c", self.scored())
        finally:
            self.con.execute("CREATE OR REPLACE MACRO fame_known_from() AS DATE '2000-01-01'")

    def test_newcomer_uses_profile_first_release_when_known(self):
        self.con.execute("UPDATE teams SET first_release = '2015-01-01' WHERE team_key = 'a'")   # 우리 데이터엔 2024 첫 등장이지만 실제 데뷔는 2015
        self.assertNotIn("a", self.scored())
        self.con.execute("UPDATE teams SET first_release = '2023-06-01' WHERE team_key = 'a'")
        self.assertIn("a", self.scored())

    def test_score_parts(self):
        a = self.scored()["a"]
        self.assertEqual((a["n_branch"], a["best_stage"], a["outlets"]), (3, 3, 1))
        self.assertAlmostEqual(a["score"], 2 * 2 + 3 + 0 + 0 + 0.5 * __import__("math").log(2) + 1)

    def test_peer_selected_when_sharing_stage_with_selected_team(self):
        self.assertEqual(self.scored()["b"]["peer_selected"], 1)

    def test_dmz_is_bonus_not_stage(self):
        e = self.scored()["e"]
        self.assertEqual((e["dmz"], e["best_stage"]), (1, 0))

    def test_outcome_before_cutoff_is_flagged_and_tier_filter_works(self):
        pool = self.scored()
        self.assertTrue(pool["f"]["had_outcome"])
        self.assertEqual(pool["a"]["is_hit"], 1)
        self.assertEqual(self.scored(outcome_tier="'final'")["b"]["is_hit"], 0)

    def test_v1_features_recent_venues_and_peer_winner(self):
        # f는 2024-12-01에 정답 → 2024-12-15 클럽3에서 f와 같이 선 h는 '수상 팀과 같은 무대'
        self.con.execute("""INSERT INTO signals VALUES ('f','공연','x','',NULL,'2024-12-15','클럽3','discovery'),
                                                       ('h','공연','x','',NULL,'2024-12-15','클럽3','discovery'),
                                                       ('h','공연','x','',NULL,'2024-11-01','클럽2','discovery')""")
        self.con.execute("INSERT INTO teams VALUES ('h','에이치','2024-11-01',NULL,NULL,NULL,'unknown','','first_seen')")
        h = self.scored()["h"]
        self.assertEqual((h["peer_winner"], h["venues"], h["recent180"]), (1, 2, 2))
        self.assertEqual(self.scored()["a"]["recent180"], 0)   # a의 마지막 신호 2024-07-01은 180일 밖

    def venue_scored(self, extra="", lookback=3, cutoff="2025-01-01"):
        """lab_scored 를 이름 붙은 선택 인자(extra, 예: 'venue_years := 1')와 함께 부른다 (v0 가중치 + 공연장 가중치 1)."""
        q = ("SELECT * FROM lab_scored(DATE '{c}', {lb}, 3, true, 'any', 24, '', "
             "['공연','선정·지원','발매','큐레이션'], 2, 1, 1, 0.5, 0.5, 1, 3, w_venues := 1, w_winner := 2{x}) "
             "ORDER BY team_key")
        cur = self.con.execute(q.format(c=cutoff, lb=lookback, x=(", " + extra) if extra else ""))
        cols = [d[0] for d in cur.description]
        return {r[0]: dict(zip(cols, r)) for r in cur.fetchall()}

    def add_venue_team(self):
        # v: 2년 전 클럽A, 반년 전 클럽B (기준일 2025-01-01)
        self.con.execute("""INSERT INTO signals VALUES ('v','공연','x','',NULL,'2022-12-01','클럽A','discovery'),
                                                       ('v','공연','x','',NULL,'2024-07-01','클럽B','discovery')""")
        self.con.execute("INSERT INTO teams VALUES ('v','브이','2022-12-01',NULL,NULL,NULL,'unknown','','first_seen')")

    def test_venue_years_defaults_to_two(self):
        """공연장 수는 기본 최근 2년만 센다 (2026-11-28 사용자 결정). 안 넘기면 venue_years := 2 와 같다."""
        self.add_venue_team()
        self.assertEqual(self.venue_scored(), self.venue_scored("venue_years := 2"))
        self.assertEqual(self.venue_scored()["v"]["venues"], 1)                  # 2022-12 클럽A는 2년 밖

    def test_venue_years_equal_to_lookback_is_old_definition(self):
        """venue_years := 신호 보는 기간(3) 이면 바꾸기 전 정의(기간 전체)와 같다 — 되돌릴 때 이 한 줄."""
        self.add_venue_team()
        old = self.venue_scored("venue_years := 3")["v"]
        new = self.venue_scored()["v"]
        self.assertEqual((old["venues"], new["venues"]), (2, 1))
        self.assertAlmostEqual(old["score"] - new["score"], math.log(3) - math.log(2))   # 공연장 점수만 달라짐
        for k in ("gigs_1y", "recent180", "n_branch", "peer_winner", "last_seen"):
            self.assertEqual(old[k], new[k])

    def test_venue_years_longer_than_lookback_is_capped(self):
        self.add_venue_team()
        self.assertEqual(self.venue_scored("venue_years := 10"), self.venue_scored("venue_years := 3"))
        self.assertEqual(self.venue_scored(lookback=1), self.venue_scored("venue_years := 1", lookback=1))

    def collab_scored(self, cutoff="2025-01-01", w_collab=1):
        q = ("SELECT * FROM lab_scored(DATE '{c}', 3, 3, true, 'any', 24, '', "
             "['공연','선정·지원','발매','큐레이션'], 2, 1, 1, 0.5, 0.5, 1, 3, w_collab := {w}) ORDER BY team_key")
        cur = self.con.execute(q.format(c=cutoff, w=w_collab))
        cols = [d[0] for d in cur.description]
        return {r[0]: dict(zip(cols, r)) for r in cur.fetchall()}

    def test_collab_est_counts_distinct_established_partners_before_cutoff(self):
        self.con.execute("""INSERT INTO collabs VALUES
            ('a','p1','파트너1','2024-05-01','feat_on_own',true),
            ('a','p1','파트너1','2024-08-01','co_lead',true),          -- 같은 파트너는 한 번만
            ('a','p2','파트너2','2023-01-01','guest_on_partner',true),
            ('a','p3','파트너3','2024-06-01','feat_on_own',false),      -- 기성 파트너 아님 → 안 셈
            ('a','p4','파트너4','2025-02-01','feat_on_own',true),       -- 기준일 뒤 → 안 셈 (시점 누수 방지)
            ('a','p5','파트너5','2021-06-01','feat_on_own',true),       -- 3년 창 밖 → 안 셈
            ('b','p1','파트너1','2024-12-31','feat_on_own',true)""")
        pool = self.collab_scored()
        self.assertEqual(pool["a"]["collab_est"], 2)
        self.assertEqual(pool["b"]["collab_est"], 1)
        self.assertEqual(pool["e"]["collab_est"], 0)
        self.assertAlmostEqual(pool["a"]["pts_collab"], __import__("math").log(3))
        self.assertAlmostEqual(pool["a"]["score"] - self.collab_scored(w_collab=0)["a"]["score"],
                               __import__("math").log(3))

    def test_collab_weight_defaults_to_zero_and_empty_table_is_fine(self):
        base = self.scored()
        self.assertEqual(base["a"]["collab_est"], 0)
        self.assertEqual(base["a"]["pts_collab"], 0)

    def test_collab_text_columns_from_header_only_csv_still_work(self):
        # 헤더만 있는 collabs.csv 를 read_csv_auto 로 읽으면 모든 칸이 글자형 → 계산식이 형 변환으로 견뎌야 함
        self.con.execute("DROP TABLE collabs")
        self.con.execute("CREATE TABLE collabs(team_key VARCHAR, partner_key VARCHAR, partner_name VARCHAR, "
                         "release_date VARCHAR, role VARCHAR, partner_established VARCHAR)")
        self.con.execute("INSERT INTO collabs VALUES ('a','p1','x','2024-05-01','feat_on_own','true')")
        self.assertEqual(self.collab_scored()["a"]["collab_est"], 1)

    def test_context_signals_are_ignored_and_hit_weight_reported(self):
        self.con.execute("UPDATE signals SET role = 'context' WHERE team_key = 'a' AND branch = '큐레이션'")
        a = self.scored()["a"]
        self.assertEqual((a["n_branch"], a["outlets"]), (2, 0))       # 맥락 출처(큐레이션)는 점수에서 빠짐
        self.assertEqual(a["hit_weight"], 3)                           # kma_rookie = S등급 가중치 3
        self.assertEqual(self.scored()["b"]["hit_weight"], 1)

    def test_backtest_counts_hits_and_random_baseline(self):
        res = {(r["k"], r["method"]): r for r in rows(self.con, "backtest.sql", cutoff="'2025-01-01'", k_list="[1,2,3]")}
        top1 = res[(1, "점수")]
        self.assertEqual(top1["hits"], 1)            # 점수 1위 = a (정답)
        self.assertEqual(top1["pool_n"], 3)          # a, b, e (f는 이미 정답이라 제외)
        self.assertEqual(top1["pool_hits"], 2)
        self.assertAlmostEqual(top1["random_expected"], round(2 / 3, 2))

    def test_candidates_sorted_by_score_and_hide_outcome_teams(self):
        out = rows(self.con, "candidates.sql", as_of="'2025-01-01'", limit="50")
        self.assertEqual(out[0]["team_key"], "a")
        self.assertNotIn("f", [r["team_key"] for r in out])

    def test_candidates_carry_newcomer_check_without_changing_scores(self):
        out = {r["team_key"]: r for r in rows(self.con, "candidates.sql", as_of="'2025-01-01'", limit="50",
                                               only_no_outcome="false")}
        self.assertEqual(out["b"]["newcomer_check"], "unverified")
        self.assertEqual(out["a"]["newcomer_check"], "first_seen")
        before = {k: r["score"] for k, r in out.items()}
        self.con.execute("UPDATE teams SET newcomer_check = 'verified'")   # 표시만 바뀌고 점수·후보군은 그대로
        after = {r["team_key"]: r["score"] for r in rows(self.con, "candidates.sql", as_of="'2025-01-01'",
                                                          limit="50", only_no_outcome="false")}
        self.assertEqual(before, after)

    def test_signal_hits_has_baseline_and_wilson_bounds(self):
        out = rows(self.con, "signal_hits.sql", cutoff="'2025-01-01'")
        self.assertTrue(out[0]["program"].startswith("(기준선)"))
        bd = [r for r in out if r["program"] == "band_discovery"][0]
        self.assertEqual((bd["teams"], bd["hits"], bd["label"]), (1, 1, "상상마당 밴드 디스커버리"))
        self.assertTrue(0 <= bd["ci_low"] <= bd["rate"] <= bd["ci_high"] <= 100)


@unittest.skipIf(duckdb is None, "duckdb 없음")
class TeamSqlTest(unittest.TestCase):
    def setUp(self):
        self.con = fixture_db()

    def test_precedents_finds_past_winner_with_shared_path(self):
        out = rows(self.con, "precedents.sql", team_key="'g'")
        self.assertEqual(out[0]["past_team"], "a")
        self.assertEqual(out[0]["shared_count"], 2)                     # 밴드 디스커버리 + 클럽1
        self.assertIn("상상마당 밴드 디스커버리", out[0]["shared_list"])
        self.assertEqual(out[0]["outcome_label"], "한대음 신인")
        self.assertEqual(out[0]["months_signal_to_outcome"], 12)         # 2024-03 첫 신호 → 2025-03 정답
        self.assertEqual(out[0]["outcome_grade"], "S")

    def test_precedents_ignores_self_and_signals_after_outcome(self):
        keys = [r["past_team"] for r in rows(self.con, "precedents.sql", team_key="'a'")]
        self.assertNotIn("a", keys)
        self.assertNotIn("g", keys)                                     # g는 정답 없음

    def test_related_teams_by_shared_stage_and_agency(self):
        self.con.execute("ALTER TABLE teams ADD COLUMN agency VARCHAR")
        self.con.execute("UPDATE teams SET agency = '레이블X' WHERE team_key IN ('a', 'e')")
        out = rows(self.con, "related.sql", team_key="'a'")
        by = {(r["related_team"], r["relation"]): r for r in out}
        self.assertEqual(by[("b", "같은 무대")]["shared_count"], 1)
        self.assertIn("클럽1", by[("b", "같은 무대")]["detail"])
        self.assertIn(("e", "같은 소속사"), by)
        self.assertNotIn("a", [r["related_team"] for r in out])

    def test_source_scorecard_measures_all_sources_regardless_of_role(self):
        self.con.execute("UPDATE signals SET role = 'context' WHERE program = 'band_discovery'")
        out = {r["src"]: r for r in rows(self.con, "source_scorecard.sql", cutoffs="(DATE '2025-01-01')",
                                          since="'2024-01-01'", horizon_months="24")}
        bd = out["선정·지원:band_discovery"]
        self.assertEqual(bd["role"], "context")                  # 맥락 출처도 성적표에는 나옴
        self.assertEqual((bd["teams"], bd["hits"]), (1, 1))       # a: 2024-03 선정 → 2025-03 정답
        self.assertEqual(bd["winners_seen"], 1)

    def test_team_timeline_newest_first_with_labels(self):
        out = rows(self.con, "team.sql", team_key="'a'")
        self.assertEqual([str(r["signal_date"]) for r in out], ["2024-07-01", "2024-06-01", "2024-03-01"])
        self.assertEqual(out[-1]["program_label"], "상상마당 밴드 디스커버리")


if __name__ == "__main__":
    unittest.main()
