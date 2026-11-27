"""웹진 수집기 변환 로직 테스트 — 네트워크 없이, 실제 페이지에서 잘라 온 조각으로."""
import csv
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import collect_webzines as cw  # noqa: E402
import validate_csv  # noqa: E402

AT = "2026-11-26T21:00:00+09:00"


def wp_post(pid, date, title, link, cats, tags):
    """WordPress REST API(_embed=wp:term) 글 1개 모양."""
    return {
        "id": pid, "date": date, "link": link, "title": {"rendered": title},
        "_embedded": {"wp:term": [
            [{"taxonomy": "category", "name": c} for c in cats],
            [{"taxonomy": "post_tag", "name": t} for t in tags],
        ]},
    }


VISLA_STOP = {"release talk", "in their playlist", "playlist", "indie", "folk", "전자음악", "하이퍼팝", "앨범"}


class VislaTest(unittest.TestCase):
    def parse(self, title, tags, cats=("FEATURE", "MUSIC")):
        post = wp_post(1, "2026-11-26T16:21:49", title, "https://visla.kr/feature/1/", list(cats), tags)
        return cw.parse_visla(post, VISLA_STOP)

    def test_release_talk_possessive(self):
        got = self.parse("Release Talk | 파편화된 너와 나를 바라보는, Jampad의 [Präparat]",
                         ["deconstructed club", "Jampad", "Präparat", "디컨스트럭티드 클럽", "잠파드"])
        self.assertEqual([a["artist"] for a in got["artists"]], ["Jampad"])
        self.assertEqual(got["release_title"], "Präparat")
        self.assertEqual(got["pick_label"], "Release Talk")
        self.assertEqual(got["is_pick"], "1")

    def test_interview_with_space_insensitive_tag(self):
        got = self.parse("Release Talk | ‘최악’의 첫 정규 [The Worst of Sailor Honeymoon], 세일러허니문",
                         ["indie", "punk", "release talk", "SAILOR HONEYMOON", "세일러 허니문"])
        self.assertEqual([a["artist"] for a in got["artists"]], ["세일러허니문"])   # 제목에 쓰인 모양

    def test_interview_two_artists(self):
        got = self.parse("20년 만에 바이닐로 돌아온 2006년의 인디팝, 우민과 에스피오네 인터뷰",
                         ["espionne", "lp", "Woomin", "바이닐", "에스피오네", "우민", "재발매"])
        self.assertEqual(sorted(a["artist"] for a in got["artists"]), ["에스피오네", "우민"])
        self.assertEqual(got["pick_label"], "Interview")

    def test_interview_without_tags_uses_slot(self):
        got = self.parse("네덜란드를 넘어 전 세계로, Tramhaus 인터뷰", [])
        self.assertEqual([a["artist"] for a in got["artists"]], ["Tramhaus"])

    def test_playlist_prefix(self):
        got = self.parse("in their playlist: Labäda Bu", ["in their playlist", "Labäda Bu", "라바다 부"])
        self.assertEqual([a["artist"] for a in got["artists"]], ["Labäda Bu"])
        self.assertEqual(got["pick_label"], "in their playlist")

    def test_news_genre_tag_ignored_and_not_pick(self):
        got = self.parse("영국 하이퍼팝 듀오 Two Shell,  곡 “Ghost 2” 뮤직비디오 공개",
                         ["electronic music", "Ghost 2", "하이퍼팝", "Two Shell"], cats=("MUSIC",))
        self.assertEqual([a["artist"] for a in got["artists"]], ["Two Shell"])
        self.assertEqual(got["is_pick"], "0")
        self.assertEqual(got["pick_label"], "News")

    def test_substring_tag_dropped(self):
        got = self.parse("Earl Sweatshirt와 The Alchemist의 합작 앨범 [Voir Dire]",
                         ["album", "earl", "Earl Sweatshirt", "The Alchemist", "VOIR DIRE"], cats=("MUSIC",))
        self.assertEqual(sorted(a["artist"] for a in got["artists"]), ["Earl Sweatshirt", "The Alchemist"])

    def test_label_tag_ignored(self):
        got = self.parse("QH 레코드가 전달하는 한국발 하우스, [Audio Smith Vol.3 Charles by Amon.Cin] 발매",
                         ["AMON.CIN", "qh", "qh records", "qh 레코드"], cats=("MUSIC",))
        self.assertEqual(got["artists"], [])

    def test_unknown_goes_to_review(self):
        got = self.parse("컴퓨터 없는 수제 테크노 그룹, Klangphonics", ["berlin", "techno", "베를린"], cats=("MUSIC",))
        self.assertEqual(got["artists"], [])

    def test_sponsor_category(self):
        got = self.parse("Release Talk | 새 앨범, omm..의 [밥]", ["omm.."], cats=("FEATURE", "MUSIC", "SPONSOR"))
        self.assertEqual(got["is_sponsored"], "1")


