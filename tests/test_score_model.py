"""score_model: 손 공식(점수 v2)과 학습 모델(로지스틱 회귀)을 같은 교차 검증으로 비교 + 리드타임·점수 안정성."""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import numpy as np  # noqa: E402

import score_model as sm  # noqa: E402


def _row(key, hit=0, weight=0, **f):
    base = {"team_key": key, "n_branch": 1, "best_stage": 0, "venues": 0, "recent180": 0, "peer_winner": 0,
            "outlets": 0, "context_outlets": 0, "peer_selected": 0, "dmz": 0, "gigs_1y": 0,
            "is_hit": hit, "hit_weight": weight}
    return {**base, **f}


class FeatureTest(unittest.TestCase):
    def test_feature_vector_uses_same_transforms_as_v2(self):
        r = _row("a", n_branch=3, best_stage=2, venues=4, recent180=6, peer_winner=1, outlets=5,
                 context_outlets=1, peer_selected=1, dmz=1, gigs_1y=9)
        v = sm.feature_vector(r)
        self.assertEqual(len(v), len(sm.FEATURES))
        expect = [2, 2, math.log(5), math.log(7), 1, 3, 1, 1, 1, math.log(10)]
        for got, want in zip(v, expect):
            self.assertAlmostEqual(got, want)

    def test_v2_weights_come_from_lab_defaults(self):
        w = sm.v2_weights()
        self.assertEqual(w["w_winner"], 2.0)
        self.assertEqual(w["w_context"], 0.5)
        self.assertEqual(w["w_gigs"], 0.0)


class StandardizerTest(unittest.TestCase):
    def test_stats_from_training_rows_only_and_constant_column_safe(self):
        x = np.array([[1.0, 5.0], [3.0, 5.0]])
        mean, std = sm.fit_standardizer(x)
        np.testing.assert_allclose(mean, [2.0, 5.0])
        np.testing.assert_allclose(std, [1.0, 1.0])            # 상수 열은 1로 (0으로 나누지 않게)
        z = sm.apply_standardizer(np.array([[5.0, 9.0]]), mean, std)
        np.testing.assert_allclose(z, [[3.0, 4.0]])


class SampleWeightTest(unittest.TestCase):
    def test_grade_weights_and_class_balance(self):
        rows = [_row("a", 1, 3), _row("b", 1, 1), _row("c"), _row("d"), _row("e"), _row("f")]
        w = sm.sample_weights(rows)
        self.assertAlmostEqual(w[0] / w[1], 3.0)                # S 등급이 B보다 3배
        self.assertAlmostEqual(w[:2].sum(), w[2:].sum())        # 정답·비정답 총 무게를 맞춤
        self.assertTrue(all(x == 1 for x in w[2:]))


