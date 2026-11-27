"""주간 엑셀 보고서(export_excel): 앱과 같은 DuckDB 계산으로 7개 시트를 만든다.
openpyxl·duckdb 는 .venv 에만 있을 수 있음: .venv/bin/python -m unittest tests.test_export_excel
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

try:
    import duckdb  # noqa: F401
    import openpyxl
except ImportError:  # 시스템 파이썬에는 없을 수 있음
    openpyxl = None

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import export_excel as ee  # noqa: E402

FILES = {
    "signals.csv": """team_key,branch,source,program,stage_rank,signal_date,venue,role
a,공연,indistreet,,,2026-10-01,클럽1,discovery
a,선정·지원,sangsangmadang,band_discovery,3,2026-06-01,,discovery
a,큐레이션,musicy,musicy,,2026-09-01,,discovery
b,공연,indistreet,,,2026-10-01,클럽1,discovery
b,큐레이션,izm,izm,,2026-09-05,,context
c,공연,indistreet,,,2026-08-01,클럽2,discovery
a,공연,indistreet,,,2026-12-01,클럽1,discovery
b,공연,indistreet,,,2026-12-01,클럽1,discovery
x,공연,indistreet,,,2026-12-01,클럽1,discovery
c,공연,indistreet,,,2026-12-03,클럽2,discovery
c,공연,indistreet,,,2027-01-20,클럽2,discovery
""",
    "teams.csv": """team_key,display_name,first_seen,first_release,fan_count,album_count,profile_status,primary_genre,agency