class WeivTest(unittest.TestCase):
    def test_review(self):
        post = wp_post(25397, "2026-10-09T10:00:00", "칩 포스트 갱(Chip Post Gang) &#8211; 우리가우리라고부르는것들 (2026)",
                       "https://www.weiv.co.kr/archives/25397", ["album", "local", "review"], ["칩 포스트 갱"])
        got = cw.parse_weiv(post)
        self.assertEqual([a["artist"] for a in got["artists"]], ["칩 포스트 갱(Chip Post Gang)"])
        self.assertEqual(got["release_title"], "우리가우리라고부르는것들")
        self.assertEqual(got["pick_label"], "Album Review")

    def test_interview_two(self):
        post = wp_post(25343, "2026-09-30T10:00:00",
                       "공간현대(空間現代), 오드 아이즈(odd eyes) | 모든 것을 공유하지 않아도, 함께 모여 음악을 들을 수 있다",
                       "https://www.weiv.co.kr/archives/25343", ["interview"], ["공간현대", "오드 아이즈"])
        got = cw.parse_weiv(post)
        self.assertEqual([a["artist"] for a in got["artists"]], ["공간현대(空間現代)", "오드 아이즈(odd eyes)"])
        self.assertEqual(got["pick_label"], "Interview")

    def test_translated_interview_uses_single_tag(self):
        post = wp_post(24764, "2024-02-24T10:00:00", "羊文学 | 花瓶の花を大切にするロックスター",
                       "https://www.weiv.co.kr/archives/24764", ["interview"], ["히쓰지분가쿠"])
        self.assertEqual([a["artist"] for a in cw.parse_weiv(post)["artists"]], ["히쓰지분가쿠"])

    def test_column_and_international_skipped(self):
        col = wp_post(1, "2025-07-07T10:00:00", "[칼럼] 2025 하계 국제 록 페스티벌 단상", "https://www.weiv.co.kr/archives/1",
                      ["article"], ["공연"])
        intl = wp_post(2, "2025-07-07T10:00:00", "Bon Iver – SABLE, fABLE (2025)", "https://www.weiv.co.kr/archives/2",
                       ["album", "international", "review"], ["Bon Iver"])
        self.assertIsNone(cw.parse_weiv(col))
        self.assertIsNone(cw.parse_weiv(intl))


IZM_REVIEW = {"id": 34300, "artists": [{"id": 1, "kr_name": "캐치더영", "en_name": "Catch The Young"}],
              "created": "2026-11-21T10:00:00", "main_category": "Review", "sub_category": "싱글",
              "detail_category": "국내", "title": "Paranoia"}


