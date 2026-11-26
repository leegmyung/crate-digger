"""선정 명단 수집기(부산 루키즈·세종 뮤즈세종·경북 054사운드빌) 변환 로직 테스트 — 네트워크 없이."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import collect_selection as cs  # noqa: E402
import validate_csv  # noqa: E402

AT = "2026-11-26T21:00:00+09:00"
URL = "https://busanrockfestival.com/ROOKIES/"

BUSAN_TOP10 = """<div><p>🔥 &lt;2026 루키즈 온 더 부락&gt; TOP 10 발표 🔥</p>
<p>🤘 루키즈 온 더 부락 TOP 10 🤘</p>
<p>✶ 김푸름<br>✶ 데이네버체인지<br>✶ Eddie and the Bricks</p>
<p>*본 순서는 순위와 무관합니다.</p>
<p>🔥 TOP 10 Announcement of &lt;2026 Rookies on the BU-ROCK&gt; 🔥</p></div>"""

BUSAN_TOP3 = """<p>🔥 &lt;2026 루키즈 온 더 부락&gt; TOP 3 발표 🔥</p>
<p>🎸 TOP 1 : Eddie and the Bricks @eddieandthebricks</p>
<p>🎸 TOP 2 : 데이네버체인지 @theynevxrchange</p>
<p>🎸 TOP 3 : 아사달 @asadal_official</p>
<p>After the heated competition, They're the Top 3 of Rookies on the BU-ROCK.</p>
<p>🎸 TOP 1 : Eddie and the Bricks</p>"""

BUSAN_RECRUIT = "<p>&lt;2025 루키즈 온 더 부락&gt; 경연대회 참가자 모집</p><p>– 2차 심사(TOP 15) : 7. 13.(일)</p>"

SEJONG_HTML = """<ul class="hi_board_list artist-ver keep">
<li><a href="https://nurirock.or.kr:443/base/board/read?boardManagementNo=7&amp;boardNo=379&amp;page=1">
<img src="https://nurirock.or.kr:443/storage/board/artist/2026/04/28/ARTIST_IMAGE_1.jpg" alt="">
<p class="info_box-new"><span class="years-item">
   2026
 </span><span class="subject-item">키라라</span></p></a></li>
<li><a href="https://nurirock.or.kr:443/base/board/read?boardManagementNo=7&amp;boardNo=302&amp;page=1">
<p class="info_box-new"><span class="years-item">2025</span><span class="subject-item">언제(unjae)</span></p></a></li>
</ul>"""

GB_ITEMS = [
    {"date": "2026-11-17T11:51:57", "link": "https://054soundville.or.kr/project/a/", "title": {"rendered": "버닝룸[IGNITION]"}},
    {"date": "2024-12-26T10:00:00", "link": "https://054soundville.or.kr/project/b/", "title": {"rendered": "💿7번국도[Lover&#8217;s Rocksteady]"}},
    {"date": "2023-11-30T10:00:00", "link": "https://054soundville.or.kr/project/c/", "title": {"rendered": "💿 밴드 다미 [그대 안에 그린]"}},
    {"date": "2023-08-14T10:00:00", "link": "https://054soundville.or.kr/project/d/", "title": {"rendered": "널디나(nerdina) 💿 IN MY DREAMS!"}},
    {"date": "2026-01-08T10:00:00", "link": "https://054soundville.or.kr/project/e/", "title": {"rendered": "[LIVE CLIP] 여름밤잔디- 여행"}},
    {"date": "2023-01-04T10:00:00", "link": "https://054soundville.or.kr/project/f/", "title": {"rendered": "악단 어떤 🎬 [공연 스케치] 오늘"}},
    {"date": "2022-02-22T10:00:00", "link": "https://054soundville.or.kr/project/g/", "title": {"rendered": "정밀아 &#8211; 방랑"}},
    {"date": "2026-09-17T10:00:00", "link": "https://054soundville.or.kr/project/h/", "title": {"rendered": "2026 Class 054"}},
]


class BusanTest(unittest.TestCase):
    def test_top10_list(self):
        rows = cs.parse_busan(BUSAN_TOP10, URL, AT)
        self.assertEqual([r["artist_text"] for r in rows], ["김푸름", "데이네버체인지", "Eddie and the Bricks"])
        self.assertEqual({(r["round"], r["stage"], r["announced_at"]) for r in rows}, {("2026", "selected", "2026")})
        self.assertEqual(rows[0]["note"], "TOP 10")

    def test_top3_with_rank_and_no_english_duplicates(self):
        rows = cs.parse_busan(BUSAN_TOP3, URL, AT)
        self.assertEqual([(r["artist_text"], r["note"]) for r in rows],
                         [("Eddie and the Bricks", "TOP 1 @eddieandthebricks"),
                          ("데이네버체인지", "TOP 2 @theynevxrchange"),
                          ("아사달", "TOP 3 @asadal_official")])
        self.assertEqual(rows[0]["stage"], "final")

    def test_recruit_page_has_no_rows(self):
        self.assertEqual(cs.parse_busan(BUSAN_RECRUIT, URL, AT), [])

    def test_stage_by_top_size(self):
        self.assertEqual(cs.busan_stage(15), "document")
        self.assertEqual(cs.busan_stage(10), "selected")
        self.assertEqual(cs.busan_stage(3), "final")


class SejongTest(unittest.TestCase):
    def test_board_items(self):
        rows = cs.parse_sejong(SEJONG_HTML, AT)
        self.assertEqual([(r["round"], r["artist_text"], r["announced_at"]) for r in rows],
                         [("2026", "키라라", "2026-04"), ("2025", "언제(unjae)", "2025")])
        self.assertEqual(rows[0]["url"], "https://nurirock.or.kr/base/board/read?boardManagementNo=7&boardNo=379")
        self.assertEqual(rows[0]["program"], "muse_sejong")


class GyeongbukTest(unittest.TestCase):
    def test_only_album_results(self):
        rows = cs.parse_gb(GB_ITEMS, AT)
        self.assertEqual([(r["artist_text"], r["note"]) for r in rows],
                         [("버닝룸", "IGNITION"), ("7번국도", "Lover’s Rocksteady"),
                          ("밴드 다미", "그대 안에 그린"), ("널디나(nerdina)", "IN MY DREAMS!")])
        self.assertEqual((rows[0]["round"], rows[0]["announced_at"], rows[0]["stage"]), ("2026", "2026-11-17", "selected"))


class WriteTest(unittest.TestCase):
    def test_written_csv_passes_validator(self):
        rows = cs.parse_busan(BUSAN_TOP3, URL, AT) + cs.parse_sejong(SEJONG_HTML, AT) + cs.parse_gb(GB_ITEMS, AT)
        with tempfile.TemporaryDirectory() as d:
            path = cs.write_csv(rows, Path(d), "2026-11-26", "all")
            errs = [i for i in validate_csv.validate_file(path) if i.level == "error"]
        self.assertEqual(path.name, "raw_kr_selection_2026-11-26_all.csv")
        self.assertEqual(errs, [])

    def test_drop_seen_rows(self):
        rows = cs.parse_busan(BUSAN_TOP3, URL, AT)
        seen = {cs.row_key(rows[0])}
        self.assertEqual(len(cs.drop_seen(rows, seen)), 2)


if __name__ == "__main__":
    unittest.main()
