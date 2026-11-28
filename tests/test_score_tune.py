"""score_tune: 기준일 하나를 빼고 가중치를 고른 뒤 뺀 기준일로 채점(교차 검증)."""
import hashlib
import sys
from datetime import date
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import score_tune as st  # noqa: E402


def _md5(k):
    return hashlib.md5(k.encode("utf-8")).hexdigest()


class MetricTest(unittest.TestCase):
    def test_auc_perfect_random_and_ties(self):
        self.assertEqual(st.auc([3, 2, 1, 0], [1, 1, 0, 0]), 1.0)
        self.assertEqual(st.auc([0, 1, 2, 3], [1, 1, 0, 0]), 0.0)
        self.assertEqual(st.auc([1, 1, 1, 1], [1, 0, 1, 0]), 0.5)      # 동점은 절반
        self.assertIsNone(st.auc([1, 2], [0, 0]))                      # 정답 없음

    def test_hits_at_k_breaks_ties_by_md5_not_label(self):
        # 마지막 신호가 없으면 앱처럼 md5(team_key) 순 — md5('c') < md5('b') 라 c가 먼저
        self.assertLess(_md5("c"), _md5("b"))
        self.assertEqual(st.hits_at_k([5, 4, 4, 1], [0, 1, 0, 1], ["d", "c", "b", "a"], k=2), 1)
        self.assertEqual(st.hits_at_k([5, 4, 4, 1], [0, 1, 0, 1], ["d", "b", "c", "a"], k=2), 0)


class WeightedAucTest(unittest.TestCase):
    def test_heavier_winner_counts_more(self):
        # 정답 2팀: 무거운 팀(3)은 맨 위, 가벼운 팀(1)은 맨 아래 → 가중 AUC는 보통 AUC보다 높다
        scores, weights = [4, 3, 2, 1], [3, 0, 0, 1]
        self.assertEqual(st.auc(scores, [1, 0, 0, 1]), 0.5)
        self.assertAlmostEqual(st.weighted_auc(scores, weights), (3 * 1.0 + 1 * 0.0) / 4)
        self.assertIsNone(st.weighted_auc([1, 2], [0, 0]))


class ScoreTest(unittest.TestCase):
    def test_score_matches_v0_formula(self):
        f = {"n_branch": 3, "best_stage": 2, "peer_selected": 1, "dmz": 0, "gigs_1y": 0, "outlets": 5,
             "recent180": 4, "venues": 2, "peer_winner": 1}
        self.assertAlmostEqual(st.score(f, dict(st.V0_WEIGHTS)), 2 * 2 + 2 + 1 + 0 + 0 + 3)


class CollabGridTest(unittest.TestCase):
    def test_collab_in_score_and_grid(self):
        f = {"n_branch": 1, "best_stage": 0, "peer_selected": 0, "dmz": 0, "gigs_1y": 0, "outlets": 0,
             "recent180": 0, "venues": 0, "peer_winner": 0, "collab_est": 2}
        w = {**dict(st.V0_WEIGHTS), "w_collab": 1.0}
        self.assertAlmostEqual(st.score(f, w) - st.score(f, dict(st.V0_WEIGHTS)), __import__("math").log(3))
        self.assertEqual(st.GRID["w_collab"], (0, 0.5, 1, 2))
        self.assertEqual(dict(st.V0_WEIGHTS)["w_collab"], 0)

    def test_grid_drops_collab_weights_when_no_collab_data(self):
        # 협업 데이터가 0건이면 w_collab 은 0만 후보 (같은 AUC 동점에서 엉뚱한 값이 골라지지 않게)
        empty = {"2025-01-01": [{"collab_est": 0}, {"collab_est": 0}]}
        some = {"2025-01-01": [{"collab_est": 0}, {"collab_est": 1}]}
        self.assertEqual(st.active_grid(empty)["w_collab"], (0,))
        self.assertEqual(st.active_grid(some)["w_collab"], (0, 0.5, 1, 2))
        self.assertEqual(st.active_grid(empty)["w_branch"], st.GRID["w_branch"])


