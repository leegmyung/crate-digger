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
        self.assertEqual(gb.analysis_genre("포크·싱어송라이터", "review"), "미분류")   # 리뷰 장르도 분석에선 제외
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


class ConfirmationLeakTest(unittest.TestCase):
    """확인된 장르 = 사후 수집 편향 (docs/methods.md): 장르를 확인한 경로가 정답 여부와 엮였는지 보여 주는 표."""

    def test_confirmation_split_by_hit(self):
        data = {"c1": [_r("a", "록·밴드", 1, hit=1), _r("b", "미분류", 1), _r("c", "미분류", 1)],
                "c2": [_r("a", "록·밴드", 1, hit=1), _r("d", "미분류", 1, hit=1)]}
        conf = {"a": "profile", "b": "inferred", "c": "", "d": "review"}
        genre_raw = {"a": "록·밴드", "b": "록·밴드", "c": "", "d": "포크"}
        rows, summary = gb.confirmation_split(data, conf, genre_raw)
        by = {r["level"]: r for r in rows}
        self.assertEqual(by["profile"]["hits"], 2)
        self.assertEqual(by["profile"]["others"], 0)
        self.assertEqual(by["inferred"]["others"], 1)
        self.assertEqual(by["빈칸"]["others"], 1)              # 장르가 비면 확신도와 상관없이 '빈칸'
        self.assertEqual(by["review"]["hits"], 1)
        self.assertAlmostEqual(summary["hit_share_confirmed"], 2 / 3)    # 정답 3행 중 확인된 장르 2행
        self.assertAlmostEqual(summary["other_share_confirmed"], 0 / 2)
        self.assertEqual(summary["hits"], 3)
        self.assertEqual(summary["others"], 2)

    def test_section_marks_biased_columns(self):
        rows = [{"level": "profile", "hits": 9, "others": 1}, {"level": "빈칸", "hits": 1, "others": 99}]
        summary = {"hits": 10, "others": 100, "hit_share_confirmed": 0.9, "other_share_confirmed": 0.01}
        text = "\n".join(gb.section_confirmation(rows, summary))
        self.assertIn("사후 수집 편향", text)
        self.assertIn("90.0%", text)
        self.assertIn("정답 팀만으로", text)
        self.assertIn("| profile | 9 | 1 |", text)


class ConfirmedBaselineTest(unittest.TestCase):
    """장르 안 AUC 는 '확인된 장르 팀끼리 전체' AUC 와 비교해 읽는다 (전체 AUC 는 쉬운 미분류 비교가 섞여 높음)."""

    def test_confirmed_row_excludes_unclassified(self):
        data = {"c": [_r("a", "록·밴드", 3, hit=1, weight=1), _r("b", "록·밴드", 1), _r("c", "포크", 2),
                      _r("d", "포크", 4, hit=1, weight=1), _r("e", "미분류", 0), _r("f", "미분류", 0)]}
        row = gb.confirmed_row(data)
        self.assertEqual(row["n"], 4)
        self.assertEqual(row["pos"], 2)
        self.assertAlmostEqual(row["auc"], 1.0)      # 확인된 팀끼리: 정답 a(3)·d(4) > 비정답 b(1)·c(2)

    def test_backtest_section_shows_confirmed_baseline(self):
        table = [{"genre": "록·밴드", "n": 2, "pos": 1, "base_rate": 0.5, "auc": 0.6, "small": False, "hit_share": 1.0,
                  "top_count": 1, "top_hits": 1, "top_recall": 1.0, "pool_share": 1.0, "top_share": 1.0, "bias": 1.0}]
        overall = {"genre": "전체", "n": 2, "pos": 1, "base_rate": 0.5, "auc": 0.9, "top_count": 1, "top_hits": 1}
        confirmed = {"n": 2, "pos": 1, "base_rate": 0.5, "auc": 0.645}
        text = "\n".join(gb.section_backtest(table, overall, confirmed))
        self.assertIn("확인된 장르 팀 전체", text)
        self.assertIn("0.645", text)


class SideBySideTest(unittest.TestCase):
    """감사 문서(docs/genre_bias_audit_2026-11-28.md) 처방: 추정 장르 포함 판 나란히 · 6-2 기준선 칸 · 미분류 이름."""

    def test_relabel_uses_given_genres_and_keeps_rows(self):
        data = {"c": [_r("a", "미분류", 1), _r("b", "록·밴드", 2)]}
        out = gb.relabel(data, {"a": "힙합", "b": ""})
        self.assertEqual([r["genre"] for r in out["c"]], ["힙합", gb.UNCLASSIFIED])
        self.assertEqual(data["c"][0]["genre"], "미분류")          # 원본은 그대로

    def test_source_hits_all_and_genre_tagged_base(self):
        data = {"c1": [_r("a", "x", 1, hit=1), _r("b", "x", 1), _r("c", "x", 1)]}
        src = {"c1": {"a": {"s1"}, "b": {"s1", "s2"}, "c": {"s2"}}}
        self.assertEqual(gb.source_hits_all(data, src), {"s1": (2, 1), "s2": (2, 0)})
        tag = {"a": "록", "b": "록"}                                # c 는 태그 없음
        self.assertEqual(gb.genre_tagged_base(data, tag), {"록": (2, 1)})

    def test_display_genre_names_unclassified_as_profile_gap(self):
        self.assertEqual(gb.display_genre(gb.UNCLASSIFIED), "미분류 (프로필 미수집·추정 장르)")
        self.assertEqual(gb.display_genre("록·밴드"), "록·밴드")

    def test_all_genre_section(self):
        t = [{"genre": "록·밴드", "n": 10, "pos": 2, "base_rate": 0.2, "auc": None, "small": True, "hit_share": 1.0,
              "top_count": 3, "top_hits": 2, "top_recall": 1.0, "pool_share": 0.5, "top_share": 0.6, "bias": 1.2}]
        text = "\n".join(gb.section_backtest_all(t))
        self.assertIn("추정 장르 포함", text)
        self.assertIn("| 록·밴드 | 10 | 2 |", text)


