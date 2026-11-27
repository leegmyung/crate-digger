"""힙합엘이 국내 뉴스 수집기 변환 로직 — 네트워크·aside 없이, 실제 목록 페이지에서 잘라 온 조각으로."""
import csv
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import collect_hiphople as ch  # noqa: E402

AT = "2026-11-27T17:00:00+09:00"

LIST_HTML = """
<div class="wz-item"><a class="ab-link" href="/news_kr/33807172"></a>
 <div class="wz-item-header"><a href="/news_kr/33807172"><span class="title">다이나믹듀오, 싱글 “하라는 랩” 공개</span></a></div>
 <div class="wz-item-meta oloi "><span><span class="date">2026.11.22</span></span></div></div>
<div class="wz-item"><a class="ab-link" href="/news_kr/33807166"></a>
 <div class="wz-item-header"><a href="/news_kr/33807166"><span class="title">힙노시스테라피 &amp; 시온, 싱글 “FROG2” 공개</span></a></div>
 <div class="wz-item-meta oloi "><span><span class="date">2026.11.22</span></span></div></div>
<div class="wz-item"><a class="ab-link" href="/news_kr/33807100"></a>
 <div class="wz-item-header"><a href="/news_kr/33807100"><span class="title">쇼미더머니12, 2차 예선 결과 공개</span></a></div>
 <div class="wz-item-meta oloi "><span><span class="date">2026.11.21</span></span></div></div>
"""


class ListParseTest(unittest.TestCase):
    def test_items_with_id_title_date(self):
        items = ch.parse_list_html(LIST_HTML)
        self.assertEqual([i["id"] for i in items], ["33807172", "33807166", "33807100"])
        self.assertEqual(items[1]["title"], "힙노시스테라피 & 시온, 싱글 “FROG2” 공개")
        self.assertEqual(items[0]["date"], "2026-11-22")
        self.assertEqual(items[0]["url"], "https://hiphople.com/news_kr/33807172")

    def test_links_with_page_query(self):
        # 브라우저로 2쪽 이상을 읽으면 링크 끝에 ?page=N 이 붙어 온다 (2026-11-27 실제 실행에서 발견)
        items = ch.parse_list_html(LIST_HTML.replace('/news_kr/33807172"', '/news_kr/33807172?page=2"'))
        self.assertEqual(items[0]["id"], "33807172")
        self.assertEqual(items[0]["url"], "https://hiphople.com/news_kr/33807172")

    def test_empty_page(self):
        self.assertEqual(ch.parse_list_html("<html></html>"), [])


class TitleParseTest(unittest.TestCase):
    def test_release_titles(self):
        cases = {
            "다이나믹듀오, 싱글 “하라는 랩” 공개": (["다이나믹듀오"], "하라는 랩"),
            "힙노시스테라피 & 시온, 싱글 “FROG2” 공개": (["힙노시스테라피", "시온"], "FROG2"),
            "언텔 & 웨이체드, EP [VIEWSIC] 공개": (["언텔", "웨이체드"], "VIEWSIC"),
            "양홍원, 싱글  “EDENMATE+” 공개": (["양홍원"], "EDENMATE+"),
            "X33D (씨드), 정규 1집 [Seed] 발매": (["X33D (씨드)"], "Seed"),
            "A x B, 디지털 싱글 〈밤〉 공개": (["A", "B"], "밤"),
            "로얄44, EP [it’s only a game] 공개": (["로얄44"], "it’s only a game"),   # 제목 안 ’ (실제 사례)
            "양홍원, 판다곰 싱글 [오보] 공개": (["양홍원", "판다곰"], "오보"),           # 이름이 쉼표로 이어짐 (실제 사례)
            "빈첸, 예스코바 정규 앨범 [VIBA] 공개": (["빈첸", "예스코바"], "VIBA"),
        }
        for title, (artists, release) in cases.items():
            with self.subTest(title=title):
                got = ch.parse_title(title)
                self.assertEqual(got["artists"], artists)
                self.assertEqual(got["release_title"], release)

    def test_non_release_news_is_not_parsed(self):
        self.assertIsNone(ch.parse_title("쇼미더머니12, 2차 예선 결과 공개"))
        self.assertIsNone(ch.parse_title("한국힙합어워즈 2027 후보 발표"))
        self.assertIsNone(ch.parse_title("싱글 “무제” 공개"))                    # 쉼표 앞 이름 없음

    def test_label_names_are_dropped(self):
        self.assertIsNone(ch.parse_title("저스트뮤직, 컴필레이션 앨범 [J] 공개"))       # 레이블만 → 팀 없음
        self.assertEqual(ch.parse_title("A & 하이라이트레코즈, 싱글 “B” 공개")["artists"], ["A"])

    def test_too_long_name_part_is_rejected(self):
        self.assertIsNone(ch.parse_title("올해 가장 주목받는 신인 래퍼들의 합동 무대 프로젝트 팀, 싱글 “X” 공개"))


