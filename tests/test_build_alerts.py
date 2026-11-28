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
        now = {"a": 2, "b": 1, "n": 2}
        before = {"a": 1, "b": 1}
        fresh = [sig("a", "큐레이션", "2026-11-25", source="musicy"), sig("n", "공연", "2026-11-20", venue="클럽"),
                 sig("n", "큐레이션", "2026-11-24", source="izm")]
        alerts = ba.detect_stage_up(now, before, TEAMS, AS_OF, fresh, first_seen={"a": "2025-01-01", "n": "2026-11-20"})
        self.assertEqual([(x["team_key"], x["type"]) for x in alerts], [("a", "stage_up"), ("n", "stage_up")])
        self.assertIn("첫 신호 → 여러 갈래", alerts[0]["text"])
        self.assertIn("새로 나타난 팀", alerts[1]["text"])     # 지난번엔 없던 팀은 '백지 →'라고 쓰지 않음

    def test_stage_up_needs_fresh_new_mention(self):
        # 새 신호 없이 단계만 바뀐 것(재계산·정답 다시 적재)은 알림 아님 — 2026-11-28 '단계 상승 1,089건' 몰림의 원인
        self.assertEqual(ba.detect_stage_up({"a": 2}, {"a": 1}, TEAMS, AS_OF, [], first_seen={"a": "2025-01-01"}), [])
        self.assertEqual(ba.detect_stage_up({"a": 2}, {"a": 1}, TEAMS, AS_OF,
                                            [sig("a", "발매", "2026-11-25", source="melon")], first_seen={}), [])   # 자기 발매는 언급 아님

    def test_stage_up_new_team_rules(self):
        fresh = [sig("n", "공연", "2026-11-25", venue="클럽")]
        # 새 팀 첫 신호 1건(1단계)은 알림 아님 — 인스타 공연 한 줄짜리 팀 수백 개가 몰림
        self.assertEqual(ba.detect_stage_up({"n": 1}, {}, TEAMS, AS_OF, fresh, first_seen={"n": "2026-11-25"}), [])
        # 지난번 후보 목록에 없었지만 옛 기록이 있는 팀(신인 판정·연결표가 바뀜)은 '새로 나타난 팀'이 아님
        two = fresh + [sig("n", "큐레이션", "2026-11-26", source="izm")]
        self.assertEqual(ba.detect_stage_up({"n": 2}, {}, TEAMS, AS_OF, two, first_seen={"n": "2024-05-01"}), [])
        self.assertEqual(len(ba.detect_stage_up({"n": 2}, {}, TEAMS, AS_OF, two, first_seen={"n": "2026-11-20"})), 1)

    def test_fresh_signal_window(self):
        self.assertTrue(ba.is_fresh(sig("a", "공연", "2026-11-01"), AS_OF))
        self.assertTrue(ba.is_fresh(sig("a", "공연", "2026-12-20"), AS_OF))          # 다가오는 일
        self.assertFalse(ba.is_fresh(sig("a", "공연", "2026-10-27"), AS_OF))         # 30일보다 옛날 = 늦게 알게 된 일

    def test_new_selection_old_date_marked_late(self):
        # 부산록페 루키즈처럼 몇 달 전 선정이 오늘 적재된 경우: 보여 주되 '늦게 확인'으로 낮춘다
        new = [sig("a", "선정·지원", "2026-08-13", source="busanrock", program="burock_rookies", stage_rank=3),
               sig("b", "선정·지원", "2026-11-25", source="x", program="band_discovery", stage_rank=3)]
        got = {x["team_key"]: x for x in ba.detect_new_selection(new, TEAMS, {}, as_of=AS_OF)}
        self.assertTrue(got["a"]["late"])
        self.assertIn("늦게 확인", got["a"]["text"])
        self.assertFalse(got["b"]["late"])
        self.assertLess(got["a"]["importance"], got["b"]["importance"])

    def test_rank_jump_only_for_active_teams(self):
        # 새 신호 없이 순위만 오른 것(계산 규칙·데이터 다시 적재)은 알림 아님
        got = ba.detect_rank_jump({"a": 10, "n": 5}, {"a": 90}, TEAMS, AS_OF, "2026-11-20", active={"a"})
        self.assertEqual([x["team_key"] for x in got], ["a"])

    def test_big_venue_first_ignores_old_and_rekeyed_history(self):
        cap = {"venues": {"큰홀": {"tier": "L"}}}
        old_rekeyed = sig("a", "공연", "2025-03-01", venue="큰홀")         # 연결표가 바뀌어 지문이 새로 생긴 옛 공연
        recent = sig("a", "공연", "2026-12-01", venue="큰홀")
        late_b = sig("b", "공연", "2026-09-01", venue="큰홀")             # 늦게 수집된 지난 공연
        new = [old_rekeyed, recent, late_b]
        self.assertEqual(ba.detect_big_venue(new, new, cap, TEAMS, as_of=AS_OF), [])

    def test_big_venue_first_only_for_newcomer_candidates(self):
        # 신인 후보(발굴 단계 후보 목록)가 아닌 기성·해외 팀(갤럭시 익스프레스·Sunny Day Service)은 큰 공연장 첫 출연 알림에서 뺀다
        cap = {"venues": {"큰홀": {"tier": "L"}}}
        new = [sig("a", "공연", "2026-12-01", venue="큰홀"), sig("b", "공연", "2026-12-02", venue="큰홀")]
        got = ba.detect_big_venue(new, new, cap, TEAMS, as_of=AS_OF, candidates={"b"})
        self.assertEqual([x["team_key"] for x in got], ["b"])
        self.assertEqual(len(ba.detect_big_venue(new, new, cap, TEAMS, as_of=AS_OF)), 2)   # 후보 목록을 안 주면 전과 같음

    def test_peer_winner_needs_recent_new_gig(self):
        pairs = {"a|w|2025-06-07|클럽": ("a", "w", "2025-06-07", "클럽"),      # 옛 무대 — 수상 팀 정답·연결표가 바뀌어 새로 생긴 연결
                 "b|w|2026-11-20|홀": ("b", "w", "2026-11-20", "홀"),          # 최근이지만 b 쪽 공연은 이미 본 것
                 "n|w|2026-11-22|홀": ("n", "w", "2026-11-22", "홀")}
        fresh_gigs = {("n", "2026-11-22", "홀")}
        got = ba.detect_new_peer_winner(pairs, set(), TEAMS, as_of=AS_OF, fresh_gigs=fresh_gigs)
        self.assertEqual([x["team_key"] for x in got], ["n"])

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

    def test_old_outcome_added_late_is_past_record_not_new(self):
        # 오늘 옛 정답을 되짚어 넣으면(발표 2021) '새 수상'처럼 보이지 않게 — 비교 기준일보다 30일 넘게 앞선 발표는 '과거 기록 추가'
        outs = [out("w", "cj_tuneup", "2021-05-01"), out("a", "museon_final", "2026-11-26"),
                out("b", "kma", "2026-10-20"), out("n", "hello", "2026-10-30")]
        got = {x["team_key"]: x["type"] for x in ba.detect_new_outcomes(outs, known=set(), teams=TEAMS, since="2026-11-27")}
        self.assertEqual(got, {"w": "past_outcome", "a": "new_outcome", "b": "past_outcome", "n": "new_outcome"})
        imp = {x["team_key"]: x["importance"] for x in ba.detect_new_outcomes(outs, known=set(), teams=TEAMS, since="2026-11-27")}
        self.assertLess(imp["w"], ba.BASE["new_gig"] + 1)                         # 등급 가산 없이 중요도 낮게(목록 뒤로)
        self.assertNotIn("past_outcome", ba.STAR_KINDS)                          # 사건 별점도 안 붙임
        # since 를 안 주면 예전처럼 모두 새 정답
        self.assertEqual({x["type"] for x in ba.detect_new_outcomes(outs, known=set(), teams=TEAMS)}, {"new_outcome"})

    def test_build_marks_stale_outcomes_with_past_type(self):
        data = {"signals": [sig("a", "공연", "2026-12-05", venue="클럽")],
                "outcomes": [out("w", "cj_tuneup", "2021-05-01"), out("a", "museon_final", "2026-11-26")],
                "teams": TEAMS, "programs": {}, "capacity": None, "snap_now": {}, "snap_before": {}, "snap_dates": (None, None),
                "event_stars": {"w": [("outcome", "2021-05-01", 5)]}}
        doc, _ = ba.build(data, {}, {}, baseline={"as_of": "2026-11-26", "signals": [], "outcomes": [], "pairs": []}, as_of=AS_OF)
        types = {a["team_key"]: a["type"] for a in doc["alerts"] if a["type"] in ("new_outcome", "past_outcome")}
        self.assertEqual(types, {"w": "past_outcome", "a": "new_outcome"})
        self.assertIn("past_outcome", doc["types"])
        self.assertIsNone(next(a for a in doc["alerts"] if a["team_key"] == "w")["stars"])

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