class ConfirmedCompositionTest(unittest.TestCase):
    """2절 확인된 장르 팀끼리 판: 미분류를 빼고, 상위 N 을 풀 크기에 비례(최소 min_top)로 다시 잰다 (감사 문서 제안)."""

    def test_proportional_top_with_floor(self):
        rows = ([_r(f"u{i}", "미분류", 0) for i in range(80)]
                + [_r(f"r{i}", "록", 10 - i) for i in range(10)] + [_r(f"f{i}", "포크", 5 - i) for i in range(10)])
        comp, n_top, n_pool = gb.composition_confirmed(rows, top_n=10, min_top=4)
        self.assertEqual(n_pool, 20)
        self.assertEqual(n_top, 4)                       # 비례로는 10×20/100 = 2팀 → 최소 4팀
        by = {c["genre"]: c for c in comp}
        self.assertNotIn("미분류", by)
        self.assertEqual(by["록"]["top_count"], 4)       # 록 점수 10·9·8·7 이 포크(5 이하)보다 위
        self.assertAlmostEqual(by["록"]["pool_share"], 0.5)
        self.assertAlmostEqual(by["록"]["bias"], 2.0)

    def test_proportional_when_large_enough(self):
        rows = [_r(f"u{i}", "미분류", 0) for i in range(50)] + [_r(f"r{i}", "록", i) for i in range(50)]
        _, n_top, n_pool = gb.composition_confirmed(rows, top_n=20, min_top=4)
        self.assertEqual((n_top, n_pool), (10, 50))      # 20 × 50/100

    def test_section_text(self):
        comp = [{"genre": "록", "top_count": 4, "all_count": 10, "top_share": 1.0, "pool_share": 0.5, "bias": 2.0}]
        text = "\n".join(gb.section_current_confirmed(comp, 4, 20, 100, 1000))
        self.assertIn("확인된 장르 팀끼리", text)
        self.assertIn("| 록 | 4 |", text)
        self.assertIn("최소", text)                       # 비례 2팀 < 4팀이라 최소를 썼다는 설명


class PointInTimeGenreTest(unittest.TestCase):
    """'그때 알 수 있던 장르만' 판: genre_seen.known_from < 기준일 인 확인 장르만 장르로 (docs/methods.md)."""

    def test_point_in_time_genres_per_cutoff(self):
        data = {"2024-01-01": [_r("a", "록·밴드", 1), _r("b", "포크", 1), _r("c", "미분류", 1)],
                "2025-01-01": [_r("a", "록·밴드", 1), _r("b", "포크", 1)]}
        seen = {"a": "2023-05-01", "b": "2024-06-01", "c": "2020-01-01"}
        out = gb.point_in_time(data, seen)
        self.assertEqual([r["genre"] for r in out["2024-01-01"]], ["록·밴드", gb.UNCLASSIFIED, gb.UNCLASSIFIED])
        self.assertEqual([r["genre"] for r in out["2025-01-01"]], ["록·밴드", "포크"])
        self.assertEqual(data["2024-01-01"][1]["genre"], "포크")       # 원본은 그대로

    def test_known_from_equal_to_cutoff_is_not_known(self):
        out = gb.point_in_time({"2024-01-01": [_r("a", "록·밴드", 1)]}, {"a": "2024-01-01"})
        self.assertEqual(out["2024-01-01"][0]["genre"], gb.UNCLASSIFIED)

    def test_load_genre_seen_falls_back_to_csv(self):
        import tempfile
        from pathlib import Path as P

        class NoTable:
            def execute(self, *_):
                raise RuntimeError("no genre_seen")
        with tempfile.TemporaryDirectory() as d:
            f = P(d) / "genre_seen.csv"
            f.write_text("team_key,genre,confidence,first_seen,first_seen_source,known_from,known_from_source,match\n"
                         "a,록,profile,2026-11-26,x,2024-05-01,y,genre\nb,포크,press,2026-11-26,x,,y,genre\n", encoding="utf-8")
            self.assertEqual(gb.load_genre_seen(NoTable(), f), {"a": "2024-05-01"})

    def test_seen_section_text(self):
        t = [{"genre": "록·밴드", "n": 10, "pos": 2, "base_rate": 0.2, "auc": None, "small": True, "hit_share": 1.0,
              "top_count": 3, "top_hits": 2, "top_recall": 1.0, "pool_share": 0.5, "top_share": 0.6, "bias": 1.2}]
        summary = {"hits": 10, "others": 100, "hit_share_confirmed": 0.14, "other_share_confirmed": 0.01}
        text = "\n".join(gb.section_backtest_seen(t, summary, {"n": 10, "pos": 2, "base_rate": 0.2, "auc": 0.7}))
        self.assertIn("그때 알 수 있던 장르만", text)
        self.assertIn("14.0%", text)
        self.assertIn("| 록·밴드 | 10 | 2 |", text)


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
