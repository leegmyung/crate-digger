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
            # 옛 글 형식 (2023~2026 실제 제목)
            "재달, [안개 속의 JDL] 공개": (["재달"], "안개 속의 JDL"),
            "수퍼비, 신보 [before the m.s.g.a] 발매": (["수퍼비"], "before the m.s.g.a"),
            "머디레드, 새 싱글 \"LOGIC\" 발표": (["머디레드"], "LOGIC"),
            "루피, 정규 2집 선공개 싱글 \"MOVING\" 발표": (["루피"], "MOVING"),
            "비프리, “네르갈” 뮤직비디오 공개": (["비프리"], "네르갈"),
            "기리보이, 씨잼, 블랙넛, EP [asdf] 공개": (["기리보이", "씨잼", "블랙넛"], "asdf"),
            "최예나 & 나우아임영 싱글 “보기 드문 여자” 공개": (["최예나", "나우아임영"], "보기 드문 여자"),
            "에픽하이 X 다비치, 싱글 “미장센” 발매 예고": (["에픽하이", "다비치"], "미장센"),
            "우슬라임 X 매튜, 합작 트랙리스트 공개": (["우슬라임", "매튜"], ""),
            "버벌진트, [10년동안의오독 II] 발매 예고": (["버벌진트"], "10년동안의오독 II"),
            "스카이민혁, 10월 6일 정규 앨범 발매 예고": (["스카이민혁"], ""),
            "드루보이, 정식 데뷔 싱글 \"All I Want Is You\" 발표": (["드루보이"], "All I Want Is You"),
            "아우릴고트, 경제환과 함께한 싱글 \"SAVE ME\" 발표": (["아우릴고트", "경제환"], "SAVE ME"),
            "pH-1, 믹스테입 [POP OFF] 발표": (["pH-1"], "POP OFF"),
            "로꼬, 우원재와 함께한 \"BROKEN IPHONE\" M/V 공개": (["로꼬", "우원재"], "BROKEN IPHONE"),
        }
        for title, (artists, release) in cases.items():
            with self.subTest(title=title):
                got = ch.parse_title(title)
                self.assertEqual(got["artists"], artists)
                self.assertEqual(got["release_title"], release)

    def test_non_release_news_is_not_parsed(self):
        for title in ("김하온, 앨범 컨셉 포토 공개", "에픽하이, ‘EPIKASE 가요제’ 본선 음원 공개",
                      "앰비션 10주년 기념 \"RED ALERT\" 공개", "로얄44, 유튜브 채널 <로얄왕국> 개설",
                      "40대 유명 래퍼, 마약류 투약 혐의", "그루비룸, 하이브 신인 튜이드 전곡 프로듀싱",
                      "DJ 펌킨, AOMG 대표이사직 사임", "하이어뮤직, 컴필레이션 [PINK TAPE] 공개"):
            with self.subTest(title=title):
                self.assertIsNone(ch.parse_title(title))
        self.assertIsNone(ch.parse_title("쇼미더머니12, 2차 예선 결과 공개"))
        self.assertIsNone(ch.parse_title("한국힙합어워즈 2027 후보 발표"))
        self.assertIsNone(ch.parse_title("싱글 “무제” 공개"))                    # 쉼표 앞 이름 없음

    def test_label_names_are_dropped(self):
        self.assertIsNone(ch.parse_title("저스트뮤직, 컴필레이션 앨범 [J] 공개"))       # 레이블만 → 팀 없음
        self.assertEqual(ch.parse_title("A & 하이라이트레코즈, 싱글 “B” 공개")["artists"], ["A"])

    def test_too_long_name_part_is_rejected(self):
        self.assertIsNone(ch.parse_title("올해 가장 주목받는 신인 래퍼들의 합동 무대 프로젝트 팀, 싱글 “X” 공개"))


