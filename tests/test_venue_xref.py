"""공연장 표기 묶기(venue_xref) 테스트."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import venue_xref as vx  # noqa: E402


class VenueKeyTest(unittest.TestCase):
    def test_club_prefix_korean_and_english(self):
        self.assertEqual(vx.venue_key("Club FF"), vx.venue_key("클럽FF"))
        self.assertEqual(vx.venue_key("Club 빵"), vx.venue_key("클럽 빵"))
        self.assertEqual(vx.venue_key("Club Victim"), vx.venue_key("VICTIM"))

    def test_spacing_and_symbols(self):
        self.assertEqual(vx.venue_key("A.O.R"), vx.venue_key("AOR"))
        self.assertEqual(vx.venue_key("스트레인지 프룻"), vx.venue_key("스트레인지프룻"))

    def test_cafe_prefix_and_branch_suffix(self):
        self.assertEqual(vx.venue_key("카페 언플러그드 홍대점"), vx.venue_key("언플러그드"))

    def test_live_hall_suffix(self):
        self.assertEqual(vx.venue_key("웨스트브릿지 라이브홀"), vx.venue_key("웨스트브릿지"))
        self.assertEqual(vx.venue_key("KT&G 상상마당 홍대 라이브홀"), vx.venue_key("상상마당 홍대 라이브홀"))
        self.assertEqual(vx.venue_key("KT&G상상마당 홍대"), vx.venue_key("상상마당 홍대 라이브홀"))

    def test_floor_written_two_ways(self):
        self.assertEqual(vx.venue_key("상상마당 부산 3층 라이브홀"), vx.venue_key("KT&G 상상마당 부산 3F 라이브홀"))

    def test_generic_name_not_emptied(self):
        # 지점 없는 '라이브홀'은 접미어를 떼면 빈 문자열이 되므로 그대로 둔다
        self.assertEqual(vx.venue_key("라이브홀"), "라이브홀")
        self.assertNotEqual(vx.venue_key("3층 라이브홀"), "")

    def test_different_venues_stay_apart(self):
        self.assertNotEqual(vx.venue_key("언플러그드 라운지"), vx.venue_key("언플러그드"))
        self.assertNotEqual(vx.venue_key("롤링홀"), vx.venue_key("롤러코스터"))

    def test_bilingual_paren(self):
        self.assertEqual(vx.venue_key("클럽 빵 (Club Bbang)"), vx.venue_key("클럽 빵"))

    def test_empty(self):
        self.assertEqual(vx.venue_key(""), "")
        self.assertEqual(vx.venue_key("  "), "")


ALIASES = [
    {"venue": "언플러그드 라운지", "variants": ["카페 언플러그드 홍대점", "언플러그드"], "reason": "같은 곳"},
    {"venue": "채널1969", "variants": ["1969"], "reason": "같은 곳"},
    {"venue": "생기스튜디오", "variants": ["@senggistudio"], "reason": "인스타 계정"},
]


class BuildTest(unittest.TestCase):
    COUNTS = {"Club FF": 1667, "클럽FF": 9, "언플러그드 라운지": 987, "카페 언플러그드 홍대점": 706,
              "언플러그드": 11, "채널1969": 283, "1969": 3, "@senggistudio": 16, "생기스튜디오": 208,
              "라이브홀": 537, "사운드홀": 36, "롤링홀": 166, "공연장 미정": 592, "": 848,
              "웨스트브릿지": 13, "웨스트브릿지 라이브홀": 25, "예스24 라이브홀": 15, "예스24 원더로크홀": 43}

    def setUp(self):
        self.mapping, self.review = vx.build_venue_xref(self.COUNTS, ALIASES)

    def test_key_groups_use_most_common_spelling(self):
        self.assertEqual(self.mapping["클럽FF"], "Club FF")
        self.assertEqual(self.mapping["Club FF"], "Club FF")
        self.assertEqual(self.mapping["웨스트브릿지"], "웨스트브릿지 라이브홀")

    def test_manual_aliases_merge_whole_key_group(self):
        self.assertEqual(self.mapping["카페 언플러그드 홍대점"], "언플러그드 라운지")
        self.assertEqual(self.mapping["언플러그드"], "언플러그드 라운지")
        self.assertEqual(self.mapping["1969"], "채널1969")
        self.assertEqual(self.mapping["@senggistudio"], "생기스튜디오")

    def test_unchanged_names_map_to_themselves(self):
        self.assertEqual(self.mapping["롤링홀"], "롤링홀")

    def test_empty_and_undecided_left_out(self):
        self.assertNotIn("", self.mapping)
        self.assertNotIn("공연장 미정", self.mapping)

    def test_generic_names_kept_and_reviewed(self):
        self.assertEqual(self.mapping["라이브홀"], "라이브홀")
        self.assertTrue(any(r["kind"] == "generic" and r["name"] == "라이브홀" for r in self.review))

    def test_similar_but_unmerged_pairs_reviewed(self):
        # '예스24 라이브홀' → 키 '예스24', '예스24 원더로크홀' → '예스24원더로크홀': 포함 관계라 사람이 확인
        self.assertNotEqual(self.mapping["예스24 라이브홀"], self.mapping["예스24 원더로크홀"])
        self.assertTrue(any(r["kind"] == "contains" and "예스24 원더로크홀" in r["names"] for r in self.review))

    def test_branchless_chain_name_is_generic(self):
        # 'KT&G 상상마당 라이브홀'은 홍대·부산·춘천 중 어디인지 모름
        self.assertTrue(vx.is_generic("KT&G 상상마당 라이브홀"))
        self.assertFalse(vx.is_generic("KT&G 상상마당 홍대 라이브홀"))

    def test_generic_names_not_used_for_contains_review(self):
        mapping, review = vx.build_venue_xref({"아트홀": 12, "예림당아트홀": 1, "하멜아트홀": 1}, [])
        self.assertFalse(any(r["kind"] == "contains" for r in review))

    def test_alias_variant_not_seen_is_ignored(self):
        mapping, _ = vx.build_venue_xref({"롤링홀": 5}, ALIASES)
        self.assertEqual(mapping, {"롤링홀": "롤링홀"})


class AddressTest(unittest.TestCase):
    def test_road_address_key(self):
        self.assertEqual(vx.address_key("서울 마포구 와우산로29길 12 지하1층"), vx.address_key("서울 마포구 와우산로29길 12)"))
        self.assertNotEqual(vx.address_key("서울 마포구 와우산로29길 15 2층"), vx.address_key("서울 마포구 와우산로33길 26 1층"))
        self.assertEqual(vx.address_key(""), "")

    def test_gig_address(self):
        self.assertEqual(vx.gig_address("Club FF (서울 마포구 와우산로17길 12)"), "서울 마포구 와우산로17길 12")
        self.assertEqual(vx.gig_address("라이브홀"), "")

    def test_alias_with_different_address_is_not_merged(self):
        # 실제 사례: '언플러그드 라운지'(와우산로29길 15)와 '카페 언플러그드 홍대점'(와우산로33길 26)은 다른 곳
        counts = {"언플러그드 라운지": 10, "카페 언플러그드 홍대점": 7}
        addrs = {"언플러그드 라운지": "서울 마포구 와우산로29길 15 2층", "카페 언플러그드 홍대점": "서울 마포구 와우산로33길 26 1층"}
        aliases = [{"venue": "언플러그드 라운지", "variants": ["카페 언플러그드 홍대점"], "reason": "x"}]
        mapping, review = vx.build_venue_xref(counts, aliases, addrs)
        self.assertEqual(mapping["카페 언플러그드 홍대점"], "카페 언플러그드 홍대점")
        self.assertTrue(any(r["kind"] == "address_conflict" for r in review))

    def test_same_address_different_names_reviewed(self):
        counts = {"채널1969": 10, "Channel 1969": 2}
        addrs = {"채널1969": "서울 마포구 연희로 35", "Channel 1969": "서울 마포구 연희로 35)"}
        _, review = vx.build_venue_xref(counts, [], addrs)
        self.assertTrue(any(r["kind"] == "same_address" for r in review))


class PgTest(unittest.TestCase):
    def test_rows_sorted_unique(self):
        rows = vx.xref_rows({"b": "B", "a": "A"})
        self.assertEqual(rows, [("a", "A"), ("b", "B")])

    def test_script_truncates_not_drops(self):
        s = vx.pg_load_script("/tmp/v.csv")
        self.assertNotIn("DROP TABLE", s)
        self.assertIn("CREATE TABLE IF NOT EXISTS ref.venue_xref (variant text PRIMARY KEY, venue text", s)
        self.assertIn("TRUNCATE ref.venue_xref", s)
        self.assertLess(s.index("BEGIN"), s.index("TRUNCATE"))
        self.assertLess(s.index("\\copy ref.venue_xref FROM '/tmp/v.csv'"), s.index("COMMIT"))

    def test_load_pg_skips_without_psql(self):
        self.assertIn("건너뜀", vx.load_pg({}, psql_path="/nonexistent/psql"))


class BranchInParenTest(unittest.TestCase):
    """'라이브홀 (KT&G 상상마당 홍대)'처럼 지점이 괄호에 있으면 괄호 앞만 남길 때 지점이 사라진다 → '건물 + 홀'로."""

    def test_branch_in_paren_moves_to_front(self):
        cases = {
            "라이브홀 (KT&G 상상마당 홍대)": "KT&G 상상마당 홍대 라이브홀",
            "3층 라이브홀 (KT&G 상상마당 부산)": "KT&G 상상마당 부산 3층 라이브홀",
            "3F 라이브홀 (KT&G 상상마당 부산)": "KT&G 상상마당 부산 3F 라이브홀",
            "사운드홀 (KT&G 상상마당 춘천)": "KT&G 상상마당 춘천 사운드홀",
            "아트홀 (KT&G 상상마당 대치)": "KT&G 상상마당 대치 아트홀",
            "KT&G 상상마당 라이브홀 (KT&G 상상마당 홍대)": "KT&G 상상마당 홍대 라이브홀",
            "라이브 스튜디오 (KT&G 상상마당 춘천아트센터)": "KT&G 상상마당 춘천아트센터 라이브 스튜디오",
            "라이브홀 (KT&amp;G 상상마당 부산)": "KT&G 상상마당 부산 라이브홀",
        }
        for raw, want in cases.items():
            self.assertEqual(vx.canonical_venue_text(raw), want, raw)
            self.assertEqual(vx.gig_detail(raw), want, raw)

    def test_address_parens_and_new_format_unchanged(self):
        for raw in ("Club FF (서울 마포구 와우산로 1)", "KT&G 상상마당 홍대 라이브홀", "롤링홀", "",
                    "라이브홀 (부산 부산진구 서면로 39)"):
            self.assertEqual(vx.canonical_venue_text(raw), raw)
        self.assertEqual(vx.gig_detail("Club FF (서울 마포구 와우산로 1)"), "Club FF")

    def test_idempotent(self):
        once = vx.canonical_venue_text("라이브홀 (KT&G 상상마당 홍대)")
        self.assertEqual(vx.canonical_venue_text(once), once)

    def test_same_hall_different_buildings_stay_apart(self):
        names = {vx.gig_detail("라이브홀 (KT&G 상상마당 홍대)"): 544, vx.gig_detail("라이브홀 (KT&G 상상마당 부산)"): 1,
                 "웨스트브릿지 라이브홀": 10, "라이브홀": 3}
        mapping, _ = vx.build_venue_xref(names, [])
        self.assertNotEqual(mapping["KT&G 상상마당 홍대 라이브홀"], mapping["KT&G 상상마당 부산 라이브홀"])
        self.assertNotEqual(mapping["KT&G 상상마당 홍대 라이브홀"], mapping["웨스트브릿지 라이브홀"])
        self.assertEqual(mapping["라이브홀"], "라이브홀")   # 지점 없는 단독 이름은 어디에도 붙이지 않음

    def test_merges_with_existing_spellings(self):
        names = {vx.gig_detail("라이브홀 (KT&G 상상마당 홍대)"): 544, "KT&G 상상마당 홍대 라이브홀": 41,
                 "상상마당 홍대 라이브홀": 18}
        mapping, _ = vx.build_venue_xref(names, [])
        self.assertEqual(len(set(mapping.values())), 1)

    def test_repo_aliases_join_busan_and_chuncheon_halls(self):
        names = {"KT&G 상상마당 부산 라이브홀": 22, "KT&G 상상마당 부산 3층 라이브홀": 51, "상상마당 부산 3층 라이브홀": 9,
                 "KT&G 상상마당 춘천 사운드홀": 51, "KT&G 상상마당 춘천 아트센터 사운드홀": 5,
                 "KT&G 상상마당 춘천 사운드홀 로비": 37}
        mapping, _ = vx.build_venue_xref(names, vx.load_aliases())
        self.assertEqual(mapping["KT&G 상상마당 부산 3층 라이브홀"], mapping["KT&G 상상마당 부산 라이브홀"])
        self.assertEqual(mapping["KT&G 상상마당 춘천 아트센터 사운드홀"], mapping["KT&G 상상마당 춘천 사운드홀"])
        self.assertNotEqual(mapping["KT&G 상상마당 춘천 사운드홀 로비"], mapping["KT&G 상상마당 춘천 사운드홀"])


class ChuncheonSpacesTest(unittest.TestCase):
    """상상마당 춘천 세부 공간을 공연장 목록(config/venues_kr.json)의 세 곳 — 사운드홀 · 야외공연장 · 건물(그 밖의 공간) — 으로."""

    NAMES = {"KT&G 상상마당 춘천 사운드홀": 51, "상상마당 춘천 사운드홀": 8, "KT&G 상상마당 춘천 아트센터 사운드홀": 5,
             "상상마당춘천 아트센터 사운드홀": 1,
             "KT&G 상상마당 춘천 야외공연장": 6, "KT&G 상상마당 춘천 아트센터 야외무대 일대": 1,
             "KT&G 상상마당 춘천": 12, "KT&G 상상마당 춘천 사운드홀 로비": 38, "KT&G 상상마당 춘천 구름다리": 6,
             "KT&G 상상마당 춘천 A동 로비": 1, "KT&G 상상마당 춘천 아트센터 B동": 1,
             "KT&G 상상마당 춘천아트센터 라이브 스튜디오": 3, "KT&G 상상마당 춘천 라이브스튜디오": 1,
             "KT&G 상상마당 춘천 아트센터&스테이": 1}

    def test_three_places(self):
        mapping, _ = vx.build_venue_xref(self.NAMES, vx.load_aliases())
        groups = {}
        for name, rep in mapping.items():
            groups.setdefault(rep, set()).add(name)
        self.assertEqual(set(groups), {"KT&G 상상마당 춘천 사운드홀", "KT&G 상상마당 춘천 야외공연장", "KT&G 상상마당 춘천"})
        self.assertIn("KT&G 상상마당 춘천 사운드홀 로비", groups["KT&G 상상마당 춘천"])      # 로비는 사운드홀이 아님
        self.assertIn("KT&G 상상마당 춘천 아트센터 야외무대 일대", groups["KT&G 상상마당 춘천 야외공연장"])

    def test_other_branches_untouched(self):
        names = {**self.NAMES, "KT&G 상상마당 홍대 라이브홀": 400, "KT&G 상상마당 부산 3층 라이브홀": 80}
        mapping, _ = vx.build_venue_xref(names, vx.load_aliases())
        self.assertEqual(mapping["KT&G 상상마당 홍대 라이브홀"], "KT&G 상상마당 홍대 라이브홀")
        self.assertEqual(mapping["KT&G 상상마당 부산 3층 라이브홀"], "KT&G 상상마당 부산 3층 라이브홀")


class DetailTest(unittest.TestCase):
    def test_detail_like_sql(self):
        # SQL: TRIM(split_part(venue_text, ' (', 1)) 과 같은 값
        self.assertEqual(vx.gig_detail("Club FF (서울 마포구 ...)"), "Club FF")
        self.assertEqual(vx.gig_detail(" 라이브홀 "), "라이브홀")
        self.assertEqual(vx.gig_detail("A&amp;B 홀 (주소)"), "A&B 홀")


class InstaHandleTest(unittest.TestCase):
    """인스타 공연장 계정의 라인업 공지는 공연장 칸에 '@계정'이 들어온다 → config/venues_kr.json instagram 칸으로
    공연장 이름에 묶는다(원본은 그대로, 연결표에서만). 공연장 계정이 아닌 '@계정'(기획사·레이블)은 그대로 둔다."""

    MASTER = {"venues": [
        {"name": "오방가르드", "instagram": "ovantgarde", "our_venue": "오방가르드"},
        {"name": "A.O.R", "instagram": "ClubAOR", "our_venue": ""},          # 우리 데이터에 대표 이름이 없어도 마스터 이름으로
        {"name": "계정 없는 곳"},
    ]}

    def _aliases(self, master):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "venues_kr.json"
            path.write_text(json.dumps(master, ensure_ascii=False), encoding="utf-8")
            return vx.insta_venue_aliases(path)

    def test_rules_from_master_instagram_field(self):
        rules = self._aliases(self.MASTER)
        self.assertEqual([(r["venue"], r["variants"]) for r in rules],
                         [("오방가르드", ["@ovantgarde"]), ("A.O.R", ["@clubaor"])])
        self.assertTrue(all(r["reason"] for r in rules))

    def test_handle_mapped_and_merged_with_venue_name(self):
        counts = {"오방가르드": 235, "@ovantgarde": 12, "@clubaor": 3, "@delay_relay": 66}
        mapping, _ = vx.build_venue_xref(counts, self._aliases(self.MASTER))
        self.assertEqual(mapping["@ovantgarde"], "오방가르드")
        self.assertEqual(mapping["@clubaor"], "A.O.R")               # 대표 이름이 데이터에 없어도 계정 → 공연장 이름
        self.assertEqual(mapping["@delay_relay"], "@delay_relay")      # 공연장 계정이 아니면 그대로
        self.assertEqual(mapping["오방가르드"], "오방가르드")

    def test_manual_rule_wins_over_master(self):
        counts = {"Club FF": 100, "@hongdaeff": 5}
        manual = [{"venue": "Club FF", "variants": ["@hongdaeff"], "reason": "수동"}]
        auto = self._aliases({"venues": [{"name": "클럽 FF", "instagram": "hongdaeff", "our_venue": ""}]})
        mapping, review = vx.build_venue_xref(counts, manual + auto)
        self.assertEqual(mapping["@hongdaeff"], "Club FF")

    def test_shared_handle_is_ambiguous_and_skipped(self):
        """한 계정을 여러 공연장(같은 건물의 여러 홀)이 같이 쓰면 어느 홀인지 몰라 규칙을 만들지 않는다 —
        만들면 그 계정을 통해 서로 다른 홀이 한 묶음으로 합쳐진다."""
        master = {"venues": [{"name": "센터 사운드홀", "instagram": "center"}, {"name": "센터 야외무대", "instagram": "Center"},
                             {"name": "오방가르드", "instagram": "ovantgarde"}]}
        rules = self._aliases(master)
        self.assertEqual([r["venue"] for r in rules], ["오방가르드"])
        counts = {"센터 사운드홀": 50, "센터 야외무대": 20, "@center": 4}
        mapping, _ = vx.build_venue_xref(counts, rules)
        self.assertEqual(mapping["센터 사운드홀"], "센터 사운드홀")
        self.assertEqual(mapping["센터 야외무대"], "센터 야외무대")
        self.assertEqual(mapping["@center"], "@center")

    def test_missing_master_is_empty(self):
        self.assertEqual(vx.insta_venue_aliases(Path("/nonexistent/venues_kr.json")), [])


if __name__ == "__main__":
    unittest.main()