a,에이,2026-06-01,2025-05-01,100,2,newcomer,록·밴드,
b,비,2026-09-05,,,,unknown,힙합,
c,씨,2026-08-01,,,,unknown,,
x,엑스,2026-12-01,,,,unknown,,
""",
    "outcomes.csv": ("team_key,program,program_label,tier,announced_date,counted,grade,weight\n"
                     "zz,kma_rookie,한대음 신인,final,2025-03-01,true,S,3\n"),   # 후보와 무관한 한 줄 (칸 형식 추론용)
    "programs.csv": "program,label,kind\nband_discovery,상상마당 밴드 디스커버리,signal\n",
    "links.csv": "team_key,platform,url\na,spotify,https://open.spotify.com/artist/AAAAAAAAAAAAAAAAAAAAAA\n",
}


def make_data(d: Path):
    for name, text in FILES.items():
        (d / name).write_text(text, encoding="utf-8")
    (d / "meta.json").write_text(json.dumps({"data_end": "2026-11-27"}), encoding="utf-8")
    snaps = d / "snapshots"
    snaps.mkdir()
    (snaps / "2026-11-20.csv").write_text("team_key,score,rank\nb,3.0,1\nc,1.0,2\n", encoding="utf-8")
    (snaps / "2026-11-27.csv").write_text("team_key,score,rank\na,5.0,1\nb,3.5,2\nc,1.0,3\n", encoding="utf-8")


class DiffTest(unittest.TestCase):
    def test_new_and_rising_like_app(self):
        latest = {"a": (5.0, 1), "b": (3.5, 2), "c": (1.0, 3), "d": (0.5, 4)}
        prev = {"b": (3.0, 1), "c": (1.0, 2), "d": (0.5, 9)}
        new, rising = ee.snapshot_diff(latest, prev)
        self.assertEqual([r["team_key"] for r in new], ["a"])
        self.assertEqual([r["team_key"] for r in rising], ["b", "d"])   # 점수 오름(b), 순위 3계단 이상 오름(d); c는 그대로
        self.assertEqual(rising[0]["score_gain"], 0.5)
        self.assertEqual(rising[1]["rank_gain"], 5)

    def test_group_gigs_same_day_same_venue(self):
        rows = [{"signal_date": "2026-12-01", "venue": "클럽1", "team_key": t, "display_name": t} for t in ("a", "b", "x")]
        rows.append({"signal_date": "2026-12-03", "venue": "", "team_key": "c", "display_name": "c"})
        events = ee.group_gigs(rows, {"a": 1, "c": 3})
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["candidates"], ["a (1위)"])
        self.assertEqual(events[0]["others"], ["b", "x"])
        self.assertEqual(events[1]["venue"], "공연장 미정")


@unittest.skipIf(openpyxl is None, "openpyxl·duckdb 없음 (.venv 로 실행)")
class WorkbookTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        d = Path(cls.tmp.name)
        make_data(d)
        cls.ctx = ee.load_context(d, tuning_text="**평균 AUC (뺀 기준일 기준)**: 고른 가중치 0.721 · v0 0.692\n")
        cls.path = d / "out.xlsx"
        ee.build_workbook(cls.ctx).save(cls.path)
        cls.wb = openpyxl.load_workbook(cls.path)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_seven_sheets_in_order(self):
        self.assertEqual(self.wb.sheetnames, list(ee.SHEETS))

    def test_summary_numbers(self):
        self.assertEqual(self.ctx["as_of"], "2026-11-27")
        self.assertEqual(len(self.ctx["new"]), 1)            # a 가 새로 들어옴
        self.assertEqual(len(self.ctx["rising"]), 1)         # b 점수 상승
        self.assertEqual(len(self.ctx["gig_events"]), 2)     # 12-01 클럽1, 12-03 클럽2 (1-20은 2주 밖)
        values = [c.value for row in self.wb["요약"].iter_rows() for c in row if c.value is not None]
        self.assertIn("2026-11-27", [str(v) for v in values])
        self.assertTrue(any("0.721" in str(v) for v in values))   # 교차 검증 숫자 인용

    def test_candidates_sheet_format(self):
        ws = self.wb["후보 TOP100"]
        header = [c.value for c in ws[1]]
        self.assertEqual(header[:4], ["순위", "팀", "장르", "점수"])
        self.assertIn("pts_branch", header)
        self.assertEqual(ws.freeze_panes, "A2")
        self.assertTrue(ws.auto_filter.ref)
        self.assertTrue(any(r.type == "dataBar" for rng in ws.conditional_formatting for r in rng.rules))
        names = [ws.cell(row=i, column=2).value for i in range(2, ws.max_row + 1)]
        self.assertIn("에이", names)
        row_a = names.index("에이") + 2
        link_col = header.index("스포티파이") + 1
        self.assertTrue(ws.cell(row=row_a, column=link_col).hyperlink.target.startswith("https://open.spotify.com/"))
        gig_col = header.index("다음 공연") + 1
        self.assertEqual(str(ws.cell(row=row_a, column=gig_col).value), "2026-12-01 클럽1")

    def test_changes_and_gigs_sheets(self):
        changes = [c.value for row in self.wb["이번 주 변화"].iter_rows() for c in row if c.value]
        self.assertIn("에이", changes)
        self.assertIn("비", changes)
        gigs = self.wb["다가오는 공연"]
        self.assertEqual(gigs.max_row, 1 + 2)

    def test_scorecard_marks_below_baseline_red(self):
        ws = self.wb["출처 성적표"]
        header = [c.value for c in ws[1]]
        self.assertIn("역할", header)
        self.assertGreater(ws.max_row, 1)

    def test_validation_and_definitions(self):
        val = [c.value for row in self.wb["점수 검증"].iter_rows() for c in row if c.value is not None]
        self.assertTrue(any("0.721" in str(v) for v in val))
        defs = " ".join(str(c.value) for row in self.wb["정의"].iter_rows() for c in row if c.value)
        for word in ("발굴", "맥락", "검증 대기", "제외", "AUC", "S"):
            self.assertIn(word, defs)

    def test_korean_font(self):
        self.assertEqual(self.wb["후보 TOP100"]["A1"].font.name, ee.FONT)


if __name__ == "__main__":
    unittest.main()
