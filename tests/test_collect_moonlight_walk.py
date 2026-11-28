"""collect_moonlight_walk: 천안 달빛산책 블로그 'Live Stage' 글 → 공연 원본(raw_kr_gig, source=regional) 행."""
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import collect_moonlight_walk as cmw  # noqa: E402
import validate_csv  # noqa: E402

AS_OF = date(2026, 11, 28)


def post(log_no, title, brief=""):
    return {"logNo": log_no, "title": title, "brief": brief}


class ParseTitleTest(unittest.TestCase):
    def test_live_stage_title(self):
        self.assertEqual(cmw.parse_title("달빛산책 Live Stage 2026. 11. 21. 돌"), ("2026-11-21", ["돌"]))

    def test_part_number_is_dropped(self):
        self.assertEqual(cmw.parse_title("달빛산책 Live Stage 2026. 05. 01. 사나이 클럽 (3)"), ("2026-05-01", ["사나이 클럽"]))
        self.assertEqual(cmw.parse_title("달빛산책 Live Stage 2026. 11. 20. 구만회 (2)"), ("2026-11-20", ["구만회"]))

    def test_short_date_prefix_title(self):
        self.assertEqual(cmw.parse_title("260404 제요한 달빛산책 Live Stage"), ("2026-04-04", ["제요한"]))

    def test_several_acts(self):
        self.assertEqual(cmw.parse_title("달빛산책 Live Stage 2026. 10. 03. 에이, 비"), ("2026-10-03", ["에이", "비"]))

    def test_special_live_takes_date_from_text(self):
        got = cmw.parse_title("달빛산책 1주년 기념 Special Live Satomi & Morishita Duo",
                              "🎸 2026년 11월 14일 토요일, 1주년 기념 공연")
        self.assertEqual(got, ("2026-11-14", ["Satomi & Morishita Duo"]))

    def test_non_show_posts(self):
        self.assertIsNone(cmw.parse_title("달빛산책의 새로운 시작을 전합니다."))
        self.assertIsNone(cmw.parse_title("달빛산책 1주년 기념 Special Live 누구", "날짜 없는 글"))
        self.assertIsNone(cmw.parse_title("천안 대관 안내"))


class ArtistUrlTest(unittest.TestCase):
    def test_handle_right_after_name(self):
        self.assertEqual(cmw.artist_url("돌", "돌 @dol._.band Vocal & Guitar 최선규님 @nevv_0"),
                         "https://www.instagram.com/dol._.band/")
        self.assertEqual(cmw.artist_url("구만회", "멤버 소개 없음"), "")


class RowsTest(unittest.TestCase):
    def setUp(self):
        self.posts = [
            post(224492736848, "달빛산책 Live Stage 2026. 11. 21. 돌", "돌 @dol._.band"),
            post(224490000002, "달빛산책 Live Stage 2026. 11. 20. 구만회 (2)"),
            post(224490000001, "달빛산책 Live Stage 2026. 11. 20. 구만회"),
            post(223000000000, "달빛산책 Live Stage 2024. 10. 01. 옛팀"),     # 2년보다 오래됨
            post(224490000003, "달빛산책의 새로운 시작을 전합니다."),
        ]

    def test_rows_one_per_show_and_act_within_two_years(self):
        rows = cmw.rows_from_posts(self.posts, "2026-11-28T21:00:00+09:00", AS_OF)
        self.assertEqual([(r["gig_date"], r["artist_text"]) for r in rows], [("2026-11-20", "구만회"), ("2026-11-21", "돌")])
        gu = rows[0]
        self.assertEqual(gu["gig_url"], "https://blog.naver.com/moonlight_walk_bar/224490000001")  # 나눠 올린 글 중 첫 글
        self.assertEqual(gu["source"], "regional")
        self.assertEqual(gu["collector"], "aside")
        self.assertEqual(gu["source_id"], "moonlight_walk:224490000001")
        self.assertEqual(gu["venue_text"], cmw.VENUE_TEXT)
        self.assertEqual(rows[1]["artist_url"], "https://www.instagram.com/dol._.band/")

    def test_written_file_passes_format_check(self):
        rows = cmw.rows_from_posts(self.posts, "2026-11-28T21:00:00+09:00", AS_OF)
        with tempfile.TemporaryDirectory() as d:
            path = cmw.write_rows(rows, Path(d), "2026-11-28")
            self.assertTrue(path.name.startswith("raw_kr_gig_2026-11-28_regional"))
            errors = [i for i in validate_csv.validate_file(path) if i.level == "error"]
            self.assertEqual(errors, [])

    def test_page_script_reads_blog_api(self):
        js = cmw.page_js(3)
        self.assertIn("moonlight_walk_bar", js)
        self.assertIn("post-list", js)
        self.assertIn("RESULT ", js)


