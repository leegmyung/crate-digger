"""데뷔 코호트 성적표(docs/lab/sql/source_scorecard_debut.sql): 과거 이력 없는 '백지 신인'을 출처가 첫 발매 뒤
N개월 안에 언급했나 → 기준일 뒤 정답을 받았나. scripts/lab_sql.py 의 fill() 로 채워 DuckDB 로 실행한다."""
import sys
import unittest
from pathlib import Path

try:
    import duckdb
except ImportError:  # 시스템 파이썬에는 없을 수 있음
    duckdb = None

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from lab_sql import fill, read_sql  # noqa: E402


def fixture(fame_from="2024-01-01"):
    """fame_from = 유명 판정(지금 팬 수)을 쓸 수 있는 가장 이른 기준일 (features.sql 의 fame_known_from 매크로 흉내)."""
    con = duckdb.connect()
    con.execute(f"CREATE MACRO fame_known_from() AS DATE '{fame_from}'")
    con.execute("""
        CREATE TABLE teams(team_key VARCHAR, display_name VARCHAR, first_seen DATE, first_release DATE,
                           fan_count INTEGER, album_count INTEGER, profile_status VARCHAR, primary_genre VARCHAR);
        INSERT INTO teams VALUES
          ('new1','뉴1','2024-03-01','2024-02-01',NULL,NULL,'newcomer',''),   -- 백지: 첫 발매 뒤 언급, 정답
          ('new2','뉴2','2024-05-01','2024-03-01',NULL,NULL,'newcomer',''),   -- 백지: 두 출처가 언급, 정답 없음
          ('new3','뉴3','2024-02-01','2024-02-01',NULL,NULL,'newcomer',''),   -- 백지: 언급 없음, 정답
          ('old1','올드','2023-01-01','2024-02-01',NULL,NULL,'newcomer',''),  -- 첫 발매 전 신호 있음 → 백지 아님
          ('late','늦게','2024-11-01','2024-10-01',NULL,NULL,'newcomer',''),  -- 언급 창이 기준일을 넘김 → 코호트 아님
          ('fam','유명','2024-03-01','2024-02-01',NULL,NULL,'famous',''),     -- 유명 팀 제외
          ('win','먼저','2024-03-01','2024-02-01',NULL,NULL,'newcomer','');   -- 기준일 전에 이미 정답 → 제외
        CREATE TABLE signals(team_key VARCHAR, branch VARCHAR, source VARCHAR, program VARCHAR,
                             stage_rank INTEGER, signal_date DATE, venue VARCHAR, role VARCHAR);
        INSERT INTO signals VALUES
          ('new1','큐레이션','musicy','음악취향Y',NULL,'2024-03-01','','discovery'),   -- 첫 발매 29일 뒤
          ('new1','공연','indistreet','',NULL,'2024-12-01','클럽','discovery'),        -- 6개월 창 밖 → 안 셈
          ('new2','큐레이션','musicy','음악취향Y',NULL,'2024-05-01','','discovery'),
          ('new2','공연','indistreet','',NULL,'2024-04-01','클럽','discovery'),
          ('old1','공연','indistreet','',NULL,'2023-01-01','클럽','discovery'),
          ('old1','큐레이션','musicy','음악취향Y',NULL,'2024-03-01','','discovery'),
          ('late','큐레이션','musicy','음악취향Y',NULL,'2024-11-01','','discovery'),
          ('fam','큐레이션','musicy','음악취향Y',NULL,'2024-03-01','','discovery'),
          ('win','큐레이션','musicy','음악취향Y',NULL,'2024-03-01','','discovery');
        CREATE TABLE outcomes(team_key VARCHAR, program VARCHAR, program_label VARCHAR, tier VARCHAR,
                              announced_date DATE, counted BOOLEAN, grade VARCHAR, weight INTEGER);
        INSERT INTO outcomes VALUES
          ('new1','kma_rookie','한대음 신인','final','2025-03-01',true,'S',3),
          ('new3','museon_final','뮤즈온','mid','2025-05-01',true,'A',2),
          ('old1','kma_rookie','한대음 신인','final','2025-03-01',true,'S',3),
          ('win','kma_rookie','한대음 신인','final','2024-10-01',true,'S',3);
    """)
    return con


