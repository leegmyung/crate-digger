"""표·목록 정렬 규칙(docs/layout_rules.md)이 공통 CSS와 화면 마크업에 실제로 들어가 있는지 검사."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "docs" / "app"


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


class LayoutRulesTest(unittest.TestCase):
    def test_rules_doc(self):
        doc = read("docs/layout_rules.md")
        for word in ("tabular-nums", "오른쪽", "말줄임", "375", "cell-entity", "tables.css"):
            self.assertIn(word, doc)

    def test_tables_css_loaded_first_from_style_css(self):
        css = read("docs/app/style.css")
        rules = [ln for ln in css.splitlines() if ln.strip() and not ln.strip().startswith(("/*", "*", "@charset"))]
        self.assertEqual(rules[0].strip(), '@import url("css/tables.css");')

    def test_tables_css_has_common_rules(self):
        css = read("docs/app/css/tables.css")
        for sel in (".table-wrap", "table.data-table", ".cell-entity", ".cell-entity-sub", ".cell-entity-actions",
                    ".col-fit", ".col-clip", "table.stack-table"):
            self.assertIn(sel, css)
        self.assertIn("font-variant-numeric: tabular-nums", css)
        self.assertIn("text-overflow: ellipsis", css)
        # 옛 위치(style.css)에 기본 표 규칙이 두 벌 남아 있지 않게
        style = read("docs/app/style.css")
        self.assertNotRegex(style, r"(?m)^table\.data-table \{")
        self.assertNotRegex(style, r"(?m)^\.table-wrap \{")

    def test_views_use_entity_cell(self):
        for rel in ("views/venues_list.js", "views/venue_tables.js", "views/charts.js", "views/festival_page.js"):
            with self.subTest(view=rel):
                self.assertIn("entityCellHtml(", (APP / rel).read_text(encoding="utf-8"))

    def test_venue_list_badges_not_glued_to_name(self):
        js = (APP / "views" / "venues_list.js").read_text(encoding="utf-8")
        # 예전: <strong>이름</strong></a> 배지 배지 — 이름 길이에 따라 배지 위치가 들쭉날쭉
        self.assertNotRegex(js, r"</strong></a>\s*\$\{venueStatusBadge")

    def test_alert_rows_have_fixed_columns(self):
        js = (APP / "views" / "today_alerts.js").read_text(encoding="utf-8")
        self.assertIn('class="alert-who"', js)
        css = read("docs/app/css/tables.css") + read("docs/app/style.css")
        self.assertRegex(css, r"\.alert-row > details > summary \{[^}]*grid-template-columns")


if __name__ == "__main__":
    unittest.main()
