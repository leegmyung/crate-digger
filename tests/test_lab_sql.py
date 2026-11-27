"""docs/lab/sql/*.sql을 로컬 DuckDB로 돌려 본다 (브라우저의 DuckDB-WASM과 같은 문법).
duckdb가 없으면 건너뛴다: .venv/bin/pip install duckdb 후 .venv/bin/python -m unittest tests.test_lab_sql
"""
import sys
import unittest
from pathlib import Path

try:
    import duckdb
except ImportError:  # 시스템 파이썬에는 없을 수 있음
    duckdb = None

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from lab_sql import DEFAULTS, SQL_DIR, fill  # noqa: E402


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
    con.execute((SQL_DIR / "features.sql").read_text(encoding="utf-8"))
    return con


def rows(con, name, **params):
    cur = con.execute(fill((SQL_DIR / name).read_text(encoding="utf-8"), **params))
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


@unittest.skipIf(duckdb is None, "duckdb 없음")
class LabSqlTest(unittest.TestCase):
    def setUp(self):
        self.con = fixture_db()

    def scored(self, cutoff="2025-01-01", **p):
        q = ("SELECT * FROM lab_scored(DATE '{c}', {lookback_years}, {newcomer_years}, {exclude_famous}, "
             "{outcome_tier}, {horizon_months}, {genre}, {branches}, {w_branch}, {w_stage}, {w_peer}, {w_dmz}, "
             "{w_gigs}, {w_outlets}, {outlet_cap}) ORDER BY team_key")
        args = {**DEFAULTS, **p}
        cur = self.con.execute(q.format(c=cutoff, **args))
        cols = [d[0] for d in cur.description]
        return {r[0]: dict(zip(cols, r)) for r in cur.fetchall()}

    def test_famous_and_old_teams_are_excluded_from_pool(self):
        pool = self.scored()
        self.assertNotIn("c", pool)       # 유명
        self.assertNotIn("d", pool)       # 2010년 첫 등장 → 신인 아님
        self.assertIn("c", self.scored(exclude_famous="false"))

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

    def test_precedents_ignores_self_and_signals_after_outcome(self):
        keys = [r["past_team"] for r in rows(self.con, "precedents.sql", team_key="'a'")]
        self.assertNotIn("a", keys)
        self.assertNotIn("g", keys)                                     # g는 정답 없음

    def test_team_timeline_newest_first_with_labels(self):
        out = rows(self.con, "team.sql", team_key="'a'")
        self.assertEqual([str(r["signal_date"]) for r in out], ["2024-07-01", "2024-06-01", "2024-03-01"])
        self.assertEqual(out[-1]["program_label"], "상상마당 밴드 디스커버리")


if __name__ == "__main__":
    unittest.main()
