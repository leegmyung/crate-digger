"""아티스트 연결표(artist_xref) 테스트 — 칸 나누기·같은 팀 다른 표기 묶기·인스타 계정 연결."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import artist_xref as ax  # noqa: E402


class SplitCellTest(unittest.TestCase):
    def test_single_name_untouched(self):
        r = ax.split_cell("다다다")
        self.assertEqual(r["parts"], ["다다다"])
        self.assertEqual(r["status"], "single")

    def test_comma_list_of_korean_names_split(self):
        r = ax.split_cell("박수정, 김민지")
        self.assertEqual(r["parts"], ["박수정", "김민지"])
        self.assertEqual(r["status"], "split")

    def test_comma_without_space(self):
        self.assertEqual(ax.split_cell("장희원,윤덕호")["parts"], ["장희원", "윤덕호"])

    def test_collab_x_split_when_korean(self):
        r = ax.split_cell("씨피카 X 김도언 X 낸시보이")
        self.assertEqual(r["parts"], ["씨피카", "김도언", "낸시보이"])
        self.assertEqual(r["status"], "split")

    def test_latin_comma_band_name_kept_as_ambiguous(self):
        r = ax.split_cell("Black Country, New Road")
        self.assertEqual(r["parts"], ["Black Country, New Road"])
        self.assertEqual(r["status"], "ambiguous")

    def test_latin_x_band_name_kept(self):
        r = ax.split_cell("Love X Stereo")
        self.assertEqual(r["parts"], ["Love X Stereo"])
        self.assertEqual(r["status"], "ambiguous")

    def test_ampersand_kept_and_flagged(self):
        r = ax.split_cell("Sweet & light")
        self.assertEqual(r["parts"], ["Sweet & light"])
        self.assertEqual(r["status"], "ambiguous")
        r2 = ax.split_cell("팻햄스터&캉뉴")
        self.assertEqual(r2["parts"], ["팻햄스터&캉뉴"])
        self.assertEqual(r2["status"], "ambiguous")

    def test_team_with_member_list_keeps_team(self):
        r = ax.split_cell("뱃사공(수림, 백찬영)")
        self.assertEqual(r["parts"], ["뱃사공"])
        self.assertEqual(r["related"], ["수림", "백찬영"])
        self.assertEqual(r["status"], "team_with_members")

    def test_member_list_with_middle_dot(self):
        r = ax.split_cell("메킷레인(루피·나플라·오왼 오바도즈·블루·영웨스트)")
        self.assertEqual(r["parts"], ["메킷레인"])
        self.assertEqual(len(r["related"]), 5)

    def test_others_count_is_partial(self):
        r = ax.split_cell("이차형 외 2명")
        self.assertEqual(r["parts"], ["이차형"])
        self.assertEqual(r["status"], "partial")

    def test_bilingual_slash_is_one_team(self):
        r = ax.split_cell("디아틱 / The ATIC")
        self.assertEqual(r["parts"], ["디아틱 / The ATIC"])
        self.assertEqual(r["status"], "bilingual")

    def test_bilingual_paren_alias_is_single(self):
        r = ax.split_cell("피치 트럭 하이재커스(Peach Truck Hijackers)")
        self.assertEqual(r["status"], "single")

    def test_empty(self):
        self.assertEqual(ax.split_cell("")["parts"], [])


class ParseNameTest(unittest.TestCase):
    def test_paren_alias(self):
        self.assertEqual(ax.parse_name("피치 트럭 하이재커스(Peach Truck Hijackers)"),
                         ("피치 트럭 하이재커스", ["Peach Truck Hijackers"]))

    def test_english_main_korean_alias(self):
        self.assertEqual(ax.parse_name("Aden (에이든)"), ("Aden", ["에이든"]))

    def test_slash_bilingual(self):
        self.assertEqual(ax.parse_name("디아틱 / The ATIC"), ("디아틱", ["The ATIC"]))

    def test_same_script_paren_not_alias(self):
        main, aliases = ax.parse_name("박혜리(정원영밴드)")
        self.assertEqual(aliases, [])

    def test_one_letter_latin_not_alias(self):
        # 'G(라이엇키즈)' = 라이엇키즈 멤버 G. 한 글자 영문은 별칭으로 보지 않는다
        self.assertEqual(ax.parse_name("G(라이엇키즈)")[1], [])

    def test_digits_paren_not_alias(self):
        self.assertEqual(ax.parse_name("정용찬 (01)")[1], [])

    def test_html_entity_and_fullwidth(self):
        self.assertEqual(ax.canonical_key("a&amp;b"), ax.canonical_key("a&b"))
        self.assertEqual(ax.canonical_key("그＿냥"), ax.canonical_key("그냥"))


class CanonicalKeyTest(unittest.TestCase):
    def test_matches_normalize_artist_key_without_index(self):
        self.assertEqual(ax.canonical_key("피치 트럭 하이재커스(Peach Truck Hijackers)"), "피치트럭하이재커스")
        self.assertEqual(ax.canonical_key("다브다 (Dabda)"), "다브다")

    def test_slash_bilingual_uses_first_part(self):
        self.assertEqual(ax.canonical_key("디아틱 / The ATIC"), "디아틱")

    def test_index_maps_english_spelling_to_group(self):
        index = {"by_key": {"peachtruckhijackers": "피치트럭하이재커스"}}
        self.assertEqual(ax.canonical_key("Peach Truck Hijackers", index), "피치트럭하이재커스")
        self.assertEqual(ax.canonical_key("모르는팀", index), "모르는팀")


class ScriptBlocksTest(unittest.TestCase):
    def test_latin_then_hangul(self):
        self.assertEqual(ax.split_script_blocks("Confined White 컨파인드 화이트"),
                         ["Confined White", "컨파인드 화이트"])

    def test_single_script(self):
        self.assertEqual(ax.split_script_blocks("Waking Suns"), ["Waking Suns"])

    def test_bracketed_part(self):
        self.assertIn("스튜디오360 경음악단", ax.split_script_blocks("studio360 group [스튜디오360 경음악단]"))


class HandleTest(unittest.TestCase):
    def test_handle_core_strips_noise(self):
        self.assertEqual(ax.handle_core("@confinedwhite_official"), "confinedwhite")
        self.assertEqual(ax.handle_core("adoyband"), "adoy")
        self.assertEqual(ax.handle_core("fleet_official_"), "fleet")

    def test_caption_name_before_handle(self):
        cap = "[VOL 131] Rising Artist * 샐리에브리웨어(sally everywhere) @sally_everywhere_ 삶의"
        self.assertEqual(ax.caption_name_for_handle(cap, "sally_everywhere_"), "샐리에브리웨어(sally everywhere)")

    def test_caption_dash_title_pattern(self):
        cap = "Sarah Julia - Bigger Picture 요즘처럼 쌀쌀해진 날씨에"
        self.assertEqual(ax.caption_name_for_handle(cap, "sarahjulia", single_tag=True), "Sarah Julia")

    def test_caption_dash_needs_single_tag(self):
        cap = "Television off - เปลืองน้ำตา | Can’t complain"
        self.assertEqual(ax.caption_name_for_handle(cap, "smallroommusic", single_tag=False), "")


class BuildXrefTest(unittest.TestCase):
    def _names(self):
        return [
            {"table": "gig", "name": "피치트럭하이재커스", "count": 12},
            {"table": "outcome", "name": "피치 트럭 하이재커스(Peach Truck Hijackers)", "count": 1},
            {"table": "press", "name": "Peach Truck Hijackers", "count": 2},
            {"table": "gig", "name": "컨파인드화이트", "count": 20},
            {"table": "selection", "name": "박수정, 김민지", "count": 1},
            # 같은 영문 별칭이 서로 다른 두 한글 팀에 붙으면 묶지 않는다
            {"table": "release", "name": "가나 (ABC)", "count": 1},
            {"table": "release", "name": "다라 (ABC)", "count": 1},
        ]

    def test_groups_bilingual_spellings(self):
        artists, review = ax.build_xref(self._names(), ig_profiles=[], ig_posts=[], platform_ids=[])
        by_key = {a["artist_key"]: a for a in artists}
        peach = by_key["피치트럭하이재커스"]
        self.assertIn("Peach Truck Hijackers", peach["aliases"])
        self.assertEqual(peach["display_name"], "피치트럭하이재커스")
        self.assertEqual(sorted(peach["sources"]), ["gig", "outcome", "press"])

    def test_selection_cell_split_into_people(self):
        artists, _ = ax.build_xref(self._names(), [], [], [])
        keys = {a["artist_key"] for a in artists}
        self.assertIn("박수정", keys)
        self.assertIn("김민지", keys)
        self.assertNotIn("박수정김민지", keys)

    def test_conflicting_alias_not_merged_and_reported(self):
        artists, review = ax.build_xref(self._names(), [], [], [])
        keys = {a["artist_key"] for a in artists}
        self.assertIn("가나", keys)
        self.assertIn("다라", keys)
        self.assertTrue(any(r["kind"] == "alias_conflict" and "abc" in r["detail"] for r in review))

    def test_instagram_link_high_when_name_and_handle_agree(self):
        ig_profiles = [{"handle": "confinedwhite_official", "name": "Confined White 컨파인드 화이트",
                        "source": "ig_artist_links"}]
        artists, _ = ax.build_xref(self._names(), ig_profiles, [], [])
        cw = {a["artist_key"]: a for a in artists}["컨파인드화이트"]
        self.assertEqual(cw["instagram"][0]["handle"], "confinedwhite_official")
        self.assertEqual(cw["instagram"][0]["confidence"], "high")
        self.assertTrue(cw["instagram"][0]["evidence"])

    def test_instagram_only_artist_is_low(self):
        ig_profiles = [{"handle": "wakingsuns.seoul", "name": "Waking Suns", "source": "ig_artist_links"}]
        artists, _ = ax.build_xref(self._names(), ig_profiles, [], [])
        ws = {a["artist_key"]: a for a in artists}["wakingsuns"]
        self.assertEqual(ws["instagram"][0]["confidence"], "low")
        self.assertEqual(ws["confidence"], "low")

    def test_caption_evidence_links_handle(self):
        posts = [{"handle": "sally_everywhere_", "caption": "Rising Artist * 샐리에브리웨어(sally everywhere) @sally_everywhere_ 삶",
                  "url": "https://www.instagram.com/x/p/1/", "single_tag": True}]
        names = self._names() + [{"table": "gig", "name": "샐리에브리웨어", "count": 3}]
        artists, _ = ax.build_xref(names, [], posts, [])
        s = {a["artist_key"]: a for a in artists}["샐리에브리웨어"]
        self.assertEqual(s["instagram"][0]["handle"], "sally_everywhere_")
        self.assertIn(s["instagram"][0]["confidence"], ("high", "mid"))
        self.assertIn("sally everywhere", s["aliases"])

    def test_group_confidence_stays_high_when_bilingual_cell_exists(self):
        names = self._names() + [{"table": "outcome", "name": "컨파인드 화이트(Confined White)", "count": 1}]
        ig = [{"handle": "confinedwhite_official", "name": "Confined White 컨파인드 화이트", "source": "x"}]
        artists, _ = ax.build_xref(names, ig, [], [])
        self.assertEqual({a["artist_key"]: a for a in artists}["컨파인드화이트"]["confidence"], "high")

    def test_two_handles_on_one_team_reported(self):
        ig = [{"handle": "confinedwhite_official", "name": "컨파인드 화이트", "source": "x"},
              {"handle": "cw_other", "name": "컨파인드화이트", "source": "x"}]
        _, review = ax.build_xref(self._names(), ig, [], [])
        self.assertTrue(any(r["kind"] == "ig_multiple_handles" for r in review))

    def test_email_like_handle_ignored(self):
        posts = [{"handle": "gmail.com", "caption": "문의 abc@gmail.com", "url": "u", "single_tag": True}]
        artists, review = ax.build_xref(self._names(), [], posts, [])
        self.assertFalse(any(i["handle"] == "gmail.com" for a in artists for i in a["instagram"]))

    def test_platform_ids_attached(self):
        ids = [{"name": "피치트럭하이재커스", "platform": "melon", "id": "123", "confidence": "high"},
               {"name": "Peach Truck Hijackers", "platform": "spotify", "id": "abc", "confidence": "mid"}]
        artists, _ = ax.build_xref(self._names(), [], [], ids)
        peach = {a["artist_key"]: a for a in artists}["피치트럭하이재커스"]
        self.assertEqual(peach["melon_id"], "123")
        self.assertEqual(peach["spotify_id"], "abc")

    def test_two_melon_ids_reported(self):
        ids = [{"name": "컨파인드화이트", "platform": "melon", "id": "1", "confidence": "high"},
               {"name": "컨파인드 화이트", "platform": "melon", "id": "2", "confidence": "high"}]
        _, review = ax.build_xref(self._names(), [], [], ids)
        self.assertTrue(any(r["kind"] == "multiple_platform_ids" for r in review))


class BacktraceCasesTest(unittest.TestCase):
    """backtrace에서 두 줄로 갈라졌던 실제 사례 (코디네이터 요청)."""

    def test_backtrace_pairs_merge(self):
        names = [
            {"table": "outcome", "name": "피치 트럭 하이재커스(Peach Truck Hijackers)", "count": 1},
            {"table": "outcome", "name": "Peach Truck Hijackers", "count": 1},
            {"table": "outcome", "name": "컨파인드 화이트(Confined White)", "count": 1},
            {"table": "outcome", "name": "컨파인드 화이트", "count": 3},
            {"table": "press", "name": "Confined White", "count": 1},
        ]
        artists, _ = ax.build_xref(names, [], [], [])
        self.assertEqual(len(artists), 2)
        index = ax.index_from_artists(artists)
        self.assertEqual(ax.canonical_key("Peach Truck Hijackers", index),
                         ax.canonical_key("피치 트럭 하이재커스(Peach Truck Hijackers)", index))
        self.assertEqual(ax.canonical_key("Confined White", index), ax.canonical_key("컨파인드 화이트", index))


class OutcomeLinkTest(unittest.TestCase):
    def test_outcome_signal_link_rate(self):
        names = [
            {"table": "outcome", "name": "피치 트럭 하이재커스(Peach Truck Hijackers)", "count": 1},
            {"table": "press", "name": "Peach Truck Hijackers", "count": 1},  # 영문 표기로만 신호 → 묶여서 연결
            {"table": "outcome", "name": "혼자팀", "count": 1},               # 신호 없음
            {"table": "gig", "name": "공연팀", "count": 1},
        ]
        artists, _ = ax.build_xref(names, [], [], [])
        stats = ax.outcome_signal_link(artists)
        self.assertEqual(stats["outcome_teams"], 2)
        self.assertEqual(stats["linked_teams"], 1)
        self.assertEqual(stats["linked_only_by_xref"], 1)


class PgRowsTest(unittest.TestCase):
    def test_variant_rows_cover_db_keys(self):
        artists, _ = ax.build_xref([
            {"table": "gig", "name": "디아틱 / The ATIC", "count": 2},
            {"table": "outcome", "name": "피치 트럭 하이재커스(Peach Truck Hijackers)", "count": 1},
        ], [], [], [])
        rows = {r[0]: r for r in ax.xref_rows(artists)}
        self.assertEqual(rows["디아틱theatic"][1], "디아틱")        # load_pg 의 예전 artist_key
        self.assertEqual(rows["peachtruckhijackers"][1], "피치트럭하이재커스")  # load_pg 의 alias_key
        self.assertEqual(len(rows), len(ax.xref_rows(artists)))  # variant_key 중복 없음

    def test_linked_instagram_handles_become_variant_keys(self):
        # 인스타 게시물에서 이름 대신 계정명만 잡힌 줄('oysters.999')도 그 팀으로 묶이게
        artists = [{"artist_key": "오이스터즈", "display_name": "오이스터즈", "keys": ["오이스터즈"], "aliases": [],
                    "confidence": "high",
                    "instagram": [{"handle": "oysters.999", "confidence": "high"},
                                  {"handle": "maybe_other", "confidence": "low"}]},
                   {"artist_key": "다른팀", "display_name": "다른팀", "keys": ["다른팀", "oysters999"], "aliases": [],
                    "confidence": "high", "instagram": []}]
        rows = {r[0]: r for r in ax.xref_rows(artists)}
        self.assertEqual(rows["oysters999"][1], "다른팀")        # 이미 다른 팀 이름 키면 계정명이 덮어쓰지 않음
        self.assertNotIn("maybeother", rows)                     # 확신 낮은 계정은 안 넣음
        rows2 = {r[0]: r for r in ax.xref_rows(artists[:1])}
        self.assertEqual(rows2["oysters999"][1], "오이스터즈")

    def test_tracked_accounts_are_marked_non_artist_without_overriding_teams(self):
        # 매거진·공연장·기관 계정명은 '팀 아님'으로 → 신호에서 빠진다. 실제 팀 이름 키는 덮어쓰지 않는다.
        artists = [{"artist_key": "클럽에프에프", "display_name": "클럽에프에프", "keys": ["clubffhongdae"],
                    "aliases": [], "confidence": "high", "instagram": []}]
        rows = {r[0]: r for r in ax.xref_rows(artists, non_artist_handles=["@kocca_official", "clubff_hongdae"])}
        self.assertEqual(rows["koccaofficial"][1], ax.NON_ARTIST_KEY)
        self.assertEqual(rows["clubffhongdae"][1], "클럽에프에프")

    def test_program_names_are_forced_non_artist(self):
        # '뮤즈온' 같은 지원 프로그램 이름은 연결표에 팀처럼 있어도 팀 아님으로 덮어쓴다
        artists = [{"artist_key": "뮤즈온", "display_name": "뮤즈온", "keys": ["뮤즈온", "museon"], "aliases": [],
                    "confidence": "low", "instagram": []}]
        rows = {r[0]: r for r in ax.xref_rows(artists, non_artist_handles=[])}
        self.assertEqual(rows["museon"][1], ax.NON_ARTIST_KEY)
        self.assertEqual(rows["뮤즈온"][1], ax.NON_ARTIST_KEY)

    def test_pg_script_refills_without_drop(self):
        # core 뷰가 ref.artist_xref 를 참조하므로 DROP 대신 비우고 다시 채운다 (한 트랜잭션)
        script = ax.pg_load_script("/tmp/x.csv")
        self.assertNotIn("DROP TABLE", script)
        self.assertIn("CREATE TABLE IF NOT EXISTS ref.artist_xref", script)
        self.assertIn("TRUNCATE ref.artist_xref", script)
        self.assertIn("\\copy ref.artist_xref FROM '/tmp/x.csv'", script)
        self.assertLess(script.index("BEGIN"), script.index("TRUNCATE"))
        self.assertLess(script.index("\\copy"), script.index("COMMIT"))

    def test_load_pg_skips_without_psql(self):
        msg = ax.load_pg([], psql_path="/nonexistent/psql")
        self.assertIn("건너뜀", msg)


class CollectInputsMelonIdTest(unittest.TestCase):
    """멜론 번호 1,000 미만(이름 속 숫자를 번호로 잘못 읽은 값: 12BH→12, D82→82)은 연결표에 쓰지 않는다."""

    def test_short_melon_ids_dropped_from_profiles_and_matches(self):
        with tempfile.TemporaryDirectory() as d:
            raw = Path(d)
            (raw / "state").mkdir()
            (raw / "raw_artist_profile_2026-11-27_melon.csv").write_text(
                "source,artist_source_id,artist_text\nmelon,82,김명남\nmelon,3201955,12BH\n", encoding="utf-8")
            (raw / "state" / "outcome_melon_match.json").write_text(json.dumps(
                {"D82": {"id": "82", "namesakes": 1}, "9B2": {"id": "9"}, "새팀": {"id": "3000007"}, "없음": None}),
                encoding="utf-8")
            (raw / "state" / "spotify_match.json").write_text(json.dumps({"D82": {"id": "4abc"}}), encoding="utf-8")
            _, _, _, ids = ax.collect_inputs(raw)
        got = {(r["platform"], r["id"]) for r in ids}
        self.assertEqual(got, {("melon", "3201955"), ("melon", "3000007"), ("spotify", "4abc")})


class LoadXrefTest(unittest.TestCase):
    def test_round_trip(self):
        artists = [{"artist_key": "피치트럭하이재커스", "display_name": "피치트럭하이재커스",
                    "aliases": ["피치트럭하이재커스", "Peach Truck Hijackers"],
                    "instagram": [{"handle": "peachtruck", "confidence": "mid", "evidence": []}],
                    "sources": ["gig"], "confidence": "high"}]
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "x.json"
            path.write_text(json.dumps(artists, ensure_ascii=False), encoding="utf-8")
            index = ax.load_xref(path)
        self.assertEqual(index["by_key"]["peachtruckhijackers"], "피치트럭하이재커스")
        self.assertEqual(index["by_handle"]["peachtruck"], "피치트럭하이재커스")
        self.assertIn("피치트럭하이재커스", index["artists"])
        self.assertEqual(ax.canonical_key("Peach Truck Hijackers", index), "피치트럭하이재커스")

    def test_missing_file_gives_empty_index(self):
        index = ax.load_xref(Path("/nonexistent/xref.json"))
        self.assertEqual(index["by_key"], {})


if __name__ == "__main__":
    unittest.main()
