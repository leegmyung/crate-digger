"""거꾸로 따라가기(정답 팀 → 앞선 신호) 분석 테스트 — 가짜 데이터로."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import backtrace as bt  # noqa: E402

OUT = [
    {"program": "penta_superrookie", "round": "2025", "announced_at": "2025-06-09", "result": "finalist", "artist_text": "산보"},
    {"program": "hello_rookie_year", "round": "2026", "announced_at": "2026-11-20", "result": "shortlist", "artist_text": "산보"},
    {"program": "kma_rookie", "round": "23회", "announced_at": "2026-02-05", "result": "nominee", "artist_text": "우희준"},
]
SEL = [
    {"program": "muse_sejong", "round": "2024", "announced_at": "2024-05", "artist_text": "산 보"},     # 앞섬
    {"program": "yoojaeha_finalist", "round": "35회", "announced_at": "2024", "artist_text": "우희준"},  # 앞섬 (2024-12-31 → 2026-02-05)
    {"program": "yoojaeha_finalist", "round": "36회", "announced_at": "2025", "artist_text": "남남"},
    {"program": "yoojaeha_finalist", "round": "34회", "announced_at": "2023", "artist_text": "옛팀"},
    {"program": "burock_rookies", "round": "2026", "announced_at": "2026-08-13", "artist_text": "산보"},  # 정답보다 늦음
]
PROF = [{"artist_text": "산보", "debut_date": "", "first_release_date": "2024-03-01", "album_count": "4"},
        {"artist_text": "우희준", "debut_date": "2019-05-01", "first_release_date": "2019-05-01", "album_count": "9"}]


class FirstOutcomeTest(unittest.TestCase):
    def test_earliest_outcome_per_team(self):
        first = bt.first_outcomes(OUT)
        self.assertEqual(first["산보"]["date"], "2025-06-09")
        self.assertEqual(first["산보"]["program"], "penta_superrookie")
        self.assertEqual(sorted(first), ["산보", "우희준"])


class PriorSignalTest(unittest.TestCase):
    def test_only_signals_strictly_before_first_outcome(self):
        prior = bt.prior_signals(SEL, bt.first_outcomes(OUT))
        self.assertEqual([(p["program"], p["lead_days"]) for p in prior["산보"]], [("muse_sejong", 374)])  # 2024-05-31 → 2025-06-09
        self.assertEqual([p["program"] for p in prior["우희준"]], ["yoojaeha_finalist"])


class CareerTest(unittest.TestCase):
    def test_years_since_first_release_at_outcome(self):
        car = bt.career_at_outcome(PROF, bt.first_outcomes(OUT))
        self.assertEqual(car["산보"]["years"], 1.3)
        self.assertTrue(car["산보"]["newcomer_rule"])        # 3년 이내 & 앨범 10개 이하(현재 기준)
        self.assertEqual(car["우희준"]["years"], 6.8)
        self.assertFalse(car["우희준"]["newcomer_rule"])


class PrecisionTest(unittest.TestCase):
    def test_hit_rate_per_signal_program_for_rounds_before_window(self):
        rates = bt.signal_hit_rates(SEL, OUT, window_start="2025-01-01")
        y = rates["yoojaeha_finalist"]
        self.assertEqual((y["teams"], y["hits"]), (2, 1))   # 기간 전 신호 팀: 우희준·옛팀 → 우희준만 적중 (36회 남남은 기간 안이라 제외)
        self.assertEqual(rates["muse_sejong"]["hits"], 1)

    def test_lookback_limits_old_signals(self):
        rates = bt.signal_hit_rates(SEL, OUT, window_start="2025-01-01", lookback_years=1)
        self.assertEqual(rates["yoojaeha_finalist"]["teams"], 1)   # 2024년 신호만 (2023년 옛팀 제외)


class TierTest(unittest.TestCase):
    def test_career_filter_drops_established_teams_from_mixed_outcomes(self):
        outs = [{"program": "burock_main", "round": "2026", "announced_at": "2026-09-04", "result": "selected", "artist_text": "강산에"},
                {"program": "burock_main", "round": "2026", "announced_at": "2026-09-04", "result": "selected", "artist_text": "새팀"},
                {"program": "burock_main", "round": "2026", "announced_at": "2026-09-04", "result": "selected", "artist_text": "모름팀"},
                {"program": "kma_rookie", "round": "23회", "announced_at": "2026-02-05", "result": "nominee", "artist_text": "강산에"}]
        profs = [{"artist_text": "강산에", "debut_date": "1993-01-01", "first_release_date": "", "album_count": "30"},
                 {"artist_text": "새팀", "debut_date": "2024-03-01", "first_release_date": "", "album_count": "3"}]
        kept = bt.filter_career(outs, profs)
        self.assertEqual([(o["program"], o["artist_text"]) for o in kept], [("burock_main", "새팀"), ("kma_rookie", "강산에")])

    def test_mid_outcomes_become_signals_for_final_outcomes(self):
        outs = [{"program": "penta_superrookie", "round": "2025", "announced_at": "2025-06-09", "result": "winner", "artist_text": "피치트럭"},
                {"program": "hello_rookie", "round": "2026-05", "announced_at": "2026-05-22", "result": "selected", "artist_text": "피치트럭"},
                {"program": "hello_rookie_year", "round": "2026", "announced_at": "2026-11-20", "result": "winner", "artist_text": "피치트럭"},
                {"program": "kma_rookie", "round": "23회", "announced_at": "2026-02-05", "result": "nominee", "artist_text": "피치트럭"}]
        sig = bt.mid_signals(outs)
        self.assertEqual({s["program"] for s in sig}, {"penta_superrookie", "hello_rookie"})
        finals = bt.first_outcomes([o for o in outs if o["program"] in ("kma_rookie", "hello_rookie_year")])
        prior = bt.prior_signals(sig, finals)
        self.assertEqual([p["program"] for p in prior["피치트럭"]], ["penta_superrookie"])   # 첫 최종 정답(한대음 2026-02) 전엔 펜타만


class XrefTest(unittest.TestCase):
    """연결표(artist_xref)로 한영 표기가 다른 같은 팀을 한 팀으로 본다."""

    INDEX = {"by_key": {"confinedwhite": "컨파인드화이트", "컨파인드화이트": "컨파인드화이트"}}
    OUTS = [{"program": "kma_rookie", "round": "23회", "announced_at": "2026-02-05", "result": "nominee", "artist_text": "컨파인드 화이트"},
            {"program": "hello_rookie_year", "round": "2026", "announced_at": "2026-11-20", "result": "winner", "artist_text": "Confined White"}]

    def tearDown(self):
        bt.use_xref(None)

    def test_without_xref_english_spelling_is_separate_team(self):
        self.assertEqual(len(bt.first_outcomes(self.OUTS)), 2)

    def test_xref_merges_spellings_into_one_team(self):
        bt.use_xref(self.INDEX)
        first = bt.first_outcomes(self.OUTS)
        self.assertEqual(list(first), ["컨파인드 화이트"])
        self.assertEqual(first["컨파인드 화이트"]["programs"], ["kma_rookie", "hello_rookie_year"])

    def test_xref_links_signal_written_in_english(self):
        bt.use_xref(self.INDEX)
        sels = [{"program": "muse_sejong", "round": "2024", "announced_at": "2024-05", "artist_text": "Confined White"}]
        prior = bt.prior_signals(sels, bt.first_outcomes(self.OUTS[:1]))
        self.assertEqual([p["program"] for p in prior["컨파인드 화이트"]], ["muse_sejong"])


if __name__ == "__main__":
    unittest.main()
