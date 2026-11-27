"""festival_profiles: 국내 페스티벌(부산록페·펜타 슈퍼루키·DMZ 피스트레인 …) 회차별 라인업 프로필."""
import json
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import festival_profiles as fp  # noqa: E402

AS_OF = date(2026, 11, 27)
TEAMS = {"a": "에이", "b": "비", "c": "씨", "d": "디", "e": "이", "n": "엔"}

# 시그널: DMZ 라인업(2024·2025), 부산록페 루키즈(2026, 연말 자리표시 날짜), 일반 공연(먼저 본 팀 판단용)
SIGNALS = [
    {"team_key": "a", "branch": "공연", "source": "indistreet", "program": "", "signal_date": "2023-05-01"},
    {"team_key": "a", "branch": "선정·지원", "source": "dmz", "program": "dmz_lineup", "signal_date": "2024-06-01"},
    {"team_key": "b", "branch": "선정·지원", "source": "dmz", "program": "dmz_lineup", "signal_date": "2024-06-01"},
    {"team_key": "a", "branch": "선정·지원", "source": "dmz", "program": "dmz_lineup", "signal_date": "2025-06-01"},
    {"team_key": "c", "branch": "선정·지원", "source": "dmz", "program": "dmz_lineup", "signal_date": "2025-06-01"},
    {"team_key": "d", "branch": "선정·지원", "source": "busanrock", "program": "burock_rookies",
     "signal_date": "2026-12-31"},
    {"team_key": "n", "branch": "공연", "source": "indistreet", "program": "", "signal_date": "2024-01-01"},
]
# 정답: 부산록페 본무대(2025) · 펜타 슈퍼루키(selected 만 라인업, finalist 는 아님) · 다른 정답
OUTCOMES = [
    {"team_key": "b", "program": "burock_main", "program_label": "부산록페 본무대", "result": "selected",
     "announced_date": date(2025, 8, 29), "counted": True, "grade": "B"},
    {"team_key": "c", "program": "burock_main", "program_label": "부산록페 본무대", "result": "selected",
     "announced_date": date(2025, 8, 29), "counted": True, "grade": "B"},
    {"team_key": "c", "program": "penta_superrookie", "program_label": "펜타포트 슈퍼루키", "result": "finalist",
     "announced_date": date(2025, 6, 9), "counted": True, "grade": "A"},
    {"team_key": "b", "program": "penta_superrookie", "program_label": "펜타포트 슈퍼루키", "result": "winner",
     "announced_date": date(2025, 6, 28), "counted": True, "grade": "A"},
    {"team_key": "b", "program": "hello_rookie_year", "program_label": "올해의 헬로루키", "result": "winner",
     "announced_date": date(2025, 12, 1), "counted": True, "grade": "S"},
    {"team_key": "e", "program": "burock_main", "program_label": "부산록페 본무대", "result": "selected",
     "announced_date": date(2025, 8, 29), "counted": True, "grade": "B"},
    {"team_key": "e", "program": "hello_rookie_year", "program_label": "올해의 헬로루키", "result": "winner",
     "announced_date": date(2025, 12, 1), "counted": True, "grade": "S"},
    {"team_key": "a", "program": "kma_rookie", "program_label": "한대음 올해의 신인", "result": "winner",
     "announced_date": date(2027, 2, 1), "counted": True, "grade": "A"},       # 기준일 뒤 → 안 셈
]
SNAPSHOT = {"a": (5, 6.0), "c": (2, 8.0), "d": (40, 1.0)}


def _build():
    apps = fp.collect_appearances(SIGNALS, OUTCOMES)
    return apps, fp.build_profiles(apps, SIGNALS, OUTCOMES, TEAMS, SNAPSHOT, AS_OF)


class AppearancesTest(unittest.TestCase):
    def test_sources_mapped_to_festivals(self):
        apps, _ = _build()
        got = sorted({(a.festival, a.team, a.day.year) for a in apps})
        self.assertIn(("dmz", "a", 2024), got)
        self.assertIn(("burock_main", "c", 2025), got)
        self.assertIn(("burock_rookies", "d", 2026), got)
        self.assertIn(("penta_superrookie", "b", 2025), got)
        self.assertNotIn(("penta_superrookie", "c", 2025), got)           # finalist 는 무대에 안 섬
        self.assertFalse(any(a.team == "n" for a in apps))                # 일반 공연은 페스티벌 아님

    def test_role_kept(self):
        apps, _ = _build()
        role = {(a.festival, a.team): a.role for a in apps}
        self.assertEqual(role[("penta_superrookie", "b")], "winner")


