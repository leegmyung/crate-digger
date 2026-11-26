"""음원 플랫폼(멜론·지니·FLO·벅스) 인디 신보 수집기 파서 테스트 — aside 없이 실제 페이지 구조를 줄인 가짜 데이터로."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import collect_platforms as cp  # noqa: E402
import validate_csv  # noqa: E402

AT = "2026-11-26T21:00:00+09:00"

BUGS_ITEM = """<li> <figure class="albumInfo" albumid="20858510" trackid="34148584" artistid="20026154">
<figcaption class="info"> <div class="albumTitle"> <a href="https://music.bugs.co.kr/album/20858510?wl_ref=list_ab_03" title="Qualia">Qualia</a> </div>
<div class="subInfo"> <p class="artist"> <a href="https://music.bugs.co.kr/artist/20026154?wl_ref=list_ab_04" class="artistTitle" title="오존(O3ohn)">오존(O3ohn)</a> </p>
<p> <time datetime="">2026.11.26</time> <span class="albumType">정규</span> </p> </div> </figcaption> </figure> </li>"""
BUGS_COLLAB = """<li><figure class="albumInfo" albumid="20858999"><div class="albumTitle"><a href="https://music.bugs.co.kr/album/20858999?wl_ref=x" title="둘이서">둘이서</a></div>
<p class="artist"><a href="https://music.bugs.co.kr/artist/1" class="artistTitle" title="가람">가람</a>, <a href="https://music.bugs.co.kr/artist/2" class="artistTitle" title="나래 &amp; 다솜">나래 &amp; 다솜</a></p>
<p><time datetime="">2026.11.25</time> <span class="albumType">싱글</span></p></figure></li>"""
BUGS_DETAIL = """<table class="info"><tbody><tr><th scope="row">유형</th><td>정규</td></tr>
<tr><th scope="row">장르</th><td> <a href="#">포크/어쿠스틱</a>, <a href="#">인디</a> </td></tr>
<tr><th scope="row">발매일</th><td> <time datetime="2026.11.26">2026.11.26</time> </td></tr>
<tr><th scope="row">유통사</th><td>MOAH</td></tr><tr><th scope="row">기획사</th><td>CAM</td></tr></tbody></table>"""

GENIE_ROWS = ["""<tr class="list" songid="118006804"><td class="info"> <a href="#" class="title ellipsis" title="Merry 성탄"> Merry 성탄</a>
<a href="#" class="artist ellipsis" onclick="fnViewArtist(81346317); return false;">베카</a> <i class="bar">|</i>
<a href="#" class="albumtitle ellipsis" onclick="fnViewAlbumLayer(88507509); return false;">Merry 성탄</a> </td></tr>""",
              """<tr class="list" songid="118006805"><td class="info"><a class="title ellipsis">두 번째 곡</a>