class ScheduleTitleTest(unittest.TestCase):
    def test_schedule_post(self):
        self.assertEqual(cmw.parse_show("🌙 2026.11.28 (토) JJJ Band – Live at 달빛산책"),
                         ("2026-11-28", "", ["JJJ Band"]))
        self.assertEqual(cmw.parse_show("2026.03.27 20:00 (금) 윤협 – Live at 달빛산책"), ("2026-03-27", "20:00", ["윤협"]))

    def test_split_acts_but_keep_ensembles_and_friends(self):
        self.assertEqual(cmw.parse_show("🌙 2026.11.21 (토) 셔츠 안 자켓 & 돌 – Live at 달빛산책")[2], ["셔츠 안 자켓", "돌"])
        self.assertEqual(cmw.parse_show("🌙 2026.07.11 (토) Trinity · 밴드희나 · 길거리베짱이 – Live at 달빛산책")[2],
                         ["Trinity", "밴드희나", "길거리베짱이"])
        self.assertEqual(cmw.parse_show("🌙 2026.08.22 (토) 홍태연 · 김의진 Quartet – Live at 달빛산책")[2], ["홍태연 · 김의진 Quartet"])
        self.assertEqual(cmw.parse_show("🌙 2026.07.18 (토) Jun_D & Friends – Live at 달빛산책")[2], ["Jun_D & Friends"])

    def test_bracket_names_pick_hangul_or_longer(self):
        self.assertEqual(cmw.parse_show("🌙 2026.10.23 (금) Min Paul (민폴) – Live at 달빛산책")[2], ["민폴"])
        self.assertEqual(cmw.parse_show("🌙 2026.07.31 (금) HSC (Highway Surf Club) – Live at 달빛산책")[2], ["Highway Surf Club"])
        self.assertEqual(cmw.parse_show("🌙 2026.05.30 (토) HWSC [Highway Surf Club] – Live at 달빛산책")[2], ["Highway Surf Club"])

    def test_open_jam_and_solo_clips_are_skipped(self):
        self.assertIsNone(cmw.parse_show("🌙 2026.06.28 (일) Moonlight Playground – Open Jam Session"))
        self.assertIsNone(cmw.parse_show("달빛산책 Live Stage Drum Solo · 양형석", "2026년 11월 6일 금요일 밤"))

    def test_anniversary_post_date_from_text(self):
        self.assertEqual(cmw.parse_show("달빛산책 1st Anniversary 첫번째 뮤지션 민타", "2026년 11월 7일 토요일, 1주년 공연"),
                         ("2026-11-07", "", ["민타"]))
        self.assertEqual(cmw.parse_show("달빛산책 1st Anniversary B.O.B (반오밴드)", "2026년 11월 7일, 마지막 무대")[2], ["반오밴드"])

    def test_same_act_across_posts_merges_ignoring_spaces(self):
        posts = [post(10, "🌙 2026.05.01 (금) 사나이클럽 – Live at 달빛산책"),
                 post(20, "달빛산책 Live Stage 2026. 05. 01. 사나이 클럽 (3)"),
                 post(5, "2026.03.27 20:00 (금) 윤협 – Live at 달빛산책")]
        rows = cmw.rows_from_posts(posts, "2026-11-28T21:00:00+09:00", AS_OF)
        self.assertEqual([(r["gig_date"], r["artist_text"], r["source_id"]) for r in rows],
                         [("2026-03-27", "윤협", "moonlight_walk:5"), ("2026-05-01", "사나이클럽", "moonlight_walk:10")])
        self.assertEqual(rows[0]["gig_time"], "20:00")


