"""이름 정규화 키와 여러 플랫폼 입점 집계 테스트."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import normalize as nz  # noqa: E402


class ArtistKeyTest(unittest.TestCase):
    def test_spacing_and_case_ignored(self):
        self.assertEqual(nz.artist_key("스트레인지 프룻"), nz.artist_key("스트레인지프룻"))
        self.assertEqual(nz.artist_key("Eddie and the Bricks"), nz.artist_key("eddie and the bricks"))

    def test_alias_in_brackets_dropped(self):
        self.assertEqual(nz.artist_key("오존(O3ohn)"), "오존")
        self.assertEqual(nz.artist_key("사뮈 (Samui)"), "사뮈")
        self.assertEqual(nz.artist_key("다브다 (Dabda)"), nz.artist_key("다브다"))

    def test_bracket_only_name_kept(self):
        self.assertEqual(nz.artist_key("(여자)아이들"), "여자아이들")
        self.assertEqual(nz.artist_key("ㅈ(지읒)"), "ㅈ")

    def test_symbols_removed(self):
        self.assertEqual(nz.artist_key("Pine."), "pine")
        self.assertEqual(nz.artist_key("GR2N!"), "gr2n")

    def test_empty(self):
        self.assertEqual(nz.artist_key(""), "")
        self.assertEqual(nz.artist_key(None), "")


class TitleKeyTest(unittest.TestCase):
    def test_feat_dropped_version_kept(self):
        self.assertEqual(nz.title_key("Tree Tree (feat. 손모은)"), nz.title_key("Tree Tree"))
        self.assertNotEqual(nz.title_key("슬픔 (Band Version)"), nz.title_key("슬픔"))

    def test_spacing_and_quotes(self):
        self.assertEqual(nz.title_key("I’m Pine. Thank you"), nz.title_key("Im Pine Thank you"))


class PlatformsSeenTest(unittest.TestCase):
    def test_counts_platforms_per_album(self):
        rows = [
            {"source": "melon", "artist_key": "에피톤프로젝트", "title_key": "겨울"},
            {"source": "flo", "artist_key": "에피톤프로젝트", "title_key": "겨울"},
            {"source": "flo", "artist_key": "에피톤프로젝트", "title_key": "겨울"},
            {"source": "bugs", "artist_key": "오존", "title_key": "qualia"},
        ]
        seen = nz.platforms_seen(rows)
        self.assertEqual(seen[("에피톤프로젝트", "겨울")], ["flo", "melon"])
        self.assertEqual(seen[("오존", "qualia")], ["bugs"])

    def test_rows_without_keys_use_raw_text(self):
        rows = [{"source": "poclanos", "artist_text": "결 (KYUL)", "title": "세탁"},
                {"source": "genie", "artist_text": "결", "title": "세탁"}]
        self.assertEqual(nz.platforms_seen(rows)[("결", "세탁")], ["genie", "poclanos"])



class SplitArtistCellTest(unittest.TestCase):
    """한 칸에 쉼표로 이어 쓴 여러 팀(오버톤 'SUMIN, Slom' 등 25건) → 팀별로. 이름 자체에 쉼표가 있는 팀은 그대로."""

    def test_splits_comma_list(self):
        self.assertEqual(nz.split_artist_cell("SUMIN, Slom"), ["SUMIN", "Slom"])
        self.assertEqual(nz.split_artist_cell("sokodomo, Loco, Valo"), ["sokodomo", "Loco", "Valo"])
        self.assertEqual(nz.split_artist_cell("Pendulum, Joey Valence & Brae"), ["Pendulum", "Joey Valence & Brae"])
        self.assertEqual(nz.split_artist_cell("Sun Gin, 격"), ["Sun Gin", "격"])

    def test_names_with_comma_kept(self):
        for name in ("Tyler, The Creator", "Mandy, Indiana", "Black Country, New Road", "tyler, the creator"):
            with self.subTest(name=name):
                self.assertEqual(nz.split_artist_cell(name), [name])

    def test_single_name_and_parens(self):
        self.assertEqual(nz.split_artist_cell("주영"), ["주영"])
        self.assertEqual(nz.split_artist_cell("X33D (씨드, Seed)"), ["X33D (씨드, Seed)"])
        self.assertEqual(nz.split_artist_cell(""), [])

    def test_headline_phrase_and_label_pieces_dropped(self):
        self.assertEqual(nz.split_artist_cell("데미지 없이도 끌어올린 타격감, 김도언"), ["김도언"])
        self.assertEqual(nz.split_artist_cell("ScreaM Records, 서울커뮤니티라디오"), ["서울커뮤니티라디오"])
        self.assertEqual(nz.split_artist_cell("QM, Fredi Casso"), ["QM", "Fredi Casso"])


if __name__ == "__main__":
    unittest.main()
