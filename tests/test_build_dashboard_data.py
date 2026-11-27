import math
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import build_dashboard_data as bd  # noqa: E402


class RecordsTest(unittest.TestCase):
    def test_parses_numbers_and_nulls(self):
        rows = bd.records("a,b,c\nfoo,12,0.5\nbar,,\n")
        self.assertEqual(rows, [{"a": "foo", "b": 12, "c": 0.5}, {"a": "bar", "b": None, "c": None}])

    def test_empty_output(self):
        self.assertEqual(bd.records(""), [])


class ProgramLabelTest(unittest.TestCase):
    def test_known_codes_translate_to_korean(self):
        self.assertEqual(bd.program_label("kma_genre"), "한대음 장르 부문")
        self.assertEqual(bd.program_label("band_discovery"), "상상마당 밴드 디스커버리")
        self.assertEqual(bd.program_label("khha_rookie"), "한국힙합어워즈 신인")

    def test_unknown_code_returns_itself(self):
        self.assertEqual(bd.program_label("custom_prog"), "custom_prog")


class InferGenresNoOutcomeLeakTest(unittest.TestCase):
    """장르 보완 규칙은 '신호' 정보(선정·지원 신호 프로그램, 발굴·맥락 출처)만 쓰고 정답(검증용) 정보는 쓰지 않는다."""

    def test_outcome_program_never_sets_genre(self):
        self.assertEqual(bd._infer_genres("", "", "khha_rookie"), [])
        self.assertEqual(bd._infer_genres("", "", "khha_rookie|rhythmer_award|kma_rookie"), [])

    def test_signal_sources_still_fill_genre(self):
        self.assertEqual(bd._infer_genres("", "rhythmer", ""), ["힙합"])            # 리드머 = 맥락 출처
        self.assertEqual(bd._infer_genres("", "", "band_discovery"), ["록·밴드"])   # 선정·지원 신호 프로그램
        self.assertEqual(bd._infer_genres("", "rhythmer", "khha_rookie|band_discovery"), ["힙합", "록·밴드"])

    def test_platform_genre_tags_win_over_hints(self):
        self.assertEqual(bd._infer_genres("인디음악|록/메탈", "rhythmer", ""), ["록·밴드"])

    def test_hint_tables_contain_no_outcome_programs(self):
        outcome_programs = set(bd.csv_schema.OUTCOME_TIER)
        self.assertFalse(set(bd.GENRE_HINT_PROGRAMS) & outcome_programs)
        self.assertFalse(set(bd.GENRE_HINT_PRESS) & outcome_programs)


class TeamKeyTest(unittest.TestCase):
    def test_uses_xref_index_when_provided(self):
        fake_index = {"by_key": {"peachtruckhijackers": "피치트럭하이재커스"}}
        self.assertEqual(bd.team_key("Peach Truck Hijackers", xref=fake_index), "피치트럭하이재커스")

    def test_falls_back_gracefully_without_xref(self):
        self.assertEqual(bd.team_key("최춘목 밴드", xref=None), "최춘목밴드")
        self.assertEqual(bd.team_key("다브다 (Dabda)", xref={}), "다브다")


class ScoreV0Test(unittest.TestCase):
    def test_exact_formula_and_breakdown(self):
        # 3 branches (+4), best_stage='selected' (+3), peer_selected=1 (+1),
        # dmz=1 (+0.5), gigs_1y=9 (+0.5*ln(10)), outlets=4 (capped at +3)
        score, parts = bd.compute_score_v0(
            n_branch=3,
            best_stage="selected",
            peer_selected=1,
            dmz=1,
            gigs_1y=9,
            outlets=4,
        )
        expected = round(2 * (3 - 1) + 3 + 1 + 0.5 + 0.5 * math.log(10) + 3, 2)
        self.assertEqual(score, expected)
        labels = [p["label"] for p in parts]
        self.assertTrue(any("갈래 3개" in l for l in labels))
        self.assertTrue(any("선정" in l for l in labels))
        self.assertTrue(any("합동무대" in l for l in labels))
        self.assertTrue(any("DMZ" in l for l in labels))
        self.assertTrue(any("공연" in l for l in labels))
        self.assertTrue(any("큐레이션" in l for l in labels))

    def test_accepts_numeric_stage_rank(self):
        score, _ = bd.compute_score_v0(n_branch=2, best_stage=4, peer_selected=0, dmz=0, gigs_1y=0, outlets=0)
        self.assertEqual(score, 6.0)


