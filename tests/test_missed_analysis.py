"""missed_analysis: 2025년 이후 정답 팀이 정답 6·12개월 전에 v2 상위 100 안에 있었나, 놓쳤으면 왜."""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import missed_analysis as ma  # noqa: E402


class DateTest(unittest.TestCase):
    def test_minus_months(self):
        self.assertEqual(ma.minus_months(date(2025, 2, 27), 6), date(2024, 8, 27))
        self.assertEqual(ma.minus_months(date(2025, 3, 31), 1), date(2025, 2, 28))   # 말일 보정
        self.assertEqual(ma.minus_months(date(2025, 1, 15), 12), date(2024, 1, 15))


class RankTest(unittest.TestCase):
    def test_rank_ties_like_app(self):
        rows = [{"team_key": "b", "score": 3}, {"team_key": "a", "score": 3}, {"team_key": "c", "score": 5}]
        self.assertEqual(ma.ranks(rows), {"c": 1, "a": 2, "b": 3})          # md5('a') < md5('b')
        rows[0]["last_seen"], rows[1]["last_seen"] = "2025-01-01", "2024-01-01"
        self.assertEqual(ma.ranks(rows), {"c": 1, "b": 2, "a": 3})          # 마지막 신호 최근 순이 먼저


class TeamInfoGenreTest(unittest.TestCase):
    def test_inferred_genre_is_unclassified(self):
        import duckdb
        con = duckdb.connect()
        con.execute("CREATE MACRO fame_known_from() AS DATE '2026-11-26'")
        con.execute("CREATE TABLE outcomes(team_key VARCHAR, counted BOOLEAN, announced_date DATE)")
        con.execute("CREATE TABLE signals(team_key VARCHAR, signal_date DATE, role VARCHAR)")
        con.execute("CREATE TABLE teams(team_key VARCHAR, profile_status VARCHAR, first_release DATE, first_seen DATE, "
                    "primary_genre VARCHAR, genre_confidence VARCHAR, display_name VARCHAR)")
        con.execute("INSERT INTO teams VALUES ('a','unknown',NULL,'2024-01-01','힙합','inferred','A'), "
                    "('b','unknown',NULL,'2024-01-01','힙합','profile','B'), "
                    "('c','unknown',NULL,'2024-01-01','록·밴드','review','C'), "
                    "('d','unknown',NULL,'2024-01-01','록·밴드','inferred_low','D')")
        self.assertEqual(ma.team_info(con, "a", date(2025, 1, 1))["genre"], "미분류")
        self.assertEqual(ma.team_info(con, "b", date(2025, 1, 1))["genre"], "힙합")
        self.assertEqual(ma.team_info(con, "c", date(2025, 1, 1))["genre"], "미분류")   # 리뷰 장르
        self.assertEqual(ma.team_info(con, "d", date(2025, 1, 1))["genre"], "미분류")   # 같은 무대 1표


class ClassifyTest(unittest.TestCase):
    def base(self, **kw):
        info = {"in_pool": False, "rank": None, "prior_outcome": False, "famous": False, "too_old": False,
                "signals_window": 0, "signals_older": 0, "scored_signals": 0}
        return {**info, **kw}

    def test_caught_and_low_rank(self):
        self.assertEqual(ma.classify(self.base(in_pool=True, rank=12), top=100), "caught")
        self.assertEqual(ma.classify(self.base(in_pool=True, rank=480), top=100), "e_low_rank")

    def test_order_of_reasons(self):
        self.assertEqual(ma.classify(self.base(prior_outcome=True, famous=True), 100), "f_prior_outcome")
        self.assertEqual(ma.classify(self.base(famous=True, too_old=True, signals_window=3), 100), "d_famous")
        self.assertEqual(ma.classify(self.base(too_old=True, signals_window=3), 100), "c_newcomer_rule")
        self.assertEqual(ma.classify(self.base(), 100), "a_no_signal")
        self.assertEqual(ma.classify(self.base(signals_older=2), 100), "a_no_signal")      # 3년 창 밖 신호만
        self.assertEqual(ma.classify(self.base(signals_window=2, scored_signals=0), 100), "b_unscored_sources")