def mentions(team, dates, source="izm"):
    """같은 출처라도 날짜가 다르면 다른 언급."""
    return [sig(team, "큐레이션", d, source=source, role="context") for d in dates]


def weekly_past(team, per_week, weeks=12, end="2026-11-20"):
    """기준일 7일 전(end)부터 거꾸로 weeks주 동안 주마다 per_week건 (출처를 바꿔 같은 날 여러 건)."""
    from datetime import date, timedelta
    out_rows = []
    for w in range(weeks):
        day = (date.fromisoformat(end) - timedelta(days=7 * w + 1)).isoformat()
        out_rows += [sig(team, "큐레이션", day, source=f"src{i}", role="context") for i in range(per_week)]
    return out_rows


class SpikeTest(unittest.TestCase):
    RECENT = ["2026-11-22", "2026-11-24", "2026-11-26"]

    def test_first_mentions_reported_as_count_not_ratio(self):
        signals = mentions("n", self.RECENT)
        alerts = ba.detect_spike(signals, signals, TEAMS, AS_OF)
        self.assertEqual(len(alerts), 1)
        a = alerts[0]
        self.assertEqual((a["type"], a["team_key"], a["recent"], a["past_weeks_total"]), ("spike", "n", 3, 0))
        self.assertIsNone(a["ratio"])
        self.assertIn("처음 3건", a["text"])

    def test_low_usual_team_shows_count_with_usual(self):
        signals = mentions("n", self.RECENT) + mentions("n", ["2026-10-01", "2026-09-10"], source="visla")
        a = ba.detect_spike(signals, signals[:3], TEAMS, AS_OF)[0]
        self.assertIsNone(a["ratio"])
        self.assertIn("12주 2건", a["text"])

    def test_ratio_against_twelve_week_average(self):
        past = weekly_past("a", 2)                                      # 평균 주 2건
        recent = [sig("a", "큐레이션", d, source=f"r{i}", role="context") for i, d in
                  enumerate(["2026-11-21", "2026-11-22", "2026-11-23", "2026-11-24", "2026-11-25", "2026-11-26"])]
        a = ba.detect_spike(past + recent, recent, TEAMS, AS_OF)[0]
        self.assertAlmostEqual(a["ratio"], 3.0)
        self.assertIn("3.0배", a["text"])
        self.assertEqual(ba.detect_spike(past + recent[:4], recent[:4], TEAMS, AS_OF), [])   # 2배는 알림 아님

    def test_needs_minimum_recent_and_a_new_signal(self):
        two = mentions("n", self.RECENT[:2])
        self.assertEqual(ba.detect_spike(two, two, TEAMS, AS_OF), [])                  # 1주 2건은 너무 적음
        three = mentions("n", self.RECENT)
        self.assertEqual(ba.detect_spike(three, [], TEAMS, AS_OF), [])                 # 새로 본 언급이 없으면 이미 알린 것

    def test_gigs_excluded_and_future_not_counted(self):
        rows = mentions("n", self.RECENT[:2]) + [sig("n", "공연", "2026-11-25", venue="클럽"),
                                                 sig("n", "큐레이션", "2026-11-25", source="x", role="excluded"),
                                                 sig("n", "큐레이션", "2026-12-01", source="y", role="context")]
        self.assertEqual(ba.detect_spike(rows, rows, TEAMS, AS_OF), [])

    def test_same_day_same_source_counts_once(self):
        rows = mentions("n", self.RECENT[:1]) + mentions("n", ["2026-11-26", "2026-11-26"])   # 1 + 1 = 2건
        self.assertEqual(ba.detect_spike(rows, rows, TEAMS, AS_OF), [])

    def test_build_includes_spike_type(self):
        self.assertIn("spike", ba.TYPES)
        data = {"signals": mentions("n", self.RECENT), "outcomes": [], "teams": TEAMS, "programs": {}, "capacity": None,
                "snap_now": {}, "snap_before": {}, "snap_dates": (None, None)}
        doc, _ = ba.build(data, {"n": 1}, {"n": 1}, baseline=None, as_of=AS_OF)
        self.assertIn("spike", {a["type"] for a in doc["alerts"]})