class IzmTest(unittest.TestCase):
    def test_domestic_review(self):
        got = cw.parse_izm(IZM_REVIEW)
        self.assertEqual(got["artists"][0]["artist"], "캐치더영 (Catch The Young)")
        self.assertEqual(got["url"], "https://izm.co.kr/posts?id=34300")
        self.assertEqual(got["published_at"], "2026-11-21")
        self.assertEqual((got["is_pick"], got["pick_label"], got["release_title"]), ("1", "싱글 리뷰", "Paranoia"))

    def test_foreign_review_skipped(self):
        self.assertIsNone(cw.parse_izm(dict(IZM_REVIEW, detail_category="해외")))

    def test_interview_and_feature(self):
        iv = cw.parse_izm({"id": 34305, "artists": [{"id": 3352, "kr_name": "지선", "en_name": None}],
                           "created": "2026-11-25T00:53:42", "main_category": "Interview", "sub_category": None,
                           "detail_category": "", "title": "지선 인터뷰"})
        self.assertEqual((iv["artists"][0]["artist"], iv["is_pick"], iv["pick_label"]), ("지선", "1", "Interview"))
        ft = cw.parse_izm({"id": 34267, "artists": [{"id": 4427, "kr_name": "전기뱀장어", "en_name": None}],
                           "created": "2026-10-28T10:00:00", "main_category": "Feature", "sub_category": "연재물",
                           "detail_category": "팟캐스트", "title": "[이즘 뮤직 클라우드] EP. 199"})
        self.assertEqual((ft["is_pick"], ft["pick_label"]), ("0", "Feature 연재물"))

    def test_interview_without_artist_is_unparsed(self):
        got = cw.parse_izm({"id": 34194, "artists": [], "created": "2026-09-10T10:00:00", "main_category": "Interview",
                            "sub_category": None, "detail_category": "", "title": "[저널-이즘] 스포츠서울 기자"})
        self.assertEqual(got["artists"], [])


RHYTHMER_HTML = (
    '<li class="lists first">\n\t\t\t\t<dl>\n\t\t\t\t\t<dt><a href="/src/go.php?n=21659&amp;m=view&amp;s=review&amp;c=16&amp;p=1">'
    '<img src="x" alt="저스트 뮤직 - The Ship Of Theseus" /></a></dt>\n\t\t\t\t\t<dd>\n\t\t\t\t\t\t<ol>\n'
    '\t\t\t\t\t\t\t<li class="loc"><a href="/src/go.php?s=review">Review</a> > <a href="/src/go.php?c=16&amp;s=review">국내 리뷰</a></li>\n'
    '\t\t\t\t\t\t\t<li class="tit"><a href="/src/go.php?n=21659&amp;m=view&amp;s=review&amp;c=16&amp;p=1">저스트 뮤직 - The Ship Of Theseus</a></li>\n'
    '\t\t\t\t\t\t\t<li class="txt"><a href="/src/go.php?n=21659&amp;m=view&amp;s=review&amp;c=16&amp;p=1">Artist: 저스트 뮤직\r\n'
    'Album: The Ship Of Theseus\r\nReleased: 2026-11-13\r\nRating: \r\nReviewer: 황두하\r\n\r\n저스트 뮤직(Just...</a></li>\n'
    '\t\t\t\t\t\t\t<li class="com">\n\t\t\t\t\t\t\t\t<strong class="author">황두하</strong>\n\t\t\t\t\t\t\t\t｜\n'
    '\t\t\t\t\t\t\t\t2026-11-20\n\t\t\t\t\t\t\t\t<!--｜\n\t\t\t\t\t\t\t\t<strong>24,928</strong> Reads-->\n'
    '\t\t\t\t\t\t\t</li>\n\t\t\t\t\t\t</ol>\n\t\t\t\t\t</dd>\n\t\t\t\t</dl>\n\t\t\t</li>\n'
    '<li class="tit"><a href="/src/go.php?n=21627&amp;m=view&amp;s=review&amp;c=16&amp;p=1">2MC(오도마 &amp; 스카이민혁) - 2MC</a></li>\n'
    '<li class="txt"><a href="/src/go.php?n=21627&amp;m=view&amp;s=review&amp;c=16&amp;p=1">Artist: 2MC(오도마 &amp; 스카이민혁)\r\n'
    'Album: 2MC\r\nReleased: 2026-10-16\r\n</a></li>\n<li class="com">\n<strong class="author">황두하</strong>\n｜\n2026-10-27\n'
)