class NoSignalKindTest(unittest.TestCase):
    def test_late_vs_absent(self):
        self.assertEqual(ma.no_signal_kind({"signals_before_outcome": 3}), "late")       # 기준일 뒤·정답 전에야 처음 나옴
        self.assertEqual(ma.no_signal_kind({"signals_before_outcome": 0}), "absent")     # 정답 전엔 어디에도 없음


class WeakFeatureTest(unittest.TestCase):
    def test_features_common_in_top_but_missing(self):
        top = [{"best_stage": 2, "venues": 3, "outlets": 0}, {"best_stage": 1, "venues": 2, "outlets": 1},
               {"best_stage": 0, "venues": 4, "outlets": 0}]
        team = {"best_stage": 0, "venues": 0, "outlets": 0}
        self.assertEqual(ma.weak_features(team, top, ("best_stage", "venues", "outlets")), ["venues", "best_stage"])


class SummaryTest(unittest.TestCase):
    def test_counts_and_source_gain(self):
        res = [
            {"team_key": "a", "horizon": 6, "reason": "caught", "genre": "록·밴드"},
            {"team_key": "b", "horizon": 6, "reason": "b_unscored_sources", "genre": "힙합",
             "what_if": {"큐레이션:hiphople": 40, "공연:instagram": 300}},
            {"team_key": "c", "horizon": 6, "reason": "b_unscored_sources", "genre": "힙합",
             "what_if": {"큐레이션:hiphople": 150}},
            {"team_key": "d", "horizon": 12, "reason": "a_no_signal", "genre": "미분류"},
        ]
        counts = ma.reason_counts(res, 6)
        self.assertEqual(counts, {"caught": 1, "b_unscored_sources": 2})
        gain = ma.source_gain(res, 6, top=100)
        self.assertEqual(gain[0], ("큐레이션:hiphople", 1, 2))           # (출처, 상위100에 들어올 팀, 그 출처에 있던 놓친 팀)
        self.assertEqual(dict((s, g) for s, g, _ in gain)["공연:instagram"], 0)


if __name__ == "__main__":
    unittest.main()


class GenreKnownShareTest(unittest.TestCase):
    """확인된 장르 = 사후 수집 편향: 우리 데이터에 없던 수상 팀은 프로필을 덜 받아 '미분류'가 많다 (docs/methods.md)."""

    def test_share_of_known_genre_by_reason(self):
        rs = [{"horizon": 6, "reason": "a_no_signal", "genre": "미분류"},
              {"horizon": 6, "reason": "a_no_signal", "genre": "록·밴드"},
              {"horizon": 6, "reason": "hit", "genre": "포크"},
              {"horizon": 6, "reason": "b_low_score", "genre": "미분류"},
              {"horizon": 12, "reason": "a_no_signal", "genre": "힙합"}]
        got = ma.genre_known_share(rs, 6)
        self.assertEqual(got, {"no_signal": (1, 2), "others": (1, 2)})

    def test_caveat_line_mentions_profile_gap(self):
        line = ma.genre_caveat_line({"no_signal": (5, 10), "others": (36, 50)})
        self.assertIn("50%", line)
        self.assertIn("72%", line)
        self.assertIn("프로필", line)
        self.assertEqual(ma.genre_caveat_line({"no_signal": (0, 0), "others": (0, 0)}), "")


class GenreDisplayTest(unittest.TestCase):
    def test_unclassified_shown_as_profile_not_collected(self):
        self.assertEqual(ma.genre_display("미분류"), "프로필 미수집")
        self.assertEqual(ma.genre_display("록·밴드"), "록·밴드")