class ClauseTest(unittest.TestCase):
    """제목 속 수식 문구(합류·입단·통해·피처링한·함께한·와의·및 …)를 팀 이름으로 넣지 않는다 — 2026-11-27 점검에서 46개가 팀 표에 섞였음.
    문구만 떼고 진짜 팀(쉼표 앞)은 살린다. 함께한·피처링한 앞의 이름은 함께한 팀으로 살린다."""

    def test_clause_pieces_dropped_names_kept(self):
        cases = {
            "미노이, AOMG 합류 및 싱글 \"어떨것같애\" 발표": ["미노이"],
            "칸, 영앤리치 레코즈 입단 및 더블 싱글 [Night In Seoul] 발표": ["칸"],
            "에이블(장현승), 마인필드 입단 후 첫 싱글 \"Feeling\" 발표": ["에이블(장현승)"],
            "지용, 마인필드 입단과 함께 새 싱글 “건물주의 아들” 발표": ["지용"],
            "잠비노, 에잇볼타운 합류와 함께 새 싱글 “24 Close-up” 발표": ["잠비노"],
            "유스 호스텔, '더 씨드' 프로젝트 통해 첫 정규 앨범 [Youth Hostel] 발표": ["유스 호스텔"],
            "양홍원, 사운드클라우드를 통해 신곡 “수도” 공개": ["양홍원"],
            "pH-1, \"BE !\" 데모 벌스 사운드클라우드 통해 공개": ["pH-1"],
            "김심야, [Dogma] 뮤직비디오 깜짝 공개": ["김심야"],
            "빈지노, [NOWITZKI] 발매 일자 및 피처링진 공개": ["빈지노"],
            "식케이 & 김하온, [ALBUM ON THE WAY!] 앨범 커버 및 트랙리스트 공개": ["식케이", "김하온"],
            "소울커넥션, 14년 만의 싱글 \"제로힙합\" 발표": ["소울커넥션"],
            "손자 보이 텔럼, 개명 후 첫 싱글 \"Sonza Boy Tell'em\" 발표": ["손자 보이 텔럼"],
            "커프, 루피와의 협업 싱글 \"Silence\" 발표": ["커프"],
            "김심야, 패션브랜드 쿠시코크와의 협업 공개": ["김심야"],
            "DJ 스패로우, EP의 선공개 싱글 “커피” 발표": ["DJ 스패로우"],
            "안경쟁이, 372, 십 선 비, 일리네어 트리뷰트 앨범 [SILLIM1LLIONAIRE] 발표": ["안경쟁이", "372", "십 선 비"],
            "말든 X 보 디아코 X 벤 에서, 합작 싱글 \"Qiller\" 발표": ["말든", "보 디아코"],
            "이그니토, LBNC 합류 후 차붐과의 합작 싱글 “Shocking Asia” 발표": ["이그니토"],
            "비아이, 드비타 피처링한 솔쟈보이와의 콜라보 트랙 “BTBT” 발표": ["비아이"],
        }
        for title, artists in cases.items():
            with self.subTest(title=title):
                self.assertEqual(ch.parse_title(title)["artists"], artists)

    def test_partner_and_featuring_names_kept(self):
        cases = {
            "스프레이, 로꼬와 문수진 등이 함께한 싱글 \"Love\" 발표": ["스프레이", "로꼬", "문수진"],
            "NSW 윤, AJ 트레이시와 함께 한 싱글 \"Flip Flap\" 발표": ["NSW 윤", "AJ 트레이시"],
            "코스믹보이, 쏠과 다운 함께한 신곡 “Alone” 발표": ["코스믹보이", "쏠", "다운"],
            "노브, 양다일 함께한 새 싱글 “언제까지나” 발표": ["노브", "양다일"],
            "미카엘, 언텔 피처링한 정규 앨범 선공개 싱글 “SZN 2022” 발표": ["미카엘", "언텔"],
            "베이스캠프, 죠지 피처링의 새 싱글 “방황” 발표": ["베이스캠프", "죠지"],
            "박찬과 24Oz의 합작 앨범 [밤고개 블루스] 발매": ["박찬", "24Oz"],
            "안병웅 X 최유정의 합작 트랙 “어라?” 발표": ["안병웅", "최유정"],
        }
        for title, artists in cases.items():
            with self.subTest(title=title):
                self.assertEqual(ch.parse_title(title)["artists"], artists)

    def test_fullwidth_ampersand_splits(self):
        got = ch.parse_title("릴체리＆골드부다, 재키와이 피처링한 “꿈” 뮤직비디오 공개")
        self.assertEqual(got["artists"], ["릴체리", "골드부다", "재키와이"])
        self.assertEqual(ch.parse_title("'FLOAT' ＆ 'SOO4', 싱글 “X” 공개")["artists"], ["FLOAT", "SOO4"])   # 이름을 감싼 따옴표는 뗌

    def test_real_names_ending_like_particles_survive(self):
        self.assertEqual(ch.parse_title("시후, 새 EP [Candid] 발표")["artists"], ["시후"])
        self.assertEqual(ch.parse_title("나후, 싱글 “밤” 공개")["artists"], ["나후"])

    def test_only_clause_means_not_parsed(self):
        self.assertIsNone(ch.parse_title("AOMG 합류 및 싱글 \"X\" 발표"))


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


class ReparseTest(unittest.TestCase):
    def test_items_log_append_and_reparse(self):
        items = ch.parse_list_html(LIST_HTML)
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "items.jsonl"
            ch.append_items(log, items[:2])
            ch.append_items(log, items[1:])                       # 겹친 글은 다시 읽을 때 하나로
            back = ch.read_items(log)
            unparsed_path = Path(d) / "u.json"
            ch.merge_unparsed(unparsed_path, [items[2]])
            ch.merge_unparsed(unparsed_path, [items[2], items[0]])
            merged = ch.read_items(unparsed_path)
        self.assertEqual([i["id"] for i in back], ["33807172", "33807166", "33807100"])
        self.assertEqual(sorted(i["id"] for i in merged), ["33807100", "33807172"])


class ReparseOutTest(unittest.TestCase):
    def test_reparse_writes_new_file_and_compares(self):
        items = [{"id": "1", "title": "미노이, AOMG 합류 및 싱글 \"어떨것같애\" 발표", "date": "2024-01-01",
                  "url": "https://hiphople.com/news_kr/1"},
                 {"id": "2", "title": "다이나믹듀오, 싱글 “하라는 랩” 공개", "date": "2024-01-02",
                  "url": "https://hiphople.com/news_kr/2"}]
        old_rows = [{"artist_text": "미노이"}, {"artist_text": "AOMG 합류 및"}, {"artist_text": "다이나믹듀오"}]
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "items.jsonl"
            ch.append_items(log, items)
            out = Path(d) / "reparse.csv"
            report = ch.reparse(log, datetime(2026, 11, 28, 1, 0), out=out, old_rows=old_rows)
            self.assertTrue(out.exists())
            with open(out, encoding="utf-8") as f:
                names = sorted(r["artist_text"] for r in csv.DictReader(f))
        self.assertEqual(names, ["다이나믹듀오", "미노이"])
        self.assertEqual(report["removed"], ["AOMG 합류 및"])
        self.assertEqual(report["added"], [])


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

    def test_since_boundary_page_is_kept(self):
        fake = lambda batch: [{"page": p, "status": 200, "html": LIST_HTML} for p in batch]   # noqa: E731
        fresh, nxt = ch.collect(5, 10, "2026-11-22", {"seen": []}, read=fake)
        self.assertEqual((len(fresh), nxt), (2, 5))               # 5쪽에 기준일보다 오래된 글 → 멈추고 다음도 5쪽

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
