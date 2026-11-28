"""coverage_targets.py — 사진·바로 듣기 수집 대상(후보 상위 + 정답 팀)과 커버리지 계산 테스트."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import coverage_targets as ct  # noqa: E402


class BuildTargetsTest(unittest.TestCase):
    def test_ranked_first_then_outcome_only_teams(self):
        rows = ct.build_targets(["b", "a", "c"], ["c", "z", "y"], {"a": "에이", "b": "비", "z": "제트"}, top_n=2)
        self.assertEqual([r["team_key"] for r in rows], ["b", "a", "c", "y", "z"])
        self.assertEqual(rows[0], {"team_key": "b", "display_name": "비", "rank": 1, "outcome": False})
        self.assertEqual(rows[2], {"team_key": "c", "display_name": "c", "rank": None, "outcome": True})  # 상위 밖·정답, 이름 모르면 키
        self.assertEqual(rows[4]["display_name"], "제트")

    def test_ranked_team_that_is_also_outcome_keeps_rank(self):
        rows = ct.build_targets(["a"], ["a"], {}, top_n=5)
        self.assertEqual(rows, [{"team_key": "a", "display_name": "a", "rank": 1, "outcome": True}])


class CoverageTest(unittest.TestCase):
    def test_percentages_for_top_groups_and_outcomes(self):
        targets = [{"team_key": k, "rank": i + 1, "outcome": False} for i, k in enumerate("abcd")]
        targets.append({"team_key": "z", "rank": None, "outcome": True})
        cov = ct.coverage(targets, photo={"a", "z"}, play={"a", "b", "c"}, groups=(2, 4))
        self.assertEqual(cov["top2"], {"teams": 2, "photo": 1, "play": 2, "photo_pct": 50.0, "play_pct": 100.0})
        self.assertEqual(cov["top4"]["play"], 3)
        self.assertEqual(cov["outcomes"], {"teams": 1, "photo": 1, "play": 0, "photo_pct": 100.0, "play_pct": 0.0})

    def test_empty_group_is_zero_not_error(self):
        self.assertEqual(ct.coverage([], set(), set(), groups=(3,))["top3"]["photo_pct"], 0.0)


class SaveLoadTest(unittest.TestCase):
    def test_round_trip_and_missing_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "t.json"
            self.assertEqual(ct.load_targets(path), [])
            ct.save_targets(path, [{"team_key": "a", "display_name": "에이", "rank": 1, "outcome": False}], "2026-11-28")
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["as_of"], "2026-11-28")
            self.assertEqual(ct.load_targets(path)[0]["display_name"], "에이")


if __name__ == "__main__":
    unittest.main()
