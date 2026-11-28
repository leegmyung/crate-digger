"""scripts/similar_validate.py — 비슷한 팀 유사도가 '같은 길'을 맞히는지 검증하는 순수 함수들."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import similar_validate as sv  # noqa: E402

BASE = {"stage": 0.40, "source": 0.25, "genre": 0.20, "level": 0.15}


def row(other, fs=0.0, fsrc=0.0, genre=False, flv=0.0):
    return {"related_team": other, "f_stage": fs, "f_source": fsrc, "same_genre": genre, "f_level": flv}


class WeightTest(unittest.TestCase):
    def test_weights_sum_to_one(self):
        for name, w in sv.WEIGHTS.items():
            self.assertAlmostEqual(sum(w.values()), 1.0, places=6, msg=name)
        self.assertEqual(sv.WEIGHTS["기본"], BASE)

    def test_weighted_sim(self):
        r = row("b", fs=1 / 3, flv=2 / 3, genre=True)
        self.assertAlmostEqual(sv.weighted_sim(r, BASE), 0.4 / 3 + 0.2 + 0.1)
        self.assertAlmostEqual(sv.weighted_sim(r, {"stage": 1, "source": 0, "genre": 0, "level": 0}), 1 / 3)


class NeighborTest(unittest.TestCase):
    def test_top_neighbors_respects_pool_order_and_zero(self):
        rows = [row("b", fs=1), row("c", fsrc=1), row("d", fs=0.5), row("x", fs=1), row("z")]
        got = sv.top_neighbors(rows, BASE, k=2, allowed={"b", "c", "d", "z"})
        self.assertEqual(got, ["b", "c"])                         # x 는 풀 밖, z 는 0점이라 안 씀
        got_stage = sv.top_neighbors(rows, {"stage": 1, "source": 0, "genre": 0, "level": 0}, k=5, allowed={"b", "c", "d", "z"})
        self.assertEqual(got_stage, ["b", "d"])                   # 같은 출처만 있는 c 는 무대 가중치만이면 0점

    def test_prior_winner_feature(self):
        rows = [row("w1", fs=1 / 3), row("w2", fsrc=1), row("n", fs=1)]
        self.assertAlmostEqual(sv.prior_winner_sim(rows, BASE, {"w1", "w2"}), 0.25)
        self.assertEqual(sv.prior_winner_sim(rows, BASE, set()), 0.0)


class BranchUpTest(unittest.TestCase):
    def test_new_branch_after_cutoff_counts_as_stage_up(self):
        before = {"a": {"공연"}, "b": {"공연", "큐레이션"}, "c": set()}
        after = {"a": {"공연", "큐레이션"}, "b": {"큐레이션"}, "c": {"공연"}}
        self.assertEqual(sv.branch_up(before, after, ["a", "b", "c", "d"]), {"a": 1, "b": 0, "c": 1, "d": 0})


class MetricTest(unittest.TestCase):
    def test_conditional_rate_and_lift(self):
        labels = {"a": 1, "b": 1, "c": 0, "d": 0, "e": 1}
        pairs = [("a", "b"), ("a", "c"), ("c", "e"), ("e", "d")]
        out = sv.conditional_rate(pairs, labels, base_keys=["a", "b", "c", "d", "e"])
        self.assertEqual(out["n"], 3)                             # X 가 맞힌 쌍: (a,b) (a,c) (e,d)
        self.assertAlmostEqual(out["rate"], 1 / 3)                # 그중 Y 도 맞힌 것 (a,b)
        self.assertAlmostEqual(out["base"], 3 / 5)
        self.assertAlmostEqual(out["lift"], (1 / 3) / (3 / 5))

    def test_conditional_rate_empty(self):
        out = sv.conditional_rate([], {"a": 0}, base_keys=["a"])
        self.assertEqual(out["n"], 0)
        self.assertIsNone(out["rate"])
        self.assertIsNone(out["lift"])

    def test_wilson_interval(self):
        lo, hi = sv.wilson(5, 20)
        self.assertLess(lo, 0.25)
        self.assertGreater(hi, 0.25)
        self.assertEqual(sv.wilson(0, 0), (None, None))

    def test_random_pairs_are_seeded_and_exclude_self(self):
        p1 = sv.random_pairs(["a", "b", "c", "d"], k=2, seed=1)
        p2 = sv.random_pairs(["a", "b", "c", "d"], k=2, seed=1)
        self.assertEqual(p1, p2)
        self.assertEqual(len(p1), 8)
        self.assertTrue(all(x != y for x, y in p1))

    def test_hit_rate_split(self):
        out = sv.split_rate([0.5, 0.0, 0.6, 0.1], [1, 0, 0, 0], threshold=0.4)
        self.assertEqual(out, {"with_n": 2, "with_rate": 0.5, "without_n": 2, "without_rate": 0.0})



class PointInTimeGenreTest(unittest.TestCase):
    """'그때 알 수 있던 장르만'(genre_seen.known_from < 기준일, scripts/genre_seen.py) — 확인된 장르 = 사후 수집 편향 대책."""

    def test_same_genre_kept_only_when_both_known_then(self):
        rows = [row("b", genre=True), row("c", genre=True), row("d", fs=0.5)]
        out = sv.pit_genre_rows(rows, "a", known={"a", "b"})
        self.assertEqual([r["same_genre"] for r in out], [True, False, False])
        self.assertEqual(rows[1]["same_genre"], True)                          # 원래 줄은 그대로
        self.assertEqual([r["same_genre"] for r in sv.pit_genre_rows(rows, "z", known={"b", "c"})], [False, False, False])

    def test_evaluate_pit_masks_genre_and_measures_known_pairs(self):
        genre_only = {"stage": 0.0, "source": 0.0, "genre": 1.0, "level": 0.0}
        d = {"cutoff": "2024-01-01", "keys": ["a", "b", "c", "d"],
             "hit": {"a": 1, "b": 1, "c": 0, "d": 0}, "hit_nob": {"a": 1, "b": 1, "c": 0, "d": 0},
             "known": {"a", "c"},
             "rows": {"a": [row("b", genre=True), row("c", genre=True)], "b": [row("a", genre=True)],
                      "c": [row("a", genre=True)], "d": []}}
        out = sv.evaluate_pit([d], genre_only)
        # 그때 장르를 안 a·c 만 같은 장르로 이어짐: a→c (c 정답 아님) → 같이 맞힌 쌍 0
        self.assertEqual((out["hit"]["n"], out["hit"]["both"]), (1, 0))
        self.assertEqual((out["hit_known_genre"]["n"], out["hit_known_genre"]["both"]), (1, 0))
        self.assertEqual(out["known_teams"], 2)
        self.assertEqual(out["known_hits"], 1)
        self.assertIn("hit_no_burock", out)


if __name__ == "__main__":
    unittest.main()
