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
]
# (키1, 키2): 다른 팀(다른 인스타·멜론 번호, 또는 뜻이 다른 이름)
DIFFERENT = [
    ("윤석철", "윤석철트리오"), ("오이스터", "오이스터즈"), ("롱아일랜드", "심아일랜드"), ("루시드림", "루시드폴"),
    ("바비돌스", "바비핀스"), ("반디시티", "윈디시티"), ("밴드그린", "밴드기린"), ("비웨이브", "영웨이브"),
    ("에이티즈", "에이퍼즈"), ("크리스탈", "크리스피"), ("트라이비", "트레이비"), ("트레이비", "트레이터"),
    ("오렌지맨", "오렌지섬"), ("나르디스", "나르키스"), ("네모난구", "네모지구"), ("다운", "따운"), ("라이스", "라이즈"),
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

    def test_same_and_different_do_not_overlap(self):
        cur = artist_xref.load_curation(PATH)
        same_groups = [{artist_xref.artist_key(n) for n in [e["main"], *e["aliases"]]} for e in cur["aliases"]]
        for a, b in DIFFERENT:
            self.assertFalse(any(a in g and b in g for g in same_groups), f"{a} ↔ {b} 가 같은 팀으로도 묶여 있음")


if __name__ == "__main__":
    unittest.main()
