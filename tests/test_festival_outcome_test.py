"""festival_outcome_test: 큰 페스티벌 메인 무대 라인업을 '시험용 정답 B'로 메모리 DuckDB 에만 더해 비교하는 도구."""
import csv
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import festival_outcome_test as ft  # noqa: E402

FIELDS = ["collected_at", "source", "collector", "program", "round", "announced_at", "result", "artist_text", "url", "note"]


def _row(name, program="penta_main", announced="2024-05-03", **flags):
    base = {"tier": "main", "first": 1, "superrookie": 0, "idol": 0, "headliner": 0}
    base.update(flags)
    note = "; ".join(f"{k}={v}" for k, v in base.items()) + "; announce=차수 발표일"
    return {"collected_at": "2026-11-27T23:00:00+09:00", "source": "manual", "collector": "manual", "program": program,
            "round": announced[:4], "announced_at": announced, "result": "selected", "artist_text": name,
            "url": "https://namu.wiki/w/x", "note": note}


class NoteTest(unittest.TestCase):
    def test_parse_flags(self):
        f = ft.parse_note("stage=KB 스테이지; tier=main; first=1; superrookie=0; idol=1; announce=차수 발표일(이름)")
        self.assertEqual(f["tier"], "main")
        self.assertTrue(f["first"])
        self.assertFalse(f["superrookie"])
        self.assertTrue(f["idol"])


class SelectTest(unittest.TestCase):
    ROWS = [_row("가"), _row("나", superrookie=1), _row("다", idol=1), _row("라", tier="sub")]

    def test_default_drops_superrookie_slot(self):
        got = [r["artist_text"] for r in ft.select(ft.read_rows(self.ROWS), ft.VARIANTS["default"])]
        self.assertEqual(got, ["가", "다", "라"])

    def test_strict_main_only_no_idol(self):
        got = [r["artist_text"] for r in ft.select(ft.read_rows(self.ROWS), ft.VARIANTS["strict"])]
        self.assertEqual(got, ["가"])

    def test_unknown_tier_counts_as_main_in_strict(self):      # 2026 펜타는 무대 정보 없음
        rows = ft.read_rows([_row("마", tier="?")])
        self.assertEqual(len(ft.select(rows, ft.VARIANTS["strict"])), 1)


class OutcomeRowsTest(unittest.TestCase):
    TEAMS = {"가": {"first_release": "2021-01-01"}, "나": {"first_release": "2015-01-01"}, "다": {"first_release": ""}}

    def test_b_grade_and_five_year_rule(self):
        rows = ft.read_rows([_row("가"), _row("나"), _row("다")])
        out = {o["team_key"]: o for o in ft.outcome_rows(rows, lambda n: n, self.TEAMS, excluded=set())}
        self.assertEqual((out["가"]["grade"], out["가"]["weight"], out["가"]["counted"]), ("B", 1, True))
        self.assertFalse(out["나"]["counted"])                 # 첫 발매 9년 뒤 → 5년 넘음
        self.assertFalse(out["다"]["counted"])                 # 첫 발매 모름 → 빼서 부풀리지 않음
        self.assertEqual(out["가"]["announced_date"], date(2024, 5, 3))
        self.assertEqual(out["가"]["program_label"], "펜타포트 본무대(시험)")

    def test_excluded_teams_skipped_and_dedup(self):
        rows = ft.read_rows([_row("가"), _row("가", announced="2024-05-17"), _row("나")])
        out = ft.outcome_rows(rows, lambda n: n, self.TEAMS, excluded={"나"})
        self.assertEqual([o["team_key"] for o in out], ["가"])  # 같은 팀·프로그램·연도는 이른 날짜 하나
        self.assertEqual(out[0]["announced_date"], date(2024, 5, 3))

    def test_key_function_used(self):
        out = ft.outcome_rows(ft.read_rows([_row("Ga Band")]), lambda n: "가", self.TEAMS, excluded=set())
        self.assertEqual(out[0]["team_key"], "가")


class SameHouseTest(unittest.TestCase):
    def test_superrookie_before_main_is_marked(self):
        new = [{"team_key": "가", "program": "penta_main", "announced_date": date(2025, 5, 1)},
               {"team_key": "나", "program": "gmf_main", "announced_date": date(2025, 8, 1)}]
        existing = [{"team_key": "가", "program": "penta_superrookie", "announced_date": date(2024, 6, 29)}]
        out = {o["team_key"]: o for o in ft.mark_same_house(new, existing)}
        self.assertEqual(out["가"]["same_house_sources"], "outcome:penta_superrookie")
        self.assertEqual(out["나"]["same_house_sources"], "")

    def test_mint_family_marked_when_other_mint_stage_first(self):
        new = [{"team_key": "다", "program": "bml_main", "announced_date": date(2024, 3, 1)},
               {"team_key": "다", "program": "gmf_main", "announced_date": date(2024, 8, 1)}]
        out = ft.mark_same_house(new, [])
        gmf = next(o for o in out if o["program"] == "gmf_main")
        self.assertEqual(gmf["same_house_sources"], "outcome:bml_main")


class CompareTest(unittest.TestCase):
    def test_summary_diff(self):
        base = {"mean_pick": 0.80, "mean_v2": 0.79, "mean_v0": 0.78, "hits50_v2": 20, "pos": 100}
        new = {"mean_pick": 0.81, "mean_v2": 0.785, "mean_v0": 0.78, "hits50_v2": 22, "pos": 130}
        d = ft.diff(base, new)
        self.assertAlmostEqual(d["mean_pick"], 0.01)
        self.assertEqual(d["hits50_v2"], 2)
        self.assertEqual(d["pos"], 30)


class ReadCsvTest(unittest.TestCase):
    def test_read_review_csv(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "r.csv"
            with open(p, "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=FIELDS)
                w.writeheader()
                w.writerow(_row("가"))
            rows = ft.read_review(p)
        self.assertEqual(rows[0]["artist_text"], "가")
        self.assertTrue(rows[0]["flags"]["first"])


if __name__ == "__main__":
    unittest.main()