def run(con, **params):
    p = {"cutoffs": "(DATE '2025-01-01')", "horizon_months": "24", "mention_months": "6", **params}
    cur = con.execute(fill(read_sql("source_scorecard_debut.sql"), **p))
    cols = [d[0] for d in cur.description]
    return {r[0]: dict(zip(cols, r)) for r in cur.fetchall()}


@unittest.skipIf(duckdb is None, "duckdb 없음")
class DebutScorecardTest(unittest.TestCase):
    def setUp(self):
        self.con = fixture()

    def test_famous_not_excluded_before_fame_known_from(self):
        # 유명 판정은 지금 팬 수라 그보다 이른 기준일에는 쓰지 않는다 → 'fam' 이 코호트에 들어옴
        out = run(fixture(fame_from="2026-11-26"))
        self.assertEqual(next(iter(out.values()))["cohort_teams"], 4)
        self.assertEqual(out["큐레이션:musicy"]["teams"], 3)

    def test_cohort_is_blank_slate_debuts_with_window_before_cutoff(self):
        # 6개월 창: 코호트 = 첫 발매가 기준일 12~6개월 전 (2024-01-01 ~ 2024-07-01) → 언급 창이 기준일 전에 끝남
        out = run(self.con)
        any_row = next(iter(out.values()))
        self.assertEqual(any_row["cohort_teams"], 3)             # new1·new2·new3 (old1·late·fam·win 빠짐)
        self.assertEqual(any_row["cohort_hits"], 2)              # new1·new3
        self.assertAlmostEqual(float(any_row["base_rate"]), 66.67, places=2)

    def test_per_source_mentions_hits_and_days(self):
        out = run(self.con)
        m = out["큐레이션:musicy"]
        self.assertEqual((m["teams"], m["hits"]), (2, 1))       # new1(정답)·new2
        self.assertEqual(int(m["median_days"]), (29 + 61) // 2)  # 2024-02-01→03-01 29일, 03-01→05-01 61일
        self.assertEqual(m["first_mention"], 1)                  # new1 은 음악취향Y가 처음, new2 는 공연이 먼저
        g = out["공연:indistreet"]
        self.assertEqual((g["teams"], g["hits"], g["first_mention"]), (1, 0, 1))   # new1 공연은 창 밖
        self.assertEqual(g["role"], "discovery")

    def test_unmentioned_row(self):
        none = run(self.con)["(언급 없음)"]
        self.assertEqual((none["teams"], none["hits"]), (1, 1))  # new3

    def test_longer_window_counts_later_mentions(self):
        # 12개월 창: 코호트 = 첫 발매가 기준일 18~12개월 전 → 2025-03-01 기준이면 2023-09-01 ~ 2024-03-01 (new1·new3)
        out = run(self.con, mention_months="12", cutoffs="(DATE '2025-03-01')")
        g = out["공연:indistreet"]
        self.assertEqual((g["teams"], g["hits"]), (1, 1))        # new1 의 2024-12 공연이 12개월 창 안 (6개월이면 밖)

    def test_multiple_cutoffs_sum(self):
        out = run(self.con, cutoffs="(DATE '2025-01-01'), (DATE '2025-07-01')")
        self.assertEqual(next(iter(out.values()))["cohort_teams"], 3 + 1)   # 2025-07 기준: late(2024-10 첫 발매)


class DebutDocTest(unittest.TestCase):
    def test_cutoffs_sql_and_small_sample_mark(self):
        import debut_cohort as dc
        self.assertEqual(dc.cutoffs_sql(["2025-01-01", "2025-07-01"]), "(DATE '2025-01-01'), (DATE '2025-07-01')")
        rows = [{"src": "공연:indistreet", "role": "discovery", "teams": 2, "hits": 1, "rate": 50.0, "lift": 1.8,
                 "median_days": 30.0, "first_mention": 2},
                {"src": "(언급 없음)", "role": None, "teams": 3, "hits": 0, "rate": 0.0, "lift": 0.0,
                 "median_days": None, "first_mention": None}]
        table = dc.source_table(rows)
        self.assertIn("표본 부족", table[2])                       # 5팀 미만 출처
        self.assertNotIn("표본 부족", table[3])                    # '언급 없음' 줄에는 안 붙임
        self.assertEqual(dc.cohort_line([]), {"n": 0, "hits": 0, "base": 0.0})
