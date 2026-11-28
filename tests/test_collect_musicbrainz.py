"""collect_musicbrainz.py — MusicBrainz(공개 음악 DB)에서 팀 공식 링크(유튜브·스포티파이·인스타) 찾기 테스트. 네트워크 없이."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import collect_musicbrainz as mb  # noqa: E402

SID = "4Z8W4fKeB5YxbusRsdQVPb"


class PickArtistTest(unittest.TestCase):
    def test_single_exact_key_match(self):
        artists = [{"id": "m1", "name": "포져군단"}, {"id": "m2", "name": "포져"}]
        self.assertEqual(mb.pick_artist("포져군단", artists)["id"], "m1")

    def test_two_namesakes_means_skip(self):
        artists = [{"id": "m1", "name": "유령서점"}, {"id": "m2", "name": "유령 서점"}]
        self.assertIsNone(mb.pick_artist("유령서점", artists))

    def test_no_match(self):
        self.assertIsNone(mb.pick_artist("천둥오리", [{"id": "m1", "name": "오리"}]))


class SearchableTest(unittest.TestCase):
    def test_short_or_common_names_are_not_searched(self):
        self.assertTrue(mb.searchable("포져군단"))
        self.assertFalse(mb.searchable("모래"))      # 한글 2자 = 짧은 이름 → 동명 위험
        self.assertFalse(mb.searchable("YB"))
        self.assertFalse(mb.searchable(""))


class ClassifyUrlsTest(unittest.TestCase):
    def test_channels_profiles_and_artist_pages_only(self):
        rels = [{"url": {"resource": "https://www.youtube.com/channel/UCALPByojGBk2ngqNeOb-nqg"}},
                {"url": {"resource": "https://www.youtube.com/@PCR_0"}},
                {"url": {"resource": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}},      # 영상 하나 → 채널 아님
                {"url": {"resource": f"https://open.spotify.com/artist/{SID}"}},
                {"url": {"resource": "https://open.spotify.com/album/" + "A" * 22}},
                {"url": {"resource": "https://www.instagram.com/poseridiott/"}},
                {"url": {"resource": "https://www.instagram.com/p/abc/"}},
                {"url": {"resource": "https://pachoongryu.bandcamp.com/"}},
                {"url": {"resource": "http://www.youtube.com/@insecure"}}]
        got = mb.classify_urls(rels)
        self.assertEqual(got["youtube"], ["https://www.youtube.com/channel/UCALPByojGBk2ngqNeOb-nqg",
                                          "https://www.youtube.com/@PCR_0"])
        self.assertEqual(got["spotify"], [SID])
        self.assertEqual(got["instagram"], ["poseridiott"])
        self.assertNotIn("bandcamp", got)

    def test_empty(self):
        self.assertEqual(mb.classify_urls([]), {})


class DatesTest(unittest.TestCase):
    """같은 조회 응답의 활동 시작(life-span.begin)·가장 이른 발매 묶음 날짜 — 데뷔 점검 두 번째 출처 (2026-11-28)."""
    def test_begin_and_earliest_release_group(self):
        detail = {"life-span": {"begin": "2012-05"}, "release-groups": [
            {"first-release-date": "2015-03-01"}, {"first-release-date": "2013"}, {"first-release-date": ""}]}
        self.assertEqual(mb.dates_of(detail), {"begin": "2012-05", "first_release": "2013"})

    def test_missing_fields_give_empty(self):
        self.assertEqual(mb.dates_of({"relations": []}), {})

    def test_run_stores_dates_without_extra_request(self):
        class Api:
            calls = []
            def __call__(self, path, params):
                self.calls.append((path, params.get("inc")))
                if path == "artist":
                    return {"artists": [{"id": "m1", "name": "포져군단", "score": 100}]}
                return {"relations": [], "life-span": {"begin": "2019"}, "release-groups": [{"first-release-date": "2020-01-02"}]}
        api = Api()
        out = mb.run([{"team_key": "pj", "display_name": "포져군단"}], {}, api, "2026-11-28")
        self.assertEqual(out["pj"]["begin"], "2019")
        self.assertEqual(out["pj"]["first_release"], "2020-01-02")
        self.assertEqual(len(api.calls), 2)
        self.assertIn("release-groups", api.calls[1][1])


class FakeApi:
    def __init__(self, search, lookup):
        self.search, self.lookup, self.calls = search, lookup, []

    def __call__(self, path, params):
        self.calls.append(path)
        if path == "artist":
            name = params["query"].split('"')[1]
            return {"artists": self.search.get(name, [])}
        return {"relations": self.lookup.get(path.split("/")[1], [])}


class RunTest(unittest.TestCase):
    def test_hits_misses_budget_and_resume(self):
        targets = [{"team_key": "pj", "display_name": "포져군단"}, {"team_key": "mr", "display_name": "모래"},
                   {"team_key": "cd", "display_name": "천둥오리"}, {"team_key": "gb", "display_name": "유령서점"}]
        api = FakeApi({"포져군단": [{"id": "m1", "name": "포져군단"}], "천둥오리": []},
                      {"m1": [{"url": {"resource": "https://www.instagram.com/poseridiott/"}}]})
        state = mb.run(targets, {}, api, today="2026-11-28", max_requests=3)
        self.assertEqual(state["pj"]["mbid"], "m1")
        self.assertEqual(state["pj"]["urls"], {"instagram": ["poseridiott"]})
        self.assertEqual(state["cd"], {"checked": "2026-11-28", "mbid": None})
        self.assertNotIn("mr", state)          # 짧은 이름은 묻지 않음
        self.assertNotIn("gb", state)          # 예산(3번) 끝
        self.assertEqual(api.calls, ["artist", "artist/m1", "artist"])
        again = FakeApi({"유령서점": []}, {})
        state2 = mb.run(targets, state, again, today="2026-11-29", max_requests=10)
        self.assertEqual(again.calls, ["artist"])   # 이미 본 팀은 다시 묻지 않음
        self.assertIn("gb", state2)

    def test_old_entries_are_rechecked_after_refresh_days(self):
        targets = [{"team_key": "cd", "display_name": "천둥오리"}]
        api = FakeApi({}, {})
        mb.run(targets, {"cd": {"checked": "2026-01-01", "mbid": None}}, api, today="2026-11-28", max_requests=5)
        self.assertEqual(api.calls, ["artist"])


if __name__ == "__main__":
    unittest.main()