class RhythmerTest(unittest.TestCase):
    def test_list_items(self):
        items = cw.parse_rhythmer_list(RHYTHMER_HTML)
        self.assertEqual(len(items), 2)
        a = items[0]
        self.assertEqual(a["url"], "http://board.rhythmer.net/src/go.php?n=21659&m=view&s=review")
        self.assertEqual(a["published_at"], "2026-11-20")
        self.assertEqual(a["artists"][0]["artist"], "저스트 뮤직")
        self.assertEqual(a["release_title"], "The Ship Of Theseus")
        self.assertEqual(a["title"], "저스트 뮤직 - The Ship Of Theseus")
        self.assertEqual(items[1]["artists"][0]["artist"], "2MC(오도마 & 스카이민혁)")
        self.assertEqual(items[1]["published_at"], "2026-10-27")


MUSICY_HTML = (
    '<li>\n<a href="?c=review&s=1&cidx=23&gp=2&ob=idx&gbn=view&ix=9472" class="y_image">\n'
    "<span class=\"y_thumb\"><img src='/upload/y-review/x.jpg' alt='Paranoia' /></span>\n</a>\n"
    '<dl class="desc_detail">\n<dt class="blind">음악 정보</dt>\n'
    '<dd class="y_title"><a href="?c=review&s=1&cidx=23&gp=2&ob=idx&gbn=view&ix=9472"><strong class="y_album">Paranoia</strong>'
    '<span class="y_artist">캐치더영  (Catch The Young)</span></a></dd>\n<dd class="date"><span>2026.10</span> 발매</dd>\n'
    '<dd class="hit2">50</dd>\n<dd class="by">by 음악취향Y <span>2026.11.02</span></dd>\n</dl>\n</li>\n'
    '<dd class="y_title"><a href="?c=review&s=1&cidx=23&gp=1&ob=idx&gbn=view&ix=9486"><strong class="y_album">QUIZ</strong>'
    '<span class="y_artist">아이아이×홈즈 </span></a></dd>\n<dd class="by">by 음악취향Y <span>2026.11.23</span></dd>\n'
    '<dd class="y_title"><a href="?c=review&s=1&cidx=23&gp=1&ob=idx&gbn=view&ix=9490"><strong class="y_album">________________________</strong>'
    '<span class="y_artist">피씨알  (PCR)</span></a></dd>\n<dd class="by">by 음악취향Y <span>2026.11.23</span></dd>\n'
)


class MusicyTest(unittest.TestCase):
    def test_list_items(self):
        items = cw.parse_musicy_list(MUSICY_HTML)
        self.assertEqual(len(items), 3)
        a = items[0]
        self.assertEqual(a["url"], "http://musicy.kr/?c=review&s=1&gbn=view&ix=9472")
        self.assertEqual(a["published_at"], "2026-11-02")
        self.assertEqual(a["artists"][0]["artist"], "캐치더영 (Catch The Young)")
        self.assertEqual(a["release_title"], "Paranoia")
        self.assertEqual(a["pick_label"], "Single-Out")
        self.assertEqual([x["artist"] for x in items[1]["artists"]], ["아이아이", "홈즈"])
        self.assertEqual(items[2]["release_title"], "")   # 밑줄만 있는 제목(특수문자 깨짐)은 비운다


