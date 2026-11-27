"""멜론 프로필 보강 명단(melon_names): 중요한 팀부터, 이미 찾아본 이름은 빼고."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import melon_names as mn  # noqa: E402

TEAMS = [{"team_key": k, "display_name": n, "profile_status": s} for k, n, s in [
    ("a", "에이", "unknown"), ("b", "비", "newcomer"), ("c", "씨", "unknown"), ("d", "디", "unknown"),
    ("e", "이", "unknown"), ("f", "에프", "unknown"), ("g", "지", "famous"), ("h", "에이치", "unknown")]]
SNAP = [{"team_key": "c", "score": "9", "rank": "1"}, {"team_key": "b", "score": "8", "rank": "2"},
        {"team_key": "a", "score": "7", "rank": "3"}, {"team_key": "zz", "score": "6", "rank": "4"}]
OUTCOMES = [{"team_key": "d", "counted": "true"}, {"team_key": "e", "counted": "false"},
            {"team_key": "a", "counted": "true"}]
SIGNALS = [{"team_key": "f", "branch": "공연", "signal_date": "2026-12-05"},
           {"team_key": "h", "branch": "공연", "signal_date": "2026-12-01"},
           {"team_key": "e", "branch": "공연", "signal_date": "2026-11-01"},   # 지난 공연
           {"team_key": "g", "branch": "공연", "signal_date": "2026-12-02"},   # 유명 → 이미 알고 있음
           {"team_key": "e", "branch": "큐레이션", "signal_date": "2026-12-09"}]


def build(**kw):
    args = dict(snapshot=SNAP, teams=TEAMS, outcomes=OUTCOMES, signals=SIGNALS, matches={}, today="2026-11-27")
    args.update(kw)
    return mn.build_names(**args)


class OrderTest(unittest.TestCase):
    def test_priority_snapshot_then_outcomes_then_upcoming_gigs(self):
        # ① 점수 상위 중 unknown (씨, 에이) ② 센 정답 unknown (디; 에이는 이미 있음) ③ 다가오는 공연 unknown (가까운 순: 에이치, 에프)
        self.assertEqual(build(), ["씨", "에이", "디", "에이치", "에프"])

    def test_limit_and_top_n_of_snapshot(self):
        self.assertEqual(build(limit=2), ["씨", "에이"])
        self.assertEqual(build(snapshot_top=1, candidate_top=0)[:2], ["씨", "디"])     # 스냅샷은 상위 1팀만 봄 (새 단계는 끔)

    def test_already_tried_names_are_skipped(self):
        got = build(matches={"씨": {"id": "1"}, "디": None})
        self.assertNotIn("씨", got)
        self.assertNotIn("디", got)          # 못 찾음(null)인데 시도 날짜를 모름 → 빼기

    def test_not_found_retried_after_30_days(self):
        old = build(matches={"디": None}, attempts={"디": "2026-10-01"})
        recent = build(matches={"디": None}, attempts={"디": "2026-11-10"})
        self.assertIn("디", old)
        self.assertNotIn("디", recent)
        self.assertNotIn("씨", build(matches={"씨": {"id": "1"}}, attempts={"씨": "2020-01-01"}))   # 찾은 이름은 다시 안 함

    def test_blank_names_and_duplicates(self):
        teams = TEAMS + [{"team_key": "x", "display_name": " ", "profile_status": "unknown"},
                         {"team_key": "y", "display_name": "씨", "profile_status": "unknown"}]
        snap = SNAP + [{"team_key": "x", "score": "5"}, {"team_key": "y", "score": "4"}]
        got = build(teams=teams, snapshot=snap)
        self.assertEqual(got.count("씨"), 1)
        self.assertNotIn(" ", got)


class AuditPriorityTest(unittest.TestCase):
    """후보 점검 (b) '기성인데 프로필이 없어 신인으로 잡힘' 팀을 명단 맨 앞(0순위)에 — 첫 발매일로 신인 판정되게."""

    def test_audit_teams_come_first(self):
        self.assertEqual(build(priority=["h", "a"]), ["에이치", "에이", "씨", "디", "에프"])

    def test_priority_team_already_matched_but_without_profile_is_included(self):
        # 멜론 번호는 찾았지만 프로필을 아직 못 받은 팀 → 명단에 넣어야 수집기가 그 프로필을 먼저 받음
        got = build(priority=["h"], matches={"에이치": {"id": "3000001"}, "씨": {"id": "3000002"}}, profiled=set())
        self.assertEqual(got[0], "에이치")
        self.assertNotIn("씨", got)                                   # 0순위가 아닌 팀은 기존 규칙 그대로
        self.assertNotIn("에이치", build(priority=["h"], matches={"에이치": {"id": "3000001"}}, profiled={"3000001"}))

    def test_audit_priority_reads_b_rows_in_rank_order(self):
        rows = [{"type": "b", "rank": "45", "team_key": "모임별"}, {"type": "c", "rank": "3", "team_key": "x"},
                {"type": "b", "rank": "16", "team_key": "검은잎들"}, {"type": "e", "rank": "1", "team_key": "12bh"}]
        self.assertEqual(mn.audit_priority(rows), ["검은잎들", "모임별"])

    def test_latest_audit_file(self):
        with tempfile.TemporaryDirectory() as d:
            for day in ("2026-11-26", "2026-11-27"):
                (Path(d) / f"candidate_audit_{day}.csv").write_text("type,rank,team_key\n", encoding="utf-8")
            self.assertEqual(mn.latest_audit(Path(d)).name, "candidate_audit_2026-11-27.csv")
            self.assertIsNone(mn.latest_audit(Path(d) / "없음"))


class ReleaseOnlyTest(unittest.TestCase):
    """발매 신호만 있고 첫 발매일이 없는 최근 팀 → 상위 후보 다음 순서 (프로필이 쌓이면 '갓 데뷔 > 아직 언급 없음'을 채움)."""
    TEAMS = TEAMS + [{"team_key": k, "display_name": n, "profile_status": "unknown", "first_release": fr} for k, n, fr in [
        ("r1", "알원", ""), ("r2", "알투", ""), ("r3", "알쓰리", ""), ("r4", "알포", "2026-10-01")]]
    SIGNALS = SIGNALS + [
        {"team_key": "r1", "branch": "발매", "signal_date": "2026-11-20"},
        {"team_key": "r2", "branch": "발매", "signal_date": "2026-11-25"},
        {"team_key": "r2", "branch": "발매", "signal_date": "2026-10-01"},
        {"team_key": "r3", "branch": "발매", "signal_date": "2026-05-01"},     # 90일 넘음
        {"team_key": "r4", "branch": "발매", "signal_date": "2026-11-26"},     # 첫 발매일 이미 있음
        {"team_key": "f", "branch": "발매", "signal_date": "2026-11-26"}]      # 공연 신호도 있음 → 발매만 팀 아님

    def test_release_only_recent_teams(self):
        self.assertEqual(mn.release_only_recent(self.SIGNALS, self.TEAMS, "2026-11-27"), ["r2", "r1"])   # 최근 발매 순
        self.assertEqual(mn.release_only_recent(self.SIGNALS, self.TEAMS, "2026-11-27", days=365), ["r2", "r1", "r3"])

    def test_order_after_snapshot_before_outcomes(self):
        got = build(teams=self.TEAMS, signals=self.SIGNALS)
        self.assertEqual(got, ["씨", "에이", "알투", "알원", "디", "에이치", "에프"])

    def test_not_found_recently_is_still_skipped(self):
        got = build(teams=self.TEAMS, signals=self.SIGNALS, matches={"알투": None}, attempts={"알투": "2026-11-20"})
        self.assertNotIn("알투", got)


class NoReleaseTopTest(unittest.TestCase):
    """R3 (2026-11-27 표본 검증): 0순위 다음은 '오늘 후보 상위 100 중 첫 발매일 없는 팀' — 신인 판정이 첫 등장(first_seen)에
    기대는 팀부터 프로필(첫 발매일)을 채운다. newcomer_check 열이 있으면 first_seen·unverified, 없으면 first_release 빈칸."""
    TEAMS = [{"team_key": k, "display_name": n, "profile_status": "unknown", "first_release": fr, **extra}
             for k, n, fr, extra in [
                 ("v", "브이", "2016-01-01", {}),                     # 사람이 확인한 데뷔일로 첫 발매일 있음
                 ("p", "피", "", {}), ("q", "큐", "", {}), ("w", "더블유", "", {}),
                 ("o", "오", "", {})]]
    SNAP = [{"team_key": "v", "score": "10"}, {"team_key": "w", "score": "9"}, {"team_key": "p", "score": "5"},
            {"team_key": "q", "score": "4"}, {"team_key": "o", "score": "1"}]

    def test_no_release_top_uses_first_release_when_no_check_column(self):
        self.assertEqual(mn.no_release_top(self.SNAP, self.TEAMS, top=4), ["w", "p", "q"])   # v는 첫 발매일 있음, o는 상위 4 밖

    def test_no_release_top_uses_newcomer_check_when_present(self):
        teams = [{**t, "newcomer_check": c} for t, c in zip(self.TEAMS, ["verified", "first_seen", "unverified", "verified", "first_seen"])]
        self.assertEqual(mn.no_release_top(self.SNAP, teams, top=4), ["p", "q"])   # 더블유는 verified → 뺌

    def test_no_release_top_comes_right_after_priority(self):
        got = build(snapshot=self.SNAP, teams=self.TEAMS, outcomes=[], signals=[], priority=["o"], candidate_top=4)
        self.assertEqual(got, ["오", "더블유", "피", "큐", "브이"])   # 0순위 → 상위 4 중 첫 발매 없음 → 나머지(점수 순)

    def test_not_found_rule_still_applies_to_new_tier(self):
        got = build(snapshot=self.SNAP, teams=self.TEAMS, outcomes=[], signals=[], candidate_top=4,
                    matches={"피": None}, attempts={"피": "2026-11-20"})
        self.assertNotIn("피", got)


class FileTest(unittest.TestCase):
    def test_latest_snapshot_file(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ("2026-11-20.csv", "2026-11-27.csv", "index.json", "notes.csv"):
                (Path(d) / name).write_text("team_key,score,rank\n", encoding="utf-8")
            self.assertEqual(mn.latest_snapshot(Path(d)).name, "2026-11-27.csv")
            self.assertIsNone(mn.latest_snapshot(Path(d) / "none"))

    def test_prune_keeps_recent_seven(self):
        with tempfile.TemporaryDirectory() as d:
            for i in range(1, 11):
                (Path(d) / f"melon_names_2026-11-{i:02d}.txt").write_text("x", encoding="utf-8")
            (Path(d) / "other.txt").write_text("x", encoding="utf-8")
            removed = mn.prune_old(Path(d), keep=7)
            left = sorted(p.name for p in Path(d).glob("melon_names_*.txt"))
            self.assertEqual(len(removed), 3)
            self.assertEqual(left[0], "melon_names_2026-11-04.txt")
            self.assertTrue((Path(d) / "other.txt").exists())

    def test_write_overwrites(self):
        with tempfile.TemporaryDirectory() as d:
            p = mn.write_names(Path(d), "2026-11-27", ["가", "나"])
            p = mn.write_names(Path(d), "2026-11-27", ["다"])
            self.assertEqual(p.read_text(encoding="utf-8"), "다\n")
            self.assertEqual(p.name, "melon_names_2026-11-27.txt")


if __name__ == "__main__":
    unittest.main()