<a href="#" class="artist ellipsis" onclick="fnViewArtist(81346317); return false;">베카</a>
<a href="#" class="albumtitle ellipsis" onclick="fnViewAlbumLayer(88507509); return false;">Merry 성탄</a></td></tr>"""]
GENIE_DETAIL = """<div class="info-zone"> <h2 class="name">Merry 성탄</h2> <ul class="info-data">
<li><span class="attr"><img alt="아티스트"></span> <span class="value"><a href="#">베카</a></span></li>
<li><span class="attr"><img alt="장르/스타일"></span> <span class="value">인디 / 가요</span></li>
<li><span class="attr"><img alt="발매사"></span> <span class="value">(주) 광수미디어</span></li>
<li><span class="attr"><img alt="기획사"></span> <span class="value">베카</span></li>
<li><span class="attr"><img alt="발매일"></span> <span class="value">2026.11.26 </span></li> </ul></div>"""

MELON_ITEM = """<li> <div class="entry"> <div class="info"> <a href="javascript:melon.link.goAlbumDetail('15199474');" class="ellipsis album_name" title="겨울 -페이지 이동">겨울</a>
<span class="ellipsis artist"> <a href="javascript:melon.link.goArtistDetail('181716');" class="artist_name " title="에피톤 프로젝트 - 페이지 이동">에피톤 프로젝트</a>
<span class="checkEllipsis" style="display: none;"><a href="javascript:melon.link.goArtistDetail('181716');" class="artist_name " title="에피톤 프로젝트 - 페이지 이동">에피톤 프로젝트</a></span> </span> </div> </div> </li>"""
MELON_DETAIL = """<div class="entry"> <div class="info"> <span class="gubun"> [싱글] </span> <div class="song_name"> <strong class="none">앨범명</strong> 겨울 </div></div>
<div class="meta"> <dl class="list"> <dt>발매일</dt> <dd>2026.11.26</dd> <dt>장르</dt> <dd>발라드, 인디음악</dd> <dt>발매사</dt> <dd>지니뮤직</dd> <dt>기획사</dt> <dd>NOL 엔터테인먼트</dd> </dl> </div>
<button id="btnLike"><span id="d_like_count" class="cnt">72</span></button></div>"""

FLO_LIST = {"code": "2000000", "data": {"albumList": [
    {"type": "ALBUM", "id": 467829870, "title": "겨울", "releaseYmd": "20261126", "genreStyle": "발라드,인디팝",
     "albumTypeStr": "싱글", "artistList": [{"id": 80021125, "name": "에피톤 프로젝트"}]},
    {"type": "ALBUM", "id": 467452064, "title": "봄", "releaseYmd": "20261120", "genreStyle": "인디록",
     "albumTypeStr": "EP", "artistList": [{"id": 20030585, "name": "사뮈 (Samui)"}]},
]}}
FLO_DETAIL = {"data": {"id": 467829870, "agencyNm": "(주)지니뮤직", "albumLabelList": [{"labelNm": "NOL 엔터테인먼트"}]}}


class BugsTest(unittest.TestCase):
    def test_list_item(self):
        [a] = cp.parse_bugs_list([BUGS_ITEM])
        self.assertEqual((a["album_id"], a["title"], a["artists"], a["released_at"], a["release_type"]),
                         ("20858510", "Qualia", ["오존(O3ohn)"], "2026-11-26", "LP"))
        self.assertEqual(a["url"], "https://music.bugs.co.kr/album/20858510")

    def test_collab_artists(self):
        [a] = cp.parse_bugs_list([BUGS_COLLAB])
        self.assertEqual(a["artists"], ["가람", "나래 & 다솜"])
        self.assertEqual(a["release_type"], "single")

    def test_detail(self):
        self.assertEqual(cp.parse_bugs_detail(BUGS_DETAIL),
                         {"distributor": "MOAH", "label": "CAM", "genre": "포크/어쿠스틱|인디", "released_at": "2026-11-26"})


class GenieTest(unittest.TestCase):
    def test_song_rows_become_one_album(self):
        albums = cp.parse_genie_list(GENIE_ROWS)
        self.assertEqual(len(albums), 1)
        self.assertEqual((albums[0]["album_id"], albums[0]["title"], albums[0]["artists"]), ("88507509", "Merry 성탄", ["베카"]))
        self.assertEqual(albums[0]["url"], "https://www.genie.co.kr/detail/albumInfo?axnm=88507509")
        self.assertEqual(albums[0]["released_at"], "")

    def test_detail(self):
        self.assertEqual(cp.parse_genie_detail(GENIE_DETAIL),
                         {"distributor": "(주) 광수미디어", "label": "베카", "genre": "인디|가요", "released_at": "2026-11-26"})


class MelonTest(unittest.TestCase):
    def test_list_item_hidden_duplicate_artist_ignored(self):
        [a] = cp.parse_melon_list([MELON_ITEM])
        self.assertEqual((a["album_id"], a["title"], a["artists"]), ("15199474", "겨울", ["에피톤 프로젝트"]))
        self.assertEqual(a["url"], "https://www.melon.com/album/detail.htm?albumId=15199474")

    def test_detail(self):
        self.assertEqual(cp.parse_melon_detail(MELON_DETAIL),
                         {"distributor": "지니뮤직", "label": "NOL 엔터테인먼트", "genre": "발라드|인디음악",
                          "released_at": "2026-11-26", "release_type": "single"})


class FloTest(unittest.TestCase):
    def test_list(self):
        albums = cp.parse_flo_list(FLO_LIST)
        self.assertEqual([(a["album_id"], a["released_at"], a["release_type"]) for a in albums],
                         [("467829870", "2026-11-26", "single"), ("467452064", "2026-11-20", "EP")])
        self.assertEqual(albums[0]["genre"], "발라드|인디팝")
        self.assertEqual(albums[0]["url"], "https://www.music-flo.com/detail/album/467829870/albumtrack")

    def test_detail(self):
        self.assertEqual(cp.parse_flo_detail(FLO_DETAIL), {"distributor": "(주)지니뮤직", "label": "NOL 엔터테인먼트"})

    def test_bad_json_gives_empty_list(self):
        self.assertEqual(cp.parse_flo_list({"code": "4000000"}), [])


class RowsTest(unittest.TestCase):
    def test_one_row_per_artist_with_keys(self):
        album = cp.parse_bugs_list([BUGS_COLLAB])[0]
        album = cp.merge_detail(album, {"distributor": "D", "label": "L", "genre": "인디", "released_at": "2026-11-25"})
        rows = cp.to_rows("bugs", album, AT)
        self.assertEqual([r["artist_text"] for r in rows], ["가람", "나래 & 다솜"])
        r = rows[0]
        self.assertEqual((r["source"], r["collector"], r["released_at"], r["distributor_text"], r["label_text"]),
                         ("bugs", "aside", "2026-11-25", "D", "L"))
        self.assertEqual((r["artist_key"], r["title_key"]), ("가람", "둘이서"))

    def test_detail_fills_missing_date_only(self):
        album = cp.parse_genie_list(GENIE_ROWS)[0]
        merged = cp.merge_detail(album, cp.parse_genie_detail(GENIE_DETAIL))
        self.assertEqual(merged["released_at"], "2026-11-26")
        self.assertEqual(album["released_at"], "")  # 원래 값은 바꾸지 않음

    def test_rows_without_date_skipped(self):
        album = cp.parse_genie_list(GENIE_ROWS)[0]
        self.assertEqual(cp.to_rows("genie", album, AT), [])

    def test_written_csv_passes_validator(self):
        rows = []
        for src, album in [("bugs", cp.parse_bugs_list([BUGS_ITEM])[0]), ("flo", cp.parse_flo_list(FLO_LIST)[0])]:
            rows += cp.to_rows(src, album, AT)
        rows += cp.to_rows("melon", cp.merge_detail(cp.parse_melon_list([MELON_ITEM])[0], cp.parse_melon_detail(MELON_DETAIL)), AT)
        with tempfile.TemporaryDirectory() as d:
            path = cp.write_csv(rows, Path(d), "2026-11-26", "platforms")
            errs = [i for i in validate_csv.validate_file(path) if i.level == "error"]
        self.assertEqual(path.name, "raw_kr_release_2026-11-26_platforms.csv")
        self.assertEqual(errs, [])

    def test_unique_albums_keeps_first(self):
        albums = cp.parse_melon_list([MELON_ITEM, MELON_ITEM])   # 멜론 목록엔 같은 앨범이 두 군데 나옴
        self.assertEqual([a["album_id"] for a in cp.unique_albums(albums)], ["15199474"])

    def test_in_window(self):
        self.assertTrue(cp.in_window("2026-11-24", "2026-11-26", days=3))
        self.assertFalse(cp.in_window("2026-11-23", "2026-11-26", days=3))
        self.assertFalse(cp.in_window("", "2026-11-26", days=3))


class IsolationTest(unittest.TestCase):
    def test_one_platform_failure_does_not_stop_others(self):
        def fake(platform, seen, today, days):
            if platform == "genie":
                raise RuntimeError("aside 결과 없음")
            return [{"source": platform}], ["1"]
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(cp, "collect_platform", side_effect=fake), \
                mock.patch.object(cp, "RAW_DIR", Path(d)), \
                mock.patch.object(cp, "STATE", Path(d) / "state" / "seen.json"), \
                mock.patch.object(cp, "ERROR_LOG", Path(d) / "state" / "errors.log"), \
                mock.patch.object(cp, "write_csv", return_value=Path(d) / "x.csv"):
            path, report, failed = cp.collect(["melon", "genie", "flo"], days=3)
        self.assertEqual(failed, ["genie"])
        self.assertTrue(any("genie" in line and "실패" in line for line in report))
        self.assertTrue(any(line.startswith("✅ flo") for line in report))


if __name__ == "__main__":
    unittest.main()
