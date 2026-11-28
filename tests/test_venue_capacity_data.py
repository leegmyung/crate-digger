"""config/venue_capacity.json 항목 형식 — 수용 인원을 적은 곳은 근거·확인 날짜·확실도·좌석/스탠딩 중 하나를 갖춰야 한다."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class VenueCapacityDataTest(unittest.TestCase):
    def setUp(self):
        self.venues = json.loads((ROOT / "config" / "venue_capacity.json").read_text(encoding="utf-8"))["venues"]

    def test_capacity_entries_have_evidence(self):
        for name, d in self.venues.items():
            if not d.get("capacity"):
                continue
            with self.subTest(venue=name):
                self.assertTrue(str(d.get("source", "")).startswith("http"), "근거 링크(source)")
                self.assertRegex(str(d.get("checked", "")), DATE, "확인 날짜(checked)")
                self.assertIn(d.get("confidence"), ("high", "mid", "low"))
                self.assertTrue(d.get("seats") or d.get("standing"), "좌석(seats) 또는 스탠딩(standing) 숫자")
                self.assertTrue(d.get("source_note"), "근거 메모(source_note)")

    def test_capacity_is_standing_first(self):
        """capacity = 스탠딩 최대, 없으면 좌석 (venue_capacity.json _설명)."""
        for name, d in self.venues.items():
            if not d.get("capacity"):
                continue
            with self.subTest(venue=name):
                self.assertEqual(d["capacity"], d.get("standing") or d.get("seats"))

    def test_top_venues_researched(self):
        """2026-11-28 조사분: 공연 밤 많은 공연장 중 KOPIS·공식 자료로 확인한 곳은 체급이 채워져 있다."""
        for name in ("네스트나다", "언플러그드 신촌점", "공상온도", "벨르", "리얼라이즈", "서울 노들섬 라이브하우스",
                     "이들스", "폼텍 웍스홀", "문화정원아트홀"):
            with self.subTest(venue=name):
                self.assertIn(name, self.venues)
                self.assertTrue(self.venues[name].get("tier"))


if __name__ == "__main__":
    unittest.main()
