"""화면 표시 이름 바로잡기 (2026-11-28) — 상위 300 후보·정답 팀 중 표시 이름이 계정명·소문자·띄어쓰기 다른 표기로 보이던 팀.

규칙: 가장 공식적인 표기 = 멜론 아티스트 프로필 이름(한영 병기면 앞 이름) > 인디스트릿 페이지 > 기사. 확실한 것만.
config/artist_aliases.json 의 display(true = main, 글자 = 그 표기)로 정하고, 팀 키는 그대로(저장값·주소 안 바뀜).
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import artist_xref as ax  # noqa: E402

# 팀 키 → 화면 이름 (근거: 멜론 프로필 이름 · 인디스트릿 · 기사 — 2026-11-28 원본 대조)
EXPECTED = {
    "gonggonggoo009": "공공구",            # 한국힙합어워즈 2023 '공공구(GongGongGoo009)'
    "bandits": "Bandits",                 # 멜론
    "데킬라올드패션드": "데킬라 올드 패션드",  # 멜론
    "웰컴투초초랜드": "웰컴투 초초랜드",
    "아나키컬쳐": "아나키 컬쳐",
    "안도프로젝트": "안도 프로젝트",
    "제임스키스": "제임스 키스",
    "릴리잇머신": "릴리 잇 머신",
    "투데이올드스니커즈": "투 데이 올드 스니커즈",
    "모스크바서핑클럽": "모스크바서핑클럽",
    "yu": "YU",
    "rosie": "ROSIE",
    "nazu": "Nazu",
    "sunflowers": "Sunflowers",
    "viridian": "Viridian",
    "murdermartyr": "MurderMartyr",
    "moim": "moim",
    "wakeupfinn": "wakeupfinn",
    "firr": "FIRR",
    "failfast": "Fail Fast",
    "xaoil": "xaoil (451)",
    "프로듀서버터스카치": "버터스카치",       # 기사 '프로듀서 ○○' — 역할 말은 이름이 아님
    "프로듀서암모나이트": "암모나이트",
    "프로듀서엔드오프": "엔드오프",
    "thehenzclub": "The Henz Club",       # 계정명 모양 → 팀 이름
    "워크맨십maalib": "워크맨십 Maalib",    # 닫는 괄호가 빠진 표기
}


def display_by_key(entries):
    """별칭 항목의 display → {그 항목 이름 키마다: 고른 표기} (팀 키는 별칭 쪽 키일 수 있음)"""
    out = {}
    for e in entries:
        d = e.get("display")
        if d is True or isinstance(d, str):
            text = ax.clean(e["main"] if d is True else d)
            for n in [e["main"], *e["aliases"]]:
                out[ax.artist_key(n)] = text
    return out


class DisplayNamesConfigTest(unittest.TestCase):
    entries = ax.load_manual_aliases(ROOT / "config" / "artist_aliases.json")

    def test_expected_display_names(self):
        got = display_by_key(self.entries)
        for key, want in EXPECTED.items():
            self.assertEqual(got.get(key), want, key)

    def test_display_attaches_to_team_key(self):
        # 고른 표기의 이름 키가 그 항목 이름들 중 하나와 같아야 팀에 붙는다
        for e in self.entries:
            d = e.get("display")
            if d in (None, False):
                continue
            text = e["main"] if d is True else d
            keys = {ax.artist_key(n) for n in [e["main"], *e["aliases"]]}
            self.assertIn(ax.artist_key(text), keys, e["main"])

    def test_chosen_names_look_official(self):
        for key, name in EXPECTED.items():
            self.assertFalse(name.startswith("프로듀서 "), name)
            self.assertEqual(name.count("("), name.count(")"), name)


if __name__ == "__main__":
    unittest.main()
