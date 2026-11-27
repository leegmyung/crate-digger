"""출처 재분류 제안(source_review): 출처 성적표와 분류표(config/source_roles.json)가 어긋나면 알려 준다."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import source_review as sr  # noqa: E402


def row(src, role, teams=100, hits=1, lift=1.0, only=0, since="2020-01-01"):
    return {"src": src, "role": role, "teams": teams, "hits": hits, "lift": lift, "only_source": only,
            "since_date": since, "rate": 1.0, "winners_seen": 3, "first_to_see": 1, "signal_rows": 500}


ROLES = {"signals": {k: {"role": r} for k, r in {
    "공연:a": "discovery", "공연:b": "discovery", "큐레이션:c": "context", "큐레이션:d": "context",
    "선정·지원:e": "excluded", "발매:f": "pending", "발매:g": "pending", "큐레이션:h": "context",
    "공연:i": "discovery"}.items()}}


class CutoffTest(unittest.TestCase):
    def test_half_year_aligned_18_12_6_months_before_data_end(self):
        cuts, since = sr.review_cutoffs("2026-11-27")
        self.assertEqual(cuts, ["2025-01-01", "2025-07-01", "2026-01-01"])
        self.assertEqual(since, "2024-07-01")

    def test_alignment_on_boundary(self):
        cuts, since = sr.review_cutoffs("2026-07-01")
        self.assertEqual(cuts, ["2025-01-01", "2025-07-01", "2026-01-01"])
        self.assertEqual(sr.review_cutoffs("2026-06-30")[0], ["2024-07-01", "2025-01-01", "2025-07-01"])

    def test_sql_values(self):
        self.assertEqual(sr.cutoffs_sql(["2025-01-01", "2025-07-01"]), "(DATE '2025-01-01'),(DATE '2025-07-01')")


class SuggestTest(unittest.TestCase):
    def suggestions(self, rows, day="2026-11-27"):
        return {s["src"]: s for s in sr.suggest(rows, ROLES, day)}

    def test_rules(self):
        got = self.suggestions([
            row("공연:a", "discovery", lift=0.8, only=0),            # 내릴 후보
            row("공연:b", "discovery", lift=0.8, only=2),            # 유일 기여가 있어 그대로
            row("큐레이션:c", "context", lift=2.1),                   # 올릴 후보 (배수)
            row("큐레이션:d", "context", lift=0.5, only=3),          # 유일 기여는 많지만 기준선 이하 → 그대로
            row("큐레이션:h", "context", lift=1.2, only=3),          # 올릴 후보 (유일 기여 + 기준선 이상)
            row("선정·지원:e", "excluded", hits=1),                   # 재검토
            row("발매:f", "pending", teams=40, since="2026-07-01"),   # 평가 가능
            row("발매:g", "pending", teams=40, since="2026-10-01"),   # 아직 90일 안 됨
            row("협업:new", "pending"),                               # 미분류
        ])
        self.assertEqual(got["공연:a"]["kind"], "demote")
        self.assertNotIn("공연:b", got)
        self.assertEqual(got["큐레이션:c"]["kind"], "promote")
        self.assertNotIn("큐레이션:d", got)
        self.assertEqual(got["큐레이션:h"]["kind"], "promote")
        self.assertEqual(got["선정·지원:e"]["kind"], "recheck")
        self.assertEqual(got["발매:f"]["kind"], "ready")
        self.assertNotIn("발매:g", got)
        self.assertEqual(got["협업:new"]["kind"], "unclassified")
        self.assertIn("context", got["공연:a"]["suggestion"])
        self.assertTrue(all(s["reason"] for s in got.values()))

    def test_small_sample_instead_of_suggestion(self):
        got = self.suggestions([row("큐레이션:h", "context", teams=12, lift=3.0),
                                row("공연:i", "discovery", teams=15, lift=0.2)])
        self.assertEqual({s["kind"] for s in got.values()}, {"small_sample"})
        self.assertIn("표본 부족", got["큐레이션:h"]["suggestion"])

    def test_no_suggestion_when_consistent(self):
        self.assertEqual(sr.suggest([row("공연:a", "discovery", lift=1.5, only=4)], ROLES, "2026-11-27"), [])

    def test_missing_numbers_do_not_crash(self):
        r = row("공연:a", "discovery")
        r.update(lift=None, teams=0, hits=0)
        self.assertEqual(sr.suggest([r], ROLES, "2026-11-27"), [])

    def test_role_from_config_not_from_scorecard(self):
        # 성적표의 role 칸이 낡았어도 판정은 지금 분류표 기준
        got = self.suggestions([row("공연:a", "context", lift=0.5, only=0)])
        self.assertEqual(got["공연:a"]["role"], "discovery")
        self.assertEqual(got["공연:a"]["kind"], "demote")


class ReportTest(unittest.TestCase):
    def test_changed_date_kept_when_same_and_updated_when_different(self):
        s1 = [{"src": "공연:a", "kind": "demote", "role": "discovery", "suggestion": "x", "reason": "y"}]
        first = sr.build_report([], s1, "2026-11-27", ["2025-01-01"], "2024-07-01", prev=None)
        self.assertEqual(first["suggestions_changed_on"], "2026-11-27")
        same = sr.build_report([], s1, "2026-11-30", ["2025-01-01"], "2024-07-01", prev=first)
        self.assertEqual(same["suggestions_changed_on"], "2026-11-27")
        s2 = s1 + [{"src": "발매:f", "kind": "ready", "role": "pending", "suggestion": "x", "reason": "y"}]
        diff = sr.build_report([], s2, "2026-12-01", ["2025-01-01"], "2024-07-01", prev=same)
        self.assertEqual(diff["suggestions_changed_on"], "2026-12-01")

    def test_public_fields_only(self):
        rep = sr.build_report([row("공연:a", "discovery")], [], "2026-11-27", ["2025-01-01"], "2024-07-01", prev=None)
        self.assertEqual(set(rep["sources"][0]), set(sr.PUBLIC_SOURCE_FIELDS))
        self.assertIn("rules", rep)


if __name__ == "__main__":
    unittest.main()