class LogisticTest(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(0)
        n = 400
        self.x = rng.normal(size=(n, 2))
        self.y = (self.x[:, 0] + 0.3 * rng.normal(size=n) > 1.0).astype(float)
        self.w = np.ones(n)

    def test_learns_informative_feature_and_ignores_noise(self):
        coef, _ = sm.fit_logistic(self.x, self.y, self.w, l2=0.01)
        self.assertGreater(coef[0], 1.0)
        self.assertLess(abs(coef[1]), 0.5)

    def test_bigger_l2_shrinks_coefficients(self):
        small, _ = sm.fit_logistic(self.x, self.y, self.w, l2=0.001)
        big, _ = sm.fit_logistic(self.x, self.y, self.w, l2=1.0)
        self.assertLess(np.linalg.norm(big), np.linalg.norm(small))

    def test_model_keeps_training_standardization(self):
        rows = [_row(str(i), int(i % 7 == 0), 2 if i % 7 == 0 else 0, venues=5 if i % 7 == 0 else 0)
                for i in range(70)]
        model = sm.train_logistic(rows, l2=0.1)
        x = np.array([sm.feature_vector(r) for r in rows])
        np.testing.assert_allclose(model.mean, x.mean(axis=0))
        new = [_row("new", venues=5), _row("old")]
        s = model.predict(new)
        self.assertGreater(s[0], s[1])                          # 공연장 많은 팀이 위


class GridTest(unittest.TestCase):
    def test_vectorized_weighted_auc_matches_score_tune(self):
        rng = np.random.default_rng(1)
        scores = rng.integers(0, 4, size=(60, 3)).astype(float)      # 동점이 많게
        weights = [3 if i % 10 == 0 else (1 if i % 13 == 0 else 0) for i in range(60)]
        got = sm.weighted_auc_matrix(scores, np.array(weights, dtype=float))
        for g in range(3):
            self.assertAlmostEqual(got[g], sm.st.weighted_auc(list(scores[:, g]), weights))

    def test_grid_matrix_score_equals_hand_formula(self):
        r = _row("a", n_branch=2, best_stage=3, venues=2, recent180=1, peer_winner=1, outlets=4, context_outlets=2)
        w = sm.v2_weights()
        self.assertAlmostEqual(float(np.array(sm.feature_vector(r)) @ sm.weight_vector(w)), sm.st.score(r, w))


class FoldTest(unittest.TestCase):
    def test_forward_folds_wait_for_horizon(self):
        cut = ["2023-01-01", "2023-07-01", "2024-01-01", "2024-07-01", "2025-01-01", "2025-07-01"]
        folds = sm.forward_folds(cut, horizon_months=24)
        self.assertEqual(folds, [("2025-01-01", ["2023-01-01"]), ("2025-07-01", ["2023-01-01", "2023-07-01"])])

    def test_choose_l2_returns_grid_value(self):
        data = {"A": [_row("a1", 1, 1, venues=3), _row("a2"), _row("a3")],
                "B": [_row("b1", 1, 2, venues=2), _row("b2"), _row("b3", venues=1)]}
        self.assertIn(sm.choose_l2(data, (0.01, 1.0)), (0.01, 1.0))


class LeadTimeTest(unittest.TestCase):
    def test_months_between_and_quartiles(self):
        self.assertAlmostEqual(sm.months_between("2024-01-01", "2025-01-01"), 366 / 30.4375)
        self.assertEqual(sm.quartiles([1, 2, 3, 4, 5]), (2.0, 3.0, 4.0))
        self.assertIsNone(sm.quartiles([]))

    def test_first_signal_strictly_before_first_outcome(self):
        signals = [
            {"team_key": "a", "source": "indistreet", "signal_date": "2024-03-01"},
            {"team_key": "a", "source": "indistreet", "signal_date": "2024-01-01"},   # 더 이른 것 사용
            {"team_key": "a", "source": "izm", "signal_date": "2025-01-01"},          # 정답과 같은 날 → 제외
            {"team_key": "b", "source": "izm", "signal_date": "2025-06-01"},          # 정답 뒤 → 제외
        ]
        outcomes = [{"team_key": "a", "announced_date": "2025-01-01", "grade": "A"},
                    {"team_key": "a", "announced_date": "2026-01-01", "grade": "S"},
                    {"team_key": "b", "announced_date": "2025-02-01", "grade": "B"}]
        leads = sm.lead_times(signals, outcomes)
        self.assertEqual([(r["team_key"], r["source"]) for r in leads], [("a", "indistreet")])
        self.assertEqual(leads[0]["grade"], "A")                  # 첫 정답의 등급
        self.assertAlmostEqual(leads[0]["months"], 366 / 30.4375)

    def test_overall_lead_uses_earliest_source(self):
        signals = [{"team_key": "a", "source": "x", "signal_date": "2024-06-01"},
                   {"team_key": "a", "source": "y", "signal_date": "2024-01-01"}]
        outcomes = [{"team_key": "a", "announced_date": "2025-01-01", "grade": "S"}]
        overall = sm.first_signal_leads(sm.lead_times(signals, outcomes))
        self.assertEqual(len(overall), 1)
        self.assertEqual(overall[0]["source"], "y")


class StabilityTest(unittest.TestCase):
    def test_compare_snapshots(self):
        prev = [{"team_key": k, "rank": i} for i, k in enumerate("abcde", 1)]
        cur = [{"team_key": k, "rank": i} for i, k in enumerate("baxce", 1)]
        res = sm.compare_snapshots(prev, cur, top=3)
        self.assertEqual(res["entered"], ["x"])
        self.assertEqual(res["exited"], ["d"])
        self.assertEqual(res["top_kept"], 2)                      # 상위3: abc → bax, 유지 a·b
        self.assertEqual(res["moves"], {"a": -1, "b": 1, "c": -1, "e": 0})   # +는 오름

    def test_change_reason(self):
        a = _row("a", venues=1)
        self.assertEqual(sm.change_reason(None, a), "새로 후보가 됨")
        self.assertEqual(sm.change_reason(a, None), "후보에서 빠짐")
        self.assertEqual(sm.change_reason(a, dict(a)), "내 특징은 그대로(다른 팀이 움직임)")
        self.assertEqual(sm.change_reason(a, {**a, "venues": 2, "recent180": 1}),
                         "특징 변화: ln(1+공연장 수), ln(1+최근 180일 신호)")
        w = sm.v2_weights()                                       # v2 에서 최근 활동 가중치는 0
        self.assertEqual(sm.change_reason(a, {**a, "venues": 2, "recent180": 1}, w), "특징 변화: ln(1+공연장 수)")
        self.assertEqual(sm.change_reason(a, {**a, "recent180": 1}, w), "점수에 안 쓰는 특징만 변함(다른 팀이 움직임)")

    def test_rank_change_summary(self):
        s = sm.rank_change_summary({"a": 0, "b": 5, "c": -30, "d": 12})
        self.assertEqual(s["n"], 4)
        self.assertAlmostEqual(s["unchanged"], 0.25)
        self.assertAlmostEqual(s["moved10"], 0.5)                 # |변동| ≥ 10
        self.assertEqual(s["abs_q"], (3.75, 8.5, 16.5))


if __name__ == "__main__":
    unittest.main()