OT_REVIEW = (
    '<meta property="og:title" content="가장 더러운 천국, PCR <________________________> (24 Underscores) - overtone">'
    '<script type="application/ld+json">[{"@context":"https://schema.org","@type":"CriticReview",'
    '"headline":"가장 더러운 천국, PCR \\u003C________________________> (24 Underscores)",'
    '"datePublished":"2026-11-18T07:25:24.124Z","itemReviewed":{"@type":"MusicAlbum","name":"PCR \\u003CDopamine Chamber>"},'
    '"keywords":["review"]}]</script>'
)
OT_INTERVIEW = (
    '<script type="application/ld+json">[{"@context":"https://schema.org","@type":"Article","headline":"문없는집 인터뷰",'
    '"datePublished":"2026-11-23T14:54:04.214Z","keywords":["interview","문없는집"],"about":"문없는집"}]</script>'
)
OT_COMMENT = (
    '<meta property="og:title" content="주영 90’s Kids Comments - overtone">'
    '<meta property="article:modified_time" content="2026-11-21T17:02:32.919Z">'
    '<span class="comment-title-measure font-bold" aria-hidden="true">90’s Kids</span>'
    '<div class="grid"><div class="text-ov-caption"><p>Artist</p><p>Release</p><p>Format</p><p>Genre</p><p>Rating</p></div>'
    '<div class="text-ov-caption"><p class="line-clamp-1">주영</p><p>2026-10-08</p><p>Album</p><p>ROCK</p><p>★3.3/5.0</p></div></div>'
)
OT_SITEMAP = (
    "<urlset><url><loc>https://overtone.kr/</loc><lastmod>2026-11-24T10:54:36Z</lastmod></url>"
    "<url><loc>https://overtone.kr/comment/%EC%A3%BC%EC%98%81-90s-kids</loc><lastmod>2026-11-21T17:02:32Z</lastmod></url>"
    "<url><loc>https://overtone.kr/article/x</loc><lastmod>2026-11-21T17:02:32Z</lastmod></url>"
    "<url><loc>https://overtone.kr/full-review/old</loc><lastmod>2022-05-01T00:00:00Z</lastmod></url>"
    "</urlset>"
)


class OvertoneTest(unittest.TestCase):
    def test_full_review(self):
        got = cw.parse_overtone_page("https://overtone.kr/full-review/a", OT_REVIEW)
        self.assertEqual(got["artists"][0]["artist"], "PCR")
        self.assertEqual(got["release_title"], "Dopamine Chamber")
        self.assertEqual(got["published_at"], "2026-11-18")
        self.assertEqual(got["pick_label"], "Full Review")

    def test_interview(self):
        got = cw.parse_overtone_page("https://overtone.kr/interview/b", OT_INTERVIEW)
        self.assertEqual((got["artists"][0]["artist"], got["title"], got["published_at"]), ("문없는집", "문없는집 인터뷰", "2026-11-23"))
        self.assertEqual(got["pick_label"], "Interview")

    def test_comment(self):
        got = cw.parse_overtone_page("https://overtone.kr/comment/c", OT_COMMENT)
        self.assertEqual(got["artists"][0]["artist"], "주영")
        self.assertEqual(got["release_title"], "90’s Kids")
        self.assertEqual(got["title"], "주영 90’s Kids Comments")
        self.assertEqual(got["published_at"], "2026-11-22")   # UTC 17시 → 한국 날짜 다음날
        self.assertEqual(got["pick_label"], "Comment")

    def test_comment_with_several_artists_split(self):
        page = OT_COMMENT.replace('<p class="line-clamp-1">주영</p>', '<p class="line-clamp-1">SUMIN, Slom</p>')
        got = cw.parse_overtone_page("https://overtone.kr/comment/c", page)
        self.assertEqual([a["artist"] for a in got["artists"]], ["SUMIN", "Slom"])
        page2 = OT_COMMENT.replace('<p class="line-clamp-1">주영</p>', '<p class="line-clamp-1">Tyler, The Creator</p>')
        self.assertEqual([a["artist"] for a in cw.parse_overtone_page("https://overtone.kr/comment/c", page2)["artists"]],
                         ["Tyler, The Creator"])

    def test_sitemap_filters_sections_and_old(self):
        urls = cw.parse_overtone_sitemap(OT_SITEMAP, ["full-review", "interview", "comment"], since="2023-01-01")
        self.assertEqual(urls, ["https://overtone.kr/comment/%EC%A3%BC%EC%98%81-90s-kids"])


