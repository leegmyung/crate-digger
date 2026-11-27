"""genre_bias: 장르별로 점수 v2가 체계적으로 올리거나 내리는지 (후보·정답·기준율·AUC·상위 100 쏠림)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import genre_bias as gb  # noqa: E402


def _r(key, genre, score, hit=0, weight=0):
    return {"team_key": key, "genre": genre, "score": score, "is_hit": hit, "hit_weight": weight}


class LabelTest(unittest.TestCase):
    def test_blank_genre_is_unclassified(self):
        for v in (None, "", "  "):
            self.assertEqual(gb.genre_label(v), "미분류")
        self.assertEqual(gb.genre_label("힙합"), "힙합")

    def test_bias_index(self):
        self.assertAlmostEqual(gb.bias_index(0.2, 0.1), 2.0)
        self.assertIsNone(gb.bias_index(0.2, 0))


class AnalysisGenreTest(unittest.TestCase):
    """비교·분석은 profile·press 장르만 — 추정(inferred) 장르는 '미분류'로 (2026-11-27 결정, docs/genre_fill.md)."""

    def test_inferred_is_unclassified(self):
        self.assertEqual(gb.analysis_genre("힙합", "inferred"), "미분류")
        self.assertEqual(gb.analysis_genre("록·밴드", "inferred_low"), "미분류")
        self.assertEqual(gb.analysis_genre("힙합", "profile"), "힙합")
        self.assertEqual(gb.analysis_genre("록·밴드", "press"), "록·밴드")
        self.assertEqual(gb.analysis_genre("록·밴드", None), "록·밴드")    # 확신도 칸이 없는 옛 CSV
        self.assertEqual(gb.analysis_genre("", ""), "미분류")

    def test_team_genres_skip_inferred(self):
        try:
            import duckdb
        except ImportError:
            self.skipTest("duckdb 없음")
        con = duckdb.connect()
        con.execute("CREATE TABLE teams(team_key VARCHAR, primary_genre VARCHAR, genre_confidence VARCHAR)")
        con.execute("INSERT INTO teams VALUES ('a','힙합','profile'), ('b','힙합·R&B','inferred'), ('c','',''), ('d','록·밴드','press')")
        self.assertEqual(gb.team_genres(con), {"a": "힙합", "b": "미분류", "c": "미분류", "d": "록·밴드"})


class TopTest(unittest.TestCase):
    def test_top_indices_tie_break_like_app(self):
        # 앱 순서: 마지막 신호 없으면 md5(team_key) 순 (md5('c') < md5('b'))
        self.assertEqual(gb.top_indices([5, 4, 4, 1], ["d", "c", "b", "a"], 2), [0, 1])
        # 마지막 신호가 더 최근인 b 가 먼저
        seen = ["2020-01-01", "2023-01-01", "2025-01-01", "2020-01-01"]
        self.assertEqual(gb.top_indices([5, 4, 4, 1], ["d", "c", "b", "a"], 2, seen), [0, 2])


class GenreTableTest(unittest.TestCase):
    def setUp(self):
        # 기준일 2개. 록은 위, 힙합은 아래에 몰림
        self.data = {
            "A": [_r("r1", "록", 9, 1, 3), _r("r2", "록", 8), _r("h1", "힙합", 1, 1, 1), _r("h2", "힙합", 0),
                  _r("u1", "미분류", 5)],
            "B": [_r("r3", "록", 7), _r("h3", "힙합", 2), _r("u2", "미분류", 6, 1, 2), _r("u3", "미분류", 3)],
        }

    def test_counts_shares_and_bias(self):
        rows = {t["genre"]: t for t in gb.genre_table(self.data, top_n=2, min_pos=1)}
        rock = rows["록"]
        self.assertEqual((rock["n"], rock["pos"]), (3, 1))
        self.assertAlmostEqual(rock["pool_share"], 3 / 9)
        self.assertAlmostEqual(rock["top_share"], 3 / 4)       # 상위2 × 기준일2 = 4자리 중 록 3 (A: r1·r2, B: r3)
        self.assertAlmostEqual(rock["bias"], (3 / 4) / (3 / 9))
        self.assertEqual(rows["힙합"]["top_count"], 0)
        self.assertEqual(rows["힙합"]["top_hits"], 0)          # 힙합 정답은 상위에 못 들어옴
        self.assertEqual(rows["록"]["top_hits"], 1)
        self.assertAlmostEqual(rows["록"]["top_recall"], 1.0)  # 록 정답 1행 모두 상위 안
        self.assertAlmostEqual(rows["힙합"]["top_recall"], 0.0)

    def test_auc_marked_small_sample(self):
        rows = {t["genre"]: t for t in gb.genre_table(self.data, top_n=2, min_pos=5)}
        self.assertIsNone(rows["록"]["auc"])
        self.assertTrue(rows["록"]["small"])
        overall = gb.overall_row(self.data, top_n=2)
        self.assertEqual(overall["pos"], 3)
        self.assertIsNotNone(overall["auc"])


class CompositionTest(unittest.TestCase):
    def test_current_top_composition(self):
        rows = [_r("a", "록", 5), _r("b", "록", 4), _r("c", "힙합", 3), _r("d", "미분류", 2)]
        comp = {c["genre"]: c for c in gb.composition(rows, top_n=2)}
        self.assertEqual(comp["록"]["top_count"], 2)
        self.assertAlmostEqual(comp["록"]["top_share"], 1.0)
        self.assertAlmostEqual(comp["록"]["pool_share"], 0.5)
        self.assertEqual(comp["힙합"]["top_count"], 0)

    def test_source_shares(self):
        team_sources = {"a": {"indistreet"}, "b": {"indistreet", "izm"}, "c": {"izm"}}
        team_genre = {"a": "록", "b": "록", "c": "힙합"}
        sh = gb.source_shares(team_sources, team_genre)
        self.assertAlmostEqual(sh["록"]["indistreet"], 1.0)
        self.assertAlmostEqual(sh["록"]["izm"], 0.5)
        self.assertAlmostEqual(sh["힙합"]["izm"], 1.0)
        self.assertNotIn("indistreet", sh["힙합"])

    def test_profile_missing_share(self):
        rows = [{"genre": "힙합", "profile_status": "unknown"}, {"genre": "힙합", "profile_status": "newcomer"},
                {"genre": "록", "profile_status": "newcomer"}]
        self.assertEqual(gb.profile_missing_share(rows), {"힙합": 0.5, "록": 0.0})

    def test_within_genre_rank(self):
        rows = [_r("a", "록", 5), _r("b", "힙합", 4), _r("c", "록", 3), _r("d", "힙합", 1)]
        ranks = gb.within_genre_ranks(rows)
        self.assertEqual(ranks, {"a": (1, 1), "b": (2, 1), "c": (3, 2), "d": (4, 2)})   # (전체 순위, 장르 내 순위)


class GenreScorecardTest(unittest.TestCase):
    def setUp(self):
        self.signals = [
            {"team_key": "h1", "source": "큐레이션:rhythmer", "signal_date": "2024-01-01"},
            {"team_key": "h1", "source": "공연:indistreet", "signal_date": "2024-03-01"},
            {"team_key": "h2", "source": "큐레이션:musicy", "signal_date": "2024-05-01"},
            {"team_key": "h2", "source": "큐레이션:rhythmer", "signal_date": "2024-05-01"},   # 같은 날 = 둘 다 '가장 먼저'
            {"team_key": "h3", "source": "큐레이션:izm", "signal_date": "2025-06-01"},        # 정답 뒤 → 안 셈
            {"team_key": "r1", "source": "공연:indistreet", "signal_date": "2024-01-01"},
        ]
        self.outcomes = [{"team_key": k, "announced_date": "2025-01-01", "grade": "A"} for k in ("h1", "h2", "h3", "r1")]
        self.genre = {"h1": "힙합", "h2": "힙합", "h3": "힙합", "r1": "R&B·소울"}

    def test_winner_sources_first_only_and_unseen(self):
        res = gb.winner_sources(self.signals, self.outcomes, self.genre, "힙합")
        self.assertEqual(res["winners"], 3)
        self.assertEqual(res["unseen"], 1)                                   # h3: 정답 전 신호 없음
        rows = {r["source"]: r for r in res["sources"]}
        self.assertEqual((rows["큐레이션:rhythmer"]["seen"], rows["큐레이션:rhythmer"]["first"]), (2, 2))
        self.assertEqual((rows["공연:indistreet"]["seen"], rows["공연:indistreet"]["first"]), (1, 0))
        self.assertEqual(rows["큐레이션:musicy"]["only"], 0)
        self.assertEqual(res["teams"][0]["team_key"], "h1")
        self.assertEqual(res["teams"][2]["sources"], [])

    def test_genre_source_hits(self):
        by_cutoff = {"A": [{"team_key": "h1", "is_hit": 1}, {"team_key": "h2", "is_hit": 0}, {"team_key": "x", "is_hit": 0}]}
        team_src = {"A": {"h1": {"큐레이션:rhythmer"}, "h2": {"큐레이션:rhythmer", "공연:indistreet"}}}
        genre = {"h1": "힙합", "h2": "힙합", "x": "록·밴드"}
        hits = gb.genre_source_hits(by_cutoff, team_src, genre)
        self.assertEqual(hits[("힙합", "큐레이션:rhythmer")], (2, 1))
        self.assertEqual(hits[("힙합", "공연:indistreet")], (1, 0))
        self.assertNotIn(("록·밴드", "공연:indistreet"), hits)


if __name__ == "__main__":
    unittest.main()
