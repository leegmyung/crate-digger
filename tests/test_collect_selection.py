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

    def test_seen_on_date_used_as_announced(self):
        rows = cs.parse_busan(BUSAN_TOP10, URL, AT, seen_on="2026-08-13")
        self.assertEqual({r["announced_at"] for r in rows}, {"2026-08-13"})

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


YJH_HTML = """<h4><strong>제 36회 유재하 음악경연대회</strong></h4><hr><table class="noBorder"><tbody>
<tr><td><strong>대상</strong><br></td><td>OU:RE(아우리) &lt;니가 보낸 기프티콘&gt;<br></td></tr>
<tr><td><strong>금상</strong><br></td><td>전유동 &lt;스피리아&gt;<br></td></tr>
<tr><td style="vertical-align: top;"><strong>동상</strong><br></td><td>누에&lt;내게 하려했던 말&gt;<br>박레안 &lt;졸업사&gt;</td></tr>
<tr><td><strong>유재하동문상</strong><br></td><td>전유동 &lt;스피리아&gt;<br></td></tr></tbody></table>
<h4><strong><span>제 1회 유재하음악경연대회</span></strong></h4><hr><table><tbody>
<tr><td><span><strong>금상</strong></span></td><td><span>조규찬 &lt;무지개&gt;<br></span></td></tr>
<tr><td><span><strong>은상</strong></span></td><td><span>정혜선<span>&nbsp;&lt;나의 하</span>늘&gt;</span></td></tr></tbody></table>"""


class YoojaehaTest(unittest.TestCase):
    def test_rounds_names_and_merged_awards(self):
        rows = cs.parse_yjh(YJH_HTML, AT)
        got = [(r["round"], r["announced_at"], r["artist_text"], r["note"]) for r in rows]
        self.assertEqual(got, [("36회", "2025", "OU:RE(아우리)", "대상"), ("36회", "2025", "전유동", "금상, 유재하동문상"),
                               ("36회", "2025", "누에", "동상"), ("36회", "2025", "박레안", "동상"),
                               ("1회", "1989", "조규찬", "금상"), ("1회", "1989", "정혜선", "은상")])
        self.assertEqual({(r["program"], r["stage"], r["source"]) for r in rows}, {("yoojaeha_finalist", "selected", "yjh")})

    def test_round_split_into_two_tables(self):   # 14회는 대상 표와 나머지 표가 따로 있음
        page = ("<h4>제 14회 유재하음악경연대회</h4><table><tr><td><strong>대상</strong></td><td>유경옥(유해인) &lt;혼자 걷는 길&gt;</td></tr></table>"
                "<table><tr><td><strong>금상</strong></td><td><p>이화동네 친구들 &lt;황당&gt;</p></td></tr></table>")
        self.assertEqual([r["artist_text"] for r in cs.parse_yjh(page, AT)], ["유경옥(유해인)", "이화동네 친구들"])

    def test_round_year(self):
        self.assertEqual((cs.yjh_year(1), cs.yjh_year(16), cs.yjh_year(17), cs.yjh_year(36)), (1989, 2004, 2006, 2025))


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
