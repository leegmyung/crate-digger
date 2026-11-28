"""players.py — 팀별 '바로 듣기' 재생 대상(스포티파이·유튜브) 고르기 테스트."""
import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import players as pl  # noqa: E402


def _v(team, vid, title, kind="stage", date="2026-01-01", channel="딩고 뮤직"):
    return {"team_key": team, "video_id": vid, "title": title, "channel_title": channel,
            "published_at": date, "kind": kind}


class YoutubePickTest(unittest.TestCase):
    def test_official_live_beats_everything(self):
        vids = [_v("a", "STAGE000001", "에이 [it's Live]"),
                _v("a", "OFFLIVE0001", "에이 - 노래 (Live Session)", kind="official_live", date="2025-01-01"),
                _v("a", "OFFMV000001", "에이 - 노래 Official MV", kind="official", date="2026-05-01")]
        self.assertEqual(pl.pick_youtube(vids, {})["video_id"], "OFFLIVE0001")

    def test_official_music_video_beats_stage(self):
        vids = [_v("a", "STAGE000001", "에이 [it's Live]", date="2026-06-01"),
                _v("a", "OFFMV000001", "에이 '노래' M/V", kind="official", date="2025-01-01")]
        self.assertEqual(pl.pick_youtube(vids, {})["video_id"], "OFFMV000001")

    def test_stage_beats_non_music_official_and_search(self):
        vids = [_v("a", "VLOG0000001", "연습 브이로그", kind="official", date="2026-09-01"),
                _v("a", "SEARCH00001", "에이 라이브", kind="search", date="2026-09-01"),
                _v("a", "STAGE000001", "에이 [it's Live]", date="2025-01-01")]
        self.assertEqual(pl.pick_youtube(vids, {})["video_id"], "STAGE000001")

    def test_non_music_official_beats_search(self):
        vids = [_v("a", "SEARCH00001", "에이 라이브", kind="search", date="2026-09-01"),
                _v("a", "VLOG0000001", "연습 브이로그", kind="official", date="2026-01-01")]
        self.assertEqual(pl.pick_youtube(vids, {})["video_id"], "VLOG0000001")

    def test_stage_picks_most_viewed_then_latest(self):
        vids = [_v("a", "STAGE000001", "에이 1", date="2026-01-01"),
                _v("a", "STAGE000002", "에이 2", date="2026-03-01"),
                _v("a", "STAGE000003", "에이 3", date="2026-02-01")]
        self.assertEqual(pl.pick_youtube(vids, {"STAGE000003": 500, "STAGE000001": 100})["video_id"], "STAGE000003")
        self.assertEqual(pl.pick_youtube(vids, {})["video_id"], "STAGE000002")

    def test_official_prefers_latest(self):
        vids = [_v("a", "OFFMV000001", "에이 MV", kind="official", date="2025-01-01"),
                _v("a", "OFFMV000002", "에이 MV 2", kind="official", date="2026-01-01")]
        self.assertEqual(pl.pick_youtube(vids, {"OFFMV000001": 10 ** 6})["video_id"], "OFFMV000002")

    def test_empty_means_none(self):
        self.assertIsNone(pl.pick_youtube([], {}))


class PlayerRowsTest(unittest.TestCase):
    def test_spotify_and_youtube_rows_per_team(self):
        links = [{"team_key": "a", "platform": "spotify", "url": "https://open.spotify.com/artist/" + "A" * 22},
                 {"team_key": "b", "platform": "melon", "url": "https://www.melon.com/artist/detail.htm?artistId=1"},
                 {"team_key": "c", "platform": "spotify", "url": "https://open.spotify.com/artist/bad"}]
        vids = [_v("a", "STAGE000001", "에이 [it's Live]"), _v("b", "STAGE000002", "비 [it's Live]")]
        rows = pl.player_rows(links, vids, {"STAGE000002": 42})
        self.assertEqual([(r["team_key"], r["kind"], r["id"]) for r in rows],
                         [("a", "spotify", "artist:" + "A" * 22), ("a", "youtube", "STAGE000001"), ("b", "youtube", "STAGE000002")])
        self.assertEqual(rows[2]["view_count"], "42")
        self.assertEqual(rows[2]["source"], "stage")
        self.assertEqual(rows[2]["channel_title"], "딩고 뮤직")
        self.assertEqual(rows[0]["source"], "spotify")
        self.assertEqual(set(rows[0]), set(pl.PLAYER_FIELDS))

    def test_first_spotify_link_wins(self):
        links = [{"team_key": "a", "platform": "spotify", "url": "https://open.spotify.com/artist/" + "A" * 22},
                 {"team_key": "a", "platform": "spotify", "url": "https://open.spotify.com/artist/" + "B" * 22}]
        rows = pl.player_rows(links, [], {})
        self.assertEqual([r["id"] for r in rows], ["artist:" + "A" * 22])

    def test_bad_video_ids_skipped(self):
        self.assertEqual(pl.player_rows([], [_v("a", "bad", "에이")], {}), [])


class ViewCountTest(unittest.TestCase):
    def test_latest_stats_file_wins(self):
        with tempfile.TemporaryDirectory() as d:
            for day, views in (("2026-11-27", "10"), ("2026-11-28", "20")):
                with open(Path(d) / f"raw_video_stats_{day}.csv", "w", encoding="utf-8", newline="") as f:
                    w = csv.writer(f)
                    w.writerow(["date", "video_id", "view_count", "like_count", "comment_count"])
                    w.writerow([day, "AAAAAAAAAAA", views, "", ""])
                    w.writerow([day, "BBBBBBBBBBB", "x", "", ""])
            self.assertEqual(pl.latest_views(Path(d)), {"AAAAAAAAAAA": 20})

    def test_missing_dir_is_empty(self):
        self.assertEqual(pl.latest_views(Path("/nonexistent-dir-xyz")), {})


if __name__ == "__main__":
    unittest.main()
