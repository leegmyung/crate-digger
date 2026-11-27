"""Tableau 추출(export_tableau): 앱과 같은 DuckDB 계산으로 긴 형식(tidy) CSV 4개 + 설계서와 칸이 맞는지.
duckdb 는 .venv 에만 있을 수 있음: .venv/bin/python -m unittest tests.test_export_tableau
"""
import csv
import sys
import tempfile
import unittest
from pathlib import Path

try:
    import duckdb  # noqa: F401
except ImportError:
    duckdb = None

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import export_tableau as et  # noqa: E402
from test_export_excel import make_data  # noqa: E402  (엑셀 테스트와 같은 가짜 랩 데이터)


def read(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


class LongFormatTest(unittest.TestCase):
    def test_score_parts_become_rows(self):
        cands = [{"team_key": "a", "display_name": "에이", "primary_genre": "록", "score": 3.5, "profile_status": "newcomer",
                  **{p: 0 for p in et.PTS_COLS}, "pts_branch": 2, "pts_stage": 1.5}]
        rows = et.score_long(cands, "2026-11-27")
        self.assertEqual(len(rows), len(et.PTS_COLS))
        self.assertEqual({r["component"] for r in rows}, set(et.COMPONENT_KO.values()))
        self.assertAlmostEqual(sum(float(r["points"]) for r in rows), 3.5)
        self.assertEqual(rows[0]["rank"], 1)


@unittest.skipIf(duckdb is None, "duckdb 없음 (.venv 로 실행)")
class ExportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        d = Path(cls.tmp.name)
        data = d / "data"
        data.mkdir()
        make_data(data)
        cls.out = d / "tableau"
        cls.counts = et.export(data, cls.out, cutoffs=("2026-11-01",))   # 가짜 데이터는 2026년 신호뿐

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_four_files_with_headers(self):
        for name, fields in et.FILES.items():
            rows = read(self.out / name)
            self.assertEqual(list(rows[0]) if rows else fields, fields, name)
            self.assertEqual(self.counts[name], len(rows))

    def test_timeline_only_candidate_teams_and_backtest_grid(self):
        teams = {r["team_key"] for r in read(self.out / "signal_timeline.csv")}
        cands = {r["team_key"] for r in read(self.out / "candidate_score_parts.csv")}
        self.assertTrue(teams <= cands)
        bt = read(self.out / "backtest.csv")
        self.assertEqual(len(bt), 1 * 4 * 3)   # 기준일 1개 × K(20·50·100·200) × 방법 3
        self.assertIn("점수", {r["method"] for r in bt})

    def test_scorecard_has_korean_role_and_below_baseline_flag(self):
        rows = read(self.out / "source_scorecard.csv")
        self.assertTrue(rows)
        self.assertTrue({r["role_ko"] for r in rows} <= {"발굴", "맥락", "검증 대기", "제외", ""})
        self.assertTrue({r["below_baseline"] for r in rows} <= {"true", "false"})


class ReadmeTest(unittest.TestCase):
    def test_readme_documents_every_column(self):
        text = (ROOT / "docs" / "tableau" / "README.md").read_text(encoding="utf-8")
        for name, fields in et.FILES.items():
            self.assertIn(name, text)
            for f in fields:
                self.assertIn(f"`{f}`", text, f"{name}.{f} 설명 없음")


if __name__ == "__main__":
    unittest.main()