class EditionTest(unittest.TestCase):
    def setUp(self):
        _, self.p = _build()

    def test_lineup_and_new_to_festival(self):
        dmz = self.p["dmz"]["editions"]
        self.assertEqual(dmz["2024"]["lineup"], 2)
        self.assertEqual(dmz["2025"]["lineup"], 2)
        self.assertAlmostEqual(dmz["2025"]["new_to_festival_share"], 0.5)   # c 만 처음 (a 는 2024에도)
        self.assertAlmostEqual(dmz["2024"]["new_to_festival_share"], 1.0)

    def test_first_festival_share(self):
        dmz = self.p["dmz"]["editions"]
        self.assertAlmostEqual(dmz["2024"]["first_festival_share"], 1.0)    # a·b 둘 다 첫 페스티벌
        self.assertAlmostEqual(dmz["2025"]["first_festival_share"], 0.5)    # c 는 DMZ(06-01)가 첫 — 부산록페(08-29)보다 먼저
        burock = self.p["burock_main"]["editions"]["2025"]
        self.assertAlmostEqual(burock["first_festival_share"], 1 / 3, places=3)        # b·c 는 그 전에 DMZ·펜타, e 만 처음

    def test_seen_before_by_our_other_signals(self):
        dmz = self.p["dmz"]["editions"]
        self.assertAlmostEqual(dmz["2024"]["seen_before_share"], 0.5)       # a 는 2023 공연으로 먼저 봄

    def test_later_winners_respect_as_of_and_exclude_same_house(self):
        dmz24 = self.p["dmz"]["editions"]["2024"]
        names = [w["team_key"] for w in dmz24["later_winners"]]
        # b: DMZ(2024-06) 뒤 첫 센 정답 = 펜타 슈퍼루키 winner(2025-06-28). a 의 정답은 기준일 뒤 → 없음
        self.assertEqual(names, ["b"])
        self.assertEqual(dmz24["later_winners"][0]["outcome"], "펜타포트 슈퍼루키")
        burock = self.p["burock_main"]["editions"]["2025"]
        # 부산록페 본무대 자체가 정답 — 같은 집안(burock_main)은 빼고 본다: e 의 첫 정답 = 헬로루키(2025-12).
        # b 는 부산록페 전에 이미 펜타 슈퍼루키(2025-06)를 받아 '그 뒤 처음 정답'이 아님, c 도 펜타 결선(2025-06)이 먼저
        self.assertEqual([w["team_key"] for w in burock["later_winners"]], ["e"])
        self.assertEqual(burock["later_winners"][0]["outcome"], "올해의 헬로루키")
        self.assertEqual(burock["later_winners_incl_same_house"], 0)        # 같은 집안을 안 빼면 e 의 첫 정답은 부산록페 자체

    def test_upcoming_edition(self):
        rookies = self.p["burock_rookies"]["editions"]["2026"]
        self.assertTrue(rookies["upcoming"])                                 # 2026-12-31 > 기준일
        self.assertEqual(rookies["later_winners"], [])

    def test_top_candidates(self):
        dmz25 = self.p["dmz"]["editions"]["2025"]
        self.assertEqual([t["team_key"] for t in dmz25["top_candidates"]], ["c", "a"])


class SameHouseTest(unittest.TestCase):
    def test_flags(self):
        _, p = _build()
        self.assertTrue(p["burock_main"]["same_house"]["is_outcome"])
        self.assertEqual(p["burock_rookies"]["same_house"]["outcome_programs"], ["burock_main"])
        self.assertIsNone(p["dmz"]["same_house"])


class FlowTest(unittest.TestCase):
    def test_flows_between_festivals(self):
        apps, _ = _build()
        flows = {(f["from"], f["to"]): f for f in fp.festival_flows(apps)}
        self.assertEqual(flows[("dmz", "burock_main")]["teams"], 2)          # b·c: DMZ 먼저, 부산록페 뒤
        self.assertEqual(flows[("dmz", "penta_superrookie")]["teams"], 1)    # b
        self.assertNotIn(("burock_main", "dmz"), flows)

    def test_overlaps_in_profile(self):
        _, p = _build()
        ov = {o["festival"]: o for o in p["dmz"]["overlaps"]}
        self.assertEqual(ov["burock_main"]["teams"], 2)
        self.assertEqual(ov["burock_main"]["this_first"], 2)


class PayloadTest(unittest.TestCase):
    def test_json_and_doc(self):
        apps, prof = _build()
        out = fp.payload(prof, fp.festival_flows(apps), AS_OF)
        json.dumps(out, ensure_ascii=False)
        self.assertEqual(out["as_of"], "2026-11-27")
        md = fp.render_doc(out)
        self.assertIn("같은 집안", md)
        self.assertIn("DMZ 피스트레인", md)


if __name__ == "__main__":
    unittest.main()
