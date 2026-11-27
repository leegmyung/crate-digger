"""발굴 단계(docs/lab/sql/discovery_stage.sql)와 문서 생성(scripts/discovery_stage.py).

단계: 0 백지 → 1 첫 신호(남의 언급 1갈래) → 2 여러 갈래(2갈래+) → 3 선정·중간 정답(선정 단계 3+·B등급 정답) → 4 졸업(S·A 정답·유명).
기준일 시점 정보만 쓴다(기준일 뒤 신호·정답은 단계에 안 들어감). 단계 안 모멘텀 = 최근 90일 언급 수 대 그 전 90일, 같은 단계 안 백분위.
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

from lab_sql import fill, read_sql  # noqa: E402
import discovery_stage as ds  # noqa: E402

AS_OF = "2025-01-01"


def fixture(fame_from="2024-06-01"):
    con = duckdb.connect()
    con.execute(f"CREATE MACRO fame_known_from() AS DATE '{fame_from}'")
    con.execute("""
        CREATE TABLE teams(team_key VARCHAR, display_name VARCHAR, first_seen DATE, first_release DATE,
                           fan_count INTEGER, album_count INTEGER, profile_status VARCHAR, primary_genre VARCHAR);
        INSERT INTO teams VALUES
          ('blank','백지','2024-10-01','2024-10-01',NULL,NULL,'newcomer','록'),     -- 자기 발매만 → 0
          ('blank2','백지2','2025-03-01','2024-09-01',NULL,NULL,'newcomer',''),    -- 첫 발매만 알고 신호는 기준일 뒤 → 0
          ('one','하나','2024-06-01',NULL,NULL,NULL,'unknown',''),                -- 공연만 → 1
          ('two','둘','2024-05-01',NULL,NULL,NULL,'unknown',''),                  -- 공연+큐레이션 → 2
          ('sel','선정','2024-03-01',NULL,NULL,NULL,'unknown',''),                -- 선정 단계 3 → 3
          ('bgrade','비등급','2024-03-01',NULL,NULL,NULL,'unknown',''),           -- B등급 정답(기준일 전) → 3
          ('grad','졸업','2024-01-01',NULL,NULL,NULL,'unknown',''),               -- A등급 정답(기준일 전) → 4
          ('fam','유명','2024-04-01',NULL,NULL,NULL,'famous',''),                 -- 유명 → 4 (fame_known_from 이후 기준일만)
          ('later','나중','2024-06-01',NULL,NULL,NULL,'unknown',''),              -- 기준일 뒤 신호·정답은 단계에 안 들어감 → 1
          ('dmz','디엠지','2024-06-01',NULL,NULL,NULL,'unknown',''),              -- 제외 출처·DMZ 단계는 안 셈 → 1
          ('old','옛팀','2015-01-01',NULL,NULL,NULL,'unknown',''),                -- 신인 기준 밖 → 없음
          ('future','미래','2025-06-01',NULL,NULL,NULL,'unknown','');             -- 기준일에 아직 모름 → 없음
        CREATE TABLE signals(team_key VARCHAR, branch VARCHAR, source VARCHAR, program VARCHAR,
                             stage_rank INTEGER, signal_date DATE, venue VARCHAR, role VARCHAR);
        INSERT INTO signals VALUES
          ('blank','발매','melon','',NULL,'2024-10-01','','pending'),
          ('blank2','공연','indistreet','',NULL,'2025-03-01','클럽','discovery'),
          ('one','공연','indistreet','',NULL,'2024-06-01','클럽','discovery'),
          ('one','공연','indistreet','',NULL,'2024-12-01','클럽2','discovery'),
          ('one','공연','indistreet','',NULL,'2024-12-15','클럽3','discovery'),
          ('two','공연','indistreet','',NULL,'2024-05-01','클럽','discovery'),
          ('two','큐레이션','musicy','musicy',NULL,'2024-08-01','','context'),
          ('sel','선정·지원','x','band_discovery',3,'2024-03-01','','discovery'),
          ('bgrade','공연','indistreet','',NULL,'2024-03-01','클럽','discovery'),
          ('grad','공연','indistreet','',NULL,'2024-01-01','클럽','discovery'),
          ('fam','공연','indistreet','',NULL,'2024-04-01','클럽','discovery'),
          ('later','공연','indistreet','',NULL,'2024-06-01','클럽','discovery'),
          ('later','선정·지원','x','band_discovery',4,'2025-02-01','','discovery'),
          ('later','큐레이션','musicy','musicy',NULL,'2025-02-01','','discovery'),
          ('dmz','공연','indistreet','',NULL,'2024-06-01','클럽','discovery'),
          ('dmz','선정·지원','x','dmz_lineup',3,'2024-07-01','','excluded'),
          ('dmz','선정·지원','x','dmz_lineup',3,'2024-07-01','','discovery'),
          ('old','공연','indistreet','',NULL,'2015-01-01','클럽','discovery'),
          ('future','공연','indistreet','',NULL,'2025-06-01','클럽','discovery');
        CREATE TABLE outcomes(team_key VARCHAR, program VARCHAR, program_label VARCHAR, tier VARCHAR,
                              announced_date DATE, counted BOOLEAN, grade VARCHAR, weight INTEGER,
                              same_house_scored BOOLEAN);
        INSERT INTO outcomes VALUES
          ('bgrade','burock_main','부산록페 본무대','mid','2024-09-01',true,'B',1,false),
          ('bgrade','kma_rookie','한대음 신인','final','2025-03-01',true,'S',3,false),   -- 이후 S → hit_sa
          ('grad','museon_final','뮤즈온','mid','2024-08-01',true,'A',2,false),
          ('later','kma_rookie','한대음 신인','final','2025-04-01',true,'S',3,false),
          ('one','hello_monthly','헬로루키 월간','mid','2025-05-01',true,'B',1,false),     -- 이후 B → hit 이지만 hit_sa 아님
          ('two','kha_rookie','한국힙합어워즈 신인','final','2025-05-01',true,'S',3,true),  -- 같은 집안 → 적중 아님
          ('sel','kma_rookie','한대음 신인','final','2025-06-01',false,'S',3,false),       -- 센 정답 아님 → 적중 아님
          ('blank','kma_rookie','한대음 신인','final','2028-01-01',true,'S',3,false);      -- 관찰 기간 밖
    """)
    return con


def run(con, as_of=AS_OF, **params):
    sql = fill(read_sql("discovery_stage.sql"), as_of=f"'{as_of}'", **params)
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    return {r[cols.index("team_key")]: dict(zip(cols, r)) for r in cur.fetchall()}


@unittest.skipIf(duckdb is None, "duckdb 없음")
class DiscoveryStageSqlTest(unittest.TestCase):
    def setUp(self):
        self.out = run(fixture())

    def test_stage_of_each_team(self):
        want = {"blank": 0, "blank2": 0, "one": 1, "two": 2, "sel": 3, "bgrade": 3, "grad": 4, "fam": 4,
                "later": 1, "dmz": 1}
        self.assertEqual({k: v["stage"] for k, v in self.out.items()}, want)

    def test_non_newcomer_and_unknown_teams_are_left_out(self):
        self.assertNotIn("old", self.out)
        self.assertNotIn("future", self.out)

    def test_stage_labels(self):
        self.assertEqual(self.out["blank"]["stage_label"], "백지")
        self.assertEqual(self.out["grad"]["stage_label"], "졸업")

    def test_famous_only_from_fame_known_from(self):
        # 유명 판정(지금 팬 수)은 그보다 이른 기준일엔 쓰지 않는다 → 공연 1갈래라 1단계
        out = run(fixture(fame_from="2026-11-26"))
        self.assertEqual(out["fam"]["stage"], 1)

    def test_future_signals_and_outcomes_do_not_leak_into_stage(self):
        self.assertEqual(self.out["later"]["stage"], 1)
        self.assertEqual(self.out["later"]["n_mention_branches"], 1)

    def test_hit_flags_after_as_of(self):
        o = self.out
        self.assertEqual((o["later"]["is_hit"], o["later"]["hit_sa"]), (1, 1))
        self.assertEqual((o["one"]["is_hit"], o["one"]["hit_sa"]), (1, 0))
        self.assertEqual((o["bgrade"]["is_hit"], o["bgrade"]["hit_sa"]), (1, 1))
        self.assertEqual(o["two"]["is_hit"], 0)      # 같은 집안 정답
        self.assertEqual(o["sel"]["is_hit"], 0)      # 센 정답 아님
        self.assertEqual(o["blank"]["is_hit"], 0)    # 관찰 기간 밖

    def test_momentum_counts_recent_vs_previous_90_days(self):
        one = self.out["one"]
        self.assertEqual((one["recent_n"], one["prev_n"]), (2, 0))   # 12-01·12-15 최근, 06-01은 180일 밖
        two = self.out["two"]
        self.assertEqual((two["recent_n"], two["prev_n"]), (0, 1))   # 08-01은 그 전 90일
        self.assertGreater(one["momentum"], 0)
        self.assertLess(two["momentum"], 0)

    def test_momentum_percentile_is_within_stage(self):
        # 1단계: one(상승)·later·dmz(보합) → one 이 단계 안 1등(백분위 1.0)
        self.assertEqual(self.out["one"]["momentum_pct"], 1.0)
        # 2단계는 two 한 팀뿐 → 비교 상대가 없어도 값은 있음(0)
        self.assertIsNotNone(self.out["two"]["momentum_pct"])

    def test_blank_has_no_momentum(self):
        self.assertIsNone(self.out["blank"]["momentum_pct"])
        self.assertEqual(self.out["blank"]["momentum_label"], "—")

    def test_momentum_label(self):
        self.assertEqual(self.out["one"]["momentum_label"], "상승")
        self.assertEqual(self.out["two"]["momentum_label"], "하락")
        self.assertEqual(self.out["dmz"]["momentum_label"], "보합")


class SummaryTest(unittest.TestCase):
    def rows(self):
        base = [
            {"stage": 1, "is_hit": 1, "hit_sa": 0, "momentum_pct": 0.9, "momentum": 0.5},
            {"stage": 1, "is_hit": 0, "hit_sa": 0, "momentum_pct": 0.1, "momentum": 0.0},
            {"stage": 1, "is_hit": 0, "hit_sa": 0, "momentum_pct": 0.5, "momentum": -0.2},
            {"stage": 3, "is_hit": 1, "hit_sa": 1, "momentum_pct": 0.0, "momentum": 0.0},
            {"stage": 0, "is_hit": 0, "hit_sa": 0, "momentum_pct": None, "momentum": None},
        ]
        return [{**r, "team_key": f"t{i}", "display_name": f"팀{i}", "recent_n": 1, "prev_n": 0,
                 "first_release": None} for i, r in enumerate(base)]

    def test_profile_only_keeps_teams_with_first_release(self):
        rows = [{"first_release": None}, {"first_release": "2024-01-01"}]
        self.assertEqual(len(ds.profile_only(rows)), 1)

    def test_stage_summary_counts_and_rates(self):
        s = {r["stage"]: r for r in ds.stage_summary(self.rows())}
        self.assertEqual((s[1]["teams"], s[1]["hits"], s[1]["hits_sa"]), (3, 1, 0))
        self.assertAlmostEqual(s[1]["rate"], 100 / 3)
        self.assertEqual(s[3]["rate"], 100.0)
        self.assertEqual(s[2]["teams"], 0)            # 빈 단계도 줄은 남는다
        self.assertIsNone(s[2]["rate"])

    def test_momentum_split_top_vs_rest(self):
        top, rest = ds.momentum_split([r for r in self.rows() if r["stage"] == 1], top_share=0.2)
        self.assertEqual((top["teams"], top["hits"]), (1, 1))
        self.assertEqual((rest["teams"], rest["hits"]), (2, 0))

    def test_direction_split(self):
        d = ds.direction_split([r for r in self.rows() if r["stage"] == 1])
        self.assertEqual({k: v["teams"] for k, v in d.items()}, {"상승": 1, "보합": 1, "하락": 1})

    def test_wilson_interval(self):
        lo, hi = ds.wilson(1, 10)
        self.assertLess(lo, 10.0)
        self.assertGreater(hi, 10.0)
        self.assertEqual(ds.wilson(0, 0), (None, None))

    def test_rising_and_overlap_helpers(self):
        self.assertTrue(ds._rising([0.5, 4.0, 5.0]))
        self.assertFalse(ds._rising([0.5, 6.0, 5.0]))
        self.assertFalse(ds._rising([0.5, None]))
        self.assertTrue(ds._overlap({"lo": 1, "hi": 5}, {"lo": 4, "hi": 9}))
        self.assertFalse(ds._overlap({"lo": 1, "hi": 3}, {"lo": 4, "hi": 9}))

    def test_key_findings_wording_follows_numbers(self):
        # 단계가 올라갈수록 정답률이 떨어지는 데이터면 '가릅니다'라고 쓰지 않는다
        rows = ([{"stage": 1, "is_hit": 1, "hit_sa": 1, "momentum": 0.0, "momentum_pct": 0.0, "first_release": None}] * 2
                + [{"stage": 2, "is_hit": 0, "hit_sa": 0, "momentum": 0.0, "momentum_pct": 0.0, "first_release": None}] * 2
                + [{"stage": 3, "is_hit": 0, "hit_sa": 0, "momentum": 0.0, "momentum_pct": 0.0, "first_release": None}] * 2)
        text = "\n".join(ds.key_findings(rows))
        self.assertIn("딱 맞지는 않습니다", text)
        self.assertNotIn("단계는 다음 정답을 가릅니다", text)

    def test_auc_of_stage(self):
        # 단계가 높을수록 정답이면 1.0
        rows = [{"stage": 1, "is_hit": 0}, {"stage": 2, "is_hit": 0}, {"stage": 3, "is_hit": 1}]
        self.assertEqual(ds.stage_auc(rows), 1.0)

    def test_markdown_has_tables(self):
        per_cut = {"2025-01-01": self.rows()}
        lines = ds.render(per_cut, today_rows=self.rows(), today="2026-11-27")
        text = "\n".join(lines)
        self.assertIn("| 단계 |", text)
        self.assertIn("첫 신호", text)
        self.assertIn("2026-11-27", text)


if __name__ == "__main__":
    unittest.main()
