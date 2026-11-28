"""collect_artist_images: 스포티파이 아티스트 사진 주소를 팀별로 모은다 (한 명씩 조회, 캐시)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import collect_artist_images as ci  # noqa: E402

IMAGES = [{"url": "https://i.scdn.co/image/big", "width": 640}, {"url": "https://i.scdn.co/image/mid", "width": 320},
          {"url": "https://i.scdn.co/image/small", "width": 160}]


class PickTest(unittest.TestCase):
    def test_picks_smallest_image_at_least_target_width(self):
        self.assertEqual(ci.pick_image(IMAGES, target=200), "https://i.scdn.co/image/mid")
        self.assertEqual(ci.pick_image(IMAGES, target=100), "https://i.scdn.co/image/small")

    def test_rejects_non_spotify_hosts_and_empty(self):
        self.assertIsNone(ci.pick_image([]))
        self.assertIsNone(ci.pick_image([{"url": "http://evil.example/x.jpg", "width": 300}]))


class TargetsTest(unittest.TestCase):
    def test_spotify_ids_from_links_skip_cached(self):
        links = [{"team_key": "a", "platform": "spotify", "url": "https://open.spotify.com/artist/AAAAAAAAAAAAAAAAAAAAAA"},
                 {"team_key": "b", "platform": "spotify", "url": "https://open.spotify.com/artist/BBBBBBBBBBBBBBBBBBBBBB"},
                 {"team_key": "c", "platform": "melon", "url": "https://www.melon.com/artist/detail.htm?artistId=1"}]
        got = ci.targets(links, cache={"a": {"url": "x"}})
        self.assertEqual(got, [("b", "BBBBBBBBBBBBBBBBBBBBBB")])

    def test_priority_order_puts_top_candidates_first(self):
        links = [{"team_key": k, "platform": "spotify", "url": "https://open.spotify.com/artist/" + k.upper() * 22}
                 for k in ("a", "b", "c")]
        got = ci.targets(links, cache={}, order=["c", "a"])
        self.assertEqual([t for t, _ in got], ["c", "a", "b"])


class RunTest(unittest.TestCase):
    def test_fetches_and_stops_at_budget(self):
        calls = []

        def fake_get(path, params):
            calls.append(path)
            return {"images": IMAGES}
        cache = ci.fetch_images([("a", "A" * 22), ("b", "B" * 22), ("c", "C" * 22)], fake_get, cache={}, budget=2)
        self.assertEqual(sorted(cache), ["a", "b"])
        self.assertEqual(cache["a"]["source"], "spotify")
        self.assertEqual(len(calls), 2)

    def test_photo_known_from_search_needs_no_request(self):
        calls = []
        cache = ci.fetch_images([("a", "A" * 22), ("b", "B" * 22)], lambda p, q: calls.append(p) or {"images": IMAGES},
                                cache={}, budget=1, known={"A" * 22: "https://i.scdn.co/image/known"})
        self.assertEqual(cache["a"]["url"], "https://i.scdn.co/image/known")
        self.assertEqual(cache["b"]["url"], "https://i.scdn.co/image/mid")
        self.assertEqual(calls, ["/artists/" + "B" * 22])

    def test_missing_image_is_cached_as_none_so_not_retried(self):
        cache = ci.fetch_images([("a", "A" * 22)], lambda p, q: {"images": []}, cache={}, budget=5)
        self.assertIsNone(cache["a"]["url"])


if __name__ == "__main__":
    unittest.main()
