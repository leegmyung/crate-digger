"""feature_lab: 기준일 시점 정보만 쓰는 새 특징 후보를 점수 v2에 하나씩 더해 교차 검증으로 재기 (제안만)."""
import math
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import feature_lab as fl  # noqa: E402

C = date(2025, 1, 1)


def _sig(team, d, branch="공연", venue="A홀", role="discovery", source="indistreet", program=None, stage=None):
    return {"team_key": team, "branch": branch, "source": source, "program": program, "stage_rank": stage,
            "signal_date": d, "venue": venue, "role": role}


def _row(key, hit=0, weight=0, **f):
    base = {"team_key": key, "n_branch": 1, "best_stage": 0, "venues": 0, "recent180": 0, "peer_winner": 0,
            "outlets": 0, "context_outlets": 0, "peer_selected": 0, "dmz": 0, "gigs_1y": 0, "collab_est": 0,
            "is_hit": hit, "hit_weight": weight}
    return {**base, **f}


class WindowTest(unittest.TestCase):
    def test_only_before_cutoff_and_inside_lookback(self):
        sigs = [_sig("a", date(2024, 12, 31)), _sig("a", C), _sig("a", date(2021, 12, 31)),
                _sig("a", date(2022, 1, 1)), _sig("a", date(2024, 6, 1), role="pending")]
        got = fl.window(sigs, C, years=3, roles=("discovery",))
        self.assertEqual(sorted(s["signal_date"] for s in got), [date(2022, 1, 1), date(2024, 12, 31)])

    def test_no_lookback_keeps_all_past(self):
        sigs = [_sig("a", date(2010, 1, 1)), _sig("a", date(2026, 1, 1))]
        self.assertEqual(len(fl.window(sigs, C, years=None, roles=("discovery",))), 1)


class WinnerTest(unittest.TestCase):
    def test_counted_outcomes_announced_before_cutoff_only(self):
        outs = [{"team_key": "w", "announced_date": date(2024, 5, 1), "counted": True},
                {"team_key": "late", "announced_date": C, "counted": True},
                {"team_key": "weak", "announced_date": date(2024, 5, 1), "counted": False}]
        self.assertEqual(fl.winners_before(outs, C), {"w"})


class GraphTest(unittest.TestCase):
    def setUp(self):
        # a·b 같은 날 같은 곳, b·c 같은 날 같은 곳, d 혼자, 공연장 미정은 무대로 안 침
        self.sigs = [_sig("a", date(2024, 3, 1)), _sig("b", date(2024, 3, 1)),
                     _sig("b", date(2024, 4, 1), venue="B홀"), _sig("c", date(2024, 4, 1), venue="B홀"),
                     _sig("d", date(2024, 4, 2), venue="B홀"),
                     _sig("x", date(2024, 5, 1), venue="공연장 미정"), _sig("y", date(2024, 5, 1), venue="공연장 미정")]

    def test_gigs_skip_unknown_venue_and_non_gig(self):
        sigs = self.sigs + [_sig("e", date(2024, 3, 1), branch="큐레이션")]
        teams = {g[0] for g in fl.gigs(sigs)}
        self.assertEqual(teams, {"a", "b", "c", "d"})

    def test_cobill_graph(self):
        adj = fl.cobill_graph(fl.gigs(self.sigs))
        self.assertEqual(adj["a"], {"b"})
        self.assertEqual(adj["b"], {"a", "c"})
        self.assertEqual(adj.get("d", set()), set())

    def test_winner_proximity_by_hops(self):
        adj = fl.cobill_graph(fl.gigs(self.sigs))
        prox = fl.winner_proximity(adj, {"a"})
        self.assertEqual(prox["b"], 1.0)
        self.assertAlmostEqual(prox["c"], 0.5)
        self.assertNotIn("a", prox)                      # 정답 팀 자신은 값 없음(후보에도 없음)
        self.assertEqual(prox.get("d", 0.0), 0.0)

    def test_peer_score_mean_only_pool_neighbors(self):
        adj = fl.cobill_graph(fl.gigs(self.sigs))
        got = fl.peer_score(adj, {"a": 2.0, "c": 4.0, "b": 1.0})    # b 이웃 = a, c
        self.assertAlmostEqual(got["b"], 3.0)
        self.assertAlmostEqual(got["a"], 1.0)
        self.assertNotIn("d", got)


class VenueQualityTest(unittest.TestCase):
    def setUp(self):
        # A홀: w(정답)·t·u, B홀: v 혼자. 공연한 팀 중 정답 비율 p0 = 1/4
        self.g = [("w", date(2024, 1, 1), "A홀"), ("t", date(2024, 2, 1), "A홀"), ("u", date(2024, 3, 1), "A홀"),
                  ("v", date(2024, 3, 1), "B홀")]

    def test_self_excluded_lift_minus_one(self):
        q = fl.venue_quality(self.g, {"w"}, prior=0)          # 평활 없이: 비율 그대로
        self.assertAlmostEqual(q["t"], (1 / 2) / (1 / 4) - 1)   # t 빼면 A홀 = w·u → 1/2, 배수 2 → 1
        self.assertAlmostEqual(q["v"], 0.0)                     # 다른 팀이 없으면 평균(배수 1 → 0)
        self.assertNotIn("w", q)                                # 정답 팀 자신은 후보가 아님

    def test_smoothing_shrinks_toward_average(self):
        raw = fl.venue_quality(self.g, {"w"}, prior=0)
        smooth = fl.venue_quality(self.g, {"w"}, prior=4)
        self.assertLess(smooth["t"], raw["t"])
        self.assertGreater(smooth["t"], 0)

    def test_no_winners_gives_zero(self):
        g = [("t", date(2024, 1, 1), "A홀"), ("u", date(2024, 1, 1), "A홀")]
        self.assertEqual(fl.venue_quality(g, set()), {"t": 0.0, "u": 0.0})


