"""페스티벌라이프(festivallife.kr) 국내 페스티벌 게시판 → 페스티벌·회차(날짜·장소·근거 글) 목록."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import collect_festivallife as cf  # noqa: E402

LIST_HTML = """
<a class="post_link_wrap _fade_link" href="/festival/?q=YTox&bmode=view&idx=174243065&t=board">
  <div class="title"> 공지 그랜드민트페스티벌 2026 - 최종 라인업 N </div></a>
<a class="post_link_wrap _fade_link" href="/festival/?q=YTox&bmode=view&idx=15132685&t=board">
  <div> 공지 인천 펜타포트 락 페스티벌 2023 - 1차 라인업 --> </div></a>
"""

POST_NEW = """<div>국내공연 캘린더</div><h1>그랜드민트페스티벌 2026 - 최종 라인업</h1>
<p>일정: 2026년 10월 17~18일 (토~일)</p><p>장소: 올림픽공원</p><p>가격: 1일권 132,000원</p>
<img src="https://cdn.imweb.me/upload/x/poster.jpg">"""
POST_OLD = """<p>공연 일정 : 2023년 8월 4~6일 (금~일)</p><p>공연 장소 : 인천 송도달빛축제공원</p>"""
POST_SPAN = """<p>일정: 2025년 9월 30일~10월 2일</p><p>장소: 부산 삼락생태공원</p>"""


class ParseTest(unittest.TestCase):
    def test_list(self):
        self.assertEqual(cf.parse_list(LIST_HTML), [("174243065", "그랜드민트페스티벌 2026 - 최종 라인업"),
                                                    ("15132685", "인천 펜타포트 락 페스티벌 2023 - 1차 라인업")])

    def test_title(self):
        self.assertEqual(cf.parse_title("그랜드민트페스티벌 2026 - 최종 라인업"), ("그랜드민트페스티벌", 2026, "최종 라인업"))
        self.assertEqual(cf.parse_title("2025 EDC KOREA - 개최 일정"), ("EDC KOREA", 2025, "개최 일정"))
        self.assertEqual(cf.parse_title("카운트다운판타지 26/27 - 2차 라인업"), ("카운트다운판타지", None, "2차 라인업"))
        self.assertEqual(cf.parse_title("DMZ 피스트레인 뮤직페스티벌 개최일정 공개!"), ("DMZ 피스트레인 뮤직페스티벌 개최일정 공개!", None, ""))

    def test_post_dates_and_venue(self):
        self.assertEqual(cf.parse_post(POST_NEW), {"dates": ["2026-10-17", "2026-10-18"], "venue": "올림픽공원",
                                                    "poster_images": 1})
        self.assertEqual(cf.parse_post(POST_OLD)["dates"], ["2023-08-04", "2023-08-05", "2023-08-06"])
        self.assertEqual(cf.parse_post(POST_OLD)["venue"], "인천 송도달빛축제공원")
        self.assertEqual(cf.parse_post(POST_SPAN)["dates"], ["2025-09-30", "2025-10-01", "2025-10-02"])

    def test_festival_key_merges_spellings(self):
        self.assertEqual(cf.festival_key("인천 펜타포트 락 페스티벌"), cf.festival_key("인천펜타포트락페스티벌"))
        self.assertEqual(cf.festival_key("그랜드민트페스티벌"), cf.festival_key("그랜드 민트 페스티벌"))


class CatalogTest(unittest.TestCase):
    def test_group_by_festival_and_year(self):
        posts = [
            {"idx": "1", "title": "그랜드민트페스티벌 2026 - 1차 라인업", "dates": [], "venue": "", "poster_images": 1},
            {"idx": "2", "title": "그랜드민트페스티벌 2026 - 최종 라인업", "dates": ["2026-10-17", "2026-10-18"],
             "venue": "올림픽공원", "poster_images": 1},
            {"idx": "3", "title": "그랜드 민트 페스티벌 2025 - 최종 라인업", "dates": ["2025-10-18"], "venue": "올림픽공원",
             "poster_images": 1},
            {"idx": "4", "title": "서울재즈페스티벌 2020 - 1차 라인업", "dates": ["2020-05-23"], "venue": "", "poster_images": 1},
            {"idx": "5", "title": "카운트다운판타지 26/27 - 2차 라인업", "dates": ["2026-12-31"], "venue": "", "poster_images": 1},
        ]
        cat = cf.build_catalog(posts, years=range(2021, 2027))
        gmf = cat[cf.festival_key("그랜드민트페스티벌")]
        self.assertEqual(sorted(gmf["editions"]), ["2025", "2026"])
        e = gmf["editions"]["2026"]
        self.assertEqual(e["dates"], ["2026-10-17", "2026-10-18"])
        self.assertEqual(e["venue"], "올림픽공원")
        self.assertEqual(len(e["posts"]), 2)
        self.assertTrue(e["posts"][0]["url"].startswith("https://www.festivallife.kr/festival/?bmode=view&idx="))
        self.assertFalse(e["lineup_text"])                     # 라인업은 포스터 그림뿐
        self.assertNotIn(cf.festival_key("서울재즈페스티벌"), cat)  # 2020 은 범위 밖
        self.assertIn("2026", cat[cf.festival_key("카운트다운판타지")]["editions"])   # 연도 없으면 첫 날짜의 해


if __name__ == "__main__":
    unittest.main()


class CrawlResumeTest(unittest.TestCase):
    def test_cached_posts_not_fetched_again(self):
        pages = {1: LIST_HTML, 2: LIST_HTML}
        calls = []

        def fake_fetch(url):
            calls.append(url)
            if "page=" in url:
                return pages.get(int(url.rsplit("=", 1)[1]), "")
            return POST_NEW
        cache = {"174243065": {"idx": "174243065", "title": "그랜드민트페스티벌 2026 - 최종 라인업",
                               "dates": ["2026-10-17"], "venue": "올림픽공원", "poster_images": 1}}
        posts = cf.crawl(5, [], fetch_fn=fake_fetch, cache=cache, pause=0)
        self.assertEqual([p["idx"] for p in posts], ["174243065", "15132685"])
        self.assertEqual(sum("bmode=view" in c for c in calls), 1)      # 캐시에 없는 글 1편만 읽음
        self.assertIn("15132685", cache)                                  # 새로 읽은 글은 캐시에 남음


class NameMergeTest(unittest.TestCase):
    def test_year_ranges_and_bilingual_names(self):
        k = cf.festival_key
        self.assertEqual(cf.parse_title("카운트다운판타지 COUNTDOWN FANTASY 2026-2027")[0:2], ("카운트다운판타지 COUNTDOWN FANTASY", None))
        self.assertEqual(k("카운트다운판타지 COUNTDOWN FANTASY"), k("카운트다운판타지"))
        self.assertEqual(k("Madly Medley 매들리 메들리"), k("매들리 메들리"))
        self.assertEqual(k("DMZ 피스트레인 뮤직 페스티벌"), k("DMZ 피스트레인 뮤직페스티벌"))
        self.assertNotEqual(k("XMF"), k("EDC KOREA"))


class NoSeparatorTitleTest(unittest.TestCase):
    def test_trailing_news_words_dropped(self):
        k = lambda t: cf.festival_key(cf.parse_title(t)[0])
        base = k("인천 펜타포트 락 페스티벌 2023 - 1차 라인업")
        for t in ("인천 펜타포트 락 페스티벌 개최 일정 공개", "인천 펜타포트 락 페스티벌 개최 확정", "﻿인천 펜타포트 락 페스티벌",
                  "[변경] 인천 펜타포트 락 페스티벌 2024 - 타임테이블"):
            self.assertEqual(k(t), base, t)
        self.assertEqual(k("부산국제록페스티벌 개최 일정 및 장소 공개!"), k("부산 국제 록 페스티벌 2025 - 최종 라인업"))
        self.assertEqual(k("뷰티풀 민트 라이프 추가 일정 전야제"), k("뷰티풀민트라이프 2023 - 최종 라인업"))
