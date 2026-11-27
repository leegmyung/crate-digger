"""video_match: 영상 제목 ↔ 팀 이름 대조 규칙 — 흔한 낱말 거르기·짧은 이름은 '팀 이름 자리'일 때만·자동 흔한 낱말 후보."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import video_match as vm  # noqa: E402


def row(display, title, kind="stage", team=None):
    return {"team_key": team or display, "display_name": display, "title": title, "kind": kind}


class CommonWordsFileTest(unittest.TestCase):
    def test_load_manual_list_and_allow(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "common.json"
            p.write_text(json.dumps({"common": ["글로벌", "Day"], "allow": ["카더가든"]}), encoding="utf-8")
            common, allow = vm.load_common(p)
        self.assertIn("글로벌", common)
        self.assertIn("day", common)                 # 소문자로 맞춘다
        self.assertIn("사랑", common)                # 코드의 기본 목록(STOPLIST)도 포함
        self.assertEqual(allow, frozenset({"카더가든"}))

    def test_missing_file_falls_back_to_stoplist(self):
        common, allow = vm.load_common(Path("/nonexistent/common.json"))
        self.assertIn("사랑", common)
        self.assertEqual(allow, frozenset())

    def test_repo_config_has_reported_words(self):
        common, _ = vm.load_common()
        for w in ("글로벌", "day", "그리고", "사랑", "우리"):
            self.assertIn(w, common)


class ShortNameTest(unittest.TestCase):
    def test_is_short(self):
        self.assertTrue(vm.is_short(("카디",)))
        self.assertTrue(vm.is_short(("day",)))
        self.assertFalse(vm.is_short(("새소년",)))
        self.assertFalse(vm.is_short(("samui",)))
        self.assertFalse(vm.is_short(("ab", "cd")))   # 낱말 둘이면 짧은 이름 아님

    def test_artist_position_needs_both_sides(self):
        def pos(title, name):
            t = title.lower()
            i = t.index(name)
            return vm.artist_position(t, i, i + len(name))
        self.assertTrue(pos("[딩고] 카디 - 노래", "카디"))           # 맨 앞(태그 뒤) + 뒤에 구분 기호
        self.assertTrue(pos("노래 | 카디", "카디"))                  # 구분 기호 뒤 + 제목 끝
        self.assertTrue(pos("노래 - 카디 (KARDI) [뮤직뱅크]", "카디"))
        self.assertTrue(pos("[카디] 라이브 클립", "카디"))            # [팀명] 형식
        self.assertFalse(pos("형선(hyngsn) - day life(feat.크루셜스타)", "day"))   # 곡 이름 첫 낱말
        self.assertFalse(pos("조이 - day by day", "day"))
        self.assertFalse(pos("오늘의 카디 노래 모음", "카디"))
        self.assertFalse(pos("뮤지컬 [카디 앤 클라이드] 배우 - 노래", "카디"))

    def test_collab_x_and_alias_paren_are_artist_formats(self):
        def pos(title, name):
            t = title.lower()
            i = t.index(name)
            return vm.artist_position(t, i, i + len(name))
        self.assertTrue(pos("[스페이스 공감] 넉살 X 까데호 - 죽", "넉살"))       # 'A X B -' 함께 무대
        self.assertTrue(pos("[스페이스 공감] 넉살 X 까데호 - 죽", "까데호"))
        self.assertTrue(pos("neu(노이 / ノイ) – 티키토크", "노이"))              # 맨 앞 이름 바로 뒤 괄호 속 별칭
        self.assertFalse(pos("[하이라이트] 유키 구라모토X박보검 - Romance", "유키"))
        self.assertFalse(pos("싸이커스 민재 [리무진서비스]", "민재"))
        self.assertFalse(pos("이 노래(카디 버전) 듣기", "카디"))                # 가운데 낱말 뒤 괄호는 아님


class KeepRowTest(unittest.TestCase):
    def setUp(self):
        self.common = frozenset({"글로벌", "그리고"}) | vm.STOPLIST
        self.keep = lambda r, auto=frozenset(): vm.keep_row(r, self.common, frozenset(), auto)

    def test_common_word_team_dropped(self):
        self.assertFalse(self.keep(row("글로벌", "원호 - BLUE │ 글로벌 대세 원호의 라이브")))
        self.assertFalse(self.keep(row("그리고", "낭만 그리고 극동아시아타이거즈 LIVE")))

    def test_short_name_needs_artist_position(self):
        self.assertFalse(self.keep(row("Day", "조이 - Day By Day", team="day")))
        self.assertFalse(self.keep(row("Day", "[FOCUS] 영재 – Errr Day | 딩고뮤직", team="day")))
        self.assertTrue(self.keep(row("Day", "Day - 첫 노래 [LIVE]", team="day")))
        self.assertTrue(self.keep(row("카디", "[딩고] 카디 - 노래")))

    def test_official_channel_is_evidence(self):
        self.assertTrue(self.keep(row("Day", "오늘 연습 브이로그", kind="official", team="day")))
        self.assertTrue(self.keep(row("글로벌", "새 노래 라이브", kind="official_live")))

    def test_long_name_kept_anywhere(self):
        self.assertTrue(self.keep(row("극동아시아타이거즈", "낭만 그리고 극동아시아타이거즈 LIVE")))
        self.assertTrue(self.keep(row("세이수미 (Say Sue Me)", "부산에서 온 say sue me 인터뷰")))

    def test_short_main_name_long_alias(self):
        # '사뮈'(두 글자)는 자리 규칙, 'Samui'(다섯 글자)는 어디 있어도 인정
        self.assertFalse(self.keep(row("사뮈 (Samui)", "오늘의 사뮈 노래 모음", team="사뮈")))
        self.assertTrue(self.keep(row("사뮈 (Samui)", "오늘의 Samui 노래 모음", team="사뮈")))

    def test_name_not_in_title_dropped(self):
        self.assertFalse(self.keep(row("로맨틱펀치", "다른 팀 - 노래")))

    def test_original_credit_not_counted(self):
        self.assertFalse(self.keep(row("로맨틱펀치", "이찬원 - 여행을 떠나요 (원곡: 로맨틱펀치)")))

    def test_auto_common_applied(self):
        self.assertFalse(self.keep(row("라이징", "라이징 스타 특집 - 누군가"), auto=frozenset({"라이징"})))

    def test_missing_display_name_kept(self):
        self.assertTrue(vm.keep_row({"team_key": "a", "title": "에이 live", "kind": "stage"},
                                    self.common, frozenset(), frozenset()))


class AutoCommonTest(unittest.TestCase):
    def test_frequent_name_mostly_mid_sentence_is_candidate(self):
        rows = [row("글로벌", f"누군가{i} - 노래 │ 글로벌 슈퍼루키 누군가{i}") for i in range(12)]
        rows += [row("실리카겔", f"실리카겔 - 노래{i}") for i in range(12)]
        rows += [row("카더가든", f"헬로루키 (feat. 누군가 그리고 카더가든) EP.{i}") for i in range(4)]
        self.assertEqual(vm.auto_common(rows, min_hits=10, max_artist_share=0.2), frozenset({"글로벌"}))

    def test_allow_list_protects(self):
        rows = [row("글로벌", f"누군가{i} - 노래 │ 글로벌 슈퍼루키") for i in range(12)]
        self.assertEqual(vm.auto_common(rows, min_hits=10, allow=frozenset({"글로벌"})), frozenset())

    def test_short_and_official_rows_ignored(self):
        rows = [row("카디", f"오늘의 카디 노래 {i}") for i in range(12)]           # 짧은 이름은 따로 엄격 규칙
        rows += [row("새소년", f"오늘 새소년 연습 {i}", kind="official") for i in range(12)]
        self.assertEqual(vm.auto_common(rows, min_hits=10), frozenset())


class FilterRowsTest(unittest.TestCase):
    def test_filter_reports_counts(self):
        rows = [row("글로벌", "원호 │ 글로벌 대세"), row("실리카겔", "실리카겔 - 노래"),
                row("Day", "조이 - Day By Day", team="day")]
        kept, report = vm.filter_rows(rows, common=frozenset({"글로벌"}) | vm.STOPLIST, allow=frozenset())
        self.assertEqual([r["team_key"] for r in kept], ["실리카겔"])
        self.assertEqual(report["before"], 3)
        self.assertEqual(report["after"], 1)
        self.assertEqual(report["dropped_by_team"]["글로벌"], 1)

    def test_auto_candidates_reported_not_applied(self):
        # 자동 후보는 사람이 보고 config 에 옮길 목록 — 진짜 팀이 섞일 수 있어 바로 적용하지 않는다
        rows = [row("라이징", f"누군가{i} - 노래 │ 라이징 스타 특집") for i in range(12)]
        kept, report = vm.filter_rows(rows, common=vm.STOPLIST, allow=frozenset())
        self.assertEqual(len(kept), 12)
        self.assertEqual(report["auto_candidates"], ["라이징"])

    def test_loose_position_for_long_names(self):
        # 날짜 뒤·# 뒤·괄호 속·영문 별칭 앞은 긴 이름의 '팀 이름 자리'로 본다 (자동 후보 계산용)
        rows = [row("극동아시아타이거즈", f"230513 극동아시아타이거즈 Far East Asian Tigers / 공연{i}") for i in range(6)]
        rows += [row("김사월", f"일상적인 가사 {i} | #KimSawol #김사월") for i in range(6)]
        rows += [row("투어스", f"OVERDRIVE - TWS (투어스) [뮤직뱅크] {i}") for i in range(6)]
        rows += [row("박주원", f"박주원 ; Butter {i}ㅣ난장LIVE") for i in range(6)]
        self.assertEqual(vm.auto_common(rows, min_hits=5), frozenset())


if __name__ == "__main__":
    unittest.main()
