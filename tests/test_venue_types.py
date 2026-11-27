import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import venue_types as vt  # noqa: E402
import venues_kr as vk  # noqa: E402


def v(name, **kw):
    return {"name": name, "aliases": [], "our_names": [], "our_venue": "", "capacity": None,
            "sources": [], "status_note": "", **kw}


CAP = {"venues": {"롤링홀": {"capacity": 450, "standing": 450, "tier": "L"},
                  "Club 빵": {"capacity": 120, "standing": 120, "tier": "S"},
                  "무신사개러지": {"capacity": 900, "standing": 900, "tier": "L"},
                  "어떤 공간": {"capacity": 80, "standing": None, "seats": 80, "tier": "S"}}}


class ClassifyTest(unittest.TestCase):
    def check(self, entry, want_type, basis_has):
        t, basis = vt.classify(entry, CAP)
        self.assertEqual(t, want_type, (entry["name"], basis))
        self.assertIn(basis_has, basis)

    def test_name_rules(self):
        self.check(v("부산음악창작소"), "creation_center", "이름")
        self.check(v("보헤미안 소극장"), "theater", "소극장")
        self.check(v("문씨어터"), "theater", "씨어터")
        self.check(v("아메노히커피점"), "cafe", "커피")
        self.check(v("살롱 문보우"), "cafe", "살롱")
        self.check(v("KINTEX"), "hall", "KINTEX")
        self.check(v("클럽 딥퍼플"), "live_club", "클럽")
        self.check(v("베리어스 재즈클럽"), "live_club", "클럽")
        self.check(v("KT&G 상상마당 춘천 야외공연장"), "festival", "야외")

    def test_main_name_beats_alias_and_live_hall_beats_theater(self):
        self.check(v("공공일클럽", aliases=["001 Live Hall"]), "live_club", "공공일클럽")
        self.check(v("드림씨어터 라이브홀"), "hall", "라이브홀")

    def test_capacity_rules_when_name_says_nothing(self):
        self.check(v("무신사 개러지", our_venue="무신사개러지"), "hall", "900")     # 401명 이상 = 홀
        self.check(v("빵", aliases=["Club 빵"]), "live_club", "클럽")               # 별칭 이름 규칙이 먼저
        self.check(v("마더스 오피스", capacity=150), "live_club", "스탠딩")          # 마스터의 수용 인원(스탠딩 기준)

    def test_seated_small_space_is_not_guessed_as_club(self):
        t, basis = vt.classify(v("어떤 공간"), CAP)
        self.assertEqual(t, "")                     # 좌석 80석만 알면 클럽·카페·소극장을 가를 수 없음
        self.assertEqual(basis, "")

    def test_note_text_counts_as_evidence(self):
        self.check(v("고요의 방", status_note="2026 라랄라온 소공연장"), "", "")  # '소공연장'은 종류를 말해 주지 않음
        e = v("THILA", sources=[{"url": "https://x", "note": "Korea Times — 홍대 라이브클럽 소개"}])
        self.check(e, "live_club", "근거 메모")

    def test_unknown_stays_blank(self):
        self.assertEqual(vt.classify(v("엠피엠지"), CAP), ("", ""))


class ApplyTest(unittest.TestCase):
    def test_researched_type_kept_when_no_new_evidence(self):
        # 이름 짐작(guess_type)으로는 나올 수 없는 값 = 앞선 조사에서 정한 값 → 새 근거가 없으면 지움 대신 유지
        cfg = {"venues": [v("남온 제주", type="cafe", city="서귀포"), v("엠피엠지", type="live_club", city="서울")]}
        new, _ = vt.apply(cfg, CAP)
        self.assertEqual(new["venues"][0]["type"], "cafe")
        self.assertIn("이전 조사", new["venues"][0]["type_basis"])
        self.assertEqual(new["venues"][1]["type"], "")          # live_club 은 이름 짐작의 기본값이라 근거가 아님

    def test_apply_sets_type_and_basis_without_touching_other_fields(self):
        cfg = {"types": dict(vk.TYPES), "venues": [v("부산음악창작소", type="live_club", city="부산"),
                                                     v("엠피엠지", type="live_club", city="서울")]}
        new, changes = vt.apply(cfg, CAP)
        self.assertEqual([e["type"] for e in new["venues"]], ["creation_center", ""])
        self.assertEqual(new["venues"][1]["type_basis"], "")
        self.assertEqual(new["venues"][0]["city"], "부산")
        self.assertEqual(cfg["venues"][0]["type"], "live_club")        # 원본은 그대로
        self.assertEqual(len(changes), 2)
        self.assertIn("theater", new["types"])

    def test_apply_twice_is_stable(self):
        cfg = {"venues": [v("남온 제주", type="cafe", city="서귀포"), v("부산음악창작소", type="live_club", city="부산"),
                          v("엠피엠지", type="live_club", city="서울")]}
        once, _ = vt.apply(cfg, CAP)
        twice, changes = vt.apply(once, CAP)
        self.assertEqual([e["type"] for e in twice["venues"]], ["cafe", "creation_center", ""])
        self.assertEqual(changes, [])

    def test_manual_type_kept(self):
        cfg = {"venues": [v("엠피엠지", type="cafe", type_basis="수동: 공연장 인스타 소개 '카페 겸 공연장'", city="서울")]}
        new, changes = vt.apply(cfg, CAP)
        self.assertEqual(new["venues"][0]["type"], "cafe")
        self.assertEqual(changes, [])


class VenuesKrRulesTest(unittest.TestCase):
    def test_theater_type_known_and_blank_type_allowed(self):
        self.assertIn("theater", vk.TYPES)
        ok = {"name": "A", "city": "서울", "province": "서울", "type": "", "status": "open", "checked": "2026-11-27",
              "sources": [{"url": "https://example.com"}]}
        self.assertEqual(vk.validate({"venues": [ok]}), [])
        self.assertTrue(vk.validate({"venues": [{**ok, "type": "stadium"}]}))

    def test_guess_type_knows_theater(self):
        self.assertEqual(vk.guess_type("보헤미안 소극장"), "theater")


if __name__ == "__main__":
    unittest.main()
