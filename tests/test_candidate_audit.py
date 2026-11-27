"""후보 점검(candidate_audit): 점수 상위 후보 중 인디 신인 발굴 대상이 아닌 팀을 근거와 함께 찾는다 (제안만)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import candidate_audit as ca  # noqa: E402


class MelonEvidenceTest(unittest.TestCase):
    def test_valid_melon_id(self):
        self.assertTrue(ca.valid_melon_id("2140277"))
        self.assertFalse(ca.valid_melon_id("12"))        # 이름 속 숫자가 번호로 잘못 들어간 경우 (12BH)
        self.assertFalse(ca.valid_melon_id(""))
        self.assertFalse(ca.valid_melon_id("abc"))

    def test_registered_before_cutoff(self):
        self.assertTrue(ca.old_melon_id("454254"))
        self.assertFalse(ca.old_melon_id("3201955"))
        self.assertFalse(ca.old_melon_id("911"))          # 잘못된 번호는 근거로 안 씀

    def test_parse_melon_desc(self):
        d = "아티스트명 딕펑스 대한민국/남성/그룹 음악장르 록/메탈, 인디음악, 국내드라마 곡재생 X 팬 13,222"
        self.assertEqual(ca.parse_desc(d), {"fans": 13222, "genres": ["록/메탈", "인디음악", "국내드라마"], "kind": "남성/그룹"})
        self.assertEqual(ca.parse_desc(""), {"fans": None, "genres": [], "kind": ""})

    def test_album_number_from_titles(self):
        self.assertEqual(ca.max_album_number(["모임 별, 정규 3집 수록 예정 트랙 선공개", "[Single-Out] 「x」"]), 3)
        self.assertEqual(ca.max_album_number(["2nd Album 발매", "4집 리뷰"]), 4)
        self.assertEqual(ca.max_album_number(["첫 EP"]), 0)


class NonTeamTest(unittest.TestCase):
    def test_patterns(self):
        self.assertIn("기획·제작사", ca.nonteam_reason("벙커프로덕션"))
        self.assertIn("계정명", ca.nonteam_reason("nib.archive"))
        self.assertIn("합동", ca.nonteam_reason("팻햄스터&캉뉴"))
        self.assertIn("합동", ca.nonteam_reason("헬리비젼 X 김오키"))
        self.assertEqual(ca.nonteam_reason("공공카펫"), "")
        self.assertEqual(ca.nonteam_reason("D82"), "")
        self.assertEqual(ca.nonteam_reason("Love X Stereo"), "")   # 영문 이름 속 X 는 팀 이름일 수 있음
        self.assertEqual(ca.nonteam_reason("I.M.F"), "")            # 대문자 약자는 계정명이 아님


class AgencyTest(unittest.TestCase):
    def test_agency_blocklist(self):
        self.assertTrue(ca.big_agency("하이브 레이블즈"))
        self.assertTrue(ca.big_agency("(주)SM엔터테인먼트"))
        self.assertFalse(ca.big_agency("매직스트로베리사운드"))
        self.assertFalse(ca.big_agency(""))


class DuplicateTest(unittest.TestCase):
    def test_pairs_by_ids_spelling_and_alias(self):
        rows = [{"team_key": "포스트이너서클", "display_name": "포스트이너서클"},
                {"team_key": "포스트이너써클", "display_name": "포스트이너써클"},
                {"team_key": "밴디츠", "display_name": "밴디츠"}, {"team_key": "bandits", "display_name": "bandits"},
                {"team_key": "공", "display_name": "공"}, {"team_key": "곰", "display_name": "곰"},
                {"team_key": "x1", "display_name": "엑스"}, {"team_key": "x2", "display_name": "와이"}]
        ids = {"x1": {"melon": "3000001"}, "x2": {"melon": "3000001"}}
        aliases = {"밴디츠": ["bandits", "밴디츠"]}
        pairs = {(p["a"], p["b"]): p["reason"] for p in ca.find_duplicates(rows, ids, aliases, cobilled=set())}
        self.assertIn("한 글자", pairs[("포스트이너서클", "포스트이너써클")])
        self.assertIn("별칭", pairs[("bandits", "밴디츠")])
        self.assertIn("멜론", pairs[("x1", "x2")])
        self.assertNotIn(("곰", "공"), pairs)                          # 두 글자 이하 이름은 한 글자 차이로 안 봄

    def test_cobilled_pair_still_reported_with_note(self):
        # 한 공연에 철자만 다르게 두 번 적힌 경우도 있어 '함께 섰으니 다른 팀'으로 단정하지 않고 표시만
        rows = [{"team_key": "포스트이너서클", "display_name": "a"}, {"team_key": "포스트이너써클", "display_name": "b"}]
        out = ca.find_duplicates(rows, {}, {}, cobilled={("포스트이너서클", "포스트이너써클")})
        self.assertEqual(len(out), 1)
        self.assertIn("같은 공연", out[0]["reason"])


class ClassifyTest(unittest.TestCase):
    def test_established_evidence(self):
        cand = {"team_key": "딕펑스", "display_name": "딕펑스", "profile_status": "unknown"}
        out = ca.classify_team(cand, agency="", melon_id="454254", desc="음악장르 록/메탈 곡재생 X 팬 13,222", titles=[])
        kinds = {f["type"] for f in out}
        self.assertEqual(kinds, {"b"})
        self.assertIn("2019년 이전", out[0]["evidence"])
        self.assertIn("팬 13,222", out[0]["evidence"])

    def test_newcomer_profile_is_not_flagged_as_old(self):
        cand = {"team_key": "a", "display_name": "에이", "profile_status": "newcomer"}
        self.assertEqual(ca.classify_team(cand, agency="", melon_id="454254", desc="", titles=[]), [])

    def test_agency_and_nonteam(self):
        cand = {"team_key": "b", "display_name": "벙커프로덕션", "profile_status": "unknown"}
        kinds = {f["type"] for f in ca.classify_team(cand, agency="JYP엔터테인먼트", melon_id="", desc="", titles=[])}
        self.assertEqual(kinds, {"a", "c"})

    def test_bad_melon_id_reported(self):
        cand = {"team_key": "12bh", "display_name": "12BH", "profile_status": "unknown"}
        out = ca.classify_team(cand, agency="", melon_id="12", desc="", titles=[])
        self.assertEqual([f["type"] for f in out], ["e"])


if __name__ == "__main__":
    unittest.main()
