"""멜론 트랙제로(인디 큐레이션) 수집기: 뮤직스토리 '#트랙제로' 글 목록 → 글마다 소개된 팀 (raw_press 형식)."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import collect_trackzero as tz  # noqa: E402

LIST_HTML = """
<li class="list_item"><div class="content"><div class="inner">
  <a href="javascript:goMstoryDetail('17404');">
    <p class="title ellipsis line_clamp2">11월 추천 신곡, 라우럴하게</p><!-- max line 2 -->
    <div class="bottom"><span class="date">2026.11.26</span></div></a></div></div></li>
<li class="list_item"><div class="content"><div class="inner">
  <a href="javascript:goMstoryDetail('17350');">
    <p class="title ellipsis line_clamp2">11월의 아티스트 김심야</p>
    <div class="bottom"><span class="date">2026.11.05</span></div></a></div></div></li>
<li class="list_item"><div class="content"><div class="inner">
  <a href="javascript:goMstoryDetail('13001');">
    <p class="title ellipsis line_clamp2">이달의 아티스트: Maria Kim (마리아 킴)</p>
    <div class="bottom"><span class="date">2023.02.02</span></div></a></div></div></li>
"""

DETAIL_HTML = """
<a href="javascript:pauseVideo();goDetail('artist', '5217456')" class="link-detail">
  <div class="info-content"><strong class="tit-content"><span class="txt-title">모로 (Moreau)</span></strong></div></a>
<a href="javascript:pauseVideo();goDetail('artist', '2740973')" class="link-detail">
  <div class="info-content"><strong class="tit-content"><span class="txt-title">ADOY</span></strong></div></a>
<a href="javascript:pauseVideo();goDetail('artist', '5217456')" class="link-detail">
  <div class="info-content"><strong class="tit-content"><span class="txt-title">모로 (Moreau)</span></strong></div></a>
<span class="screen-out">아티스트명 : </span>
<span class="txt-description ellipsis">Cosmic Chips</span>
<span class="screen-out">아티스트명 : </span>
<span class="txt-description ellipsis">ADOY</span>
"""


class ListTest(unittest.TestCase):
    def test_parse_list(self):
        got = tz.parse_list(LIST_HTML)
        self.assertEqual(got[0], {"seq": "17404", "title": "11월 추천 신곡, 라우럴하게", "date": "2026-11-26"})
        self.assertEqual([p["seq"] for p in got], ["17404", "17350", "13001"])

    def test_post_kind(self):
        self.assertEqual(tz.post_kind("11월의 아티스트 김심야"), "이달의 아티스트")
        self.assertEqual(tz.post_kind("이달의 아티스트: QM"), "이달의 아티스트")
        self.assertEqual(tz.post_kind("11월 추천 신곡, 라우럴하게"), "추천 신곡")
        self.assertEqual(tz.post_kind("트랙제로 추천 신곡"), "추천 신곡")
        self.assertEqual(tz.post_kind("Hello, 12 Rookies!"), "기획")
        # 공연 후기·라이브클럽데이 안내는 공연 홍보라 큐레이션 신호로 안 씀
        self.assertEqual(tz.post_kind("트랙제로 Alive Vol.13 이달의 아티스트 강허달림 공연 후기"), "공연")
        self.assertEqual(tz.post_kind("올해의 마지막 라이브 동선: '제85회 라이브클럽데이'"), "공연")

    def test_month_artist_from_title(self):
        self.assertEqual(tz.month_artist("11월의 아티스트 김심야"), "김심야")
        self.assertEqual(tz.month_artist("이달의 아티스트: Maria Kim (마리아 킴)"), "Maria Kim (마리아 킴)")
        self.assertEqual(tz.month_artist("10월의 아티스트 jisokuryClub"), "jisokuryClub")
        self.assertEqual(tz.month_artist("11월 추천 신곡"), "")


class DetailTest(unittest.TestCase):
    def test_artists_with_melon_ids_then_names_without(self):
        self.assertEqual(tz.parse_detail(DETAIL_HTML),
                         [("모로 (Moreau)", "5217456"), ("ADOY", "2740973"), ("Cosmic Chips", "")])

    def test_names_without_letters_dropped(self):   # 2023-03 추천 신곡 글에 이름이 '-'인 연관 아티스트가 있었음
        html = """<a href="javascript:goDetail('artist', '2018879')"><span class="txt-title">-</span></a>"""
        self.assertEqual(tz.parse_detail(html), [])

    def test_short_ids_dropped(self):
        html = """<a href="javascript:goDetail('artist', '82')"><span class="txt-title">D82</span></a>"""
        self.assertEqual(tz.parse_detail(html), [("D82", "")])


class RowsTest(unittest.TestCase):
    def test_month_artist_post_uses_title_artist_only(self):
        post = {"seq": "17350", "title": "11월의 아티스트 김심야", "date": "2026-11-05"}
        rows = tz.post_rows(post, [("김심야", "1234567"), ("손심바", "2345678")], "2026-11-27T18:00:00+09:00")
        self.assertEqual([r["artist_text"] for r in rows], ["김심야"])
        r = rows[0]
        self.assertEqual((r["source"], r["outlet"], r["collector"], r["published_at"]),
                         ("trackzero", "멜론 트랙제로", "script", "2026-11-05"))
        self.assertEqual((r["is_pick"], r["pick_label"]), ("1", "이달의 아티스트"))
        self.assertTrue(r["url"].endswith("mstorySeq=17350"))

    def test_playlist_post_one_row_per_artist(self):
        post = {"seq": "17404", "title": "11월 추천 신곡, 라우럴하게", "date": "2026-11-26"}
        rows = tz.post_rows(post, [("모로 (Moreau)", "5217456"), ("ADOY", "2740973")], "t")
        self.assertEqual([(r["artist_text"], r["is_pick"], r["pick_label"]) for r in rows],
                         [("모로 (Moreau)", "1", "추천 신곡"), ("ADOY", "1", "추천 신곡")])

    def test_theme_post_is_not_pick_and_gig_post_skipped(self):
        theme = {"seq": "1", "title": "1970-80년대 한국 전자음악", "date": "2026-10-15"}
        self.assertEqual(tz.post_rows(theme, [("신중현", "")], "t")[0]["is_pick"], "0")
        gig = {"seq": "2", "title": "제85회 라이브클럽데이", "date": "2026-11-10"}
        self.assertEqual(tz.post_rows(gig, [("A", "")], "t"), [])


class StateTest(unittest.TestCase):
    def test_new_posts_and_melon_ids(self):
        posts = tz.parse_list(LIST_HTML)
        state = {"seen": ["17404"], "melon_ids": {}}
        self.assertEqual([p["seq"] for p in tz.new_posts(posts, state)], ["17350", "13001"])
        st = tz.mark_seen(state, ["17350"], {"김심야": "1234567"}, "2026-11-27")
        self.assertEqual(st["seen"], ["17404", "17350"])
        self.assertEqual(st["melon_ids"], {"김심야": "1234567"})
        self.assertEqual(state["seen"], ["17404"])          # 원래 상태는 그대로

    def test_write_rows_new_file_when_exists(self):
        with tempfile.TemporaryDirectory() as d:
            p1 = tz.write_rows([{"artist_text": "a"}], Path(d), "2026-11-27")
            p2 = tz.write_rows([{"artist_text": "b"}], Path(d), "2026-11-27")
            self.assertEqual(p1.name, "raw_press_2026-11-27_trackzero.csv")
            self.assertNotEqual(p1, p2)


if __name__ == "__main__":
    unittest.main()
