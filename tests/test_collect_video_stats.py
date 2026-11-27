"""유튜브 매일 지표: 영상 조회수·좋아요를 날짜별로 쌓고(collect_video_stats), 팀별 7일 증가량을 낸다(export_video_momentum).
네트워크 없이 가짜 API 로 테스트."""
import csv
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import collect_video_stats as cvs  # noqa: E402
import collect_videos as cv  # noqa: E402
import export_video_momentum as evm  # noqa: E402

IDS = [f"vid{i:08d}" for i in range(120)]   # 11자 영상 번호 120개


def fake_get_factory(calls, fail_after=None):
    def fake_get(endpoint, params, cost):
        calls.append((endpoint, params, cost))
        if fail_after is not None and len(calls) > fail_after:
            raise cv.QuotaExceeded("하루 한도")
        ids = params["id"].split(",")
        return {"items": [{"id": i, "statistics": {"viewCount": "100", "likeCount": "7", "commentCount": "1"}}
                          for i in ids if i != IDS[5]]}       # 지워진 영상은 결과에 없음
    return fake_get


class CollectTest(unittest.TestCase):
    def test_video_ids_unique_and_valid(self):
        rows = [{"team_key": "a", "video_id": IDS[0]}, {"team_key": "b", "video_id": IDS[0]},
                {"team_key": "a", "video_id": "bad"}, {"team_key": "c", "video_id": IDS[1]}]
        self.assertEqual(cvs.video_ids(rows), [IDS[0], IDS[1]])

    def test_batches_of_50_one_unit_each(self):
        calls = []
        rows = cvs.fetch_stats(IDS, fake_get_factory(calls), "2026-11-28")
        self.assertEqual(len(calls), 3)                               # 50 + 50 + 20
        self.assertTrue(all(c[0] == "videos" and c[1]["part"] == "statistics" and c[2] == 1 for c in calls))
        self.assertEqual(len(calls[0][1]["id"].split(",")), 50)
        self.assertEqual(len(rows), 119)                              # 결과에 없는 영상 1개 제외
        self.assertEqual(rows[0], {"date": "2026-11-28", "video_id": IDS[0], "view_count": 100, "like_count": 7,
                                   "comment_count": 1})

    def test_quota_stop_keeps_rows_so_far(self):
        calls = []
        rows = cvs.fetch_stats(IDS, fake_get_factory(calls, fail_after=1), "2026-11-28")
        self.assertEqual(len(rows), 49)                               # 첫 묶음(50개 중 1개 없음)까지만
        self.assertEqual(len(calls), 2)

    def test_hidden_counts_become_blank(self):
        get = lambda e, p, c: {"items": [{"id": IDS[0], "statistics": {"viewCount": "5"}}]}   # noqa: E731
        self.assertEqual(cvs.fetch_stats([IDS[0]], get, "2026-11-28")[0]["like_count"], "")

    def test_write_daily_file_overwrites_same_day(self):
        with tempfile.TemporaryDirectory() as d:
            p = cvs.write_rows(Path(d), "2026-11-28", [{"date": "2026-11-28", "video_id": IDS[0], "view_count": 1,
                                                       "like_count": 0, "comment_count": 0}])
            p = cvs.write_rows(Path(d), "2026-11-28", [])
            self.assertEqual(p.name, "raw_video_stats_2026-11-28.csv")
            self.assertEqual(p.read_text(encoding="utf-8").strip(), ",".join(cvs.COLUMNS))

    def test_stats_file_is_not_read_as_videos(self):
        # 랩 내보내기는 raw_video_*.csv 를 영상 목록으로 읽는다 → 통계 행엔 team_key 가 없어 영상으로 안 섞여야 함
        import export_lab_data as ex
        stats = [{"date": "2026-11-28", "video_id": IDS[0], "view_count": "1", "like_count": "", "comment_count": ""}]
        self.assertEqual(ex.video_rows(stats), [])
        self.assertNotIn("team_key", cvs.COLUMNS)


def stat(day, vid, views):
    return {"date": day, "video_id": vid, "view_count": str(views), "like_count": "", "comment_count": ""}


class MomentumTest(unittest.TestCase):
    VIDEOS = [{"team_key": "a", "video_id": IDS[0]}, {"team_key": "a", "video_id": IDS[1]},
              {"team_key": "b", "video_id": IDS[2]}, {"team_key": "c", "video_id": IDS[3]}]

    def test_seven_day_gain_per_team(self):
        stats = [stat("2026-11-20", IDS[0], 100), stat("2026-11-20", IDS[1], 50), stat("2026-11-20", IDS[2], 10),
                 stat("2026-11-25", IDS[0], 150),
                 stat("2026-11-27", IDS[0], 200), stat("2026-11-27", IDS[1], 60), stat("2026-11-27", IDS[2], 10),
                 stat("2026-11-27", IDS[3], 999)]
        rows = {r["team_key"]: r for r in evm.momentum_rows(stats, self.VIDEOS)}
        self.assertEqual(rows["a"]["views_7d_gain"], 110)            # (200-100)+(60-50), 기준 = 7일 전(11-20)
        self.assertEqual(rows["a"]["latest_views"], 260)
        self.assertEqual(rows["a"]["videos"], 2)
        self.assertEqual(rows["b"]["views_7d_gain"], 0)
        self.assertEqual(rows["c"]["views_7d_gain"], "")             # 7일 전 기록이 없으면 빈 칸 (아직 모름)
        self.assertEqual(rows["c"]["latest_views"], 999)

    def test_no_history_yet(self):
        rows = evm.momentum_rows([stat("2026-11-28", IDS[0], 5)], self.VIDEOS)
        self.assertEqual(rows, [{"team_key": "a", "views_7d_gain": "", "latest_views": 5, "videos": 1}])
        self.assertEqual(evm.momentum_rows([], self.VIDEOS), [])

    def test_write_csv(self):
        with tempfile.TemporaryDirectory() as d:
            p = evm.write_csv(Path(d) / "video_momentum.csv", [{"team_key": "a", "views_7d_gain": 1, "latest_views": 2, "videos": 1}])
            with open(p, encoding="utf-8") as f:
                self.assertEqual(list(csv.DictReader(f))[0]["views_7d_gain"], "1")
            self.assertEqual(evm.FIELDS, ["team_key", "views_7d_gain", "latest_views", "videos"])


if __name__ == "__main__":
    unittest.main()
