"""recency_lab: '공연장 수'·'수상 팀과 같은 무대'를 최근 N년 공연으로만 셌을 때를 흉내 낸다 (점수 정의는 안 바꿈)."""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import recency_lab as rl  # noqa: E402

CUT = date(2025, 1, 1)


def gig(team, d, venue, role="discovery", branch="공연"):
    return {"team_key": team, "branch": branch, "signal_date": d, "venue": venue, "role": role}


class WindowStartTest(unittest.TestCase):
    def test_calendar_years_back(self):
        self.assertEqual(rl.years_before(date(2025, 1, 1), 2), date(2023, 1, 1))
        self.assertEqual(rl.years_before(date(2024, 2, 29), 1), date(2023, 2, 28))   # 윤일


class ShortFeatsTest(unittest.TestCase):
    def setUp(self):
        self.sigs = [
            gig("a", date(2022, 6, 1), "옛클럽"),            # 2년 밖
            gig("a", date(2024, 3, 1), "빵"),
            gig("a", date(2024, 3, 1), "빵"),                # 같은 공연장 한 번만
            gig("a", date(2024, 5, 1), "FF"),
            gig("a", date(2024, 6, 1), ""),                  # 공연장 모름 = 안 셈
            gig("a", date(2024, 7, 1), "Sharp", role="pending"),   # 검증 대기 = 점수에 안 씀
            gig("a", date(2025, 2, 1), "미래"),              # 기준일 뒤
            gig("w", date(2022, 6, 1), "옛클럽"),            # 수상 팀과 같은 무대 — 2년 밖
            gig("w", date(2024, 5, 1), "FF"),                # 수상 팀과 같은 무대 — 1년 안
            gig("b", date(2023, 3, 1), "빵"),
            gig("w", date(2023, 3, 1), "빵"),                # b와 같은 무대 — 그때 w는 이미 수상(2023-01)
        ]
        self.outs = [{"team_key": "w", "announced_date": date(2023, 1, 1), "counted": True},
                     {"team_key": "x", "announced_date": date(2025, 6, 1), "counted": True}]   # 기준일 뒤 = 안 씀

    def test_venues_counted_inside_window_only(self):
        one = rl.short_feats(self.sigs, self.outs, CUT, 1)
        three = rl.short_feats(self.sigs, self.outs, CUT, 3)
        self.assertEqual(one["a"]["venues"], 2)          # 빵·FF
        self.assertEqual(three["a"]["venues"], 3)        # + 옛클럽

    def test_peer_winner_needs_winner_already_awarded_and_inside_window(self):
        one = rl.short_feats(self.sigs, self.outs, CUT, 1)
        self.assertEqual(one["a"]["peer_winner"], 1)     # 2024-05 FF에서 w(2023 수상)와 같은 무대
        self.assertNotIn("b", one)                       # 2023-03 무대는 1년 밖 → 기간 안 공연 없음 = 0
        two = rl.short_feats(self.sigs, self.outs, CUT, 2)
        self.assertEqual(two["b"]["peer_winner"], 1)
        self.assertEqual(two["w"]["peer_winner"], 0)     # 자기 자신은 안 셈

    def test_with_feats_returns_new_rows(self):
        rows = [{"team_key": "a", "venues": 3, "peer_winner": 0}, {"team_key": "z", "venues": 1, "peer_winner": 1}]
        feats = {"a": {"venues": 2, "peer_winner": 1}}
        out = rl.with_feats(rows, feats, ("venues",))
        self.assertEqual([r["venues"] for r in out], [2, 0])          # 기간 안 공연이 없는 팀은 0
        self.assertEqual([r["peer_winner"] for r in out], [0, 1])     # 바꾸라고 한 특징만
        self.assertEqual(rows[0]["venues"], 3)                         # 원래 행은 그대로


class ChangedRowsTest(unittest.TestCase):
    def test_counts_rows_whose_feature_differs(self):
        rows = [{"team_key": "a", "venues": 3, "peer_winner": 1}, {"team_key": "b", "venues": 0, "peer_winner": 0}]
        self.assertEqual(rl.changed_rows(rows, {"a": {"venues": 2, "peer_winner": 1}}), (1, 0))
        self.assertEqual(rl.changed_rows(rows, {}), (1, 1))                  # a는 기간 안 공연 없음 → 둘 다 0으로 바뀜


class DormantTopTest(unittest.TestCase):
    def test_counts_dormant_teams_in_app_top_k(self):
        rows = [{"team_key": k, "last_seen": date(2024, 1, 1)} for k in ("old", "new", "mid")]
        scores = [3.0, 2.0, 1.0]
        act = {"old": ("2023-06-01", 0), "new": ("2024-12-01", 2), "mid": ("2023-01-01", 0)}
        self.assertEqual(rl.dormant_in_top(rows, scores, act, CUT, 2), ["old"])
        self.assertEqual(rl.dormant_in_top(rows, scores, act, CUT, 3), ["old", "mid"])


if __name__ == "__main__":
    unittest.main()
