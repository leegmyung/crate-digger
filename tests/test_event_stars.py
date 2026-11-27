import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import event_stars as es  # noqa: E402


def sig(team, day, branch, source="src", program="", venue="", role="discovery", stage_rank=None):
    return {"team_key": team, "signal_date": day, "branch": branch, "source": source, "program": program,
            "venue": venue, "role": role, "stage_rank": stage_rank}


def out(team, day, grade="A", program="hello_rookie_year", label="올해의 헬로루키", counted=True):
    return {"team_key": team, "announced_date": day, "grade": grade, "program": program,
            "program_label": label, "counted": counted}


TIERS = {"롤링홀": "L", "Club 빵": "S", "예스24 라이브홀": "XL", "부산 오방가르드": "S"}
CITY = {"롤링홀": "서울", "Club 빵": "서울", "예스24 라이브홀": "서울", "부산 오방가르드": "부산"}


class StageBeforeTest(unittest.TestCase):
    def test_blank_first_and_multi_branch(self):
        rows = [sig("a", "2024-01-01", "발매"), sig("a", "2024-02-01", "공연", venue="Club 빵"),
                sig("a", "2024-03-01", "큐레이션", source="izm")]
        self.assertEqual(es.stage_before(rows, [], "2024-01-15"), 0)   # 자기 발매만
        self.assertEqual(es.stage_before(rows, [], "2024-02-15"), 1)   # 공연 1갈래
        self.assertEqual(es.stage_before(rows, [], "2024-03-15"), 2)   # 2갈래

    def test_selection_and_outcomes_raise_stage(self):
        rows = [sig("a", "2024-02-01", "선정·지원", program="busan_rookies", stage_rank=3)]
        self.assertEqual(es.stage_before(rows, [], "2024-02-02"), 3)
        self.assertEqual(es.stage_before([], [out("a", "2024-01-01", grade="B")], "2024-02-01"), 3)
        self.assertEqual(es.stage_before([], [out("a", "2024-01-01", grade="S")], "2024-02-01"), 4)

    def test_excluded_and_dmz_do_not_count(self):
        rows = [sig("a", "2024-02-01", "선정·지원", program="dmz_lineup", stage_rank=2),
                sig("a", "2024-02-01", "공연", role="excluded", venue="Club 빵")]
        self.assertEqual(es.stage_before(rows, [], "2024-03-01"), 0)

    def test_same_day_is_not_before(self):
        rows = [sig("a", "2024-02-01", "공연", venue="Club 빵")]
        self.assertEqual(es.stage_before(rows, [], "2024-02-01"), 0)


class DetectEventsTest(unittest.TestCase):
    def kinds(self, events):
        return sorted((e["team_key"], e["date"], e["kind"]) for e in events)

    def test_finds_each_kind_once(self):
        signals = [
            sig("a", "2024-01-10", "공연", venue="부산 오방가르드"),
            sig("a", "2024-02-10", "공연", venue="Club 빵"),           # 처음 서울 (지방에서 먼저)
            sig("a", "2024-03-10", "큐레이션", source="izm"),
            sig("a", "2024-03-20", "큐레이션", source="izm"),           # 같은 매체 두 번째는 사건 아님
            sig("a", "2024-04-10", "선정·지원", program="busan_rookies", stage_rank=3),
            sig("a", "2024-05-10", "공연", venue="롤링홀"),             # 큰 공연장 첫 출연
            sig("a", "2024-06-10", "공연", venue="예스24 라이브홀"),     # 이미 큰 무대에 섰으므로 사건 아님
        ]
        events = es.detect_events(signals, [out("a", "2024-07-01")], TIERS, CITY, "2024-12-31")
        self.assertEqual(self.kinds(events), [
            ("a", "2024-01-10", "first_mention"),
            ("a", "2024-02-10", "first_seoul_gig"),
            ("a", "2024-03-10", "magazine"),
            ("a", "2024-04-10", "selection"),
            ("a", "2024-05-10", "big_venue_first"),
            ("a", "2024-07-01", "outcome"),
        ])

    def test_seoul_first_only_after_regional_gig(self):
        signals = [sig("b", "2024-02-10", "공연", venue="Club 빵")]
        kinds = {e["kind"] for e in es.detect_events(signals, [], TIERS, CITY, "2024-12-31")}
        self.assertNotIn("first_seoul_gig", kinds)

    def test_future_events_and_low_selection_steps_skipped(self):
        signals = [sig("c", "2025-03-01", "공연", venue="롤링홀"),
                   sig("c", "2024-03-01", "선정·지원", program="muse_on", stage_rank=1)]
        kinds = {e["kind"] for e in es.detect_events(signals, [], TIERS, CITY, "2024-12-31")}
        self.assertNotIn("big_venue_first", kinds)   # 기준일 뒤
        self.assertNotIn("selection", kinds)         # 서류 통과(1)는 사건 아님
        self.assertIn("first_mention", kinds)

    def test_uncounted_outcome_ignored(self):
        events = es.detect_events([], [out("d", "2024-07-01", counted="false")], TIERS, CITY, "2024-12-31")
        self.assertEqual(events, [])


