"""live_sessions: 무대·라이브 세션 채널 출연을 임시 '큐레이션' 신호로 만들어 출처처럼 재기."""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import live_sessions as ls  # noqa: E402

VIDEOS = [
    {"team_key": "a", "video_id": "1", "title": "a 라이브", "channel_title": "스페이스 공감", "published_at": "2025-11-02", "kind": "stage"},
    {"team_key": "a", "video_id": "2", "title": "a 또", "channel_title": "스페이스 공감", "published_at": "2025-11-02", "kind": "stage"},
    {"team_key": "b", "video_id": "3", "title": "b", "channel_title": "it's Live", "published_at": "2025-12-01", "kind": "stage"},
    {"team_key": "c", "video_id": "4", "title": "c 공식", "channel_title": "c 채널", "published_at": "2025-12-01", "kind": "official"},
    {"team_key": "d", "video_id": "5", "title": "d", "channel_title": "모르는 채널", "published_at": "2025-12-01", "kind": "stage"},
]


class SignalRowsTest(unittest.TestCase):
    def test_stage_videos_from_known_channels_become_curation_signals(self):
        rows = ls.video_signal_rows(VIDEOS, role="discovery")
        self.assertEqual(len(rows), 2)                          # 같은 팀·채널·날짜는 한 줄, 공식 채널·모르는 채널은 뺌
        a = next(r for r in rows if r["team_key"] == "a")
        self.assertEqual((a["branch"], a["source"], a["signal_date"], a["role"]), ("큐레이션", "video_ebs_space", "2025-11-02", "discovery"))
        self.assertEqual(next(r for r in rows if r["team_key"] == "b")["source"], "video_its_live")

    def test_source_key_matches_scorecard_key(self):
        self.assertEqual(ls.src_key("video_ebs_space"), "큐레이션:video_ebs_space")


class SameHouseTest(unittest.TestCase):
    def test_ebs_space_before_hello_rookie_is_same_house(self):
        sig = ls.video_signal_rows(VIDEOS, role="discovery")
        outs = [{"team_key": "a", "program": "hello_rookie_year", "announced_date": date(2026, 11, 20)},
                {"team_key": "a", "program": "penta_superrookie", "announced_date": date(2026, 5, 30)},
                {"team_key": "a", "program": "hello_rookie", "announced_date": date(2025, 10, 1)},   # 영상보다 먼저 → 아님
                {"team_key": "b", "program": "hello_rookie", "announced_date": date(2026, 4, 28)}]  # it's Live 는 EBS 아님
        tags = ls.same_house_tags(outs, sig)
        self.assertEqual(tags, {("a", "hello_rookie_year", date(2026, 11, 20))})


class SummaryTest(unittest.TestCase):
    def test_channel_coverage(self):
        cov = {c["source"]: c for c in ls.channel_coverage(VIDEOS)}
        self.assertEqual((cov["video_ebs_space"]["videos"], cov["video_ebs_space"]["teams"]), (2, 1))
        self.assertEqual(cov["video_ebs_space"]["first"], "2025-11-02")


if __name__ == "__main__":
    unittest.main()