class CleanupTest(unittest.TestCase):
    def test_hangul_ampersand_splits_but_rnb_does_not(self):
        self.assertEqual(cmw.split_acts("숙희&재유"), ["숙희", "재유"])
        self.assertEqual(cmw.split_acts("김윤지 R&B Band"), ["김윤지 R&B Band"])

    def test_part_suffixes_are_dropped(self):
        self.assertEqual(cmw.split_acts("B.O.B (반오밴드) #2"), ["반오밴드"])
        self.assertEqual(cmw.split_acts("Min Paul (민폴) 2nd"), ["민폴"])

    def rows(self, posts):
        return [(r["gig_date"], r["artist_text"]) for r in cmw.rows_from_posts(posts, "2026-11-28T21:00:00+09:00", AS_OF)]

    def test_recap_with_wrong_date_is_dropped_when_schedule_exists(self):
        posts = [post(1, "🌙 2026.07.25 (토) Born2Blues – Live at 달빛산책"),
                 post(2, "🌙 2026.07.24 (금) 박지윤 Trio – Live at 달빛산책"),
                 post(3, "달빛산책 Live Stage 2026. 07. 24. Born2Blues")]
        self.assertEqual(self.rows(posts), [("2026-07-24", "박지윤 Trio"), ("2026-07-25", "Born2Blues")])

    def test_same_day_typo_spelling_and_pieces_merge(self):
        posts = [post(1, "🌙 2026.07.31 (금) HSC (Highway Surf Club) – Live at 달빛산책"),
                 post(2, "달빛산책 Live Stage 2026. 07. 31. Highwway Surf Club"),
                 post(3, "🌙 2026.05.29 (금) 김윤지 R&B Band – Live at 달빛산책"),
                 post(4, "달빛산책 Live Stage 2026. 05. 29. 김윤지 R&B밴드"),
                 post(5, "🌙 2026.08.22 (토) 홍태연 · 김의진 Quartet – Live at 달빛산책"),
                 post(6, "달빛산책 Live Stage 2026. 08. 22. 홍태연, 김의진 Quartet")]
        self.assertEqual(self.rows(posts), [("2026-05-29", "김윤지 R&B Band"), ("2026-07-31", "Highway Surf Club"),
                                            ("2026-08-22", "홍태연 · 김의진 Quartet")])


class MonthlyRerunTest(unittest.TestCase):
    def test_recap_of_saved_show_is_not_written_again(self):
        first = cmw.rows_from_posts([post(1, "🌙 2026.10.10 (토) 소면 – Live at 달빛산책"),
                                     post(2, "🌙 2026.10.31 (토) 이문혁 Quartet – Live at 달빛산책")],
                                    "2026-11-28T21:00:00+09:00", AS_OF)
        later = cmw.rows_from_posts([post(9, "달빛산책 Live Stage 2026. 10. 10. 소면"),          # 같은 공연 후기
                                     post(8, "달빛산책 Live Stage 2026. 10. 30. 이문혁 Quartet"),  # 날짜 어긋난 후기
                                     post(7, "🌙 2026.12.05 (토) 새팀 – Live at 달빛산책")],
                                    "2026-12-31T21:00:00+09:00", date(2026, 12, 31))
        with tempfile.TemporaryDirectory() as d:
            cmw.write_rows(first, Path(d), "2026-11-28")
            fresh = cmw.only_new_shows(later, Path(d))
        self.assertEqual([(r["gig_date"], r["artist_text"]) for r in fresh], [("2026-12-05", "새팀")])


if __name__ == "__main__":
    unittest.main()
