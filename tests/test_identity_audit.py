"""팀 신원 점검(scripts/identity_audit.py): 번호(멜론·스포티파이)·인스타 보유율, 충돌, '번호 먼저' 묶기 시뮬레이션.
artist_xref.py 는 고치지 않고 그 결과(연결표)와 입력(플랫폼 번호 기록)만 읽어 계산한다."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import identity_audit as ia  # noqa: E402


def artists():
    return [
        {"artist_key": "다브다", "display_name": "다브다", "aliases": ["다브다", "Dabda"], "keys": ["dabda", "다브다"],
         "instagram": [{"handle": "dabda_band", "confidence": "high"}], "melon_id": "1001001", "sources": ["gig"]},
        {"artist_key": "dabdaband", "display_name": "dabda band", "aliases": ["dabda band"], "keys": ["dabdaband"],
         "instagram": [], "sources": ["press"]},                                  # 같은 번호 → 합쳐질 팀
        {"artist_key": "공원", "display_name": "공원", "aliases": ["공원"], "keys": ["공원"],
         "instagram": [{"handle": "park_a", "confidence": "mid"}], "melon_id": "2002002", "sources": ["gig"]},  # 번호 2개 → 갈라질 팀
        {"artist_key": "이름만", "display_name": "이름만", "aliases": ["이름만"], "keys": ["이름만"],
         "instagram": [{"handle": "only_low", "confidence": "low"}], "sources": ["gig"]},  # 근거가 이름뿐
        {"artist_key": "쌍둥이a", "display_name": "쌍둥이a", "aliases": ["쌍둥이a"], "keys": ["쌍둥이a"],
         "instagram": [{"handle": "twin", "confidence": "high"}], "sources": ["gig"]},
        {"artist_key": "쌍둥이b", "display_name": "쌍둥이b", "aliases": ["쌍둥이b"], "keys": ["쌍둥이b"],
         "instagram": [{"handle": "twin", "confidence": "mid"}], "sources": ["gig"]},     # 한 계정에 두 팀
    ]


def records():
    return [
        {"name": "다브다", "platform": "melon", "id": "1001001", "confidence": "high"},
        {"name": "Dabda", "platform": "melon", "id": "1001001", "confidence": "high"},   # 묶음을 번호가 확인
        {"name": "dabda band", "platform": "melon", "id": "1001001", "confidence": "high"},
        {"name": "공원", "platform": "melon", "id": "2002002", "confidence": "high"},
        {"name": "공원", "platform": "melon", "id": "3003003", "confidence": "mid"},
        {"name": "공원", "platform": "spotify", "id": "SPX", "confidence": "high"},
        {"name": "여러 아티스트", "platform": "melon", "id": "0", "confidence": "high"},   # 공용 번호
        {"name": "이름만", "platform": "melon", "id": "9009009", "confidence": "high"},   # 차단 번호
        {"name": "없는팀", "platform": "melon", "id": "7007007", "confidence": "high"},   # 연결표에 없는 이름
    ]


CURATION = {"platform_ids": [{"team": "이름만", "platform": "melon", "id": "8008008", "not": ["9009009"]}]}


class UsableRecordsTest(unittest.TestCase):
    def test_drops_shared_and_blocked_ids_and_adds_pins(self):
        recs = ia.usable_records(records(), CURATION)
        ids = {(r["platform"], r["id"]) for r in recs}
        self.assertNotIn(("melon", "0"), ids)
        self.assertNotIn(("melon", "9009009"), ids)
        self.assertIn(("melon", "8008008"), ids)        # 사람이 고정한 번호는 high 로 더함


class MappingTest(unittest.TestCase):
    def setUp(self):
        self.mapped, self.unmapped = ia.map_records(ia.usable_records(records(), CURATION), artists())

    def test_names_map_to_team_keys(self):
        teams = {(m["name"], m["team"]) for m in self.mapped}
        self.assertIn(("Dabda", "다브다"), teams)
        self.assertIn(("dabda band", "dabdaband"), teams)
        self.assertEqual(self.unmapped, 1)               # '없는팀'

    def test_conflicts(self):
        c = ia.id_conflicts(self.mapped)
        self.assertEqual(c["multi_id_teams"]["melon"], {"공원": {"2002002", "3003003"}})
        self.assertEqual(c["multi_team_ids"][("melon", "1001001")], {"다브다", "dabdaband"})

    def test_conflicts_high_only(self):
        c = ia.id_conflicts(self.mapped, min_conf="high")
        self.assertEqual(c["multi_id_teams"]["melon"], {})   # 3003003 은 mid

    def test_id_confirms_name_merge(self):
        # 다브다 묶음(keys 2개)은 두 표기가 같은 멜론 번호 → 번호가 확인
        self.assertEqual(ia.id_confirmed_merges(artists(), self.mapped), {"confirmed": 1, "contradicted": 0, "no_id": 0})

    def test_different_platforms_are_not_a_contradiction(self):
        # 표기 A에 멜론 번호, 표기 B에 스포티파이 번호 → 서로 견줄 수 없음(어긋남 아님)
        arts = [{"artist_key": "x", "keys": ["x", "y"], "aliases": ["x", "y"], "instagram": []}]
        mapped = [{"team": "x", "variant": "x", "platform": "melon", "id": "1", "confidence": "high"},
                  {"team": "x", "variant": "y", "platform": "spotify", "id": "S", "confidence": "high"}]
        self.assertEqual(ia.id_confirmed_merges(arts, mapped), {"confirmed": 0, "contradicted": 0, "no_id": 1})
        mapped[1] = {**mapped[1], "platform": "melon", "id": "2"}
        self.assertEqual(ia.id_confirmed_merges(arts, mapped)["contradicted"], 1)

    def test_short_name_drops_real_name_in_parens(self):
        self.assertEqual(ia.short_name("규리 (KYURI) (김규리)"), "규리")
        self.assertEqual(ia.short_name("다브다"), "다브다")

    def test_paren_only_groups(self):
        display = {"a": "규리", "b": "규리 (KYURI) (김규리)", "c": "WOOD", "d": "우드"}
        self.assertEqual(ia.paren_only_groups([{"a", "b"}, {"c", "d"}], display), 1)

    def test_simulation(self):
        sim = ia.simulate(self.mapped, min_conf="mid")
        self.assertEqual(sim["merge_groups"], [{"dabdaband", "다브다"}])
        self.assertEqual(sim["teams_absorbed"], 1)          # 2팀 → 1팀
        self.assertEqual(sim["split_teams"], {"공원": {"melon": {"2002002", "3003003"}}})
        self.assertEqual(sim["teams_added"], 1)             # 공원 → 2팀


class HoldingTest(unittest.TestCase):
    def test_holding_rates(self):
        h = ia.holding(artists())
        self.assertEqual(h["teams"], 6)
        self.assertEqual(h["melon"], 2)
        self.assertEqual(h["instagram"], 4)                # high·mid 만 (low 제외)
        self.assertEqual(h["any_id"], 4)                   # 번호나 인스타(high·mid) 중 하나라도
        self.assertEqual(h["name_only"], 2)                # dabdaband·이름만: 근거가 이름뿐

    def test_holding_subset(self):
        h = ia.holding(artists(), keys={"다브다", "없음"})
        self.assertEqual((h["teams"], h["melon"], h["missing"]), (1, 1, 1))

    def test_instagram_conflicts(self):
        c = ia.ig_conflicts(artists())
        self.assertEqual(c["multi_team_handles"], {"twin": {"쌍둥이a", "쌍둥이b"}})
        self.assertEqual(c["multi_handle_teams"], {})


class RenderTest(unittest.TestCase):
    def test_render_contains_sections(self):
        mapped, unmapped = ia.map_records(ia.usable_records(records(), CURATION), artists())
        groups = {"전체": None, "후보 상위 300": {"다브다"}, "정답 팀": {"공원"}}
        lines = ia.render(artists(), mapped, unmapped, groups, impact={})
        text = "\n".join(lines)
        for word in ("보유율", "충돌", "번호 먼저", "오류 신고"):
            self.assertIn(word, text)
        self.assertNotIn("/Users/", text)


if __name__ == "__main__":
    unittest.main()
