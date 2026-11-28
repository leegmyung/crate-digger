"""실제 연결표(config/artist_aliases.json) 데이터 검사 — 형식이 맞고, 2026-11-28에 확인한 중복 의심 쌍이 모두 정리돼 있는지."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import artist_xref  # noqa: E402
import data_checks as dc  # noqa: E402

PATH = ROOT / "config" / "artist_aliases.json"

# (키1, 키2): 같은 팀(같은 인스타·스포티파이 주소, 같은 날 같은 공연장, 철자 흔들림)
SAME = [
    ("sallyeverywhere샐리에브리웨어", "샐리에브리웨어"), ("fleet플릿", "플릿"), ("pnr", "피스앤로맨스"),
    ("menandthem", "맨앤뎀"), ("underflow언더플로우", "언더플로우"), ("sosoyon", "소소욘"), ("izoko", "이조코"),
    ("frnk", "프랭크"), ("revesenrebirth", "리버스앤리버스"), ("reversenrebirth", "revesenrebirth"),
    ("sabbaha", "사바하"), ("thejoyfools", "조이풀스"), ("mischiefers", "미스치퍼스"), ("baan", "반"),
    ("eddieandthebricks", "에디앤더브릭스"), ("redc", "레드씨"), ("송남현", "준비왕송남현"),
    ("줄라이원스모어", "줄라이원츠모어"), ("라이프라디", "라이프라디오"), ("amyiee", "amyiie"),
    ("디비아디", "디비아이디"), ("수련", "suryeon"), ("mountxir", "mountxlr"), ("더블랭크샵", "더블랭크숍"),
    ("러브x스테레오", "러브엑스테레오"), ("머쉬베놈", "머쉬베놈과"), ("cifika", "cifikas"),
    ("shallowleve", "shallowlevee"),
    # 2차 (높음·중간 쌍): 같은 인스타·같은 날 같은 공연장·같은 글의 표기 흔들림
    ("더리셋터즈", "리셋터즈"), ("리추얼리티", "리츄얼리티"), ("매디엑스피", "메디엑스피"), ("넉살x까데호", "넉살까데호"),
    ("릴체리x골드부다", "릴체리골드부다"), ("워크맨쉽maalib", "워크맨십maalib"), ("플랫폼스테레오", "플렛폼스테레오"),
    ("킬카이저", "킬카이져"), ("포보틀스", "포보틀즈"), ("플레이버대쉬", "플레이버대시"), ("모사이코", "모싸이코"),
    ("마인드애틱", "마인드에틱"), ("스태리웨이브", "스테리웨이브"), ("henzclub", "thehenzclub"),
    ("13children", "서틴칠드런"), ("deny", "디나이"), ("giok", "지옥"), ("himinn", "히민"), ("howcani", "하우캔아이"),
    ("lucyvalentine", "루시발렌타인"), ("myveryend", "마이베리엔드"), ("omilgop", "오미일곱"), ("roon", "룬"),
    ("scarletkimband", "스칼렛킴밴드"), ("wakingsuns", "웨이킹선스"), ("나르샤", "나르샤browneyedgirls"),
    ("나미카이", "namikai"), ("모하니", "mohani"), ("사케비", "sakebi"), ("로얄44", "royal44"), ("디디한", "didihan"),
    ("해로이키", "haeroiki"), ("송요다", "songyoda"), ("욘욘", "yonyon"),
]
# (정답 키, 신호 팀 키): 정답 표기만 달라 우리 신호와 못 이어졌던 팀
OUTCOME_LINKS = [("포쳐군단", "포져군단"), ("스윔레빗", "swimrabbit"), ("스윔레빗", "스윔래빗"), ("나인티오원", "9001"),
                 ("투톤쉐이프", "twotoneshape")]
# (키1, 키2): 다른 팀(다른 인스타·멜론 번호, 또는 뜻이 다른 이름)
DIFFERENT = [
    ("윤석철", "윤석철트리오"), ("오이스터", "오이스터즈"), ("롱아일랜드", "심아일랜드"), ("루시드림", "루시드폴"),
    ("바비돌스", "바비핀스"), ("반디시티", "윈디시티"), ("밴드그린", "밴드기린"), ("비웨이브", "영웨이브"),
    ("에이티즈", "에이퍼즈"), ("크리스탈", "크리스피"), ("트라이비", "트레이비"), ("트레이비", "트레이터"),
    ("오렌지맨", "오렌지섬"), ("나르디스", "나르키스"), ("네모난구", "네모지구"), ("다운", "따운"), ("라이스", "라이즈"),
    ("변하은", "변하은과하이에나"),
]


class ArtistAliasesDataTest(unittest.TestCase):
    def test_file_loads_without_format_errors(self):
        cur = artist_xref.load_curation(PATH)
        self.assertGreater(len(cur["aliases"]), 0)

    def test_checked_pairs_leave_duplicate_list(self):
        cur = artist_xref.load_curation(PATH)
        keys = sorted({k for pair in SAME + DIFFERENT for k in pair})
        left = {tuple(sorted((a, b))) for _, a, b, _ in dc.duplicate_candidates(keys, (), cur)}
        for a, b in SAME + DIFFERENT:
            self.assertNotIn(tuple(sorted((a, b))), left, f"{a} ↔ {b} 가 아직 중복 의심에 남음")

    def test_outcome_names_join_signal_teams(self):
        """정답에만 있던 표기 → 우리 신호 팀 키 (2026-11-28 정답·신호 0 팀 점검)."""
        cur = artist_xref.load_curation(PATH)
        groups = [{artist_xref.artist_key(n) for n in [e["main"], *e["aliases"]]} for e in cur["aliases"]]
        for outcome_key, signal_key in OUTCOME_LINKS:
            self.assertTrue(any(outcome_key in g and signal_key in g for g in groups), f"{outcome_key} → {signal_key} 연결 없음")

    def test_same_and_different_do_not_overlap(self):
        cur = artist_xref.load_curation(PATH)
        same_groups = [{artist_xref.artist_key(n) for n in [e["main"], *e["aliases"]]} for e in cur["aliases"]]
        for a, b in DIFFERENT:
            self.assertFalse(any(a in g and b in g for g in same_groups), f"{a} ↔ {b} 가 같은 팀으로도 묶여 있음")


if __name__ == "__main__":
    unittest.main()
