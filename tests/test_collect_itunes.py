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


class EnglishNameTest(unittest.TestCase):
    """소여: 한글로 찾으면 다른 가수만, 영문 활동명 'Sawyer'로 찾으면 우리 밴드 (첫 발매 2026 = 팀 프로필 2026-04-27)."""

    def search(self, term):
        self.calls.append(term)
        if term == "소여":
            return [song(6834559596, "소여", "세실리아 테마곡", "OST", date_="2026-11-20T00:00:00Z")]
        if term.lower() == "sawyer":
            return [song(1895097317, "Sawyer", "A boy dreaming of universe", "A boy dreaming of universe - Single",
                         date_="2026-04-27T00:00:00Z")]
        return []

    def setUp(self):
        self.calls = []

    def test_english_name_found_and_confirmed_by_year(self):
        targets = [{"team_key": "소여", "display_name": "소여"}]
        # 한글 '소여'(6834559596)는 차단 목록의 다른 가수 → 없는 것으로 보고 영문으로 더 찾는다
        state = ci.run(targets, {}, self.search, date(2026, 11, 28), max_requests=5, skip=set(), aliases={},
                       releases={}, first_release={"소여": "2026-04-27"}, en_names={"소여": ["sawyer"]},
                       blocked={("소여", "6834559596")})
        self.assertEqual(self.calls, ["소여", "sawyer"])
        self.assertEqual((state["소여"]["artist_id"], state["소여"]["confidence"]), (1895097317, "year"))
        self.assertEqual(state["소여"]["terms"], ["소여", "sawyer"])

    def test_blocked_korean_namesake_does_not_stop_english_search(self):
        # 한글 검색에서 이름이 같은 다른 가수(소여)가 잡혀도, 확인 등급이 아니면 영문으로 더 찾아본다
        targets = [{"team_key": "소여", "display_name": "소여"}]
        state = ci.run(targets, {}, self.search, date(2026, 11, 28), max_requests=5, skip=set(), aliases={},
                       releases={}, first_release={"소여": "2025-01-01"}, en_names={"소여": ["sawyer"]})
        self.assertEqual(self.calls, ["소여", "sawyer"])
        self.assertEqual(state["소여"]["confidence"], "name")

    def test_fresh_miss_retried_only_with_new_english_terms(self):
        targets = [{"team_key": "소여", "display_name": "소여"}]
        old = {"소여": {"checked": "2026-11-27", "artist_id": None, "terms": ["소여"]}}
        state = ci.run(targets, old, self.search, date(2026, 11, 28), max_requests=5, skip=set(), aliases={},
                       releases={}, first_release={"소여": "2026-04-27"}, en_names={"소여": ["sawyer"]},
                       blocked={("소여", "6834559596")})
        self.assertEqual(self.calls, ["sawyer"])
        self.assertEqual(state["소여"]["confidence"], "year")
        again = ci.run(targets, state, self.search, date(2026, 11, 28), max_requests=5, skip=set(), aliases={},
                       releases={}, first_release={}, en_names={"소여": ["sawyer"]})
        self.assertEqual(self.calls, ["sawyer"])        # 다 해 본 검색어면 다시 안 찾음
        self.assertEqual(again["소여"]["artist_id"], 1895097317)


class BlockedStoredEntryTest(EnglishNameTest):
    def test_stored_blocked_artist_is_searched_again(self):
        targets = [{"team_key": "소여", "display_name": "소여"}]
        old = {"소여": {"checked": "2026-11-28", "artist_id": 6834559596, "confidence": "year"}}
        state = ci.run(targets, old, self.search, date(2026, 11, 28), max_requests=5, skip=set(), aliases={},
                       releases={}, first_release={"소여": "2026-04-27"}, en_names={"소여": ["sawyer"]},
                       blocked={("소여", "6834559596")})
        self.assertEqual(self.calls, ["소여", "sawyer"])
        self.assertEqual(state["소여"]["artist_id"], 1895097317)


