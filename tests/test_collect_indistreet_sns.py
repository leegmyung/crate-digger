"""scripts/collect_indistreet_sns.py — 인디스트릿 아티스트 페이지 구조화 데이터(sameAs)에서 팀 공식 인스타 계정."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import collect_indistreet_sns as cis  # noqa: E402

PAGE = """<html><head>
<script type="application/ld+json">{"@context":"https://schema.org","@type":"MusicGroup","name":"시네마스퀘어",
"description":"Guitar : @maya_csq","url":"https://indistreet.com/artists/cinemasquare",
"sameAs":["https://www.instagram.com/cinema_square_official.com__/","https://www.youtube.com/@csq"]}</script>
<script type="application/ld+json">{"@type":"Event","name":"공연","url":"https://indistreet.com/events/1"}</script>
</head><body><a href="https://www.instagram.com/maya_csq/">@maya_csq</a></body></html>"""


class ParseTest(unittest.TestCase):
    def test_same_as_only_from_artist_block(self):
        self.assertEqual(cis.parse_same_as(PAGE, "https://indistreet.com/artists/cinemasquare"),
                         ["https://www.instagram.com/cinema_square_official.com__/", "https://www.youtube.com/@csq"])
        self.assertEqual(cis.parse_same_as(PAGE, "https://indistreet.com/artists/other"), [])   # 다른 팀 페이지 블록이면 안 씀
        self.assertEqual(cis.parse_same_as("<html>없음</html>", "x"), [])
        self.assertEqual(cis.parse_same_as('<script type="application/ld+json">{깨진</script>', "x"), [])

    def test_pick_instagram_exactly_one(self):
        self.assertEqual(cis.pick_instagram(["https://www.instagram.com/abc.band/", "https://youtu.be/x"]), "abc.band")
        self.assertIsNone(cis.pick_instagram(["https://www.instagram.com/a/", "https://instagram.com/b"]))   # 둘이면 모름
        self.assertIsNone(cis.pick_instagram(["https://www.instagram.com/p/AbC/"]))                          # 게시물 주소
        self.assertIsNone(cis.pick_instagram([]))


class TargetTest(unittest.TestCase):
    def test_single_page_teams_only(self):
        rows = [{"artist_text": "에이", "artist_url": "https://indistreet.com/artists/a?x=1"},
                {"artist_text": "에이", "artist_url": "https://indistreet.com/artists/a"},
                {"artist_text": "비", "artist_url": "https://indistreet.com/artists/b1"},
                {"artist_text": "비", "artist_url": "https://indistreet.com/artists/b2"},          # 동명 의심 → 뺌
                {"artist_text": "씨", "artist_url": "https://www.indiego.co.kr/x"}]
        got = cis.team_pages(rows, key_of=lambda name: {"에이": "a", "비": "b", "씨": "c"}[name])
        self.assertEqual(got, {"a": "https://indistreet.com/artists/a"})

    def test_due_recheck_after_30_days(self):
        state = {"a": {"checked": "2026-11-01"}, "b": {"checked": "2026-11-20"}}
        self.assertEqual(cis.due(["a", "b", "c"], state, "2026-12-05"), ["c", "a"])


if __name__ == "__main__":
    unittest.main()