class ScoreTest(unittest.TestCase):
    def test_small_team_gets_more_stars_for_same_event(self):
        ev = {"kind": "selection", "base": 3, "detail": "부산 루키즈 선정"}
        small, _ = es.score_event(ev, stage=0)
        big, _ = es.score_event(ev, stage=3)
        self.assertGreater(small, big)

    def test_stars_clamped_and_reason_explains(self):
        stars, reason = es.score_event({"kind": "outcome", "base": 5, "detail": "올해의 헬로루키 (S)"}, stage=0)
        self.assertEqual(stars, 5)
        self.assertIn("백지", reason)
        low, _ = es.score_event({"kind": "magazine", "base": 1, "detail": "IZM"}, stage=4)
        self.assertEqual(low, 1)

    def test_first_mention_is_modest(self):
        stars, _ = es.score_event({"kind": "first_mention", "base": es.FIRST_MENTION_BASE, "detail": "공연"}, stage=0)
        self.assertEqual(stars, 3)

    def test_big_venue_as_first_ever_gig_gets_no_small_team_bonus(self):
        events = es.detect_events([sig("e", "2024-05-10", "공연", venue="예스24 라이브홀")], [], TIERS, CITY, "2024-12-31")
        big = [e for e in events if e["kind"] == "big_venue_first"][0]
        self.assertTrue(big["no_history"])
        stars, reason = es.score_event(big, stage=0)
        self.assertEqual(stars, 4)                      # 기본 4(XL) + 0, 백지 +2 를 주지 않음
        self.assertIn("첫 공연", reason)

    def test_tier_jump_bonus(self):
        ev = {"kind": "big_venue_first", "base": 3, "detail": "롤링홀 (L급)", "tier_jump": True}
        jump, reason = es.score_event(ev, stage=2)
        plain, _ = es.score_event({**ev, "tier_jump": False}, stage=2)
        self.assertEqual(jump, plain + 1)
        self.assertIn("체급", reason)


class WindowTest(unittest.TestCase):
    def test_counts_before_and_after(self):
        rows = [sig("a", "2024-01-05", "공연", venue="Club 빵"), sig("a", "2024-01-05", "공연", venue="Club 빵", source="x"),
                sig("a", "2024-01-20", "큐레이션", source="izm"),
                sig("a", "2024-02-10", "공연", venue="롤링홀"),
                sig("a", "2024-02-20", "큐레이션", source="visla"), sig("a", "2024-02-21", "선정·지원", stage_rank=2),
                sig("a", "2024-04-01", "공연", venue="롤링홀")]                    # 28일 밖
        w = es.window_counts(rows, "2024-02-01", "2024-12-31")
        self.assertEqual(w["gigs_before_28"], 1)        # 같은 날 공연은 한 번
        self.assertEqual(w["mentions_before_28"], 1)
        self.assertEqual(w["gigs_after_28"], 1)
        self.assertEqual(w["mentions_after_28"], 2)
        self.assertEqual(w["after_window_days"], 28)

    def test_after_window_cut_at_as_of(self):
        w = es.window_counts([], "2024-12-20", "2024-12-31")
        self.assertEqual(w["after_window_days"], 11)


class BuildFileTest(unittest.TestCase):
    def test_build_rows_and_write(self):
        data = {"signals": [sig("a", "2024-01-10", "공연", venue="부산 오방가르드"),
                            sig("a", "2024-05-10", "공연", venue="롤링홀")],
                "outcomes": [], "tiers": TIERS, "venue_city": CITY}
        rows = es.build_rows(data, "2024-12-31")
        self.assertTrue(all(1 <= r["stars"] <= 5 for r in rows))
        self.assertEqual([r["kind"] for r in rows], ["first_mention", "big_venue_first"])
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "event_stars.csv"
            es.write_csv(rows, p)
            with open(p, encoding="utf-8") as f:
                back = list(csv.DictReader(f))
            self.assertEqual(list(back[0])[:5], ["team_key", "date", "kind", "stars", "reason"])
            self.assertEqual(len(back), 2)

    def test_venue_city_map_uses_aliases(self):
        cfg = {"venues": [{"name": "오방가르드", "city": "부산", "aliases": ["Obang"], "our_names": ["부산 오방가르드"],
                           "our_venue": ""}]}
        m = es.venue_city_map(cfg)
        self.assertEqual(m["부산 오방가르드"], "부산")
        self.assertEqual(m["Obang"], "부산")

    def test_tier_map(self):
        self.assertEqual(es.tier_map({"venues": {"롤링홀": {"tier": "L"}, "x": {}}}), {"롤링홀": "L"})


if __name__ == "__main__":
    unittest.main()
