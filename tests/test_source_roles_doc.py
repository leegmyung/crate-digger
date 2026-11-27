"""source_roles_doc: docs/source_roles.md 의 성적표 구간(주석 마커 사이)만 자동 생성으로 교체."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import source_roles_doc as srd  # noqa: E402


def card(src, role, teams, hits, rate, lift, seen=0, first=0, only=0, lead=None, since="2023-01-02", rows=10):
    return {"src": src, "role": role, "signal_rows": rows, "since_date": since, "teams": teams, "hits": hits,
            "rate": rate, "lift": lift, "base_rate": 0.9, "winners_seen": seen, "first_to_see": first,
            "only_source": only, "median_lead_months": lead}


class ReplaceTest(unittest.TestCase):
    def test_replace_only_between_markers(self):
        text = "앞\n<!-- AUTO:X:START -->\n옛 표\n<!-- AUTO:X:END -->\n뒤\n"
        out = srd.replace_block(text, "X", "새 표")
        self.assertEqual(out, "앞\n<!-- AUTO:X:START -->\n새 표\n<!-- AUTO:X:END -->\n뒤\n")
        self.assertEqual(srd.replace_block(out, "X", "새 표"), out)          # 여러 번 돌려도 같음

    def test_missing_marker_raises(self):
        with self.assertRaises(ValueError):
            srd.replace_block("마커 없음", "X", "새 표")


class TableTest(unittest.TestCase):
    def test_scored_table_rows_and_order(self):
        rows = [card("공연:indistreet", "discovery", 3459, 48, 1.39, 1.6, 56, 34, 24, 10.0, "2024-01-04"),
                card("큐레이션:weiv", "context", 14, 0, 0.0, 0.0),
                card("발매:melon", "pending", 0, 0, None, None, since="2026-11-24", rows=42)]
        lines = srd.scored_table(rows, {"공연:indistreet": "인디스트릿 공연"})
        self.assertIn("| 공연:indistreet (인디스트릿 공연) | discovery | 2024-01 | 3,459 | 48 | 1.39% | 1.6 | 56 (34 / 24) | 10 |", lines)
        self.assertIn("| 큐레이션:weiv | context | 2023-01 | 14 | 0 | 0% | — | 0 | — |", lines)
        self.assertFalse(any("발매:melon" in ln for ln in lines))            # 후보 0팀(검증 대기)은 아래 표로

    def test_pending_table_reeval_date(self):
        rows = [card("발매:melon", "pending", 0, 0, None, None, since="2026-11-24", rows=42)]
        lines = srd.pending_table(rows, {})
        self.assertIn("| 발매:melon | 2026-11-24 | 42 | 2027-02-24 이후 |", lines)

    def test_summary_sentence(self):
        s = srd.summary_line(("2024-07-01", "2025-01-01"), 130, 0.89)
        self.assertIn("기준일 2개(2024-07-01·2025-01-01)", s)
        self.assertIn("**130팀**", s)
        self.assertIn("**0.89%**", s)


if __name__ == "__main__":
    unittest.main()