class SignalDateAndRookieTest(unittest.TestCase):
    def test_selection_year_only_does_not_show_dec_31(self):
        today = date(2026, 11, 27)
        label, sort_d = bd.format_signal_date(
            branch="선정·지원",
            signal_date="2026-12-31",
            raw_date="2026",
            round_text="2026",
            today=today,
        )
        self.assertEqual(label, "2026 선정")
        self.assertEqual(sort_d, "2026-11-27")

    def test_future_gig_marked_scheduled_and_clamped_for_last_seen(self):
        today = date(2026, 11, 27)
        label, sort_d = bd.format_signal_date(
            branch="공연",
            signal_date="2026-11-28",
            raw_date="2026-11-28",
            round_text="",
            today=today,
        )
        self.assertEqual(label, "2026-11-28 (예정)")
        self.assertEqual(sort_d, "2026-11-28")
        self.assertEqual(bd.clamp_date_to_today("2026-12-31", today=today), "2026-11-27")

    def test_rookie_proxy_from_first_seen_all(self):
        today = date(2026, 11, 27)
        info_recent = bd.rookie_status_info("확인 안 됨", "2025-09-01", today=today)
        self.assertEqual(info_recent["rookie_label"], "신인 추정")
        self.assertTrue(info_recent["is_rookie_pool"])
        self.assertIn("년 전 첫 등장", info_recent["first_seen_text"])

        info_old = bd.rookie_status_info("확인 안 됨", "2020-05-01", today=today)
        self.assertEqual(info_old["rookie_label"], "3년+ 활동")
        self.assertFalse(info_old["is_rookie_pool"])

        info_confirmed = bd.rookie_status_info("신인", "2025-01-01", today=today)
        self.assertEqual(info_confirmed["rookie_label"], "신인 확인")
        self.assertTrue(info_confirmed["is_rookie_pool"])


class ManualExcludeAndEnrichTest(unittest.TestCase):
    def test_manual_famous_excluded_from_candidates_and_logged(self):
        cands = [
            {"artist_key": "혁오", "artist": "혁오", "n_branch": 3, "n_signals": 12, "fan_count": None},
            {"artist_key": "최춘목밴드", "artist": "최춘목밴드", "n_branch": 3, "n_signals": 10, "fan_count": None},
        ]
        kept, excl = bd.apply_manual_exclusions(cands, [])
        self.assertEqual([c["artist_key"] for c in kept], ["최춘목밴드"])
        self.assertEqual(len(excl), 1)
        self.assertEqual(excl[0]["artist"], "혁오")
        self.assertIn("수동 제외", excl[0]["reason"])

    def test_enrich_sorts_by_score_v0_and_infers_safe_genres(self):
        today = date(2026, 11, 27)
        cands = [
            {
                "artist_key": "low_team", "artist": "로우팀", "n_branch": 2, "n_signals": 5,
                "branches": "공연 · 큐레이션", "first_seen": "2026-09-01", "last_seen": "2026-11-20",
                "first_seen_all": "2025-06-01", "status": "확인 안 됨",
                "best_stage": 0, "dmz": 0, "peer_selected": 0, "gigs_1y": 3, "outlets": 1,
                "raw_genres": "", "press_sources": "rhythmer", "sel_programs": "",
                "already_outcome": None,
            },
            {
                "artist_key": "top_team", "artist": "탑팀", "n_branch": 3, "n_signals": 10,
                "branches": "공연 · 선정·지원 · 큐레이션", "first_seen": "2026-06-01", "last_seen": "2026-12-31",
                "first_seen_all": "2025-11-01", "status": "확인 안 됨",
                "best_stage": 3, "dmz": 0, "peer_selected": 1, "gigs_1y": 10, "outlets": 1,
                "raw_genres": "인디음악|록/메탈", "press_sources": "musicy", "sel_programs": "burock_rookies",
                "already_outcome": None,
            },
        ]
        sigs = [
            {"artist_key": "top_team", "signal_date": "2026-12-31", "raw_date": "2026", "round": "2026",
             "branch": "선정·지원", "source": "busanrock", "title": "burock_rookies", "detail": "2026 · selected",
             "url": "https://example.com/1"},
            {"artist_key": "top_team", "signal_date": "2026-11-01", "raw_date": "2026-11-01", "round": "",
             "branch": "공연", "source": "indistreet", "title": "가을 공연", "detail": "Club FF",
             "url": "https://example.com/2"},
        ]
        enriched = bd.enrich_candidates(cands, sigs, today=today)
        self.assertEqual([c["artist_key"] for c in enriched], ["top_team", "low_team"])
        self.assertGreater(enriched[0]["score_v0"], enriched[1]["score_v0"])
        self.assertEqual(enriched[0]["last_seen"], "2026-11-27")
        self.assertEqual(enriched[0]["primary_genre"], "록·밴드")
        self.assertEqual(enriched[1]["primary_genre"], "힙합")  # safe rhythmer fallback
        self.assertEqual(enriched[0]["signals"][0]["date_label"], "2026 선정")
        self.assertEqual(enriched[0]["rookie_label"], "신인 추정")

    def test_filter_recent_press_drops_famous_and_non_artists(self):
        rows = [
            {"artist_key": "koccamusic", "artist": "@koccamusic", "source": "instagram", "kind": "인스타 큐레이터",
             "published_at": "2026-11-25", "title": "공고", "url": "https://ig/1"},
            {"artist_key": "colde", "artist": "Colde", "source": "visla", "kind": "웹매거진",
             "published_at": "2026-11-24", "title": "기사", "url": "https://visla/1"},
            {"artist_key": "신인팀", "artist": "신인팀", "source": "visla", "kind": "웹매거진",
             "published_at": "2026-11-24", "title": "신인 소개", "url": "https://visla/2"},
        ]
        out = bd.filter_recent_press(rows, candidate_keys={"신인팀"})
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["artist"], "신인팀")
        self.assertTrue(out[0]["is_candidate"])


