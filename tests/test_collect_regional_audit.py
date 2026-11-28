import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import collect_regional_audit as cra  # noqa: E402


def gig(venue, day, artist, title="공연", url="https://example.com/g"):
    return {"venue_text": venue, "gig_date": day, "artist_text": artist, "title": title, "gig_url": url}


MASTER = [
    {"name": "세종 음악창작소 누리락", "aliases": [], "city": "세종", "province": "세종", "type": "creation_center",
     "status": "open"},
    {"name": "A.O.R", "aliases": [], "city": "서울", "province": "서울", "type": "live_club", "status": "open"},
    {"name": "버찌라이브하우스", "aliases": [], "city": "대전", "province": "대전", "type": "hall", "status": "open"},
]


class VenueStatsTest(unittest.TestCase):
    def test_counts_distinct_gigs_and_teams_since_date(self):
        rows = [
            gig("세종 음악창작소 누리락 (세종특별자치시 갈매로 387)", "2026-11-28", "우희준", "디깅 23", "u1"),
            gig("세종 음악창작소 누리락 (세종특별자치시 갈매로 387)", "2026-11-28", "우희준", "디깅 23", "u1b"),
            gig("세종 음악창작소 누리락", "2025-05-31", "옥상달빛", "디깅 14", "u2"),
            gig("세종 음악창작소 누리락", "2023-05-27", "ADOY", "디깅 1", "u3"),   # 2년보다 옛날 → 빠짐
        ]
        stats = cra.venue_stats(rows, {}, since=date(2024, 11, 28))
        s = stats["세종 음악창작소 누리락"]
        self.assertEqual(s["gigs"], 2)          # 같은 날·같은 제목 = 1건
        self.assertEqual(s["teams"], 2)
        self.assertEqual(s["last"], "2026-11-28")

    def test_xref_maps_variant_to_canonical(self):
        rows = [gig("그린빈버찌라이브하우스", "2026-01-01", "A")]
        stats = cra.venue_stats(rows, {"그린빈버찌라이브하우스": "버찌"}, since=date(2025, 1, 1))
        self.assertIn("버찌", stats)


class PressLineupTest(unittest.TestCase):
    def test_venue_lineup_post_becomes_gig_row(self):
        r = {"pick_label": "venue_lineup", "outlet": "@vinta_suwon", "published_at": "2026-11-18",
             "artist_text": "band_heemee", "url": "https://www.instagram.com/p/x/"}
        g = cra.press_lineup_row(r)
        self.assertEqual((g["venue_text"], g["gig_date"], g["artist_text"]), ("@vinta_suwon", "2026-11-18", "band_heemee"))

    def test_other_press_rows_ignored(self):
        self.assertIsNone(cra.press_lineup_row({"pick_label": "pick", "outlet": "izm"}))


class RegionalTableTest(unittest.TestCase):
    def test_lists_only_non_seoul_master_venues_sorted_by_gigs(self):
        stats = {"세종 음악창작소 누리락": {"gigs": 2, "teams": 2, "last": "2026-11-28"}}
        table = cra.regional_table(MASTER, stats)
        names = [r["name"] for r in table]
        self.assertNotIn("A.O.R", names)
        self.assertEqual(names[0], "세종 음악창작소 누리락")
        self.assertEqual(table[1]["gigs"], 0)   # 버찌: 우리 기록 없음

    def test_skips_closed_venues(self):
        master = [*MASTER, {"name": "닫힌곳", "city": "부산", "province": "부산", "status": "closed"}]
        self.assertNotIn("닫힌곳", [r["name"] for r in cra.regional_table(master, {})])

    def test_city_summary_sums_by_city(self):
        table = [{"city": "세종", "gigs": 2, "teams": 2}, {"city": "세종", "gigs": 1, "teams": 1},
                 {"city": "대전", "gigs": 0, "teams": 0}]
        summary = {r["city"]: r for r in cra.city_summary(table)}
        self.assertEqual(summary["세종"]["gigs"], 3)
        self.assertEqual(summary["세종"]["venues"], 2)
        self.assertEqual(summary["대전"]["empty"], 1)


if __name__ == "__main__":
    unittest.main()
