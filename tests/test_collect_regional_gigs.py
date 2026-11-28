import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import collect_regional_gigs as crg  # noqa: E402
import collect_regional_lineups as crl  # noqa: E402
from csv_schema import TABLES  # noqa: E402
from validate_csv import validate_file  # noqa: E402

LIST_HTML = """
<div class="show-list__mid__item"><div class="show-list__mid__item__cont"> [ 예매중 ]
<h3 class="show-list__mid__item__cont__tit">디깅라이브세종 [ep23] 우희준</h3>
<p class="show-list__mid__item__cont__date"> 2026.11.28 </p>
<dl class="dl_type"><dt>주최</dt><dd>세종시</dd><dt>공연장소</dt><dd>세종음악창작소 공연장</dd></dl></div>
<div class="show-list__mid__item__btn-box">
<a href="https://www.nurirock.or.kr:443/base/nrr/performance/read?performanceNo=169&amp;menuLevel=2&amp;menuNo=31">상세보기</a>
</div></div>
<div class="show-list__mid__item"><div class="show-list__mid__item__cont">
<h3 class="show-list__mid__item__cont__tit">[일반예매] 2026 세종보헤미안뮤직페스티벌</h3>
<p class="show-list__mid__item__cont__date"> 2026.10.30
   ~
   2026.11.01 </p>
<dl class="dl_type"><dt>공연장소</dt><dd>세종중앙공원 도시축제마당</dd></dl></div>
<div class="show-list__mid__item__btn-box">
<a href="https://www.nurirock.or.kr:443/base/nrr/performance/read?performanceNo=173&amp;menuNo=31">상세보기</a>
</div></div>
"""


class ParseListTest(unittest.TestCase):
    def test_reads_title_dates_place_and_number(self):
        items = crg.parse_nurirock_list(LIST_HTML)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0], {"no": "169", "title": "디깅라이브세종 [ep23] 우희준", "start": "2026-11-28",
                                    "end": "2026-11-28", "place": "세종음악창작소 공연장"})
        self.assertEqual(items[1]["start"], "2026-10-30")
        self.assertEqual(items[1]["end"], "2026-11-01")

    def test_empty_page_gives_no_items(self):
        self.assertEqual(crg.parse_nurirock_list("<html></html>"), [])


class PerformersFromTitleTest(unittest.TestCase):
    def check(self, title, expected):
        self.assertEqual(crg.performers_from_title(title), expected, title)

    def test_digging_live(self):
        self.check("디깅라이브세종 [ep23] 우희준", ["우희준"])
        self.check("디깅 라이브 세종 (ep1)  ADOY(아도이)", ["ADOY"])
        self.check("디깅라이브세종 [ep16] 쏠X소울딜리버리", ["쏠", "소울딜리버리"])
        self.check("디깅라이브세종 [ep17] 3호선 버터플라이", ["3호선 버터플라이"])

    def test_muse_showcase_and_monthly(self):
        self.check("2026 뮤즈세종 쇼케이스 올디 벗 구디 <Overture>", ["올디 벗 구디"])
        self.check("2024 뮤즈세종 쇼케이스 양치기소년단 <EARTH WIND ＆ SHEPHERD>", ["양치기소년단"])
        self.check("월간 누리락 Vol.13 '엠관 앤 리엘'", ["엠관 앤 리엘"])
        self.check("월간 누리락 Vol.11 'ㅈ(지읒)'", ["지읒"])      # 한 글자 이름은 괄호 속 표기로

    def test_program_name_is_not_a_team(self):
        self.check("뮤즈세종 단독공연<송선호 재즈쿼텟 '사계'>", [])
        self.check("뮤즈세종 단독공연 <윤슬로의 구름꽂이>", [])

    def test_solo_concert_and_tour(self):
        self.check("양말서랍 단독콘서트 '선택과 집중'", ["양말서랍"])
        self.check("브로콜리너마저 전국투어 콘서트 '이른열 대야 : 전국 인디-자랑!'", ["브로콜리너마저"])

    def test_skips_non_live_or_multi_act(self):
        for title in ("바이닐 스튜디오 [11월의 ARCHIVING : 신해철]", "2026 대중음악아카데미 - 키라라의 라이브시퀀싱",
                      "[일반예매] 2026 세종보헤미안뮤직페스티벌", "2026년 누리락밴드 합동공연",
                      "디깅 라이브 세종 2차 패키지(세종시민 선예매)", "2026 지역&전국 음악창작소 교류공연 in 세종"):
            self.check(title, [])


class VenueTextTest(unittest.TestCase):
    def test_nurirock_places_become_one_venue_with_address(self):
        for place in ("세종음악창작소 공연장", "세종음악창작소 누리락", "누리락 공연장", "세종음악창작소 스튜디오"):
            self.assertEqual(crg.nurirock_venue_text(place), crg.NURIROCK_VENUE)

    def test_other_places_keep_name(self):
        self.assertEqual(crg.nurirock_venue_text("서울마포음악창작소 라이브홀"), "서울마포음악창작소 라이브홀")


class RowsTest(unittest.TestCase):
    def test_title_rows_follow_schema(self):
        items = crg.parse_nurirock_list(LIST_HTML)
        rows = crg.rows_from_nurirock(items, "2026-11-28T15:00:00+09:00")
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["artist_text"], "우희준")
        self.assertEqual(r["gig_date"], "2026-11-28")
        self.assertEqual(r["venue_text"], crg.NURIROCK_VENUE)
        self.assertTrue(r["gig_url"].startswith("https://www.nurirock.or.kr/base/nrr/performance/read?performanceNo=169"))
        self.assertEqual(set(r), {f.name for f in TABLES["raw_kr_gig"]["fields"]})

    def test_lineup_rows_have_order_time_and_size(self):
        event = crl.Event("2026-06-27", "2026 세종보헤미안스테이지", crl.SEJONG_ARTS_CENTER, "https://example.com/e",
                          (("양치기소년단", "14:30"), ("우희준", "15:10")))
        rows = crg.rows_from_lineups([event], "2026-11-28T15:00:00+09:00")
        self.assertEqual([r["lineup_order"] for r in rows], ["1", "2"])
        self.assertEqual(rows[1]["lineup_time"], "15:10")
        self.assertEqual(rows[0]["lineup_size"], "2")

    def test_written_file_passes_validator(self):
        rows = crg.rows_from_lineups(crl.EVENTS, "2026-11-28T15:00:00+09:00")
        with tempfile.TemporaryDirectory() as d:
            path = crg.write_csv(rows, Path(d), "2026-11-28")
            self.assertEqual([i for i in validate_file(path) if i.level == "error"], [])
            with open(path, encoding="utf-8") as f:
                self.assertEqual(len(list(csv.DictReader(f))), len(rows))

    def test_dedupes_same_key(self):
        rows = crg.rows_from_lineups([crl.EVENTS[0], crl.EVENTS[0]], "2026-11-28T15:00:00+09:00")
        self.assertEqual(len(crg.dedupe(rows)), len(crl.EVENTS[0].acts))


class LineupDataTest(unittest.TestCase):
    def test_every_event_has_date_venue_source_and_acts(self):
        for e in crl.EVENTS:
            self.assertRegex(e.day, r"^\d{4}-\d{2}-\d{2}$")
            self.assertTrue(e.venue_text and e.url.startswith("https://") and e.acts, e)
            for name, start in e.acts:
                self.assertTrue(name.strip(), e)
                self.assertRegex(start or "00:00", r"^\d{2}:\d{2}$")


if __name__ == "__main__":
    unittest.main()
