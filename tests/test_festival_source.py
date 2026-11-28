"""큰 페스티벌 라인업 원본(source='festival')은 화면 정보만 — 점수·검증·공연장 계산에 안 씀.

파이프라인 원칙: 출처는 후보 신호/정답 한쪽만. 큰 페스티벌 본무대는 '정답 성격'(크고 경쟁 센 무대)이고 정답 반영은
사용자 결정 대기라, 신호 역할은 excluded(알림·사건 별점·점수 특징·같은 무대·공연장 사다리가 이미 거름) +
역할을 보지 않던 계산(공연장 프로필·예전 대시보드 자료·페스티벌 화면 '먼저 본 팀')도 막는다.
"""
import csv
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build_dashboard_data as bdd  # noqa: E402
import collect_festival_lineups as cfl  # noqa: E402
import festival_profiles as fp  # noqa: E402
import venue_profiles as vp  # noqa: E402
from csv_schema import GIG_SOURCES  # noqa: E402

SIG_FIELDS = ["team_key", "branch", "source", "program", "stage_rank", "signal_date", "venue", "role"]


class SourceCodeTest(unittest.TestCase):
    def test_schema_and_collector(self):
        self.assertIn("festival", GIG_SOURCES)
        self.assertEqual(cfl.SOURCE, "festival")

    def test_role_excluded(self):
        roles = json.loads((ROOT / "config" / "source_roles.json").read_text(encoding="utf-8"))
        entry = roles["signals"]["공연:festival"]
        self.assertEqual(entry["role"], "excluded")
        self.assertIn("화면 정보만", entry["reason"])


class BlockedConsumersTest(unittest.TestCase):
    def test_venue_profiles_skip_excluded_rows(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            with open(d / "signals.csv", "w", encoding="utf-8", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=SIG_FIELDS)
                w.writeheader()
                w.writerow({"team_key": "a", "branch": "공연", "source": "indistreet", "signal_date": "2025-01-01",
                            "venue": "클럽 에이", "role": "discovery"})
                w.writerow({"team_key": "a", "branch": "공연", "source": "festival", "signal_date": "2025-08-01",
                            "venue": "송도달빛축제공원", "role": "excluded"})
            (d / "teams.csv").write_text("team_key,display_name\na,에이\n", encoding="utf-8")
            (d / "outcomes.csv").write_text("team_key,announced_date\n", encoding="utf-8")
            (d / "meta.json").write_text('{"data_end": "2026-11-28"}', encoding="utf-8")
            gigs, *_ = vp.load_lab(d)
        self.assertEqual([g[2] for g in gigs], ["클럽 에이"])

    def test_dashboard_sql_drops_festival_rows(self):
        sql = bdd.scored_signal_sql("SELECT count(*) FROM core.v_signal s JOIN core.v_signal_base b ON true")
        self.assertIn("source <> 'festival'", sql)
        self.assertIn("core.v_signal_base", sql)          # 다른 뷰 이름은 그대로
        self.assertEqual(sql.count("source <> 'festival'"), 1)

    def test_festival_page_seen_before_ignores_excluded(self):
        sigs = [{"team_key": "a", "branch": "공연", "source": "festival", "program": "", "signal_date": "2024-01-01",
                 "role": "excluded"},
                {"team_key": "b", "branch": "공연", "source": "indistreet", "program": "", "signal_date": "2024-01-01",
                 "role": "discovery"}]
        got = fp._first_signal_days(sigs, fp.FESTIVALS)
        self.assertEqual(got, {"b": date(2024, 1, 1)})


if __name__ == "__main__":
    unittest.main()
