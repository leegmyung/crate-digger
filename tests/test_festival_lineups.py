"""국내 큰 페스티벌 연도별 라인업(config/festival_lineups.json) — 형식, 공연 원본 행, 페스티벌 화면 반영."""
import json
import re
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import collect_festival_lineups as cfl  # noqa: E402
import festival_profiles as fp  # noqa: E402
import validate_csv as vc  # noqa: E402
from csv_schema import TABLES  # noqa: E402

CFG = json.loads((ROOT / "config" / "festival_lineups.json").read_text(encoding="utf-8"))
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")

MINI = {"festivals": {
    "gmf": {"label": "그랜드 민트 페스티벌", "venue_text": "올림픽공원 (서울특별시 송파구 올림픽로 424)", "editions": {
        "2024": {"source_url": "https://namu.wiki/w/x#2024년", "days": ["2024-10-26", "2024-10-27"], "official_total": 3,
                 "acts": [{"name": "에이", "day": "2024-10-26", "stage": "Mint Breeze Stage", "korean": True},
                          {"name": "비", "day": "2024-10-27", "stage": "", "korean": True},
                          {"name": "Foreign Act", "day": "2024-10-27", "stage": "", "korean": False}]}}}}}


class ConfigShapeTest(unittest.TestCase):
    def test_editions(self):
        self.assertGreaterEqual(len(CFG["festivals"]), 5)
        for fest, f in CFG["festivals"].items():
            self.assertTrue(f.get("label") and f.get("venue_text"), fest)
            for year, e in f["editions"].items():
                with self.subTest(festival=fest, year=year):
                    self.assertTrue(e["source_url"].startswith("https://"))
                    self.assertTrue(e["acts"])
                    for a in e["acts"]:
                        self.assertRegex(a["day"], ISO)
                        self.assertTrue(a["day"].startswith(year), a)
                        self.assertIsInstance(a["korean"], bool)
                        self.assertTrue(a["name"].strip())
                    names = [a["name"] for a in e["acts"]]
                    self.assertEqual(len(names), len(set(names)), "같은 회차에 같은 이름 두 번")
                    if e.get("official_total") is not None:
                        self.assertEqual(e["official_total"], len(e["acts"]))

    def test_foreign_acts_marked(self):
        """해외 팀은 korean=false (공연 원본·화면 팀 목록에서 빠짐)."""
        acts = {(f, a["name"]): a["korean"] for f, x in CFG["festivals"].items()
                for e in x["editions"].values() for a in e["acts"]}
        self.assertFalse(acts[("penta", "TURNSTILE")])
        self.assertFalse(acts[("burock", "Suede")])
        self.assertTrue(acts[("penta", "실리카겔")])


class RawRowsTest(unittest.TestCase):
    def test_rows_only_korean_and_valid(self):
        rows = cfl.rows_from_config(MINI, "2026-11-28T12:00:00+09:00")
        self.assertEqual([r["artist_text"] for r in rows], ["에이", "비"])
        self.assertEqual(rows[0]["source"], "festival")
        self.assertEqual(rows[0]["gig_date"], "2024-10-26")
        self.assertIn("그랜드 민트 페스티벌", rows[0]["title"])
        spec = TABLES["raw_kr_gig"]
        header = [f.name for f in spec["fields"]]
        self.assertEqual(vc.check_rows(rows, header, spec), [])

    def test_skip_already_collected(self):
        """같은 날 같은 팀이 이미 다른 원본(인디스트릿 등)에 있으면 다시 쓰지 않음 — 신호 두 번 방지."""
        rows = cfl.rows_from_config(MINI, "2026-11-28T12:00:00+09:00", skip={("2024-10-26", cfl.name_key("에이"))})
        self.assertEqual([r["artist_text"] for r in rows], ["비"])


class FestivalPageTest(unittest.TestCase):
    def test_lineup_festivals_on_page(self):
        apps = fp.collect_appearances([], [], lineups=MINI, key_of=lambda n: {"에이": "a", "비": "b"}.get(n, n))
        got = sorted((a.festival, a.team, a.day) for a in apps)
        self.assertEqual(got, [("gmf", "a", date(2024, 10, 26)), ("gmf", "b", date(2024, 10, 27))])

    def test_known_festivals_have_lineup_key(self):
        keys = {f.key: f.lineup for f in fp.FESTIVALS}
        for k in ("penta_main", "gmf", "bml"):
            self.assertIn(k, keys)
        self.assertEqual(keys["dmz"], "dmz")
        self.assertEqual(keys["burock_main"], "burock")


if __name__ == "__main__":
    unittest.main()


class CatalogTest(unittest.TestCase):
    """페스티벌라이프 목록(config/festival_catalog.json) → 화면 '날짜·장소만' 목록 + 라인업 페스티벌 연결."""

    CAT = {"festivals": {
        "그랜드민트페스티벌": {"name": "그랜드민트페스티벌", "editions": {
            "2022": {"dates": ["2022-10-22"], "venue": "올림픽공원", "posts": [{"title": "t", "kind": "최종 라인업", "url": "https://www.festivallife.kr/festival/?bmode=view&idx=1"}], "lineup_text": False}}},
        "잔다리페스티벌": {"name": "잔다리페스타", "editions": {
            "2024": {"dates": ["2024-10-03", "2024-10-04"], "venue": "홍대 일대", "posts": [{"title": "t2", "kind": "개최 일정", "url": "https://www.festivallife.kr/festival/?bmode=view&idx=2"}], "lineup_text": False}}}}}

    def test_catalog_entries(self):
        rows = {r["name"]: r for r in fp.catalog_entries(self.CAT)}
        self.assertEqual(rows["그랜드민트페스티벌"]["festival"], "gmf")        # 라인업 페스티벌과 연결
        self.assertEqual(rows["잔다리페스타"]["festival"], "zandari")            # 포스터로 라인업을 채운 페스티벌과 연결
        e = rows["잔다리페스타"]["editions"]["2024"]
        self.assertEqual(e, {"dates": ["2024-10-03", "2024-10-04"], "venue": "홍대 일대",
                             "url": "https://www.festivallife.kr/festival/?bmode=view&idx=2"})


class PosterEditionsTest(unittest.TestCase):
    """2026-11-28 공식 포스터(페스티벌라이프 글의 그림)를 읽어 채운 회차 — 국내 팀만, 근거 URL, 동명 위험 표시."""

    EXPECT = {("gmf", "2022"), ("burock", "2022"), ("penta", "2021"), ("letsrock", "2026"), ("letsrock", "2025"),
              ("soundplanet", "2026"), ("soundplanet", "2025"), ("gyeonggi_indie", "2026"), ("gyeonggi_indie", "2024"),
              ("zandari", "2025")}

    def test_poster_editions_present(self):
        for fest, year in self.EXPECT:
            with self.subTest(festival=fest, year=year):
                e = CFG["festivals"][fest]["editions"][year]
                self.assertIn("festivallife.kr", e["source_url"])
                self.assertGreaterEqual(sum(a["korean"] for a in e["acts"]), 5)

    def test_name_risk_flag_shape(self):
        for fest, f in CFG["festivals"].items():
            for year, e in f["editions"].items():
                for a in e["acts"]:
                    if "name_risk" in a:
                        self.assertIsInstance(a["name_risk"], str)
                        self.assertTrue(a["name_risk"].strip())

    def test_new_festivals_on_page(self):
        lineup_keys = {f.lineup for f in fp.FESTIVALS if f.lineup}
        for k in ("letsrock", "soundplanet", "gyeonggi_indie", "zandari"):
            self.assertIn(k, lineup_keys)
