"""scripts/collect_indiego_sns.py — 인디고 아티스트 페이지 JSON-LD(mainEntityOfPage + sameAs)에서 팀 공식 인스타."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import collect_indiego_sns as cig  # noqa: E402

URL = "https://www.indiego.co.kr/artists/3394-사양"
PAGE = """<script type="application/ld+json">{"@type":"Organization","url":"https://www.indiego.co.kr",
"sameAs":["https://www.instagram.com/indiego_ipo/"]}</script>
<script type="application/ld+json">{"@type":"MusicGroup","name":"사양","mainEntityOfPage":"https://www.indiego.co.kr/artists/3394-사양",
"sameAs":["https://www.instagram.com/bandsayang"]}</script>"""


class ParseTest(unittest.TestCase):
    def test_artist_block_by_main_entity_not_site_block(self):
        self.assertEqual(cig.parse_same_as(PAGE, URL), ["https://www.instagram.com/bandsayang"])
        self.assertEqual(cig.parse_same_as(PAGE, "https://www.indiego.co.kr/artists/1-다른팀"), [])

    def test_quoted_url_for_korean_slug(self):
        self.assertEqual(cig.quoted(URL), "https://www.indiego.co.kr/artists/3394-%EC%82%AC%EC%96%91")

    def test_team_pages_single_only(self):
        rows = [{"artist_text": "사양", "artist_url": URL + "?x"}, {"artist_text": "사양", "artist_url": URL},
                {"artist_text": "둘", "artist_url": "https://www.indiego.co.kr/artists/1-둘"},
                {"artist_text": "둘", "artist_url": "https://www.indiego.co.kr/artists/2-둘"},
                {"artist_text": "딴곳", "artist_url": "https://indistreet.com/artists/x"}]
        self.assertEqual(cig.team_pages(rows, key_of=lambda n: n), {"사양": URL})


if __name__ == "__main__":
    unittest.main()
