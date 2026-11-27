"""same_house: 신호 출처와 정답 프로그램이 같은 집안(같은 주최·같은 매체)일 때, 그 짝 정답을 빼면 성적이 얼마나 바뀌나."""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import same_house as sh  # noqa: E402

PAIR = {"key": "hl_khha", "name": "힙합엘이 ↔ 한국힙합어워즈", "sources": ["큐레이션:hiphople"],
        "outcomes": ["khha_rookie"], "relation": "공동 주최"}


class PairTableTest(unittest.TestCase):
    def test_pairs_are_well_formed(self):
        keys = [p["key"] for p in sh.PAIRS]
        self.assertEqual(len(keys), len(set(keys)))
        for p in sh.PAIRS:
            self.assertTrue(p["sources"] and p["outcomes"] and p["relation"])
            self.assertTrue(all(":" in s for s in p["sources"]))       # '갈래:출처' 키 (config/source_roles.json 과 같은 꼴)


class RelabelTest(unittest.TestCase):
    def setUp(self):
        self.outcomes = {
            "a": [("khha_rookie", date(2025, 3, 1), 2)],                           # 짝 정답만
            "b": [("khha_rookie", date(2025, 3, 1), 2), ("cj_tuneup", date(2025, 6, 1), 3)],
            "c": [("khha_rookie", date(2025, 3, 1), 2)],                           # 출처 신호 없음 → 그대로
        }
        self.sources = {"a": {"큐레이션:hiphople"}, "b": {"큐레이션:hiphople", "공연:indistreet"}, "c": {"공연:indistreet"}}

    def test_label_drops_only_same_house_outcomes_for_teams_with_the_source(self):
        cut = date(2025, 1, 1)
        lab = lambda k, pairs: sh.label(self.outcomes.get(k, []), self.sources.get(k, set()), pairs, cut, 24)  # noqa: E731
        self.assertEqual(lab("a", []), (1, 2))
        self.assertEqual(lab("a", [PAIR]), (0, 0))
        self.assertEqual(lab("b", [PAIR]), (1, 3))                    # 다른 정답(CJ 튠업)은 남음
        self.assertEqual(lab("c", [PAIR]), (1, 2))

    def test_window(self):
        late = {"x": [("cj_tuneup", date(2027, 6, 1), 3)]}
        self.assertEqual(sh.label(late["x"], set(), [], date(2025, 1, 1), 24), (0, 0))   # 관찰 기간 밖


class SourceCardTest(unittest.TestCase):
    def test_rate_lift_and_same_house_share(self):
        # 후보 4팀: a·b 는 출처에 나옴(둘 다 정답, a 는 짝 정답만), c 정답(출처 없음), d 정답 아님
        pool = [{"team_key": k, "cutoff": date(2025, 1, 1)} for k in "abcd"]
        outcomes = {"a": [("khha_rookie", date(2025, 3, 1), 2)],
                    "b": [("cj_tuneup", date(2025, 6, 1), 3)],
                    "c": [("museon_final", date(2025, 6, 1), 2)]}
        srcs = {(date(2025, 1, 1), "a"): {"큐레이션:hiphople"}, (date(2025, 1, 1), "b"): {"큐레이션:hiphople"},
                (date(2025, 1, 1), "c"): set(), (date(2025, 1, 1), "d"): set()}
        card = sh.source_card(pool, outcomes, srcs, PAIR, 24)
        self.assertEqual((card["teams"], card["hits"], card["hits_ex"]), (2, 2, 1))
        self.assertAlmostEqual(card["same_house_share"], 0.5)
        self.assertAlmostEqual(card["rate"], 1.0)
        self.assertAlmostEqual(card["base"], 3 / 4)
        self.assertAlmostEqual(card["base_ex"], 2 / 4)
        self.assertAlmostEqual(card["lift"], 1.0 / 0.75)
        self.assertAlmostEqual(card["lift_ex"], 0.5 / 0.5)


if __name__ == "__main__":
    unittest.main()