class ArtistLookupTest(unittest.TestCase):
    """영문 이름은 곡 검색 상위가 동명 다른 가수로 채워진다 → 아티스트 검색 + 아티스트별 곡 조회, 확인된 아티스트가 딱 하나일 때만."""

    class Fake:
        def __init__(self, songs_by_artist, artists):
            self.songs_by_artist, self.artists_list, self.calls = songs_by_artist, artists, []

        def __call__(self, term):
            self.calls.append(("song", term))
            return [song(889293, "Sawyer Brown", "x", "y", date_="1990-01-01T00:00:00Z")]

        def artists(self, term):
            self.calls.append(("artist", term))
            return self.artists_list

        def songs_of(self, artist_id):
            self.calls.append(("lookup", artist_id))
            return self.songs_by_artist.get(artist_id, [])

    ARTISTS = [{"artistId": 111, "artistName": "Sawyer"}, {"artistId": 1895097317, "artistName": "Sawyer"},
               {"artistId": 889293, "artistName": "Sawyer Brown"}]
    SONGS = {111: [song(111, "Sawyer", "Old Song", "Old", date_="2012-01-01T00:00:00Z")],
             1895097317: [song(1895097317, "Sawyer", "A boy dreaming of universe", "A boy dreaming of universe - Single",
                               date_="2026-04-27T00:00:00Z")]}

    def run_team(self, fake, first="2026-04-27"):
        return ci.run([{"team_key": "소여", "display_name": "소여"}], {}, fake, date(2026, 11, 28), max_requests=10,
                      skip=set(), aliases={}, releases={}, first_release={"소여": first}, en_names={"소여": ["sawyer"]})

    def test_one_confirmed_namesake_is_picked(self):
        fake = self.Fake(self.SONGS, self.ARTISTS)
        state = self.run_team(fake)
        self.assertEqual((state["소여"]["artist_id"], state["소여"]["confidence"]), (1895097317, "year"))
        self.assertIn(("lookup", 1895097317), fake.calls)
        self.assertNotIn(("lookup", 889293), fake.calls)          # 이름이 다른 아티스트는 조회 안 함

    def test_two_confirmed_namesakes_means_none(self):
        songs = dict(self.SONGS)
        songs[111] = [song(111, "Sawyer", "Other 2026", "Other", date_="2026-02-01T00:00:00Z")]
        state = self.run_team(self.Fake(songs, self.ARTISTS))
        self.assertNotIn(state["소여"].get("confidence"), ("titles", "year"))

    def test_no_confirmed_namesake_keeps_unconfirmed(self):
        state = self.run_team(self.Fake(self.SONGS, self.ARTISTS), first="2020-01-01")
        self.assertNotIn(state["소여"].get("confidence"), ("titles", "year"))


class TitleSearchTest(unittest.TestCase):
    """이름 검색으로 못 찾으면 우리 곡 제목(멜론 데뷔곡·발매 기록)으로 곡 검색 → 이름(영문 후보 포함)이 맞는 아티스트."""

    class Fake:
        def __init__(self):
            self.calls = []

        def __call__(self, term):
            self.calls.append(("song", term))
            return []

        def artists(self, term):
            self.calls.append(("artist", term))
            return []

        def songs_of(self, artist_id):
            return []

        def songs_by_title(self, title):
            self.calls.append(("title", title))
            if title == "우주를 꿈꾸는 소년":
                return [song(1895097317, "Sawyer", "A boy dreaming of universe", "A boy dreaming of universe - Single",
                             date_="2026-04-27T00:00:00Z"),
                        song(5, "다른 가수", "우주를 꿈꾸는 소년", "커버", date_="2026-05-01T00:00:00Z")]
            return []

    def test_title_search_finds_english_named_artist(self):
        fake = self.Fake()
        state = ci.run([{"team_key": "소여", "display_name": "소여"}], {}, fake, date(2026, 11, 28), max_requests=10,
                       skip=set(), aliases={}, releases={}, first_release={"소여": "2026-04-27"},
                       en_names={"소여": ["sawyer"]}, titles={"소여": ["우주를 꿈꾸는 소년"]})
        self.assertEqual((state["소여"]["artist_id"], state["소여"]["confidence"]), (1895097317, "year"))
        self.assertIn(("title", "우주를 꿈꾸는 소년"), fake.calls)

    def test_title_search_needs_name_match(self):
        fake = self.Fake()
        state = ci.run([{"team_key": "소여", "display_name": "소여"}], {}, fake, date(2026, 11, 28), max_requests=10,
                       skip=set(), aliases={}, releases={}, first_release={"소여": "2026-04-27"},
                       en_names={}, titles={"소여": ["우주를 꿈꾸는 소년"]})
        self.assertIsNone(state["소여"].get("artist_id"))       # 영문 후보가 없으면 'Sawyer'를 우리 팀으로 볼 근거 없음


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