class RankCapTest(unittest.TestCase):
    def test_sort_by_importance_and_cap_per_type(self):
        alerts = [{"type": "new_gig", "importance": 10, "date": "2026-12-01", "team_key": f"t{i}"} for i in range(5)]
        alerts += [{"type": "new_outcome", "importance": 100, "date": "2026-11-26", "team_key": "w"}]
        got = ba.rank_and_cap(alerts, caps={"new_gig": 2}, default_cap=20)
        self.assertEqual(got[0]["type"], "new_outcome")
        self.assertEqual(sum(1 for a in got if a["type"] == "new_gig"), 2)

    def test_future_dates_sorted_as_found_on(self):
        # 선정 기간 끝날처럼 미래 날짜는 정렬에서 알게 된 날(as_of)로 친다 — 같은 중요도면 미래 날짜가 맨 위로 가지 않게
        alerts = [{"type": "new_selection", "importance": 70, "date": "2027-03-01", "team_key": "f"},
                  {"type": "new_selection", "importance": 70, "date": "2026-11-27", "team_key": "t"},
                  {"type": "new_selection", "importance": 70, "date": "2026-11-20", "team_key": "o"}]
        got = ba.rank_and_cap(alerts, caps={}, default_cap=20, as_of=AS_OF)
        self.assertEqual([a["team_key"] for a in got], ["f", "t", "o"])   # f 는 as_of(11-27)와 같게 → 안정 정렬로 입력 순서
        alerts[0]["date"] = "2027-03-01"
        got2 = ba.rank_and_cap(list(reversed(alerts)), caps={}, default_cap=20, as_of=AS_OF)
        self.assertEqual([a["team_key"] for a in got2], ["t", "f", "o"])

    def test_also_lists_other_types_for_same_team(self):
        alerts = [{"type": "stage_up", "importance": 50, "date": AS_OF, "team_key": "a"},
                  {"type": "peer_winner", "importance": 45, "date": AS_OF, "team_key": "a"},
                  {"type": "new_gig", "importance": 10, "date": AS_OF, "team_key": "b"}]
        got = {(a["team_key"], a["type"]): a for a in ba.add_also(alerts)}
        self.assertEqual(got[("a", "stage_up")]["also"], ["peer_winner"])
        self.assertEqual(got[("b", "new_gig")]["also"], [])

    def test_top_candidate_boost(self):
        a = [{"type": "new_gig", "importance": 10, "date": "2026-12-01", "team_key": "a"}]
        boosted = ba.boost_candidates(a, {"a": 5})
        self.assertGreater(boosted[0]["importance"], 10)
        self.assertEqual(boosted[0]["rank"], 5)
        self.assertEqual(a[0]["importance"], 10)      # 원본은 그대로


