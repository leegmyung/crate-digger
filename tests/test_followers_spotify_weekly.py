"""scripts/followers_spotify_weekly.py — 관찰 팀 스포티파이 팔로워 주 1회 (/v1/artists?ids=, 50팀씩, 하루 예산 공유)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import collect_spotify as cs  # noqa: E402
import followers_spotify_weekly as fw  # noqa: E402

ID = lambda n: f"{n:0>22}"  # noqa: E731  22자 스포티파이 번호


class FakeClient:
    def __init__(self, pages, fail_at=None):
        self.pages = list(pages)
        self.calls = []
        self.fail_at = fail_at

    def get(self, path, params):
        self.calls.append((path, params["ids"].split(",")))
        if self.fail_at is not None and len(self.calls) == self.fail_at:
            raise cs.RateLimited("429 오래 기다리라고 함")
        return self.pages.pop(0)


class IdsTest(unittest.TestCase):
    def test_spotify_ids_from_links_and_batches(self):
        teams = [{"team_key": "a"}, {"team_key": "b"}, {"team_key": "c"}]
        links = {"a": {"spotify": f"https://open.spotify.com/artist/{ID(1)}"},
                 "b": {"spotify": "https://open.spotify.com/album/xyz"}}
        self.assertEqual(fw.spotify_ids(teams, links), [("a", ID(1))])
        self.assertEqual(fw.batches(list(range(120)), 50), [list(range(50)), list(range(50, 100)), list(range(100, 120))])


class RunTest(unittest.TestCase):
    def run_weekly(self, client, pairs, day="2026-11-30", state=None):
        d = tempfile.mkdtemp()
        log, st = Path(d) / "followers_spotify.jsonl", Path(d) / "weekly.json"
        if state:
            st.write_text(json.dumps(state), encoding="utf-8")
        res = fw.run_weekly(client, pairs, day, log, st)
        lines = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
        return res, lines, json.loads(st.read_text(encoding="utf-8")) if st.exists() else None

    def test_records_followers_and_marks_week(self):
        pairs = [("a", ID(1)), ("b", ID(2))]
        client = FakeClient([{"artists": [{"id": ID(1), "followers": {"total": 10}}, {"id": ID(2), "followers": {"total": 3}}]}])
        res, lines, state = self.run_weekly(client, pairs)
        self.assertEqual(lines, [{"team_key": "a", "spotify_id": ID(1), "date": "2026-11-30", "followers": 10},
                                 {"team_key": "b", "spotify_id": ID(2), "date": "2026-11-30", "followers": 3}])
        self.assertEqual((res["recorded"], res["empty"], res["requests"]), (2, 0, 1))
        self.assertEqual(state["last_run"], "2026-11-30")

    def test_empty_followers_not_recorded_only_counted(self):
        client = FakeClient([{"artists": [{"id": ID(1), "followers": {"total": None}}, None]}])
        res, lines, _ = self.run_weekly(client, [("a", ID(1)), ("b", ID(2))])
        self.assertEqual(lines, [])
        self.assertEqual((res["recorded"], res["empty"]), (0, 2))
        self.assertIn("비어", res["note"])

    def test_skips_if_run_within_a_week(self):
        client = FakeClient([])
        res, _, _ = self.run_weekly(client, [("a", ID(1))], day="2026-12-03", state={"last_run": "2026-11-30"})
        self.assertTrue(res["skipped"])
        self.assertEqual(client.calls, [])

    def test_rate_limit_stops_and_waits_until_next_week(self):
        pairs = [(f"t{i}", ID(i)) for i in range(60)]
        client = FakeClient([{"artists": [{"id": ID(i), "followers": {"total": i}} for i in range(50)]}], fail_at=2)
        res, lines, state = self.run_weekly(client, pairs)
        self.assertEqual(len(lines), 50)                       # 첫 묶음은 남김
        self.assertIn("429", res["stopped"])
        self.assertEqual(state["last_run"], "2026-11-30")      # 이번 주는 끝 — 다음 주에 다시
        self.assertEqual([len(ids) for _, ids in client.calls], [50, 10])


if __name__ == "__main__":
    unittest.main()
