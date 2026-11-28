import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import collect_regional_busan as crb  # noqa: E402


def item(kind, title, dates, place, cast):
    spans = "".join(f"<span>{d}</span>" for d in dates) + "<span></span>"
    return (f'<li><a class="item"><div class="txt"><div class="board-type"><span>{kind}</span></div>'
            f'<div class="board-subject">{title}</div><div class="board-date">{spans}</div>'
            f'<div class="board-place">{place}</div><div class="board-cast">{cast}</div></div></a></li>')


PAGE = "".join([
    item("쇼케이스", "14일의 금요일", ["2025-11-14"], "KT&amp;G상상마당부산 라이브홀", "오하이오블루팁, 뱁새들"),
    item("쇼케이스", "해서웨이 South Termianl", ["2025-10-24", "2025-11-01"], "상상마당부산, 롤링홀 홍대", "해서웨이"),
    item("협력사업", "대구부산서울인디교류전", ["2019-10-19"], "바이닐언더그라운드, 오방가르드, 노드(부산)",
         "사이드카, 까데호"),
])


class ParseTest(unittest.TestCase):
    def test_reads_every_card(self):
        items = crb.parse_list(PAGE)
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0]["title"], "14일의 금요일")
        self.assertEqual(items[0]["dates"], ["2025-11-14"])
        self.assertEqual(items[0]["places"], ["KT&G상상마당부산 라이브홀"])
        self.assertEqual(items[1]["dates"], ["2025-10-24", "2025-11-01"])

    def test_single_digit_day_is_padded(self):
        page = item("쇼케이스", "T", ["2025-11-2"], "메트로라운지", "A")
        self.assertEqual(crb.parse_list(page)[0]["dates"], ["2025-11-02"])


class CastTest(unittest.TestCase):
    def test_splits_and_cleans_roles(self):
        self.assertEqual(crb.split_cast("브로큰발렌타인(멘토), 리제스트, 홈바디(멘티)"), ["브로큰발렌타인", "리제스트", "홈바디"])

    def test_comma_inside_parentheses_stays_with_team(self):
        self.assertEqual(crb.split_cast("해서웨이(강키위, 최세요, 이특민), 임성완"), ["해서웨이", "임성완"])
        self.assertEqual(crb.split_cast("From 2020 (라원, 헤니)"), ["From 2020"])

    def test_drops_counts_and_staff(self):
        self.assertEqual(crb.split_cast("모멘츠유미, 자이, 조연희 외 7명"), ["모멘츠유미", "자이", "조연희"])
        self.assertEqual(crb.split_cast("헤드터너, 일렉펀트 등 총24팀"), ["헤드터너", "일렉펀트"])
        self.assertEqual(crb.split_cast("밴드기린, 수프라메플라워 대표 정다솜"), ["밴드기린"])

    def test_collab_split(self):
        self.assertEqual(crb.split_cast("제이통X로다운30, 이슬아X이찬희"), ["제이통", "로다운30", "이슬아", "이찬희"])


class GigsTest(unittest.TestCase):
    def test_dates_pair_with_places_in_order(self):
        gigs = crb.gigs_from_items(crb.parse_list(PAGE))
        sth = [(g["day"], g["venue_text"]) for g in gigs if g["title"].startswith("해서웨이")]
        self.assertEqual(sth, [("2025-10-24", "상상마당부산"), ("2025-11-01", "롤링홀 홍대")])

    def test_region_suffix_of_last_place_spreads_and_first_place_used_for_one_day(self):
        gigs = [g for g in crb.gigs_from_items(crb.parse_list(PAGE)) if g["title"].startswith("대구부산")]
        self.assertEqual({g["venue_text"] for g in gigs}, {"바이닐언더그라운드 (부산)"})
        self.assertEqual([g["artist"] for g in gigs], ["사이드카", "까데호"])
        self.assertEqual(gigs[0]["lineup_size"], "2")

    def test_busan_interplay_not_daejeon(self):
        page = item("브랜드공연", "더 애프터 파티", ["2019-03-23"], "인터플레이(금정구)", "밴드88")
        self.assertEqual(crb.gigs_from_items(crb.parse_list(page))[0]["venue_text"], "인터플레이 부산 (금정구)")

    def test_ambiguous_dates_and_places_skipped(self):
        page = item("협력사업", "잔다리", ["2019-09-28", "2019-09-29"], "에반스라운지, 스틸페이스, 프리즘홀", "보수동쿨러")
        self.assertEqual(crb.gigs_from_items(crb.parse_list(page)), [])

    def test_source_id_and_url_are_stable(self):
        g = crb.gigs_from_items(crb.parse_list(PAGE))[0]
        self.assertTrue(g["source_id"].startswith("musiclabbusan:"))
        self.assertTrue(g["url"].startswith("https://www.musiclabbusan.com/board/photo#"))


if __name__ == "__main__":
    unittest.main()
