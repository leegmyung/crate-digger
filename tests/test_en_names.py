"""en_names.py — 팀별 영문 활동명 모으기(검색 전용) 테스트. 네트워크 없이."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import en_names as en  # noqa: E402


class LatinPairTest(unittest.TestCase):
    def test_both_orders(self):
        self.assertEqual(en.latin_pair("사우스카니발 (South Carnival)"), ("사우스카니발", "South Carnival"))
        self.assertEqual(en.latin_pair("Sun The Lily (썬더릴리)"), ("썬더릴리", "Sun The Lily"))
        self.assertEqual(en.latin_pair("장박이(VIAS)"), ("장박이", "VIAS"))

    def test_not_a_pair(self):
        self.assertIsNone(en.latin_pair("소여"))
        self.assertIsNone(en.latin_pair("새벽 (feat. 누구)"))
        self.assertIsNone(en.latin_pair("밴드 (2024)"))
        self.assertIsNone(en.latin_pair("A (B)"))


class HandleTest(unittest.TestCase):
    def test_strips_band_and_official_words(self):
        self.assertEqual(en.handle_name("band_sawyer"), "sawyer")
        self.assertEqual(en.handle_name("official_kimsejeong"), "kimsejeong")
        self.assertEqual(en.handle_name("lunedi_niverse"), "lunedi niverse")
        self.assertEqual(en.handle_name("ghost_bookstore_official"), "ghost bookstore")
        self.assertEqual(en.handle_name("the.doorbell.band"), "the doorbell")

    def test_too_short_or_numeric(self):
        self.assertIsNone(en.handle_name("band_ab"))
        self.assertIsNone(en.handle_name("12345"))
        self.assertIsNone(en.handle_name(""))


class BuildTest(unittest.TestCase):
    def test_sources_merge_and_only_korean_named_teams(self):
        display = {"소여": "소여", "사우스카니발": "사우스카니발", "pcr": "PCR"}
        got = en.build(display,
                       xref_aliases={"사우스카니발": ["사우스카니발", "South Carnival"]},
                       raw_texts=["사우스카니발 (South Carnival)", "소여 (Sawyer Band)", "PCR (피씨알)"],
                       musicbrainz={"소여": {"mbid": "m", "name": "Sawyer"}},
                       spotify={}, handles={"소여": ["band_sawyer"]})
        self.assertEqual([x["name"] for x in got["소여"]], ["Sawyer Band", "Sawyer"])   # 더 나은 출처가 있으면 인스타 계정은 안 씀
        self.assertEqual([x["name"] for x in got["사우스카니발"]], ["South Carnival"])
        self.assertNotIn("pcr", got)                 # 이미 영문 이름인 팀은 필요 없음

    def test_handle_used_only_when_no_better_source(self):
        got = en.build({"소여": "소여"}, {}, [], {}, {}, {"소여": ["band_sawyer"]})
        self.assertEqual(got["소여"], [{"name": "sawyer", "source": "instagram"}])

    def test_spotify_name_counts(self):
        got = en.build({"소여": "소여"}, {}, [], {}, {"소여": "Sawyer"}, {})
        self.assertEqual(got["소여"], [{"name": "Sawyer", "source": "spotify"}])

    def test_names_for_search_dedupes_by_key(self):
        state = {"소여": [{"name": "Sawyer", "source": "musicbrainz"}, {"name": "SAWYER", "source": "raw"}]}
        self.assertEqual(en.names_for(state, "소여"), ["Sawyer"])
        self.assertEqual(en.names_for(state, "없는팀"), [])


if __name__ == "__main__":
    unittest.main()