class SimpleFeatureTest(unittest.TestCase):
    def test_acceleration_recent_vs_previous_180(self):
        sigs = [_sig("a", date(2024, 12, 1)), _sig("a", date(2024, 11, 1)), _sig("a", date(2024, 5, 1)),
                _sig("b", date(2024, 5, 1))]
        acc = fl.acceleration(sigs, C)
        self.assertAlmostEqual(acc["a"], math.log(3) - math.log(2))
        self.assertAlmostEqual(acc["b"], math.log(1) - math.log(2))

    def test_tenure_and_last_gap_in_years(self):
        sigs = [_sig("a", date(2023, 1, 1)), _sig("a", date(2024, 7, 1))]
        self.assertAlmostEqual(fl.tenure_years(sigs, C)["a"], (C - date(2023, 1, 1)).days / 365.25)
        self.assertAlmostEqual(fl.last_gap_years(sigs, C)["a"], (C - date(2024, 7, 1)).days / 365.25)

    def test_source_count_uses_source_and_program(self):
        sigs = [_sig("a", date(2024, 1, 1)), _sig("a", date(2024, 2, 1)),
                _sig("a", date(2024, 3, 1), branch="선정·지원", source="sangsangmadang", program="band_discovery"),
                _sig("a", date(2024, 3, 2), source="sangsangmadang")]
        self.assertEqual(fl.source_count(sigs)["a"], 3)

    def test_region_of_and_spread(self):
        self.assertEqual(fl.region_of("대구 제임스레코드"), "대구")
        self.assertEqual(fl.region_of("인천여관X루비살롱"), "인천")
        self.assertEqual(fl.region_of("Club 빵"), "서울")
        g = [("a", C, "Club 빵"), ("a", C, "대구 제임스레코드"), ("b", C, "Club FF")]
        self.assertEqual(fl.region_spread(g), {"a": 1, "b": 0})

    def test_stage_rise_recent_year_over_before(self):
        sel = dict(branch="선정·지원", source="yjh", program="p", venue=None)
        sigs = [_sig("a", date(2022, 6, 1), stage=1, **sel), _sig("a", date(2024, 6, 1), stage=3, **sel),
                _sig("b", date(2024, 6, 1), stage=3, **sel), _sig("c", date(2022, 6, 1), stage=3, **sel),
                _sig("d", date(2024, 6, 1), stage=4, branch="선정·지원", source="dmz", program="dmz_lineup")]
        r = fl.stage_rise(sigs, C)
        self.assertEqual(r["a"], 2)
        self.assertEqual(r["b"], 3)
        self.assertEqual(r.get("c", 0), 0)
        self.assertNotIn("d", r)                          # DMZ는 v2 처럼 빼고 셈


class EvaluateTest(unittest.TestCase):
    def setUp(self):
        # 기준일 3개. v2 점수는 모두 같고(구분 못 함), 새 특징 f 는 정답 팀만 1 → 더하면 좋아져야 함
        self.data, self.extra = {}, {}
        for c in ("c1", "c2", "c3"):
            rows = ([_row(f"{c}h", hit=1, weight=2, last_seen=date(2020, 1, 1))]      # 동점이면 맨 아래(가장 오래됨)
                    + [_row(f"{c}n{i}", last_seen=date(2024, 1, 1)) for i in range(5)])
            self.data[c] = rows
            self.extra[c] = {r["team_key"]: {"f": 1.0 if r["is_hit"] else 0.0} for r in rows}

    def test_scale_is_std_and_safe_for_constant(self):
        self.assertGreater(fl.feature_scale(self.data, self.extra, "f"), 0)
        const = {c: {k: {"g": 3.0} for k in v} for c, v in self.extra.items()}
        self.assertEqual(fl.feature_scale(self.data, const, "g"), 1.0)

    def test_loco_picks_positive_weight_and_beats_base(self):
        res = fl.evaluate_feature(self.data, self.extra, "f", grid=(-0.5, 0.5, 1.0))
        for c in self.data:
            self.assertGreater(res["picks"][c], 0)
            self.assertEqual(res["cv"][c]["auc"], 1.0)
            self.assertEqual(res["base"][c]["auc"], 0.0)          # 앱 순서: 동점 → 마지막 신호 최근 순
        self.assertGreater(res["cv_mean"], res["base_mean"])
        self.assertEqual(res["cv_hits"]["hits20"], 3)

    def test_distinct_scores_counts_v2_values(self):
        rows = [_row("a"), _row("b"), _row("c", n_branch=2)]     # a·b 동점, c 혼자
        self.assertEqual(fl.distinct_scores(rows), 2)

    def test_small_weight_only_breaks_ties(self):
        # 정답 팀이 동점 묶음 안에 있을 때, 작은 가중치는 묶음 밖 순서를 바꾸지 않고 묶음 안만 가른다
        rows = [_row("top", n_branch=3), _row("h", hit=1, weight=1), _row("n")]
        extra = {"h": {"f": 1.0}, "n": {"f": 0.0}, "top": {"f": 0.0}}
        s = fl.combined_scores(rows, extra, {"f": 0.1}, {"f": 1.0})
        self.assertGreater(s[0], s[1])
        self.assertGreater(s[1], s[2])

    def test_missing_team_value_counts_as_zero(self):
        extra = {c: {} for c in self.data}
        res = fl.evaluate_feature(self.data, extra, "f", grid=(0.5,))
        self.assertAlmostEqual(res["cv_mean"], res["base_mean"])


if __name__ == "__main__":
    unittest.main()