class RowsTest(unittest.TestCase):
    def test_rows_validate_and_sponsored(self):
        art = {"id": "1", "url": "https://visla.kr/feature/1/", "published_at": "2026-11-26",
               "title": "[AD] 새 앨범 소개, Jampad의 [Präparat]", "release_title": "Präparat",
               "is_pick": "1", "pick_label": "Release Talk", "is_sponsored": "0",
               "artists": [{"artist": "Jampad"}, {"artist": "Jampad"}]}
        rows = cw.to_rows("visla", "VISLA", art, AT)
        self.assertEqual(len(rows), 1)   # 같은 글 같은 팀은 1행
        self.assertEqual(rows[0]["is_sponsored"], "1")   # 제목의 [AD]
        with tempfile.TemporaryDirectory() as d:
            path = cw.write_csv(rows, Path(d), "2026-11-26", "visla")
            self.assertEqual(path.name, "raw_press_2026-11-26_visla.csv")
            issues = validate_csv.validate_file(path)
            self.assertEqual([i for i in issues if i.level == "error"], [])
            with open(path, encoding="utf-8") as fh:
                self.assertEqual(next(csv.DictReader(fh))["source"], "visla")

    def test_sponsored_regex(self):
        self.assertTrue(cw.is_sponsored("이 글은 협찬을 받아 작성"))
        self.assertTrue(cw.is_sponsored("Sponsored by X"))
        self.assertFalse(cw.is_sponsored("ADHD를 앓고 있는"))
        self.assertFalse(cw.is_sponsored("트랜스 컴필레이션 [AD:TRANCE 10] 공개"))   # 앨범 이름 속 AD
        self.assertTrue(cw.is_sponsored("AD | 브랜드와 함께한 플레이리스트"))
        self.assertFalse(cw.is_sponsored("Release Talk | 지하의 소리"))


class ResumeTest(unittest.TestCase):
    def test_batches_reported_and_seen_skipped(self):
        def fake(cfg, since):
            yield [("1", "2026-11-20", cw.article("1", "https://x.kr/1", "2026-11-20", "A – B", ["A"], "1", "Review")),
                   ("2", "2026-11-20", None)]
            yield [("3", "2022-01-01", None), ("4", "2026-11-21", cw.article("4", "https://x.kr/4", "2026-11-21", "?", [], "1", "Review"))]
        cw.FETCHERS["fake"] = fake
        calls = []
        try:
            n, review, ids, span, in_scope = cw.collect_outlet("fake", {"name": "X"}, "2023-01-01", {"2"}, AT,
                                                               lambda r, v, i: calls.append((len(r), len(v), i)))
        finally:
            del cw.FETCHERS["fake"]
        self.assertEqual(calls, [(1, 0, ["1"]), (0, 1, ["4"])])   # 묶음마다 저장, 본 글(2)·옛 글(3)은 건너뜀
        self.assertEqual((n, len(review), ids, span, in_scope), (1, 1, ["1", "4"], ("2026-11-20", "2026-11-21"), 2))


class StateTest(unittest.TestCase):
    def test_since_from_state(self):
        self.assertEqual(cw.since_for({}, "2023-01-01", "2026-11-26"), "2023-01-01")
        self.assertEqual(cw.since_for({"last_run": "2026-11-20"}, "2023-01-01", "2026-11-26"), "2026-11-06")


if __name__ == "__main__":
    unittest.main()


MUSICY_DETAIL = (
    '<dd class="v_album_volume"><strong class="album_t">Volume</strong> <span class="v_album_desc">1</span></dd>'
    '<dd class="v_album_data"><!-- <strong class="num"></strong> --><strong class="album_t">장르</strong> '
    '<span class="v_album_desc">록</span></dd>'
    '<dd class="v_album_data"><strong class="album_t">유통사</strong> <span class="v_album_desc">더 볼트</span></dd>'
)


