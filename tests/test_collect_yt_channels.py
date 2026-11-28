"""collect_yt_channels.py — 팀 공식 유튜브 채널의 아바타·최신 영상 받기 테스트. 네트워크 없이."""
import csv
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import collect_videos as cv  # noqa: E402
import collect_yt_channels as yc  # noqa: E402

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 28, 12, 0, tzinfo=KST)
CID = "UCALPByojGBk2ngqNeOb-nqg"


class CandidateTest(unittest.TestCase):
    def test_links_then_musicbrainz_then_instagram_bio(self):
        links = [{"team_key": "a", "platform": "youtube", "url": "https://www.youtube.com/@aaa"},
                 {"team_key": "c", "platform": "instagram", "url": "https://www.instagram.com/c_band/"}]
        mbz = {"a": {"mbid": "m", "urls": {"youtube": ["https://www.youtube.com/@a_mb"]}},
               "b": {"mbid": "m", "urls": {"youtube": ["https://www.youtube.com/channel/" + CID]}},
               "x": {"mbid": None}}
        ig = {"c_band": {"links": [{"kind": "youtube", "url": "https://youtube.com/@cband?si=xyz"},
                                   {"kind": "youtube", "url": "https://youtu.be/dQw4w9WgXcQ"}]},
              "non_artists": {"c_band": {"links": [{"kind": "youtube", "url": "https://youtube.com/@nope"}]}}}
        got = yc.candidate_channels(links, mbz, ig)
        self.assertEqual(got["a"], ("https://www.youtube.com/@aaa", "links"))
        self.assertEqual(got["b"], ("https://www.youtube.com/channel/" + CID, "musicbrainz"))
        self.assertEqual(got["c"], ("https://youtube.com/@cband", "instagram"))   # 영상 주소는 채널 아님
        self.assertNotIn("x", got)


class YtSearchCandidateTest(unittest.TestCase):
    def test_search_found_channels_are_lowest_priority_candidates(self):
        links = [{"team_key": "a", "platform": "youtube", "url": "https://www.youtube.com/@aaa"}]
        found = {"a": {"checked": "2026-11-28", "channel_id": CID}, "b": {"checked": "2026-11-28", "channel_id": CID},
                 "c": {"checked": "2026-11-28", "channel_id": ""}}
        got = yc.candidate_channels(links, {}, {}, found)
        self.assertEqual(got["a"], ("https://www.youtube.com/@aaa", "links"))
        self.assertEqual(got["b"], ("https://www.youtube.com/channel/" + CID, "yt_search"))
        self.assertNotIn("c", got)


class AvatarTest(unittest.TestCase):
    def test_prefers_medium_https_google_host(self):
        th = {"default": {"url": "https://yt3.ggpht.com/a=s88"}, "medium": {"url": "https://yt3.ggpht.com/a=s240"},
              "high": {"url": "https://yt3.ggpht.com/a=s800"}}
        self.assertEqual(yc.pick_avatar(th), "https://yt3.ggpht.com/a=s240")

    def test_rejects_other_hosts(self):
        self.assertEqual(yc.pick_avatar({"medium": {"url": "https://evil.example/a.jpg"}}), "")
        self.assertEqual(yc.pick_avatar({}), "")


class FakeClient:
    def __init__(self, channels, playlist, budget=100):
        self.channels, self.playlist, self.calls = channels, playlist, []
        self.quota = cv.Quota(budget)

    def get(self, endpoint, params, cost):
        self.quota.spend(cost)
        self.calls.append((endpoint, {k: v for k, v in params.items() if k != "part"}))
        if endpoint == "channels":
            key = params.get("forHandle") or params.get("id") or params.get("forUsername")
            return {"items": self.channels.get(key, [])}
        return {"items": self.playlist}


def _channel(cid=CID, title="포져군단"):
    return [{"id": cid, "snippet": {"title": title, "thumbnails": {"medium": {"url": "https://yt3.ggpht.com/p=s240"}}},
             "contentDetails": {"relatedPlaylists": {"uploads": "UU" + cid[2:]}}}]


PLAYLIST = [{"snippet": {"title": "포져군단 - 노래 (Live Session)", "channelTitle": "포져군단", "channelId": CID},
             "contentDetails": {"videoId": "AAAAAAAAAAA", "videoPublishedAt": "2026-10-01T00:00:00Z"}},
            {"snippet": {"title": "포져군단 'Song' MV", "channelTitle": "포져군단", "channelId": CID},
             "contentDetails": {"videoId": "BBBBBBBBBBB", "videoPublishedAt": "2026-09-01T00:00:00Z"}},
            {"snippet": {"title": "비공개 영상"}, "contentDetails": {"videoId": "CCCCCCCCCCC"}}]


