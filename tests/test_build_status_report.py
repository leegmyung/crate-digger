"""진행 점검표 자동 생성(build_status_report): 공개 파일만 읽어 단계별 상태·규모·검증·검증 대기·일일 기록을 한 장으로."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_status_report as sr  # noqa: E402

TUNING = "**평균 AUC (뺀 기준일 기준)**: 고른 가중치 0.721 · v0 0.692 · 공연 수만 0.596 · 갈래 수만 0.579\n"
XREF = "| **정답 팀 중 신호(공연·선정·발매·기사)와 이어진 팀** | 362 / 479팀 (75.6%) |\n"


def make_root(d: Path, collect_runs=None, meta=None):
    (d / "docs" / "data").mkdir(parents=True)
    lab = d / "docs" / "lab" / "data"
    (lab / "snapshots").mkdir(parents=True)
    (d / "docs" / "log").mkdir(parents=True)
    (d / "docs" / "sql").mkdir(parents=True)
    (d / "config").mkdir()
    runs = collect_runs if collect_runs is not None else [
        {"date": "2026-11-26", "source": "indistreet", "table": "raw_kr_gig", "rows": 200, "file_ok": True, "prev_rows": None},
        {"date": "2026-11-27", "source": "indistreet", "table": "raw_kr_gig", "rows": 190, "file_ok": True, "prev_rows": 200},
        {"date": "2026-11-27", "source": "musicy", "table": "raw_press", "rows": 10, "file_ok": False, "prev_rows": 12},
    ]
    (d / "docs" / "data" / "collect.json").write_text(json.dumps({"generated": "2026-11-27T21:30:00+09:00", "runs": runs}), encoding="utf-8")
    (lab / "meta.json").write_text(json.dumps(meta or {"generated_at": "2026-11-27T21:40:00+09:00", "data_end": "2026-11-27",
                                                       "uses_artist_xref": True, "rows": {"signals": 4}}), encoding="utf-8")
    (lab / "signals.csv").write_text(
        "team_key,branch,source,program,stage_rank,signal_date,venue,role\n"
        "a,공연,indistreet,,,2026-11-01,클럽,discovery\nb,공연,indistreet,,,2026-11-02,클럽,discovery\n"
        "a,큐레이션,musicy,musicy,,2026-10-01,,discovery\nc,발매,melon,,,2026-11-24,,pending\n", encoding="utf-8")
    (lab / "teams.csv").write_text("team_key,display_name,profile_status\na,에이,newcomer\nb,비,unknown\nc,씨,famous\n", encoding="utf-8")
    (lab / "outcomes.csv").write_text("team_key,program,counted,grade,weight\na,kma_rookie,true,S,3\nb,mucon,false,B,1\nc,indiestance,true,A,2\n", encoding="utf-8")
    for name, n in (("links.csv", 2), ("videos.csv", 3), ("images.csv", 1)):
        (lab / name).write_text("team_key,x\n" + "".join(f"t{i},v\n" for i in range(n)), encoding="utf-8")
    (lab / "snapshots" / "index.json").write_text(json.dumps({"dates": ["2026-11-27", "2026-11-20"]}), encoding="utf-8")
    (d / "docs" / "data" / "source_review.json").write_text(json.dumps({
        "generated_at": "2026-11-27T21:45:00+09:00", "data_end": "2026-11-27", "cutoffs": ["2025-01-01"],
        "suggestions": [{"src": "큐레이션:izm", "role": "context", "kind": "promote", "suggestion": "discovery로 올릴 후보", "reason": "배수 1"}],
        "sources": [{"src": "공연:indistreet", "role": "discovery", "teams": 100, "hits": 2, "rate": 2.0, "lift": 1.4, "only_source": 3}]}),
        encoding="utf-8")
    (d / "config" / "source_roles.json").write_text(json.dumps({"signals": {
        "공연:indistreet": {"role": "discovery", "reason": "x"}, "발매:melon": {"role": "pending", "reason": "2026-11부터"},
        "반응:youtube": {"role": "pending", "reason": "2026-11-27부터 기록"}}}), encoding="utf-8")
    (d / "docs" / "score_tuning.md").write_text(TUNING, encoding="utf-8")
    (d / "docs" / "artist_xref.md").write_text(XREF, encoding="utf-8")
    (d / "docs" / "sql" / "README.md").write_text("# x\n\n_자동 생성: `python3 scripts/run_pg_queries.py` · 2026-11-27 21:35 기준 데이터_\n", encoding="utf-8")
    for day in range(18, 28):
        (d / "docs" / "log" / f"2026-11-{day:02d}.md").write_text("x", encoding="utf-8")


class ParseTest(unittest.TestCase):
    def test_score_and_xref_lines(self):
        self.assertEqual(sr.parse_auc(TUNING), {"v2": "0.721", "v0": "0.692", "gigs": "0.596"})
        self.assertIsNone(sr.parse_auc("형식이 바뀐 문서"))
        self.assertEqual(sr.parse_link_rate(XREF), {"linked": 362, "total": 479, "pct": "75.6"})
        self.assertIsNone(sr.parse_link_rate(""))


class ReportTest(unittest.TestCase):
    def build(self, **kw):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        d = Path(tmp.name)
        make_root(d, **kw)
        return sr.collect_report(d, today="2026-11-28")

    def test_stages(self):
        st = {s["name"]: s for s in self.build()["stages"]}
        self.assertEqual(st["수집"]["last"], "2026-11-27")
        self.assertEqual(st["수집"]["state"], "ok")
        self.assertEqual(st["형식 검사"]["state"], "warn")           # 1개 파일 실패
        self.assertIn("1/2", st["형식 검사"]["detail"])
        self.assertEqual(st["이름·공연장 묶기"]["state"], "ok")
        self.assertEqual(st["분석 SQL"]["last"], "2026-11-27 21:35")
        self.assertEqual(st["점수"]["last"], "2026-11-27")
        self.assertEqual(st["앱"]["state"], "ok")
        self.assertIn("2팀", st["프로필 보강"]["detail"])            # 프로필 있는 팀 = unknown 아닌 팀 (신인·유명) 2팀

    def test_stale_and_drop_detection(self):
        runs = [{"date": "2026-11-20", "source": "x", "table": "raw_kr_gig", "rows": 100, "file_ok": True, "prev_rows": None},
                {"date": "2026-11-25", "source": "x", "table": "raw_kr_gig", "rows": 10, "file_ok": True, "prev_rows": 100}]
        st = {s["name"]: s for s in self.build(collect_runs=runs)["stages"]}
        self.assertEqual(st["수집"]["state"], "bad")                 # 3일 전이 마지막 → 오래됨
        self.assertIn("급감", st["수집"]["detail"])

    def test_scale_validation_pending_logs(self):
        rep = self.build()
        scale = rep["scale"]
        self.assertEqual(scale["branches"]["공연"], {"rows": 2, "teams": 2})
        self.assertEqual(scale["outcomes"], {"rows": 3, "counted": 2, "by_grade": {"S": 1, "A": 1}})
        self.assertEqual(scale["profiles"]["unknown"], 1)
        self.assertEqual((scale["links"], scale["videos"], scale["images"]), (2, 3, 1))
        self.assertEqual(rep["validation"]["auc"]["v2"], "0.721")
        self.assertEqual(rep["validation"]["link_rate"]["pct"], "75.6")
        self.assertEqual(len(rep["validation"]["suggestions"]), 1)
        pend = {p["src"]: p for p in rep["pending"]}
        self.assertEqual(pend["발매:melon"]["since"], "2026-11-24")
        self.assertEqual(pend["발매:melon"]["review_on"], "2027-02-22")   # +90일
        self.assertEqual(pend["반응:youtube"]["since"], "")               # 신호 표에 없음 → 기록 시작일 모름
        self.assertEqual([l["name"] for l in rep["logs"]][0], "2026-11-27.md")
        self.assertEqual(len(rep["logs"]), 7)

    def test_missing_files_marked_check_needed(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        rep = sr.collect_report(Path(tmp.name), today="2026-11-28")
        self.assertTrue(all(s["state"] in ("bad", "check") for s in rep["stages"]))
        self.assertIsNone(rep["validation"]["auc"])


class HtmlTest(unittest.TestCase):
    def test_static_page_dark_mode_and_escaping(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        d = Path(tmp.name)
        make_root(d)
        rep = sr.collect_report(d, today="2026-11-28")
        rep["validation"]["suggestions"][0]["reason"] = "<script>x</script>"
        html = sr.render_html(rep)
        self.assertIn("<!doctype html>", html.lower())
        self.assertNotIn("<script", html.lower())                    # 외부·내부 스크립트 없음
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("prefers-color-scheme: dark", html)
        self.assertIn('name="viewport"', html)
        self.assertIn("2026-11-27.md", html)
        self.assertNotIn("/Users/", html)


if __name__ == "__main__":
    unittest.main()


class AnalysisLinesTest(unittest.TestCase):
    """③ 검증에 붙는 분석 지표 줄: 각 문서·CSV 에서 읽고, 파일이 없거나 형식을 못 읽으면 그 줄은 뺀다."""

    def test_parsers(self):
        self.assertEqual(sr.parse_debut("- 백지 신인 63팀 중 50팀(79%)은 첫 발매 뒤 6개월 안에 어느 출처에도 안 나왔다."),
                         {"cohort": 63, "unmentioned": 50, "pct": 79, "months": 6})
        self.assertEqual(sr.parse_missed("- 정답 6개월 전에 상위 100 안에 있던 팀은 5/70팀, 12개월 전에는 4/70팀이다."),
                         {"m6": 5, "m12": 4, "total": 70})
        self.assertEqual(sr.parse_fan_history("| 팬 수 기록이 있는 아티스트 | 1,309 |\n| 두 날짜 이상 기록된 아티스트 (변화를 볼 수 있음) | 12 |"),
                         {"artists": 1309, "multi": 12})
        self.assertIsNone(sr.parse_debut("다른 글"))

    def test_lines_from_root_and_omit_missing(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            lab = root / "docs" / "lab" / "data"
            lab.mkdir(parents=True)
            (lab / "teams.csv").write_text("team_key,first_release\na,2024-01-01\nb,\n", encoding="utf-8")
            (lab / "outcomes.csv").write_text("team_key,counted,same_house_sources,same_house_scored\n"
                                              "a,true,큐레이션:hiphople,false\nb,true,,false\nc,true,큐레이션:musicy,true\n", encoding="utf-8")
            (root / "docs" / "debut_cohort.md").write_text("- 백지 신인 10팀 중 8팀(80%)은 첫 발매 뒤 6개월 안에 어느 출처에도 안 나왔다.", encoding="utf-8")
            lines = sr.analysis_lines(root)
        text = "\n".join(lines)
        self.assertIn("80%", text)                                  # 데뷔 코호트
        self.assertIn("첫 발매일이 있는 팀 1", text)
        self.assertIn("같은 집안 표시 정답 2행", text)
        self.assertIn("점수 검증에서 뺀 1행", text)
        self.assertNotIn("놓친 정답", text)                          # missed_analysis.md 없음 → 줄 생략
        self.assertNotIn("팬 수 기록", text)                         # fan_history.md 없음 → 줄 생략


class OpsLinesTest(unittest.TestCase):
    """③ 검증에 붙는 운영 줄: 데이터 검사 요약·앱 보조 데이터·알림 수·정답 행 수. 파일이 없으면 그 줄은 뺀다."""

    def _root(self, d: Path, with_files: bool = True) -> Path:
        make_root(d)
        if with_files:
            (d / "docs" / "data" / "data_checks.json").write_text(json.dumps(
                {"today": "2026-11-28", "summary": "통과 16 · 경고 4 · 실패 1", "checks": []}), encoding="utf-8")
            meta = json.loads((d / "docs" / "lab" / "data" / "meta.json").read_text(encoding="utf-8"))
            meta.update({"extras": ["city_profiles", "lineup_roles", "venue_tiers"],
                         "extras_updated_at": "2026-11-28T00:21:28+09:00"})
            (d / "docs" / "lab" / "data" / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
            (d / "docs" / "data" / "alerts.json").write_text(json.dumps({
                "as_of": "2026-11-28", "types": {"stage_up": "단계 상승", "new_gig": "새 공연"},
                "counts_found": {"stage_up": 678, "new_gig": 365}, "counts_shown": {"stage_up": 20, "new_gig": 300},
                "alerts": []}), encoding="utf-8")
        return d

    def test_lines_with_files(self):
        with tempfile.TemporaryDirectory() as t:
            rep = sr.collect_report(self._root(Path(t)), today="2026-11-28")
        ops = rep["validation"]["ops"]
        text = "\n".join(o["text"] for o in ops)
        self.assertIn("데이터 검사 2026-11-28: 통과 16 · 경고 4 · 실패 1", text)
        self.assertTrue(any((o.get("href") or "").endswith("docs/data_checks.md") for o in ops))
        self.assertIn("앱 보조 데이터 3개", text)
        self.assertIn("2026-11-28 00:21", text)
        self.assertIn("알림 2026-11-28: 320건", text)                    # 보여 주는 수 합계
        self.assertIn("단계 상승 20(찾은 678)", text)
        self.assertIn("새 공연 300(찾은 365)", text)
        self.assertIn("정답 3행 · 셈 정답 2행", text)                    # outcomes.csv 에서 셈 (하드코딩 아님)

    def test_missing_files_omit_lines(self):
        with tempfile.TemporaryDirectory() as t:
            rep = sr.collect_report(self._root(Path(t), with_files=False), today="2026-11-28")
        text = "\n".join(o["text"] for o in rep["validation"]["ops"])
        self.assertNotIn("데이터 검사", text)
        self.assertNotIn("앱 보조 데이터", text)
        self.assertNotIn("알림", text)
        self.assertIn("정답 3행", text)

    def test_empty_root_has_no_ops(self):
        with tempfile.TemporaryDirectory() as t:
            rep = sr.collect_report(Path(t), today="2026-11-28")
        self.assertEqual(rep["validation"]["ops"], [])

    def test_html_shows_link_and_escapes(self):
        with tempfile.TemporaryDirectory() as t:
            rep = sr.collect_report(self._root(Path(t)), today="2026-11-28")
        rep["validation"]["ops"][0]["text"] = "<b>x</b>"
        html = sr.render_html(rep)
        self.assertIn('href="https://github.com/leegmyung/gigle-research/blob/main/docs/data_checks.md"', html)
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", html)
        self.assertIn("앱 보조 데이터 3개", html)