class RowsTest(unittest.TestCase):
    def test_rows_follow_raw_press_columns(self):
        items = ch.parse_list_html(LIST_HTML)
        rows, unparsed = ch.items_to_rows(items, AT)
        self.assertEqual([r["artist_text"] for r in rows], ["다이나믹듀오", "힙노시스테라피", "시온"])
        r = rows[1]
        self.assertEqual((r["source"], r["outlet"], r["collector"]), ("hiphople", "HIPHOPLE", "aside"))
        self.assertEqual((r["published_at"], r["release_title"], r["is_pick"]), ("2026-11-22", "FROG2", "0"))
        self.assertEqual(r["pick_label"], "국내 뉴스")
        self.assertEqual(set(r), set(ch.COLUMNS))
        self.assertEqual([u["id"] for u in unparsed], ["33807100"])

    def test_write_csv_header(self):
        rows, _ = ch.items_to_rows(ch.parse_list_html(LIST_HTML), AT)
        with tempfile.TemporaryDirectory() as d:
            path = ch.write_rows(rows, Path(d), "2026-11-27")
            with open(path, encoding="utf-8") as fh:
                got = list(csv.DictReader(fh))
        self.assertEqual(path.name, "raw_press_2026-11-27_hiphople.csv")
        self.assertEqual(len(got), 3)


class StateTest(unittest.TestCase):
    def test_new_items_stop_at_seen_and_since(self):
        items = ch.parse_list_html(LIST_HTML)
        state = {"seen": ["33807166"]}
        fresh, stop = ch.select_new(items, state, since="2026-11-01")
        self.assertEqual([i["id"] for i in fresh], ["33807172", "33807100"])
        self.assertFalse(stop)
        fresh, stop = ch.select_new(items, {"seen": []}, since="2026-11-22")
        self.assertEqual([i["id"] for i in fresh], ["33807172", "33807166"])
        self.assertTrue(stop)                                     # 기준일보다 오래된 글이 나오면 멈춤

    def test_state_roundtrip_and_next_page(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.json"
            self.assertEqual(ch.load_state(p), {"seen": [], "backfill_next_page": 1, "last_run": ""})
            st = ch.mark_seen(ch.load_state(p), ["1", "2"], backfill_next_page=3, today="2026-11-27")
            ch.save_state(p, st)
            again = ch.load_state(p)
        self.assertEqual(again["seen"], ["1", "2"])
        self.assertEqual(again["backfill_next_page"], 3)
        self.assertEqual(again["last_run"], "2026-11-27")


class CollectLoopTest(unittest.TestCase):
    def test_pages_until_empty_and_next_page(self):
        pages = {1: LIST_HTML, 2: LIST_HTML.replace("338071", "338070"), 3: ""}
        calls = []

        def fake_read(batch):
            calls.append(list(batch))
            return [{"page": p, "status": 200, "html": pages.get(p, "")} for p in batch]

        fresh, nxt = ch.collect(1, 10, "2026-01-01", {"seen": []}, read=fake_read)
        self.assertEqual(len(fresh), 6)                           # 1·2쪽 3건씩, 3쪽은 빈 쪽 → 멈춤
        self.assertEqual(nxt, 3)                                  # 다음 실행은 3쪽부터
        self.assertEqual(calls, [[1, 2, 3, 4, 5]])

    def test_failed_read_keeps_start_page(self):
        fresh, nxt = ch.collect(7, 2, "2026-01-01", {"seen": []}, read=lambda batch: None)
        self.assertEqual((fresh, nxt), ([], 7))


class GuardTest(unittest.TestCase):
    def test_evening_window_blocked(self):
        self.assertTrue(ch.in_blocked_window(datetime(2026, 11, 27, 21, 5, tzinfo=ch.KST)))
        self.assertTrue(ch.in_blocked_window(datetime(2026, 11, 27, 22, 59, tzinfo=ch.KST)))
        self.assertFalse(ch.in_blocked_window(datetime(2026, 11, 27, 23, 0, tzinfo=ch.KST)))
        self.assertFalse(ch.in_blocked_window(datetime(2026, 11, 27, 16, 0, tzinfo=ch.KST)))

    def test_list_js_waits_crawl_delay_and_uses_pages(self):
        js = ch.list_js([3, 4])
        self.assertIn("/news_kr?page=", js)
        self.assertIn(str(ch.CRAWL_DELAY_MS), js)
        self.assertIn("[3, 4]", js)


if __name__ == "__main__":
    unittest.main()
