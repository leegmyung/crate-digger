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

    def test_channel_title_keyword_fallback(self):
        # 백필로 새로 들어올 채널(온스테이지 등)은 API 채널 이름이 정확히 무엇일지 몰라 낱말로도 찾는다
        self.assertEqual(ls.channel_source("네이버 ONSTAGE"), "video_onstage")
        self.assertEqual(ls.channel_source("온스테이지 2.0"), "video_onstage")
        self.assertEqual(ls.channel_source("EBS 스페이스 공감"), "video_ebs_space")
        self.assertEqual(ls.channel_source("문화콘서트 난장"), "video_nanjang")
        self.assertIsNone(ls.channel_source("어떤 팀 공식 채널"))

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



class StageVideosTest(unittest.TestCase):
    def test_all_stage_videos_not_capped_per_team(self):
        # 앱용 videos.csv 는 팀당 6개(최신순)라 옛 출연이 잘린다 — 평가는 원본 전체를 같은 거르기 규칙으로
        raw = [{"team_key": "실리카겔", "display_name": "실리카겔", "video_id": f"{i:011d}", "kind": "stage",
                "title": f"실리카겔 - 노래{i}", "channel_title": "스페이스 공감", "published_at": f"20{21 + i // 4}-01-0{1 + i % 4}T00:00:00Z"}
               for i in range(10)]
        raw.append({"team_key": "글로벌", "display_name": "글로벌", "video_id": "GLOBALVIDEO", "kind": "stage",
                    "title": "원호 │ 글로벌 대세", "channel_title": "it's Live", "published_at": "2024-01-01T00:00:00Z"})
        out = ls.stage_videos(raw)
        self.assertEqual(len(out), 10)                          # 10개 모두, 흔한 낱말 팀(글로벌)은 빠짐
        self.assertEqual(min(v["published_at"] for v in out), "2021-01-01")


class VideoFeatureTest(unittest.TestCase):
    SIG = [{"team_key": "a", "source": "video_ebs_space", "signal_date": "2022-05-01"},
           {"team_key": "a", "source": "video_its_live", "signal_date": "2022-06-01"},
           {"team_key": "a", "source": "video_its_live", "signal_date": "2022-07-01"},
           {"team_key": "a", "source": "video_dingo", "signal_date": "2023-02-01"},      # 기준일 뒤 → 안 셈
           {"team_key": "b", "source": "video_kbs_kpop", "signal_date": "2018-01-01"}]   # 3년보다 전 → 안 셈

    def test_distinct_channels_in_lookback_before_cutoff(self):
        self.assertEqual(ls.video_feature(self.SIG, "2023-01-01"), {"a": 2.0})

    def test_source_subset(self):
        self.assertEqual(ls.video_feature(self.SIG, "2023-01-01", sources={"video_its_live"}), {"a": 1.0})


class JudgeTest(unittest.TestCase):
    def test_role_rules(self):
        j = lambda **r: ls.judge_channel({"teams": 50, "hits": 5, "lift": 1.0, "only_source": 0, "first_to_see": 0, **r})[0]
        self.assertEqual(j(teams=12), "pending")                # 표본 부족
        self.assertEqual(j(lift=2.3), "discovery")
        self.assertEqual(j(lift=1.1, only_source=3), "discovery")
        self.assertEqual(j(lift=1.2), "context")
        self.assertEqual(j(lift=0.6, only_source=0), "excluded")
        self.assertEqual(j(lift=0.6, only_source=1), "context")


if __name__ == "__main__":
    unittest.main()
