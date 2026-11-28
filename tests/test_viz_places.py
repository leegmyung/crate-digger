"""그림 규칙(docs/layout_rules.md 7절)을 도시·공연장 목록·지역 지도 그림에도 — 색은 --viz-* 토큰(의미)만, 막대는 viz_bars.js 하나로.

화면 코드는 브라우저 모듈이라 규칙이 CSS·코드에 들어 있는지만 본다. 실제 모습은 e2e 120칸·m375 와 docs/ux/2026-11-28/viz/ 전후 스크린샷.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "docs" / "app"


def css_rule(text: str, selector: str) -> str:
    """선택자 하나로 시작하는 규칙 몸통(첫 번째) — 없으면 ''"""
    m = re.search(r"(^|\n)\s*" + re.escape(selector) + r"\s*\{([^}]*)\}", text)
    return m.group(2) if m else ""


class PlacesVizColorTest(unittest.TestCase):
    places = (APP / "css" / "places.css").read_text(encoding="utf-8")
    style = (APP / "style.css").read_text(encoding="utf-8")

    def test_month_bars_neutral_latest_focus(self):
        self.assertIn("var(--viz-neutral)", css_rule(self.places, ".place-month"))
        self.assertIn("var(--viz-focus)", css_rule(self.places, ".place-month.is-latest"))

    def test_region_map_marks_use_focus_token(self):
        for sel in (".rm-heat circle", ".rm-dot"):
            body = css_rule(self.places, sel)
            self.assertIn("var(--viz-focus)", body, sel)
            self.assertNotIn("var(--accent)", body, sel)

    def test_venue_list_tier_bars_and_dots(self):
        self.assertIn("var(--viz-neutral)", css_rule(self.style, ".vl-tier-fill"))
        self.assertIn("var(--viz-focus)", css_rule(self.style, ".vl-tier-btn.is-active .vl-tier-fill"))
        self.assertIn("var(--viz-compare-2)", css_rule(self.style, ".vl-dot.tier-u"))

    def test_no_raw_colors_in_place_figures(self):
        for sel in (".place-month", ".vl-tier-fill", ".rm-dot", ".rm-heat circle"):
            body = css_rule(self.places, sel) or css_rule(self.style, sel)
            self.assertIsNone(re.search(r"#[0-9a-fA-F]{3,6}\b|rgba?\(", body), sel)


class MonthBarsSharedTest(unittest.TestCase):
    def test_city_and_venue_list_use_shared_helper(self):
        for rel in ("views/city_page.js", "views/venues_list.js"):
            js = (APP / rel).read_text(encoding="utf-8")
            self.assertIn("from '../viz_bars.js'", js, rel)
            self.assertNotRegex(js, r"Math\.max\(\w+ \? \d+ : \d+", f"{rel}: 0인 달을 막대로 부풀리지 않기")


if __name__ == "__main__":
    unittest.main()