class RunTest(unittest.TestCase):
    def test_new_channel_gets_avatar_and_latest_videos(self):
        targets = [{"team_key": "pj", "display_name": "포져군단"}, {"team_key": "zz", "display_name": "없음"}]
        cands = {"pj": ("https://www.youtube.com/channel/" + CID, "musicbrainz")}
        client = FakeClient({CID: _channel()}, PLAYLIST)
        state, rows = yc.run(targets, cands, {}, client, NOW, linked=set())
        ch = state["teams"]["pj"]
        self.assertEqual((ch["channel_id"], ch["title"], ch["source"]), (CID, "포져군단", "musicbrainz"))
        self.assertEqual(ch["avatar"], "https://yt3.ggpht.com/p=s240")
        self.assertEqual(ch["checked"], "2026-11-28")
        self.assertEqual([(r["video_id"], r["kind"]) for r in rows],
                         [("AAAAAAAAAAA", "official_live"), ("BBBBBBBBBBB", "official")])
        self.assertEqual(rows[0]["team_key"], "pj")
        self.assertEqual(rows[0]["display_name"], "포져군단")
        self.assertEqual([c[0] for c in client.calls], ["channels", "playlistItems"])

    def test_linked_channel_skips_playlist_because_collect_videos_has_it(self):
        targets = [{"team_key": "pj", "display_name": "포져군단"}]
        client = FakeClient({"@pj": _channel()}, PLAYLIST)
        state, rows = yc.run(targets, {"pj": ("https://www.youtube.com/@pj", "links")}, {}, client, NOW, linked={"pj"})
        self.assertEqual(rows, [])
        self.assertEqual(client.calls, [("channels", {"forHandle": "@pj"})])
        self.assertIn("pj", state["teams"])

    def test_missing_channel_is_remembered_and_fresh_entries_skipped(self):
        targets = [{"team_key": "pj", "display_name": "포져군단"}, {"team_key": "ok", "display_name": "오케이"}]
        cands = {"pj": ("https://www.youtube.com/@gone", "links"), "ok": ("https://www.youtube.com/@ok", "links")}
        old = {"teams": {"ok": {"channel_id": CID, "checked": "2026-11-20"}}, "misses": {}}
        client = FakeClient({}, [])
        state, _ = yc.run(targets, cands, old, client, NOW, linked={"pj", "ok"})
        self.assertEqual(state["misses"]["pj"]["url"], "https://www.youtube.com/@gone")
        self.assertEqual(len(client.calls), 1)       # ok 는 30일 안이라 다시 안 물음

    def test_stale_entry_refreshed_after_30_days(self):
        targets = [{"team_key": "pj", "display_name": "포져군단"}]
        old = {"teams": {"pj": {"channel_id": CID, "checked": "2026-10-01"}}, "misses": {}}
        client = FakeClient({"@pj": _channel()}, [])
        state, _ = yc.run(targets, {"pj": ("https://www.youtube.com/@pj", "links")}, old, client, NOW, linked={"pj"})
        self.assertEqual(state["teams"]["pj"]["checked"], "2026-11-28")

    def test_budget_stop_keeps_what_was_done(self):
        targets = [{"team_key": "a", "display_name": "에이"}, {"team_key": "b", "display_name": "비"}]
        cands = {"a": ("https://www.youtube.com/@a", "links"), "b": ("https://www.youtube.com/@b", "links")}
        client = FakeClient({"@a": _channel(), "@b": _channel()}, [], budget=1)
        state, _ = yc.run(targets, cands, {}, client, NOW, linked={"a", "b"})
        self.assertEqual(list(state["teams"]), ["a"])


class PlaylistErrorTest(unittest.TestCase):
    def test_channel_without_uploads_still_keeps_avatar(self):
        class NoPlaylist(FakeClient):
            def get(self, endpoint, params, cost):
                if endpoint == "playlistItems":
                    self.quota.spend(cost)
                    raise cv.YouTubeError("x", 404, "playlistNotFound")
                return super().get(endpoint, params, cost)
        client = NoPlaylist({CID: _channel()}, [])
        state, rows = yc.run([{"team_key": "pj", "display_name": "포져군단"}],
                             {"pj": ("https://www.youtube.com/channel/" + CID, "musicbrainz")}, {}, client, NOW, linked=set())
        self.assertEqual(rows, [])
        self.assertEqual(state["teams"]["pj"]["avatar"], "https://yt3.ggpht.com/p=s240")


class WriteRowsTest(unittest.TestCase):
    def test_rows_go_to_raw_video_channels_file(self):
        with tempfile.TemporaryDirectory() as d:
            row = cv.make_row(NOW, "pj", "포져군단", "AAAAAAAAAAA", "t", "c", CID, "2026-10-01T00:00:00Z", "official", "")
            path = yc.write_raw(Path(d), NOW, [row])
            self.assertEqual(path.name, "raw_video_2026-11-28_channels.csv")
            with open(path, encoding="utf-8") as f:
                self.assertEqual(list(csv.DictReader(f))[0]["video_id"], "AAAAAAAAAAA")


if __name__ == "__main__":
    unittest.main()
