"""KT&G 상상마당 공연 목록 수집기 변환 로직 테스트 — 인터넷 없이 가상 데이터로."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import collect_ssm_shows as ssm  # noqa: E402
import validate_csv  # noqa: E402

AT = "2026-11-26T18:00:00+09:00"


def item(**kw):
    base = {"contentsSeq": 3188, "title": "신해경 단독 콘서트 나의 가역반응 사가 - 서울, 부산",
            "performanceLocation": "KT&amp;G 상상마당 부산 3F 라이브홀", "spaceCd": "BS",
            "startDt": "20261121", "term": "2026.11.21~2026.11.21", "cdVal": "콘서트",
            "genreTxt": "", "status": "end"}
    base.update(kw)
    return base


DETAIL = """
<table><tr><th class="center" scope="row">시간</th>
<td>
      18:00~19:40
   <br/>(러닝타임 100분)</td></tr>
<tr><th class="center" scope="row">장소</th><td>KT&amp;G 상상마당 부산 3F 라이브홀</td></tr></table>
<a>공유하기</a>
<div class="detail_txt"><p>&#39;술&#39; 기로운 직장생활 제 3탄</p>
<p>일시: 2018년 7월 3일 (화) 20:00</p>
<p>출연: 몽니, 데이브레이크&amp;nbsp;</p>
<p>티켓: 스탠딩 예매 35,000원</p></div>
<a href="#">목록</a>
"""


class TitlePerformerTest(unittest.TestCase):
    def check(self, title, expected):
        self.assertEqual(ssm.performers_from_title(title), expected, title)

    def test_solo_concert_patterns(self):
        self.check("신해경 단독 콘서트 나의 가역반응 사가 - 서울, 부산", ["신해경"])
        self.check("2025 이랑 단독공연 &lt;SHAME&gt; 스탠딩", ["이랑"])
        self.check("먼데이프로젝트 시즌7 BUSAN［허회경 단독 콘서트］", ["허회경"])
        self.check("킹스턴 루디스카 20주년 단독 콘서트", ["킹스턴 루디스카"])
        self.check("빌리카터 2017 단독콘서트 We Can Fight", ["빌리카터"])

    def test_tour_release_and_season_patterns(self):
        self.check("아일 전국투어 &lt;HERE I&#39;ll AM&gt; 서울", ["아일"])
        self.check("hathaw9y 정규 2집 Lovers 발매공연 [LOVERS] : 부산", ["hathaw9y"])
        self.check("친친탱고 정규 1집 쇼케이스 ［Tango del Mar］ - 부산", ["친친탱고"])
        self.check("9와 숫자들 2024 가을콘서트 &lsquo;높은 마음으로 살아야지&rsquo; - 부산", ["9와 숫자들"])
        self.check("[SANGSANGSOUNDS] 2024 브로콜리너마저 연말공연 - 매일 새롭게 태어나는 꿈", ["브로콜리너마저"])
        self.check("2026 유리상자 콘서트 &lt;꽃을 든 상자&gt;", ["유리상자"])
        self.check("장범준 여름 클럽 투어 in 부산 Day 1", ["장범준"])
        self.check("찰리빈웍스 부산 단독공연 '봄소풍'", ["찰리빈웍스"])
        self.check("위위 첫 번째 단독 콘서트 'HANA'", ["위위"])
        self.check("2022 이랑 연말 단독 공연 <PRIDE>", ["이랑"])

    def test_whole_title_wins_over_bracket_subtitle(self):
        self.check("전기뱀장어 단독 콘서트 [엣큥, 지각이다...! 콘서트]", ["전기뱀장어"])
        self.check("먼데이프로젝트 시즌8 : Try Again [안다영 단독 콘서트]", ["안다영"])

    def test_series_and_pair_patterns(self):
        self.check("상상스테이지 070 :  BORABORA (보라보라)", ["BORABORA"])
        self.check("스테이플러 x 자그마치", ["스테이플러", "자그마치"])
        self.check("러브레이크 X 자라섬", [])   # 러브레이크는 춘천 기획 시리즈 이름이라 팀이 아님
        self.check("허클베리핀 17th 옐로우 콘서트", [])
        self.check("SSHOWBOX 초승 단독 공연", ["초승"])
        self.check("홍크（HONK）단독 콘서트 'samsa'", ["홍크"])
        self.check("새소년 EP 발매 단독콘서트 [여름깃]", ["새소년"])
        self.check("MUSIC RUNWAY：베리코이버니 X 크리스피", [])
        self.check("브로콜리너마저 장기 공연 〈이른 열대야 2026〉 부산 공연", ["브로콜리너마저"])

    def test_unclear_titles_give_nothing(self):
        for t in ["제 37회 라이브 클럽데이", "2022 백석예술대학교 정기공연 [B.A.U Mix Vol.22]",
                  "텐텐페스티벌 : 10년이 10냐?", "2019 ASIAN POP STAGE", "작곡의 밤",
                  "2025 KT&amp;G 상상실현 페스티벌", "BUSAN ROCKING ROOKIE SHOW",
                  "KT&amp;G 상상마당 춘천배 가정의달 노래자랑 -우리의 노래-",
                  "루프탑 공연: 스크린 오브 뮤직", "2022년 상생 공연 대관료 지원 프로그램",
                  "슈가레코드 레이블 콘서트 Vol. 4 앵콜 조인트 공연"]:
            self.check(t, [])


class BodyPerformerTest(unittest.TestCase):
    def test_colon_line_split_on_commas(self):
        self.assertEqual(ssm.performers_from_body(["일시: 2018", "출연: 몽니, 데이브레이크"]), ["몽니", "데이브레이크"])

    def test_bullet_artist_line_and_x_separator(self):
        self.assertEqual(ssm.performers_from_body(["• 출연 아티스트: 유도원, 소행성"]), ["유도원", "소행성"])
        self.assertEqual(ssm.performers_from_body(["출연 아디오스오디오 x 코토바"]), ["아디오스오디오", "코토바"])
        self.assertEqual(ssm.performers_from_body(["- 라인업 : 1일) 투페이스/ 로켓단(박실)/ 카이저소제"]),
                         ["투페이스", "로켓단", "카이저소제"])

    def test_drops_vague_entries(self):
        self.assertEqual(ssm.performers_from_body(["-출연: ODEE, VIANN 외"]), ["ODEE", "VIANN"])
        self.assertEqual(ssm.performers_from_body(["출연: 김세현 밴드 그리고 초대손님"]), [])
        self.assertEqual(ssm.performers_from_body(["출연: 백석대학교 문화예술학부 실용음악전공생 정기공연"]), [])
        self.assertEqual(ssm.performers_from_body(["*출연자 소개*", "공연상세 / 출연진정보"]), [])

    def test_guest_parentheses_and_roles(self):
        self.assertEqual(ssm.performers_from_body(["출연: 맥대지 (Guest 팔로알토, 킨샤위시 외)"]),
                         ["맥대지", "팔로알토", "킨샤위시"])
        self.assertEqual(ssm.performers_from_body(["출연: 새소년 with Special Guest"]), ["새소년"])
        self.assertEqual(ssm.performers_from_body(["출연: 이주호 감독, 술탄 오브 더 디스코"]), ["술탄 오브 더 디스코"])
        self.assertEqual(ssm.performers_from_body(["출연: special guests"]), [])

    def test_role_words_dates_and_spaced_names(self):
        self.assertEqual(ssm.performers_from_body(["출연 : 싱어송라이터 임헌일"]), ["임헌일"])
        self.assertEqual(ssm.performers_from_body(["출연 : 포 크 스 푼"]), ["포크스푼"])
        self.assertEqual(ssm.performers_from_body(["출연: 10월 14일 - 레이브릭스, 인플레이스"]), ["레이브릭스", "인플레이스"])
        self.assertEqual(ssm.performers_from_body(["출연: 바운스실용음악학원"]), [])

    def test_quoted_name_after_role_word(self):
        self.assertEqual(ssm.performers_from_body(["출연 : 싱어송라이터'모노제이'"]), ["모노제이"])


class DetailAndRowTest(unittest.TestCase):
    def test_parse_detail_time_and_body(self):
        d = ssm.parse_detail(DETAIL)
        self.assertEqual(d["time"], "18:00")
        self.assertIn("출연: 몽니, 데이브레이크", d["lines"])

    def test_escaped_html_body_is_unwrapped(self):
        page = "<a>공유하기</a><div>&lt;p&gt;출연: 안녕바다&lt;br /&gt;&lt;/p&gt;&lt;p&gt;티켓: 5만원&lt;/p&gt;</div><a>목록</a>"
        self.assertEqual(ssm.performers_from_body(ssm.parse_detail(page)["lines"]), ["안녕바다"])

    def test_time_falls_back_to_body_date_line(self):
        page = "<a>공유하기</a><p>일시: 2019년 6월 2일 (일) 17:00</p><p>출연: 안녕바다</p><a>목록</a>"
        self.assertEqual(ssm.parse_detail(page)["time"], "17:00")

    def test_rows_prefer_body_over_title(self):
        rows = ssm.to_rows(item(), ssm.parse_detail(DETAIL), AT)
        self.assertEqual([r["artist_text"] for r in rows], ["몽니", "데이브레이크"])
        r = rows[0]
        self.assertEqual((r["source"], r["collector"], r["source_id"]), ("sangsangmadang", "script", "3188"))
        self.assertEqual((r["gig_date"], r["gig_time"]), ("2026-11-21", "18:00"))
        self.assertEqual(r["gig_url"], "https://www.sangsangmadang.com/show/detail/3188")
        self.assertEqual(r["venue_text"], "KT&G 상상마당 부산 3F 라이브홀")
        self.assertEqual(r["title"], "신해경 단독 콘서트 나의 가역반응 사가 - 서울, 부산")

    def test_rows_fall_back_to_title(self):
        rows = ssm.to_rows(item(), {"time": "", "lines": []}, AT)
        self.assertEqual([r["artist_text"] for r in rows], ["신해경"])

    def test_short_venue_gets_branch_name_in_front(self):
        # 지점을 괄호에 두면 공연장 칸(괄호 앞)에서 지점이 사라진다 → '건물 + 홀' 한 이름으로
        self.assertEqual(ssm.venue_text(item(performanceLocation="라이브홀", spaceCd="HD")),
                         "KT&G 상상마당 홍대 라이브홀")
        self.assertEqual(ssm.venue_text(item(performanceLocation="사운드홀 ", spaceCd="CC")),
                         "KT&G 상상마당 춘천 사운드홀")
        self.assertEqual(ssm.venue_text(item(performanceLocation="3층 라이브홀", spaceCd="BS")),
                         "KT&G 상상마당 부산 3층 라이브홀")

    def test_chain_name_without_branch_gets_branch(self):
        self.assertEqual(ssm.venue_text(item(performanceLocation="KT&G 상상마당 라이브홀", spaceCd="HD")),
                         "KT&G 상상마당 홍대 라이브홀")

    def test_empty_location_is_branch_label(self):
        self.assertEqual(ssm.venue_text(item(performanceLocation="", spaceCd="DC")), "KT&G 상상마당 대치")

    def test_non_music_shows_skipped(self):
        self.assertTrue(ssm.is_music(item()))
        self.assertFalse(ssm.is_music(item(cdVal="뮤지컬")))
        self.assertFalse(ssm.is_music(item(cdVal="연극")))
        self.assertFalse(ssm.is_music(item(cdVal="직접입력", genreTxt="영화")))
        self.assertFalse(ssm.is_music(item(cdVal="직접입력", genreTxt="스탠드업 코미디")))
        self.assertTrue(ssm.is_music(item(cdVal="직접입력", genreTxt="버스킹")))

    def test_bad_date_gives_no_rows(self):
        self.assertEqual(ssm.to_rows(item(startDt=""), {"time": "", "lines": []}, AT), [])

    def test_written_file_passes_validator(self):
        rows = (ssm.to_rows(item(), ssm.parse_detail(DETAIL), AT)
                + ssm.to_rows(item(contentsSeq=1, title="아일 전국투어 서울"), {"time": "", "lines": []}, AT))
        with tempfile.TemporaryDirectory() as d:
            path = ssm.write_csv(rows, Path(d), "2026-11-26")
            self.assertEqual(path.name, "raw_kr_gig_2026-11-26_sangsangmadang.csv")
            errs = [i for i in validate_csv.validate_file(path) if i.level == "error"]
        self.assertEqual(errs, [])


class SinceTest(unittest.TestCase):
    def test_filter_since(self):
        items = [item(startDt="20261121"), item(startDt="20190101"), item(startDt="20270102")]
        self.assertEqual([i["startDt"] for i in ssm.select_items(items, "2020-01-01")], ["20261121", "20270102"])
        self.assertEqual(len(ssm.select_items(items, "")), 3)


if __name__ == "__main__":
    unittest.main()
