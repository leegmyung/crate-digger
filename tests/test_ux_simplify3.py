"""쉬운 화면 3차 — 발굴 '주목 이유' 두 줄까지 (docs/layout_rules.md 3절) · 도시·페스티벌 같은 블록 순서.

화면 코드는 브라우저 모듈(DuckDB)이라 node 로 못 불러와서, 규칙이 코드·CSS·문서에 있는지만 본다.
실제 모습은 bash scripts/e2e_check.sh 와 docs/ux/2026-11-28/after3/ 스크린샷으로 확인.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "docs" / "app"


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


class WhyCellTwoLinesTest(unittest.TestCase):
    def test_reason_cell_wraps_text_in_clamp_with_full_title(self):
        js = read("docs/app/views/candidates.js")
        self.assertRegex(js, r'class="why-cell[^"]*" title="\$\{escapeHtml\(whyTxt\)\}"><span class="why-clamp">')
        self.assertIn('class="cand-mobile-why why-clamp" title="${escapeHtml(whyTxt)}"', js)

    def test_clamp_css_two_lines(self):
        css = read("docs/app/css/ux.css")
        block = re.search(r"\.why-clamp\s*\{([^}]*)\}", css)
        self.assertIsNotNone(block, "ux.css 에 .why-clamp 규칙")
        self.assertIn("-webkit-line-clamp: 2", block.group(1))
        self.assertRegex(css, r"\.cand-table td\.why-cell\s*\{[^}]*white-space:\s*normal")

    def test_layout_rule_documented(self):
        self.assertIn("why-clamp", read("docs/layout_rules.md"))


class PlaceBlockOrderTest(unittest.TestCase):
    """도시·페스티벌도 공연장과 같은 순서: 머리 → 질문 3개(venue-qa) → 숫자 줄 → 이번 달/다가오는 것 → 나머지"""

    def assert_order(self, rel: str, markers: list[str]):
        js = read(rel)
        pos = []
        for m in markers:
            i = js.find(m)
            self.assertGreaterEqual(i, 0, f"{rel}: '{m}' 없음")
            pos.append(i)
        self.assertEqual(pos, sorted(pos), f"{rel}: 블록 순서 {markers}")

    def test_city_page_order(self):
        self.assert_order("docs/app/views/city_page.js", ["${qaHtml}", "${kpiHtml}", "${upcomingHtml}"])

    def test_festival_page_order(self):
        self.assert_order("docs/app/views/festival_page.js", ["${qaHtml}", "${kpiHtml}", "${editionsHtml}"])

    def test_qa_markup_shared(self):
        # 질문 상자 모양은 공연장과 같은 부품(insight_text.js placeQaHtml)
        for rel in ("docs/app/views/venue.js", "docs/app/views/city_page.js", "docs/app/views/festival_page.js"):
            self.assertIn("placeQaHtml(", read(rel), rel)


if __name__ == "__main__":
    unittest.main()
