"""scripts/build_design_mocks.py — 디자인 시안 HTML에 넣을 실제 상위 10팀 데이터 만들기."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_design_mocks as bdm  # noqa: E402


class PercentileTest(unittest.TestCase):
    def test_zero_or_negative_is_zero(self):
        self.assertEqual(bdm.percentile(0, [0, 0, 1, 2]), 0)

    def test_top_value_is_near_100(self):
        pool = list(range(1, 101))
        self.assertGreaterEqual(bdm.percentile(100, pool), 99)

    def test_ties_use_mid_rank(self):
        # 4개 중 2개가 같은 값(2): 아래 1개 + 같은 값 절반(1) = 2/4 → 50
        self.assertEqual(bdm.percentile(2, [1, 2, 2, 3]), 50)

    def test_empty_pool(self):
        self.assertEqual(bdm.percentile(3, []), 0)


class EventLabelTest(unittest.TestCase):
    PROGRAMS = {"burock_rookies": "부산록페 루키"}

    def test_program_label_wins(self):
        row = {"source": "busanrock", "program": "burock_rookies", "venue": ""}
        self.assertEqual(bdm.event_label(row, self.PROGRAMS), "부산록페 루키")

    def test_curation_program_name_is_used(self):
        row = {"source": "visla", "program": "VISLA", "venue": ""}
        self.assertEqual(bdm.event_label(row, self.PROGRAMS), "VISLA")

    def test_gig_shows_source_and_venue(self):
        row = {"source": "indistreet", "program": "", "venue": "클럽 FF"}
        self.assertEqual(bdm.event_label(row, self.PROGRAMS), "인디스트릿 · 클럽 FF")

    def test_unknown_source_falls_back_to_code(self):
        row = {"source": "newsrc", "program": "", "venue": ""}
        self.assertEqual(bdm.event_label(row, self.PROGRAMS), "newsrc")


class RecentEventsTest(unittest.TestCase):
    def test_excludes_future_and_sorts_desc(self):
        rows = [
            {"team_key": "a", "branch": "공연", "source": "indistreet", "program": "", "venue": "X", "signal_date": "2026-11-01"},
            {"team_key": "a", "branch": "선정·지원", "source": "busanrock", "program": "p", "venue": "", "signal_date": "2026-12-31"},
            {"team_key": "a", "branch": "큐레이션", "source": "izm", "program": "이즘", "venue": "", "signal_date": "2026-11-20"},
            {"team_key": "b", "branch": "공연", "source": "indistreet", "program": "", "venue": "Y", "signal_date": "2026-11-25"},
        ]
        got = bdm.recent_events(rows, "a", "2026-11-27", {}, n=5)
        self.assertEqual([e["date"] for e in got], ["2026-11-20", "2026-11-01"])
        self.assertEqual(got[0], {"date": "2026-11-20", "branch": "큐레이션", "label": "이즘"})

    def test_limit(self):
        rows = [{"team_key": "a", "branch": "공연", "source": "indistreet", "program": "", "venue": "",
                 "signal_date": f"2026-10-{d:02d}"} for d in range(1, 20)]
        self.assertEqual(len(bdm.recent_events(rows, "a", "2026-11-27", {}, n=5)), 5)


class SummaryTest(unittest.TestCase):
    def test_clauses_only_for_present_signals(self):
        facts = {"gigs_1y": 22, "venues": 8, "best_stage": 2, "peer_winner": 1, "outlets": 0,
                 "context_outlets": 0, "n_branch": 2}
        clauses = bdm.summary_clauses(facts)
        self.assertEqual(clauses[0], "최근 1년 공연 22회 · 공연장 8곳")
        self.assertIn("선정·지원 2단계", clauses)
        self.assertIn("수상 팀과 같은 무대", clauses)
        self.assertFalse(any("매거진" in c for c in clauses))

    def test_venues_without_recent_gigs(self):
        facts = {"gigs_1y": 0, "venues": 7, "best_stage": 0, "peer_winner": 0, "outlets": 1,
                 "context_outlets": 3, "n_branch": 3}
        clauses = bdm.summary_clauses(facts)
        self.assertEqual(clauses[0], "공연장 7곳")
        self.assertIn("발굴 매거진 1곳", clauses)
        self.assertIn("맥락 매거진 3곳", clauses)

    def test_topic_particle(self):
        self.assertEqual(bdm.topic_particle("포져군단"), "은")   # 받침 있음
        self.assertEqual(bdm.topic_particle("하즈"), "는")       # 받침 없음
        self.assertEqual(bdm.topic_particle("PCR"), "은(는)")    # 한글 아님


class InjectTest(unittest.TestCase):
    HTML = ('<html><body><script id="mock-data" type="application/json">OLD</script>'
            '<script>run()</script></body></html>')

    def test_replaces_only_data_block(self):
        out = bdm.inject_data(self.HTML, {"a": 1})
        self.assertIn('<script id="mock-data" type="application/json">{"a": 1}</script>', out)
        self.assertIn("<script>run()</script>", out)
        self.assertNotIn("OLD", out)

    def test_escapes_closing_tag(self):
        out = bdm.inject_data(self.HTML, {"a": "</script><b>"})
        block = out.split('type="application/json">', 1)[1].split("</script>", 1)[0]
        self.assertEqual(json.loads(block), {"a": "</script><b>"})

    def test_missing_marker_raises(self):
        with self.assertRaises(ValueError):
            bdm.inject_data("<html></html>", {})


class BuildPayloadTest(unittest.TestCase):
    """실제 docs/lab/data 로 상위 10팀을 만든다 (duckdb 없으면 건너뜀)."""

    @classmethod
    def setUpClass(cls):
        try:
            import duckdb  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("duckdb 없음 (.venv/bin/python 으로 실행)")
        cls.payload = bdm.build_payload()

    def test_top10_follows_latest_snapshot_order(self):
        # 스냅샷 순서를 따르되, 지금 규칙에서 후보가 아닌 팀(dropped)은 건너뛰고 다음 순위로 채운다
        snap_keys = [r["team_key"] for r in bdm.latest_snapshot()]
        keys = [t["key"] for t in self.payload["teams"]]
        self.assertEqual(len(keys), 10)
        self.assertEqual(keys, sorted(keys, key=snap_keys.index))
        skipped = [k for k in snap_keys[:snap_keys.index(keys[-1]) + 1] if k not in keys]
        self.assertEqual(sorted(skipped), sorted(d["key"] for d in self.payload["dropped"]))
        self.assertEqual([t["rank"] for t in self.payload["teams"]], list(range(1, 11)))

    def test_parts_add_up_to_score(self):
        for t in self.payload["teams"]:
            self.assertAlmostEqual(sum(p["pts"] for p in t["parts"]), t["score"], delta=0.05, msg=t["name"])

    def test_each_team_has_parts_and_name(self):
        keys = [c["key"] for c in self.payload["components"]]
        for t in self.payload["teams"]:
            self.assertTrue(t["name"])
            self.assertEqual([p["key"] for p in t["parts"]], keys)
            for p in t["parts"]:
                self.assertTrue(0 <= p["pct"] <= 100)

    def test_pool_size_and_date(self):
        self.assertGreater(self.payload["pool_size"], 10)
        self.assertRegex(self.payload["as_of"], r"^\d{4}-\d{2}-\d{2}$")


if __name__ == "__main__":
    unittest.main()
