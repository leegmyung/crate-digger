"""collect_itunes.py — iTunes 30초 미리듣기 찾기(확인 등급·요청 상한·갱신) 테스트. 네트워크 없이."""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import collect_itunes as ci  # noqa: E402


def song(artist_id, artist, track, album, date_="2025-03-01T00:00:00Z", preview="https://audio-ssl.itunes.apple.com/p/a.m4a"):
    return {"kind": "song", "artistId": artist_id, "artistName": artist, "trackId": 77, "trackName": track,
            "collectionName": album, "releaseDate": date_, "previewUrl": preview,
            "artworkUrl100": "https://is1-ssl.mzstatic.com/image/thumb/a/100x100bb.jpg",
            "trackViewUrl": "https://music.apple.com/us/album/x/1?i=77", "artistViewUrl": "https://music.apple.com/us/artist/x/1"}


class ConfidenceTest(unittest.TestCase):
    def test_title_overlap_beats_year(self):
        pick = {"titles": {"Angel", "Green"}, "first_year": "2025"}
        self.assertEqual(ci.confidence(pick, our_titles=["angel"], first_release="2024-01-01"), "titles")

    def test_same_first_release_year(self):
        pick = {"titles": {"X"}, "first_year": "2025"}
        self.assertEqual(ci.confidence(pick, our_titles=[], first_release="2025-06-16"), "year")

    def test_name_only(self):
        pick = {"titles": {"X"}, "first_year": "2019"}
        self.assertEqual(ci.confidence(pick, our_titles=["y"], first_release="2025-04-07"), "name")
        self.assertEqual(ci.confidence(pick, our_titles=[], first_release=""), "name")


class EntryTest(unittest.TestCase):
    def test_entry_keeps_links_and_earliest_year(self):
        results = [song(1, "Post Inner Circle", "Angel", "Angel - Single", date_="2026-01-02T00:00:00Z"),
                   song(1, "Post Inner Circle", "Green", "Green", date_="2025-06-16T00:00:00Z")]
        entry = ci.entry_for(["포스트이너서클", "Post Inner Circle"], results, our_titles=[], first_release="2025-06-16",
                             today=date(2026, 11, 28))
        self.assertEqual(entry["confidence"], "year")
        self.assertEqual(entry["artist_url"], "https://music.apple.com/us/artist/x/1")
        self.assertEqual(entry["preview"]["track_name"], "Angel")       # 가장 최근 곡
        self.assertEqual(entry["preview"]["preview_url"], "https://audio-ssl.itunes.apple.com/p/a.m4a")
        self.assertEqual(entry["preview"]["track_url"], "https://music.apple.com/us/album/x/1?i=77")
        self.assertEqual(entry["checked"], "2026-11-28")

    def test_no_match_is_remembered(self):
        entry = ci.entry_for(["없는팀"], [song(1, "다른팀", "a", "b")], [], "", date(2026, 11, 28))
        self.assertEqual(entry, {"checked": "2026-11-28", "artist_id": None})

    def test_unsafe_link_back_dropped(self):
        bad = dict(song(1, "Pipe Lips", "a", "b"), trackViewUrl="javascript:alert(1)")
        entry = ci.entry_for(["Pipe Lips"], [bad], [], "", date(2026, 11, 28))
        self.assertEqual(entry["preview"]["track_url"], "")


class RunTest(unittest.TestCase):
    def test_order_cap_skip_and_refresh(self):
        targets = [{"team_key": k, "display_name": n} for k, n in (("a", "에이팀"), ("b", "비팀"), ("c", "씨팀"), ("d", "디팀"))]
        calls = []

        def search(term):
            calls.append(term)
            return [song(1, term, "곡", "앨범")]
        state = ci.run(targets, {"a": {"checked": "2026-11-20", "artist_id": None}}, search, date(2026, 11, 28),
                       max_requests=2, skip={"b"}, aliases={}, releases={}, first_release={})
        self.assertEqual(calls, ["씨팀", "디팀"])                  # a 는 30일 안, b 는 이미 재생 가능
        self.assertEqual(state["c"]["artist_name"], "씨팀")
        old = ci.run(targets, {"a": {"checked": "2026-10-01", "artist_id": None}}, search, date(2026, 11, 28),
                     max_requests=1, skip={"b", "c", "d"}, aliases={}, releases={}, first_release={})
        self.assertEqual(old["a"]["checked"], "2026-11-28")         # 30일 지나면 다시


class PlayerRowsTest(unittest.TestCase):
    def test_only_confirmed_entries_become_player_rows(self):
        state = {"a": {"artist_id": 1, "confidence": "year", "artist_name": "A",
                       "preview": {"preview_url": "https://audio-ssl.itunes.apple.com/p/a.m4a", "track_name": "곡",
                                   "track_url": "https://music.apple.com/us/album/x/1?i=77", "release_date": "2025-03-01"}},
                 "b": {"artist_id": 2, "confidence": "name", "preview": {"preview_url": "https://audio-ssl.itunes.apple.com/b.m4a"}},
                 "c": {"artist_id": None}}
        rows = ci.player_rows(state)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["kind"], "itunes")
        self.assertEqual(rows[0]["id"], "https://audio-ssl.itunes.apple.com/p/a.m4a")
        self.assertEqual(rows[0]["page_url"], "https://music.apple.com/us/album/x/1?i=77")
        self.assertEqual(rows[0]["source"], "itunes")


if __name__ == "__main__":
    unittest.main()