class AppOrderTest(unittest.TestCase):
    """동점 처리를 앱 후보 목록(candidates.sql: ROUND(score,2) DESC, last_seen DESC, md5(team_key))과 같게."""

    def test_ties_by_recent_last_seen_then_missing_last(self):
        order = st.app_order([1, 1, 1, 2], ["a", "b", "c", "d"],
                             [date(2024, 1, 1), date(2025, 1, 1), None, date(2020, 1, 1)])
        self.assertEqual(order, [3, 1, 0, 2])                       # d(점수 2) → b(최근) → a → c(날짜 없음은 맨 뒤)

    def test_same_last_seen_falls_back_to_md5(self):
        keys = ["x", "y", "z"]
        order = st.app_order([1, 1, 1], keys, ["2024-05-01"] * 3)   # 글자 날짜도 받음
        self.assertEqual([keys[i] for i in order], sorted(keys, key=_md5))

    def test_no_rounding_option_for_model_scores(self):
        # 앱에 안 보이는 모델 점수(로지스틱)는 반올림 없이, 동점 순서만 같게
        self.assertEqual(st.app_order([1.004, 1.001], ["a", "b"], [date(2024, 1, 1), date(2025, 1, 1)], decimals=None),
                         [0, 1])

    def test_scores_rounded_to_two_decimals_like_app(self):
        # 1.004 와 1.001 은 앱에서 둘 다 1.00 → 마지막 신호가 최근인 쪽이 위
        self.assertEqual(st.app_order([1.004, 1.001], ["a", "b"], [date(2024, 1, 1), date(2025, 1, 1)]), [1, 0])
        self.assertEqual(st.app_order([1.01, 1.001], ["a", "b"], [date(2024, 1, 1), date(2025, 1, 1)]), [0, 1])

    def test_hits_at_k_uses_last_seen(self):
        seen_hit_recent = [date(2020, 1, 1), date(2025, 1, 1), date(2024, 1, 1), date(2020, 1, 1)]
        seen_hit_old = [date(2020, 1, 1), date(2023, 1, 1), date(2024, 1, 1), date(2020, 1, 1)]
        args = ([5, 4, 4, 1], [0, 1, 0, 1], ["d", "c", "b", "a"])
        self.assertEqual(st.hits_at_k(*args, k=2, last_seen=seen_hit_recent), 1)
        self.assertEqual(st.hits_at_k(*args, k=2, last_seen=seen_hit_old), 0)

    def test_ranked_auc_counts_negatives_below_each_hit(self):
        # 순서(위→아래): 정답(3) · 비정답 · 정답(1) · 비정답 → (3×2/2 + 1×1/2) / 4
        weights = [3, 0, 1, 0]
        self.assertAlmostEqual(st.ranked_weighted_auc([0, 1, 2, 3], weights), (3 * 1.0 + 1 * 0.5) / 4)
        self.assertIsNone(st.ranked_weighted_auc([0, 1], [0, 0]))

    def test_app_auc_breaks_ties_instead_of_half(self):
        scores, weights = [1, 1, 1, 1], [2, 0, 0, 0]
        seen = [date(2025, 1, 1), date(2024, 1, 1), date(2024, 1, 1), date(2023, 1, 1)]
        self.assertEqual(st.weighted_auc(scores, weights), 0.5)                     # 옛 방식: 동점은 절반
        self.assertEqual(st.app_auc(scores, weights, ["h", "a", "b", "c"], seen), 1.0)   # 앱 순서: 정답이 맨 위

    def test_evaluate_uses_app_order(self):
        base = {"n_branch": 1, "best_stage": 0, "peer_selected": 0, "dmz": 0, "gigs_1y": 0, "outlets": 0,
                "recent180": 0, "venues": 0, "peer_winner": 0}
        rows = [{**base, "team_key": "h", "is_hit": 1, "hit_weight": 2, "last_seen": date(2025, 1, 1)}] + [
            {**base, "team_key": f"n{i}", "is_hit": 0, "hit_weight": 0, "last_seen": date(2023, 1, 1)} for i in range(4)]
        e = st.evaluate({"c": rows}, dict(st.V0_WEIGHTS))["c"]
        self.assertEqual(e["auc"], 1.0)
        self.assertEqual(e["plain_auc"], 1.0)
        self.assertEqual(e["hits20"], 1)

    def test_features_query_returns_last_seen(self):
        class Cur:
            description = [("team_key",), ("last_seen",)]

            def fetchall(self):
                return [("a", date(2024, 1, 1))]

        class Con:
            def execute(self, q):
                self.q = q
                return Cur()
        con = Con()
        rows = st.features(con, "2025-01-01")
        self.assertIn("last_seen", con.q)
        self.assertEqual(rows[0]["last_seen"], date(2024, 1, 1))


class TieRuleNoteTest(unittest.TestCase):
    def test_note_has_reason_and_before_after(self):
        note = st.tie_rule_note()
        self.assertIn("앱 후보 목록과 같게", note)
        self.assertIn("0.786 → 0.805", note)      # 바꾼 날 같은 데이터로 잰 고정값 (나중 데이터 숫자가 섞이지 않게)
        self.assertIn("23 → 23", note)


class DataRefreshNoteTest(unittest.TestCase):
    def test_note_has_rows_and_before_after(self):
        note = st.data_refresh_note({"pick": 0.81, "v0": 0.8}, {"pick": 30, "v0": 28}, n_rows=9000, n_pos=150)
        self.assertIn(st.DATA_REFRESH["what"], note)
        b = st.DATA_REFRESH   # 전 숫자는 상수에서 (데이터를 다시 갱신해 상수를 바꿔도 테스트가 따라감)
        self.assertIn(f"{b['rows']:,} → 9,000", note)
        self.assertIn(f"{b['pos']} → 150", note)
        self.assertIn("→ 0.810", note)
        self.assertIn("→ 30", note)


class LocoTest(unittest.TestCase):
    def test_held_out_cutoff_never_used_for_choosing(self):
        # 기준일 A에서만 좋은 가중치 x, 나머지에서 좋은 가중치 y → A를 뺄 때는 y가 골라져야 함
        table = {"x": {"A": 0.9, "B": 0.5, "C": 0.5}, "y": {"A": 0.6, "B": 0.7, "C": 0.7}}
        picks = st.loco_pick(table)
        self.assertEqual(picks["A"], "y")
        self.assertEqual(picks["B"], "x")                               # A·C 평균: x 0.70 > y 0.65


if __name__ == "__main__":
    unittest.main()
