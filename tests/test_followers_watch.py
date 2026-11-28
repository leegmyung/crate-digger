"""scripts/followers_watch.py — 팔로워 기록용 관찰 목록 (상위 300 + 앱에서 내려받은 관심 팀)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import followers_watch as fw  # noqa: E402


class LinkTest(unittest.TestCase):
    def test_melon_id_and_instagram_handle(self):
        self.assertEqual(fw.melon_id("https://www.melon.com/artist/detail.htm?artistId=991470"), "991470")
        self.assertIsNone(fw.melon_id("https://www.melon.com/artist/detail.htm"))
        self.assertEqual(fw.insta_handle("https://www.instagram.com/oysters.999/"), "oysters.999")
        self.assertIsNone(fw.insta_handle("https://www.instagram.com/p/AbC123/"))      # 게시물 주소는 계정 아님
        self.assertIsNone(fw.insta_handle("https://example.com/x"))


class BuildTest(unittest.TestCase):
    def test_top_n_then_watch_teams_without_duplicates(self):
        targets = [{"team_key": f"t{i}", "rank": i} for i in range(1, 6)] + [{"team_key": "w0", "rank": None}]
        names = {"팀 셋": "t3", "관심팀": "w1"}
        teams = fw.build_watch(targets, ["관심팀", "팀 셋", "모름"], names, top_n=3)
        self.assertEqual([(t["team_key"], t["why"]) for t in teams],
                         [("t1", "top"), ("t2", "top"), ("t3", "top"), ("w1", "watch")])

    def test_ids_and_handles_from_links(self):
        teams = [{"team_key": "a", "why": "top"}, {"team_key": "b", "why": "watch"}, {"team_key": "c", "why": "watch"}]
        links = {"a": {"melon": "https://www.melon.com/artist/detail.htm?artistId=1",
                       "instagram": "https://www.instagram.com/aa/"},
                 "b": {"melon": "https://www.melon.com/artist/detail.htm?artistId=2"}}
        out = fw.attach_links(teams, links)
        self.assertEqual(out[0], {"team_key": "a", "why": "top", "melon_id": "1", "instagram": "aa"})
        self.assertEqual(fw.melon_extra_ids(out), ["2"])          # 상위 팀은 collect_artists --refresh 가 이미 7일마다 봄
        self.assertEqual(fw.instagram_handles(out), ["aa"])

    def test_indistreet_sns_fills_missing_instagram_only(self):
        links = {"a": {"instagram": "https://www.instagram.com/aa/"}, "b": {}}
        sns = {"a": {"instagram": "zz"}, "b": {"instagram": "bb"}, "c": {"instagram": None}}
        out = fw.merge_indistreet(links, sns)
        self.assertEqual(out["a"]["instagram"], "https://www.instagram.com/aa/")     # 이미 있는 연결이 먼저
        self.assertEqual(out["b"]["instagram"], "https://www.instagram.com/bb/")
        self.assertNotIn("c", out)
        self.assertEqual(links["b"], {})                                             # 원본은 그대로

    def test_watch_names_from_app_csv(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "watchlist_2026-11-28.csv"
            f.write_text("﻿팀,장르,상태\n포져군단,록,지켜보는 중\nPCR,록,연락함\n", encoding="utf-8")
            self.assertEqual(fw.watch_names([f]), ["포져군단", "PCR"])


if __name__ == "__main__":
    unittest.main()
