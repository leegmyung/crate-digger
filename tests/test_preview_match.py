"""preview_match.py — iTunes·Deezer 검색 결과에서 같은 팀을 보수적으로 고르기 테스트. 네트워크 없이."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import preview_match as pm  # noqa: E402


def song(artist_id, artist, track, album, date="2025-01-01T00:00:00Z", preview="https://audio-ssl.itunes.apple.com/a.m4a"):
    return {"wrapperType": "track", "kind": "song", "artistId": artist_id, "artistName": artist, "trackName": track,
            "collectionName": album, "releaseDate": date, "previewUrl": preview,
            "artworkUrl100": "https://is1-ssl.mzstatic.com/image/thumb/x/100x100bb.jpg",
            "trackViewUrl": "https://music.apple.com/kr/album/x?i=1", "artistViewUrl": "https://music.apple.com/kr/artist/x/1"}


class ItunesPickTest(unittest.TestCase):
    def test_one_artist_with_same_name_key(self):
        res = [song(1, "포져군단", "노래", "앨범"), song(1, "포져군단", "노래2", "앨범2", date="2026-01-01T00:00:00Z"),
               song(2, "포져", "다른", "다른 앨범")]
        got = pm.itunes_pick("포져군단", res)
        self.assertEqual(got["artist_id"], 1)
        self.assertEqual(got["titles"], {"노래", "노래2", "앨범", "앨범2"})
        self.assertEqual(got["preview"]["trackName"], "노래2")     # 가장 최근 곡

    def test_two_artists_with_same_name_means_skip(self):
        res = [song(1, "유령서점", "a", "b"), song(2, "유령 서점", "c", "d")]
        self.assertIsNone(pm.itunes_pick("유령서점", res))

    def test_collab_credit_is_not_a_match(self):
        self.assertIsNone(pm.itunes_pick("포져군단", [song(3, "포져군단 & 다른팀", "a", "b")]))

    def test_unsafe_preview_url_is_dropped(self):
        got = pm.itunes_pick("포져군단", [song(1, "포져군단", "a", "b", preview="http://evil.example/a.m4a")])
        self.assertIsNone(got["preview"])


class AliasTest(unittest.TestCase):
    def test_itunes_accepts_english_alias(self):
        got = pm.itunes_pick(["실리카겔", "Silica Gel"], [song(5, "Silica Gel", "NO PAIN", "POWER ANDRE 99")])
        self.assertEqual(got["artist_id"], 5)

    def test_deezer_ignores_empty_duplicate_entries(self):
        arts = [{"id": 1, "name": "Silica Gel", "nb_album": 21}, {"id": 2, "name": "실리카겔", "nb_album": 0}]
        self.assertEqual(pm.deezer_pick(["실리카겔", "Silica Gel"], arts)["id"], 1)

    def test_deezer_two_real_entries_still_skip(self):
        arts = [{"id": 1, "name": "Silica Gel", "nb_album": 21}, {"id": 3, "name": "Silica Gel", "nb_album": 14}]
        self.assertIsNone(pm.deezer_pick(["Silica Gel"], arts))


class DeezerPickTest(unittest.TestCase):
    def test_exactly_one_same_key_artist(self):
        arts = [{"id": 10, "name": "Leaveourtears", "picture_medium": "https://e-cdns-images.dzcdn.net/a/250x250.jpg"},
                {"id": 11, "name": "Leave Our Tears Band"}]
        self.assertEqual(pm.deezer_pick("Leaveourtears", arts)["id"], 10)

    def test_namesakes_skip(self):
        arts = [{"id": 10, "name": "아토"}, {"id": 12, "name": "ATO"}, {"id": 13, "name": "아토"}]
        self.assertIsNone(pm.deezer_pick("아토", arts))


class VerifyTest(unittest.TestCase):
    def test_any_title_overlap_after_normalizing(self):
        self.assertTrue(pm.titles_overlap({"그 여름"}, {"그여름", "다른곡"}))
        self.assertFalse(pm.titles_overlap({"그 여름"}, {"가을"}))
        self.assertFalse(pm.titles_overlap(set(), {"가을"}))

    def test_title_variants_like_single_suffix_still_overlap(self):
        self.assertTrue(pm.titles_overlap({"Qualia"}, {"Qualia - Single"}))
        self.assertTrue(pm.titles_overlap({"새벽 (Feat. 누구)"}, {"새벽"}))


class SafeUrlTest(unittest.TestCase):
    def test_hosts(self):
        self.assertTrue(pm.safe_url("https://audio-ssl.itunes.apple.com/x.m4a", pm.ITUNES_AUDIO_HOSTS))
        self.assertFalse(pm.safe_url("https://evil.example/x.m4a", pm.ITUNES_AUDIO_HOSTS))
        self.assertFalse(pm.safe_url("http://audio-ssl.itunes.apple.com/x.m4a", pm.ITUNES_AUDIO_HOSTS))


if __name__ == "__main__":
    unittest.main()
