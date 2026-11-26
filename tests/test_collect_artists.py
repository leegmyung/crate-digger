"""아티스트 메타데이터(멜론 아티스트 페이지) 수집기 테스트 — aside 없이 실제 페이지 구조를 줄인 가짜 데이터로."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import collect_artists as ca  # noqa: E402
import validate_csv  # noqa: E402

AT = "2026-11-26T21:00:00+09:00"
INFO = """<div class="wrap_atist_info"> <p class="title_atist"><strong class="none">아티스트명</strong>에피톤&nbsp;프로젝트</p>
<dl class="atist_info clfix"> <dt>데뷔</dt> <dd> <span class="gubun">2006.12.12</span> <a href="#" class="btn_play_song"> <span class="icon_play">곡재생</span>
<span class="songname12">좋았던 순간은 늘 잔인하다</span> </a> </dd> <dt>활동유형</dt> <dd>솔로</dd> <dt>소속사</dt> <dd>(주)인터파크</dd> </dl></div>"""
DETAIL_DL = ["데뷔 2006.12.12 활동년대 2000, 2010, 2020 년대 유형 솔로 |남성 장르 인디음악, 발라드, 록/메탈 소속사명 (주)인터파크", "국적 대한민국"]
PAGE = {"info": INFO, "fan": "33,496", "dl": DETAIL_DL + ["SNS 페이스북 트위터 YouTube https://www.youtube.com/@epitone"],
        "albums": "앨범(46)", "album_dates": ["2026.11.26", "2008.05.01", "2007.03.15"]}
GROUP = {"info": """<div class="wrap_atist_info"><p class="title_atist"><strong class="none">아티스트명</strong>고고학 (Gogohawk)</p>
<dl class="atist_info"><dt>활동유형</dt><dd>그룹</dd></dl></div>""", "fan": "1,162", "albums": "앨범(15)",
         "dl": ["유형 그룹 장르 인디음악, 록/메탈, 재즈", "아티스트명 강전호 대한민국/남성/솔로 음악장르 팬맺기 9 아티스트명 하범석 대한민국/남성/솔로 음악장르 인디음악|포크/블루스",
                "국적 대한민국 YouTube https://www.youtube.com/channel/UC123"],
         "album_dates": ["2023.09.26", "2022.12.22", "2022.12.04"]}
NEWBIE = {"info": """<div class="wrap_atist_info"><p class="title_atist"><strong class="none">아티스트명</strong>새벽정류장</p>
<dl class="atist_info"><dt>데뷔</dt><dd><span class="gubun">2026.03</span></dd><dt>활동유형</dt><dd>그룹</dd></dl></div>""",
          "fan": "0", "dl": [], "albums": "앨범(2)"}


class MelonArtistTest(unittest.TestCase):
    def test_full_profile(self):
        p = ca.parse_melon_artist(PAGE)
        self.assertEqual(p, {"artist_text": "에피톤 프로젝트", "debut_date": "2006-12-12", "debut_title": "좋았던 순간은 늘 잔인하다",
                             "activity_type": "솔로", "agency_text": "(주)인터파크", "genre": "인디음악|발라드|록/메탈",
                             "nationality": "대한민국", "fan_count": "33496", "album_count": "46",
                             "first_release_date": "2007-03-15", "youtube_url": "https://www.youtube.com/@epitone"})

    def test_member_list_and_sns_do_not_leak_into_genre_or_nationality(self):
        p = ca.parse_melon_artist(GROUP)
        self.assertEqual((p["genre"], p["nationality"], p["youtube_url"], p["first_release_date"], p["debut_date"]),
                         ("인디음악|록/메탈|재즈", "대한민국", "https://www.youtube.com/channel/UC123", "2022-12-04", ""))

    def test_partial_debut_and_missing_fields(self):
        p = ca.parse_melon_artist(NEWBIE)
        self.assertEqual((p["artist_text"], p["debut_date"], p["agency_text"], p["fan_count"], p["album_count"]),
                         ("새벽정류장", "2026-03", "", "0", "2"))

    def test_empty_page(self):
        self.assertEqual(ca.parse_melon_artist({})["artist_text"], "")


class TargetsTest(unittest.TestCase):
    def test_new_melon_artist_ids_from_release_rows(self):
        rows = [{"source": "melon", "artist_source_id": "181716", "artist_text": "에피톤 프로젝트"},
                {"source": "melon", "artist_source_id": "181716", "artist_text": "에피톤 프로젝트"},
                {"source": "melon", "artist_source_id": "", "artist_text": "번호 없음"},
                {"source": "bugs", "artist_source_id": "20026154", "artist_text": "오존"},
                {"source": "melon", "artist_source_id": "999", "artist_text": "이미 봄"}]
        self.assertEqual(ca.targets(rows, seen={"999"}), ["181716"])


class RowTest(unittest.TestCase):
    def test_row_and_validator(self):
        rows = [ca.to_row("181716", ca.parse_melon_artist(PAGE), AT), ca.to_row("5", ca.parse_melon_artist(NEWBIE), AT)]
        self.assertEqual(rows[0]["url"], "https://www.melon.com/artist/detail.htm?artistId=181716")
        self.assertEqual(rows[0]["artist_key"], "에피톤프로젝트")
        with tempfile.TemporaryDirectory() as d:
            path = ca.write_csv(rows, Path(d), "2026-11-26")
            errs = [i for i in validate_csv.validate_file(path) if i.level == "error"]
        self.assertEqual(path.name, "raw_artist_profile_2026-11-26_melon.csv")
        self.assertEqual(errs, [])

    def test_page_without_name_gives_no_row(self):
        self.assertIsNone(ca.to_row("1", ca.parse_melon_artist({}), AT))


if __name__ == "__main__":
    unittest.main()