class BacktestFallbackTest(unittest.TestCase):
    def test_parses_markdown_table_fallback(self):
        md = """
### a09_score_v0_backtest

| 기준일 | 후보_팀수 | 이후_정답_팀수 | 상위_k | 방법 | 맞힌_팀수 | 적중률_pct | 무작위_기대_팀수 | 무작위_대비_배수 |
|---|---|---|---|---|---|---|---|---|
| 2025-01-01 | 2583 | 29 | 20 | 점수 v0 | 2 | 10.0 | 0.2 | 8.9 |
| 2025-01-01 | 2583 | 29 | 20 | 갈래 수만 | 1 | 5.0 | 0.2 | 4.5 |
"""
        rows = bd.parse_a09_markdown(md)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["cutoff"], "2025-01-01")
        self.assertEqual(rows[0]["k"], 20)
        self.assertEqual(rows[0]["method"], "점수 v0")
        self.assertEqual(rows[0]["hits"], 2)
        self.assertEqual(rows[0]["random_expected"], 0.2)
        self.assertEqual(rows[0]["lift"], 8.9)

    def test_normalize_a09_preserves_floats_from_records(self):
        csv_text = (
            "기준일,후보_팀수,이후_정답_팀수,상위_k,방법,맞힌_팀수,적중률_pct,무작위_기대_팀수,무작위_대비_배수\n"
            "2025-01-01,2583,29,200,점수 v0,7,3.5,2.2,3.1\n"
        )
        rows = bd._normalize_a09_rows(bd.records(csv_text))
        self.assertEqual(rows[0]["hit_rate_pct"], 3.5)
        self.assertEqual(rows[0]["random_expected"], 2.2)
        self.assertEqual(rows[0]["lift"], 3.1)


class BuildTest(unittest.TestCase):
    def test_records_error_when_one_query_fails_and_keeps_others(self):
        def fake_run(sql):
            if "v_outcome_team" in sql and "lead_time" in sql:
                raise RuntimeError("boom")
            if "FROM raw.raw_press" in sql and "last_30d" in sql:
                raise RuntimeError("boom")
            return "a,b\nx,1\n"

        out = bd.build(run=fake_run, use_xref_sql=False, xref={})
        self.assertIn("generated", out)
        self.assertEqual(len(out["errors"]), 1)
        self.assertIn("press_summary", out["errors"][0])
        self.assertEqual(out["sections"]["collection"], [{"a": "x", "b": 1}])

    def test_prev_snapshot_deltas(self):
        prev = {
            "generated": "2026-11-26T00:00:00+09:00",
            "sections": {
                "collection": [{"rows": 100}],
                "candidates": [{"artist_key": "a"}],
                "quality": [{"item": "멜론 프로필이 있는 팀", "value": 50}],
            },
        }

        def fake_run(sql):
            if "GROUP BY branch, source" in sql:
                return "branch,source,rows,teams,first_date,last_date\n공연,indiego,150,20,2025-01-01,2026-11-27\n"
            if "AS score_v0" in sql or "r.n_branch" in sql or "best_stage" in sql:
                return (
                    "artist_key,artist,n_branch,n_signals,branches,first_seen,last_seen,first_seen_all,"
                    "status,first_release,fan_count,already_outcome,raw_genres,press_sources,sel_programs,"
                    "best_stage,dmz,gigs_1y,outlets,peer_selected\n"
                    "a,에이,2,5,공연 · 발매,2026-10-01,2026-11-20,2025-10-01,신인,2025-01-01,100,,록,,band_discovery,3,0,5,1,1\n"
                    "b,비,2,3,공연 · 큐레이션,2026-10-01,2026-11-21,2025-11-01,확인 안 됨,,,,인디음악,musicy,,0,0,3,1,0\n"
                )
            if "멜론 프로필이 있는 팀" in sql:
                return "item,value\n멜론 프로필이 있는 팀,88\n"
            return ""

        out = bd.build(run=fake_run, prev=prev, use_xref_sql=False, xref={})
        self.assertEqual(out["deltas"]["candidates"], 1)
        self.assertEqual(out["deltas"]["total_rows"], 50)
        self.assertEqual(out["deltas"]["profiles"], 38)


if __name__ == "__main__":
    unittest.main()
