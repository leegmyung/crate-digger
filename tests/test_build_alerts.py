"""매일 알림(scripts/build_alerts.py): 랩 데이터·스냅샷·발굴 단계로 '오늘 새로 생긴 일'을 찾는다.
'새로' = 지난 실행 때 본 상태(state)와 비교. state 가 없으면 기준일 7일 전까지를 이미 본 것으로 친다."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_alerts as ba  # noqa: E402

AS_OF = "2026-11-27"


def sig(team, branch, date, source="indistreet", program="", stage_rank=None, venue="", role="discovery"):
    return {"team_key": team, "branch": branch, "source": source, "program": program, "stage_rank": stage_rank,
            "signal_date": date, "venue": venue, "role": role}


def out(team, program, date, grade="A", counted=True, label="뮤즈온"):
    return {"team_key": team, "program": program, "program_label": label, "announced_date": date,
            "counted": counted, "grade": grade}


TEAMS = {"a": "에이", "b": "비", "w": "수상팀", "n": "뉴"}


class KeyTest(unittest.TestCase):
    def test_signal_key_is_stable_and_short(self):
        s = sig("a", "공연", "2026-11-20", venue="클럽")
        self.assertEqual(ba.signal_key(s), ba.signal_key(dict(s)))
        self.assertNotEqual(ba.signal_key(s), ba.signal_key({**s, "venue": "다른"}))
        self.assertLessEqual(len(ba.signal_key(s)), 16)


class DetectTest(unittest.TestCase):
    def test_stage_up(self):
        now = {"a": 2, "b": 1, "n": 1}
        before = {"a": 1, "b": 1}
        alerts = ba.detect_stage_up(now, before, TEAMS, AS_OF)
        self.assertEqual([(x["team_key"], x["type"]) for x in alerts], [("a", "stage_up"), ("n", "stage_up")])
        self.assertIn("첫 신호 → 여러 갈래", alerts[0]["text"])
        self.assertIn("새로 나타난 팀", alerts[1]["text"])     # 지난번엔 없던 팀은 '백지 →'라고 쓰지 않음

    def test_new_selection_and_outcome(self):
        new = [sig("a", "선정·지원", "2026-11-25", source="x", program="band_discovery", stage_rank=3),
               sig("a", "선정·지원", "2026-11-25", source="x", program="dmz_lineup", stage_rank=2, role="excluded"),
               sig("b", "공연", "2026-11-25", venue="클럽")]
        sel = ba.detect_new_selection(new, TEAMS, {"band_discovery": "밴드 디스커버리"})
        self.assertEqual(len(sel), 1)
        self.assertIn("밴드 디스커버리", sel[0]["text"])
        outs = [out("w", "museon_final", "2026-11-26"), out("b", "kma", "2026-11-26", counted=False)]
        got = ba.detect_new_outcomes(outs, known=set(), teams=TEAMS)
        self.assertEqual([x["team_key"] for x in got], ["w"])

    def test_blank_first_mention(self):
        new = [sig("n", "선정·지원", "2026-11-26", source="x", program="muse_sejong", stage_rank=1),
               sig("n", "발매", "2026-11-26", source="melon"),
               sig("a", "공연", "2026-11-26", venue="클럽")]
        got = ba.detect_blank_first_mention(new, {"n": 0, "a": 1}, TEAMS, {})
        self.assertEqual([x["team_key"] for x in got], ["n"])
        self.assertGreater(got[0]["importance"], ba.BASE["blank_first_mention"])   # 선정·지원이면 더 중요

    def test_rank_jump(self):
        now = {"a": 10, "b": 40, "n": 5}
        before = {"a": 90, "b": 45}
        got = {x["team_key"]: x for x in ba.detect_rank_jump(now, before, TEAMS, AS_OF, "2026-11-20")}
        self.assertIn("a", got)          # 80계단 상승
        self.assertNotIn("b", got)       # 5계단
        self.assertIn("n", got)          # 새로 상위권
        self.assertIn("90위 → 10위", got["a"]["text"])

    def test_new_gigs_one_per_team_date_venue(self):
        new = [sig("a", "공연", "2026-12-05", venue="클럽"), sig("a", "공연", "2026-12-05", venue="클럽", source="ig"),
               sig("b", "공연", "2026-12-06", venue="홀", role="excluded"),
               sig("b", "공연", "2026-11-01", venue="홀")]             # 늦게 수집된 지난 공연 → 알림 아님
        got = ba.detect_new_gigs(new, TEAMS, AS_OF)
        self.assertEqual(len(got), 1)
        self.assertTrue(got[0]["upcoming"])
        self.assertEqual(len(got[0]["evidence"]), 2)

    def test_big_venue_first(self):
        cap = {"tiers": [{"tier": "S", "max": 150}, {"tier": "M", "max": 400}, {"tier": "L", "max": 1000},
                         {"tier": "XL", "max": None}],
               "venues": {"큰홀": {"tier": "L"}, "작은클럽": {"tier": "S"}, "모름": {"tier": None}}}
        all_sigs = [sig("a", "공연", "2026-01-01", venue="큰홀"), sig("a", "공연", "2026-12-01", venue="큰홀"),
                    sig("b", "공연", "2026-12-01", venue="큰홀"), sig("b", "공연", "2026-06-01", venue="작은클럽")]
        new = [all_sigs[1], all_sigs[2]]
        got = ba.detect_big_venue(new, all_sigs, cap, TEAMS)
        self.assertEqual([x["team_key"] for x in got], ["b"])       # a 는 전에 큰홀에 섰음
        self.assertEqual(ba.detect_big_venue(new, all_sigs, None, TEAMS), [])   # 체급 파일이 없으면 건너뜀

    def test_peer_winner_pairs_and_new_links(self):
        sigs = [sig("a", "공연", "2026-11-20", venue="클럽"), sig("w", "공연", "2026-11-20", venue="클럽"),
                sig("b", "공연", "2025-01-01", venue="클럽"), sig("w", "공연", "2025-01-01", venue="클럽")]
        outs = [out("w", "museon_final", "2025-06-01")]
        pairs = ba.peer_winner_pairs(sigs, outs)
        self.assertEqual(len(pairs), 1)                 # 2025-01-01 엔 w 가 아직 정답 전
        got = ba.detect_new_peer_winner(pairs, known=set(), teams=TEAMS)
        self.assertEqual(got[0]["team_key"], "a")
        self.assertIn("수상팀", got[0]["text"])

    def test_peer_winner_one_alert_per_team(self):
        pairs = {"a|w|2026-11-20|클럽": ("a", "w", "2026-11-20", "클럽"),
                 "a|b|2026-11-25|홀": ("a", "b", "2026-11-25", "홀")}
        got = ba.detect_new_peer_winner(pairs, known=set(), teams=TEAMS)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["date"], "2026-11-25")      # 가장 최근 무대
        self.assertEqual(set(got[0]["winners"]), {"w", "b"})
        self.assertEqual(ba.detect_new_peer_winner(pairs, known=set(pairs), teams=TEAMS), [])


class RankCapTest(unittest.TestCase):
    def test_sort_by_importance_and_cap_per_type(self):
        alerts = [{"type": "new_gig", "importance": 10, "date": "2026-12-01", "team_key": f"t{i}"} for i in range(5)]
        alerts += [{"type": "new_outcome", "importance": 100, "date": "2026-11-26", "team_key": "w"}]
        got = ba.rank_and_cap(alerts, caps={"new_gig": 2}, default_cap=20)
        self.assertEqual(got[0]["type"], "new_outcome")
        self.assertEqual(sum(1 for a in got if a["type"] == "new_gig"), 2)

    def test_top_candidate_boost(self):
        a = [{"type": "new_gig", "importance": 10, "date": "2026-12-01", "team_key": "a"}]
        boosted = ba.boost_candidates(a, {"a": 5})
        self.assertGreater(boosted[0]["importance"], 10)
        self.assertEqual(boosted[0]["rank"], 5)
        self.assertEqual(a[0]["importance"], 10)      # 원본은 그대로


class BaselineTest(unittest.TestCase):
    def test_state_baseline_same_day_reuses_previous_baseline(self):
        state = {"as_of": AS_OF, "current": {"signals": ["x"]}, "baseline": {"signals": ["old"]}}
        self.assertEqual(ba.baseline_from_state(state, AS_OF), {"signals": ["old"]})   # 하루 두 번 돌려도 같은 알림
        self.assertEqual(ba.baseline_from_state(state, "2026-11-28"), {"signals": ["x"]})
        self.assertIsNone(ba.baseline_from_state(None, AS_OF))
        self.assertIsNone(ba.baseline_from_state({"as_of": "2026-11-30", "current": {}}, AS_OF))   # 미래 state 는 무시

    def test_window_baseline_without_state(self):
        sigs = [sig("a", "공연", "2026-11-01", venue="클럽"), sig("a", "공연", "2026-11-25", venue="클럽"),
                sig("a", "공연", "2026-12-25", venue="클럽")]
        outs = [out("w", "m", "2026-10-01"), out("w", "m2", "2026-11-26")]
        base = ba.window_baseline(sigs, outs, AS_OF, days=7)
        self.assertEqual(base["signals"], [ba.signal_key(sigs[0])])
        self.assertEqual(base["outcomes"], [ba.outcome_key(outs[0])])


class BuildTest(unittest.TestCase):
    def test_build_end_to_end_without_duckdb(self):
        data = {
            "signals": [sig("a", "공연", "2026-11-01", venue="클럽"), sig("a", "큐레이션", "2026-11-25", source="musicy", role="context"),
                        sig("a", "공연", "2026-12-05", venue="클럽")],
            "outcomes": [out("w", "museon_final", "2026-11-26")],
            "teams": TEAMS, "programs": {}, "capacity": None,
            "snap_now": {"a": 3}, "snap_before": {"a": 200}, "snap_dates": ("2026-11-27", "2026-11-20"),
        }
        stages_now, stages_before = {"a": 2}, {"a": 1}
        doc, state = ba.build(data, stages_now, stages_before, baseline=None, as_of=AS_OF)
        types = {a["type"] for a in doc["alerts"]}
        self.assertTrue({"stage_up", "new_outcome", "rank_jump", "new_gig"} <= types)
        self.assertEqual(doc["baseline"]["kind"], "window")
        self.assertEqual(state["as_of"], AS_OF)
        self.assertIn("signals", state["current"])
        for a in doc["alerts"]:
            self.assertTrue({"type", "type_label", "team_key", "name", "date", "found_on", "text", "evidence",
                             "importance"} <= set(a))
            self.assertEqual(a["found_on"], AS_OF)

    def test_same_day_rerun_gives_same_alerts(self):
        data = {"signals": [sig("a", "공연", "2026-11-01", venue="클럽"), sig("a", "공연", "2026-12-05", venue="클럽")],
                "outcomes": [], "teams": TEAMS, "programs": {}, "capacity": None,
                "snap_now": {}, "snap_before": {}, "snap_dates": (None, None)}
        doc1, state1 = ba.build(data, {"a": 1}, {"a": 1}, baseline=None, as_of=AS_OF)
        doc2, state2 = ba.build(data, {"a": 1}, {}, baseline=ba.baseline_from_state(state1, AS_OF), as_of=AS_OF)
        strip = lambda d: [(a["type"], a["team_key"], a["date"]) for a in d["alerts"]]  # noqa: E731
        self.assertEqual(strip(doc1), strip(doc2))
        doc3, _ = ba.build(data, {"a": 1}, {}, baseline=ba.baseline_from_state(state2, "2026-11-28"), as_of="2026-11-28")
        self.assertEqual(doc3["alerts"], [])                 # 다음 날엔 이미 본 것


if __name__ == "__main__":
    unittest.main()