class GenreTest(unittest.TestCase):
    """리뷰의 장르 표시 → raw_press.genre (2026-11-28, docs/genre_fill.md). 매체가 붙인 장르 글자를 그대로 남긴다."""

    def test_musicy_detail_genre(self):
        self.assertEqual(cw.parse_musicy_genre(MUSICY_DETAIL), "록")
        self.assertEqual(cw.parse_musicy_genre("<html>장르 없음</html>"), "")
        self.assertEqual(cw.musicy_detail_url("http://musicy.kr/?c=review&s=1&gbn=view&ix=9490"),
                         "http://musicy.kr/?c=review&s=1&gbn=viewok&ix=9490")

    def test_overtone_comment_genre(self):
        self.assertEqual(cw.parse_overtone_page("https://overtone.kr/comment/c", OT_COMMENT)["genre"], "ROCK")
        self.assertEqual(cw.parse_overtone_page("https://overtone.kr/full-review/a", OT_REVIEW)["genre"], "")

    def test_visla_genre_tags_only(self):
        self.assertEqual(cw.visla_genre(["release talk", "omm..", "indie rock", "바이닐", "앰비언트 트랜스"]),
                         "indie rock|앰비언트 트랜스")
        post = wp_post(1, "2026-11-26T16:21:49", "Release Talk | 새 앨범, omm..의 [밥]", "https://visla.kr/feature/1/",
                       ["FEATURE", "MUSIC"], ["release talk", "omm..", "indie rock", "Folk"])
        self.assertEqual(cw.parse_visla(post, VISLA_STOP)["genre"], "indie rock|Folk")
        self.assertEqual(cw.visla_post_id("https://visla.kr/feature/355075/"), "355075")
        # '실험·기타' 갈래는 키워드가 넓어('world' → 'World cup') VISLA 태그에선 쓰지 않는다
        self.assertEqual(cw.visla_genre(["Ambient Trance", "World cup", "월드컵", "국악"]), "Ambient Trance")

    def test_rows_carry_genre_and_validate(self):
        art = cw.article("1", "https://overtone.kr/comment/c", "2026-11-26", "주영 90’s Kids Comments", ["주영"], "1",
                         "Comment", "90’s Kids", genre="ROCK")
        rows = cw.to_rows("overtone", "overtone", art, AT)
        self.assertEqual(rows[0]["genre"], "ROCK")
        self.assertIn("genre", cw.COLUMNS)
        with tempfile.TemporaryDirectory() as d:
            path = cw.write_csv(rows, Path(d), "2026-11-26", "overtone")
            self.assertEqual([i for i in validate_csv.validate_file(path) if i.level == "error"], [])
        self.assertEqual(cw.article("1", "u", "2026-11-26", "t", ["a"], "1", "x")["genre"], "")

    def test_backfill_targets_and_reference(self):
        rows = [{"source": "musicy", "url": "m1", "genre": ""}, {"source": "musicy", "url": "m1", "genre": ""},
                {"source": "overtone", "url": "o1", "genre": "POP"},          # 이미 장르 있음
                {"source": "izm", "url": "i1", "genre": ""},                  # 장르 표시 없는 매체
                {"source": "visla", "url": "v1"}, {"source": "musicy", "url": "m2", "genre": ""}]
        self.assertEqual(cw.genre_backfill_targets(rows, done={"m2"}), [("musicy", "m1"), ("visla", "v1")])
        got = cw.backfill_genres([("musicy", "m1"), ("visla", "v1")], lambda s, u: {"m1": "록"}.get(u, ""), delay=0)
        self.assertEqual([(r["url"], r["source"], r["genre"]) for r in got], [("m1", "musicy", "록"), ("v1", "visla", "")])
        with tempfile.TemporaryDirectory() as d:
            ref = Path(d) / "press_genres.csv"
            self.assertEqual(cw.merge_genre_reference(ref, got, "2026-11-28"), 2)
            self.assertEqual(cw.merge_genre_reference(ref, [{"url": "m1", "source": "musicy", "genre": "포크"}], "2026-11-29"), 2)
            with open(ref, encoding="utf-8") as f:
                saved = {r["url"]: r for r in csv.DictReader(f)}
            self.assertEqual(saved["m1"]["genre"], "포크")              # 새로 본 값으로 바뀜
            self.assertEqual(saved["v1"]["checked_at"], "2026-11-28")   # 장르 없음도 '봤음'으로 남김(다시 안 받게)
            self.assertEqual(cw.load_genre_reference(ref)["m1"], "포크")
            self.assertEqual(cw.load_genre_reference(Path(d) / "없음.csv"), {})