class StarsTest(unittest.TestCase):
    """알림마다 사건 별점(stars) — 앱 alertStars 와 같은 규칙: 같은 팀·같은 날짜·종류 대응, 없으면 null."""
    def test_load_event_stars_keeps_file_order_and_numbers(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "event_stars.csv"
            p.write_text("team_key,date,kind,stars,reason\n"
                         "a,2026-11-26,outcome,5,x\n"
                         "a,2026-11-26,outcome,2,중복이면 앞 줄\n"
                         "b,2026-11-20,first_mention,3,x\n", encoding="utf-8")
            got = ba.load_event_stars(p)
        self.assertEqual(got["a"][0], ("outcome", "2026-11-26", 5))
        self.assertEqual(len(got["a"]), 2)
        self.assertEqual(ba.load_event_stars(Path(d) / "없음.csv"), {})     # 파일이 없으면 빈 것

    def test_attach_stars_maps_types_and_dates(self):
        stars = {"a": [("outcome", "2026-11-26", 5), ("outcome", "2026-11-26", 2)],
                 "b": [("first_mention", "2026-11-20", 3), ("selection", "2026-11-21", 4)],
                 "c": [("big_venue_first", "2026-12-01", 4)]}
        alerts = [{"type": "new_outcome", "team_key": "a", "date": "2026-11-26"},
                  {"type": "blank_first_mention", "team_key": "b", "date": "2026-11-20"},
                  {"type": "new_selection", "team_key": "b", "date": "2026-11-20"},      # 날짜가 다르면 없음
                  {"type": "big_venue_first", "team_key": "c", "date": "2026-12-01"},
                  {"type": "stage_up", "team_key": "a", "date": "2026-11-26"},           # 대응하는 사건 종류 없음
                  {"type": "new_gig", "team_key": "z", "date": "2026-12-05"}]
        got = [a["stars"] for a in ba.attach_stars(alerts, stars)]
        self.assertEqual(got, [5, 3, None, 4, None, None])
        self.assertNotIn("stars", alerts[0])                                            # 원본은 그대로

    def test_build_gives_every_alert_a_stars_field(self):
        data = {"signals": [sig("a", "공연", "2026-12-05", venue="클럽")],
                "outcomes": [out("w", "museon_final", "2026-11-26")], "teams": TEAMS, "programs": {}, "capacity": None,
                "snap_now": {}, "snap_before": {}, "snap_dates": (None, None),
                "event_stars": {"w": [("outcome", "2026-11-26", 5)]}}
        doc, _ = ba.build(data, {}, {}, baseline=None, as_of=AS_OF)
        self.assertTrue(doc["alerts"])
        self.assertTrue(all("stars" in a for a in doc["alerts"]))
        self.assertEqual(next(a for a in doc["alerts"] if a["type"] == "new_outcome")["stars"], 5)


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
