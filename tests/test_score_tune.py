"""score_tune: 기준일 하나를 빼고 가중치를 고른 뒤 뺀 기준일로 채점(교차 검증)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import score_tune as st  # noqa: E402


class MetricTest(unittest.TestCase):
    def test_auc_perfect_random_and_ties(self):
        self.assertEqual(st.auc([3, 2, 1, 0], [1, 1, 0, 0]), 1.0)
        self.assertEqual(st.auc([0, 1, 2, 3], [1, 1, 0, 0]), 0.0)
        self.assertEqual(st.auc([1, 1, 1, 1], [1, 0, 1, 0]), 0.5)      # 동점은 절반
        self.assertIsNone(st.auc([1, 2], [0, 0]))                      # 정답 없음

    def test_hits_at_k_breaks_ties_by_key_not_label(self):
        self.assertEqual(st.hits_at_k([5, 4, 4, 1], [0, 1, 0, 1], ["d", "c", "b", "a"], k=2), 0)
        self.assertEqual(st.hits_at_k([5, 4, 4, 1], [0, 1, 0, 1], ["d", "b", "c", "a"], k=2), 1)


class ScoreTest(unittest.TestCase):
    def test_score_matches_v0_formula(self):
        f = {"n_branch": 3, "best_stage": 2, "peer_selected": 1, "dmz": 0, "gigs_1y": 0, "outlets": 5,
             "recent180": 4, "venues": 2, "peer_winner": 1}
        self.assertAlmostEqual(st.score(f, dict(st.V0_WEIGHTS)), 2 * 2 + 2 + 1 + 0 + 0 + 3)


class LocoTest(unittest.TestCase):
    def test_held_out_cutoff_never_used_for_choosing(self):
        # 기준일 A에서만 좋은 가중치 x, 나머지에서 좋은 가중치 y → A를 뺄 때는 y가 골라져야 함
        table = {"x": {"A": 0.9, "B": 0.5, "C": 0.5}, "y": {"A": 0.6, "B": 0.7, "C": 0.7}}
        picks = st.loco_pick(table)
        self.assertEqual(picks["A"], "y")
        self.assertEqual(picks["B"], "x")                               # A·C 평균: x 0.70 > y 0.65


if __name__ == "__main__":
    unittest.main()
