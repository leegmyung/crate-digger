"""dormant_check: 후보 상위 팀 중 해체·활동 중단이 의심되는 팀(1년 넘게 신호 없음 + 최근 1년 공연 0)을 고르고 앱 '휴면' 기준과 비교한다."""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import dormant_check as dc  # noqa: E402

AS_OF = date(2026, 11, 28)


def cand(key, last_seen, gigs_1y=0, recent180=0, score=3.0, pts_venues=1.0, name=None):
    return {"team_key": key, "display_name": name or key, "last_seen": last_seen, "gigs_1y": gigs_1y,
            "recent180": recent180, "score": score, "pts_venues": pts_venues}


class RuleTest(unittest.TestCase):
    def test_dormant_needs_one_year_silence_and_no_gigs(self):
        self.assertTrue(dc.is_dormant(cand("a", date(2025, 11, 28)), AS_OF))          # 딱 1년
        self.assertFalse(dc.is_dormant(cand("b", date(2025, 11, 29)), AS_OF))         # 1년이 안 됨
        self.assertFalse(dc.is_dormant(cand("c", date(2024, 1, 1), gigs_1y=1), AS_OF))
        self.assertTrue(dc.is_dormant(cand("d", "2024-05-01"), AS_OF))                # 글자 날짜도 받음

    def test_app_dormant_rule_matches_ui(self):
        """docs/app/ui.js isDormantTeam: 최근 180일 신호 0 + 최근 1년 공연 0."""
        self.assertTrue(dc.is_app_dormant(cand("a", date(2026, 5, 1))))
        self.assertFalse(dc.is_app_dormant(cand("b", date(2026, 11, 1), recent180=1)))
        self.assertFalse(dc.is_app_dormant(cand("c", date(2024, 1, 1), gigs_1y=2)))

    def test_compare_counts_both_and_only(self):
        rows = [cand("old", date(2024, 1, 1)), cand("mid", date(2026, 5, 1)),
                cand("busy", date(2026, 11, 1), recent180=3, gigs_1y=2)]
        cmp = dc.compare(rows, AS_OF)
        self.assertEqual(cmp["both"], ["old"])
        self.assertEqual(cmp["app_only"], ["mid"])     # 반년~1년 조용한 팀: 앱 휴면엔 걸리지만 이 점검엔 안 걸림
        self.assertEqual(cmp["rule_only"], [])


class ActivityTest(unittest.TestCase):
    """점수는 '검증 대기' 출처(인디고·인스타 등)를 빼고 세지만, 활동 여부는 모든 신호로 본다 (와비킹: 2026-06 인디고 공연)."""

    def test_activity_uses_every_signal_until_as_of(self):
        sigs = [{"team_key": "a", "branch": "공연", "signal_date": "2026-06-27", "role": "pending"},
                {"team_key": "a", "branch": "큐레이션", "signal_date": "2024-11-25", "role": "discovery"},
                {"team_key": "b", "branch": "큐레이션", "signal_date": "2025-07-10", "role": "pending"},
                {"team_key": "b", "branch": "공연", "signal_date": "2027-01-01", "role": "pending"}]   # 기준일 뒤 = 미래 공연, 안 셈
        act = dc.activity(sigs, AS_OF)
        self.assertEqual(act["a"], ("2026-06-27", 1))
        self.assertEqual(act["b"], ("2025-07-10", 0))

    def test_merge_activity_overrides_scored_fields(self):
        row = cand("a", date(2024, 11, 25))
        merged = dc.merge_activity(row, {"a": ("2026-06-27", 1)})
        self.assertFalse(dc.is_dormant(merged, AS_OF))
        self.assertEqual(row["last_seen"], date(2024, 11, 25))                       # 원래 행은 그대로
        self.assertTrue(dc.is_dormant(dc.merge_activity(row, {}), AS_OF))
        self.assertTrue(dc.is_app_dormant(merged))                                    # 앱 꼬리표는 점수 값(검증 대기 제외) 기준


class InstaTest(unittest.TestCase):
    def test_insta_status(self):
        links = {"a": {"instagram": "https://www.instagram.com/a_band/"}, "b": {"melon": "x"}}
        self.assertEqual(dc.insta_status("a", links), "계정 있음 (게시물 확인 안 함)")
        self.assertEqual(dc.insta_status("b", links), "계정 없음")


class ReviewTest(unittest.TestCase):
    def test_review_row_and_excluded_split(self):
        review = {"x": {"status": "해외 팀", "note": "일본 밴드 내한", "url": "https://example.com/x"},
                  "y": {"status": "확인 못 함", "note": "", "url": ""}}
        excluded = {"x": "해외 팀 …"}
        self.assertEqual(dc.review_cell("x", review), "해외 팀 — 일본 밴드 내한 ([근거](https://example.com/x))")
        self.assertEqual(dc.review_cell("y", review), "확인 못 함")
        self.assertEqual(dc.review_cell("z", review), "아직 안 봄")
        self.assertEqual(dc.already_excluded(review, excluded), ["x"])

    def test_timeless_share(self):
        """기간 제한 없는 점수(공연장 수 + 정답 팀과 같은 무대)가 점수에서 차지하는 비중."""
        row = cand("a", date(2024, 1, 1), score=4.0, pts_venues=1.0) | {"pts_winner": 2}
        self.assertEqual(dc.timeless_share(row), 0.75)
        self.assertEqual(dc.timeless_share(cand("a", date(2024, 1, 1), score=0, pts_venues=1.0)), 0.0)


class RenderTest(unittest.TestCase):
    def test_render_lists_ranked_teams_and_comparison(self):
        rows = [cand("old", date(2024, 1, 1), name="옛팀"), cand("mid", date(2026, 5, 1))]
        ranked = [(1, rows[0]), (2, rows[1])]
        md = dc.render(ranked, AS_OF, links={}, review={}, excluded={}, top=300)
        self.assertIn("| 1 | 옛팀 |", md)
        self.assertIn("앱 '휴면'", md)
        self.assertNotIn("| 2 | mid |", md)                                           # 이 점검 목록엔 1년 기준만

    def test_replace_block_keeps_hand_written_text(self):
        doc = "머리말\n<!-- AUTO:LIST:START -->\n옛 내용\n<!-- AUTO:LIST:END -->\n손으로 쓴 꼬리"
        out = dc.replace_block(doc, "LIST", "새 내용")
        self.assertEqual(out, "머리말\n<!-- AUTO:LIST:START -->\n새 내용\n<!-- AUTO:LIST:END -->\n손으로 쓴 꼬리")
        self.assertIn("<!-- AUTO:LIST:START -->", dc.replace_block("", "LIST", "x"))   # 마커 없으면 끝에 붙임


if __name__ == "__main__":
    unittest.main()
