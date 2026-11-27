"""lineup_roles: 공연 원본에서 단독·헤드라이너·서포트를 가려 팀별로 세기 (출연 순서 정보는 믿을 수 없어 쓰지 않음)."""
import csv
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import lineup_roles as lr  # noqa: E402

AS_OF = date(2026, 11, 27)


def g(url, d, title, acts, source="indistreet"):
    return lr.Gig(source=source, url=url, date=d, title=title, acts=tuple(acts))


GIGS = [
    g("u1", date(2024, 3, 1), "ROCKERS vol.1", [("a", "에이밴드"), ("b", "비밴드"), ("c", "씨밴드")]),       # 셋 다 서포트(제목에 이름 없음)
    g("u2", date(2024, 9, 1), "에이밴드 단독 콘서트", [("a", "에이밴드")]),                                  # a 단독
    g("u3", date(2025, 2, 1), "비밴드 EP 발매 공연 with 씨밴드", [("b", "비밴드"), ("c", "씨밴드")]),        # 제목에 둘 다 → 헤드라이너 모름
    g("u4", date(2025, 5, 1), "씨밴드 쇼케이스", [("c", "씨밴드"), ("d", "디밴드")]),                        # c 헤드라이너, d 서포트
    g("u5", date(2027, 1, 1), "에이밴드 단독", [("a", "에이밴드")]),                                         # 예정 공연
    g("u6", date(2025, 6, 1), "큰 축제", [(f"t{i}", f"팀{i}") for i in range(13)] + [("a", "에이밴드")]),   # 페스티벌(13팀 초과) 제외
]


class HeadlineTest(unittest.TestCase):
    def test_solo_is_headliner(self):
        self.assertEqual(lr.headliners(GIGS[1]), {"a"})

    def test_title_naming_exactly_one_act(self):
        self.assertEqual(lr.headliners(GIGS[3]), {"c"})
        self.assertEqual(lr.headliners(GIGS[2]), set())             # 두 팀이 다 제목에 → 모름
        self.assertEqual(lr.headliners(GIGS[0]), set())

    def test_short_names_do_not_match_by_accident(self):
        gig = g("x", date(2024, 1, 1), "A Night of Rock", [("a1", "A"), ("b1", "비")])
        self.assertEqual(lr.headliners(gig), set())


class TeamRolesTest(unittest.TestCase):
    def setUp(self):
        self.r = {row["team_key"]: row for row in lr.team_roles(GIGS, AS_OF)}

    def test_counts(self):
        a = self.r["a"]
        self.assertEqual((a["gigs"], a["solo_gigs"], a["headline_gigs"], a["support_gigs"]), (2, 1, 1, 1))
        self.assertAlmostEqual(a["headline_share"], 0.5)
        self.assertAlmostEqual(a["avg_lineup"], 2.0)               # (3 + 1) / 2 — 예정·페스티벌 제외
        self.assertNotIn("t1", self.r)

    def test_support_to_headline(self):
        self.assertEqual(self.r["a"]["support_to_headline"], 1)     # 서포트(2024-03) → 단독(2024-09)
        self.assertEqual(self.r["a"]["first_headline_date"], "2024-09-01")
        self.assertEqual(self.r["c"]["support_to_headline"], 1)     # 서포트(u1) → 헤드라이너(u4)
        self.assertEqual(self.r["d"]["support_to_headline"], 0)
        self.assertEqual(self.r["b"]["headline_gigs"], 0)            # u3 는 헤드라이너를 모르는 공연 → 서포트도 아님
        self.assertEqual(self.r["b"]["support_gigs"], 1)

    def test_csv_columns(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "lineup_roles.csv"
            lr.write_csv(list(self.r.values()), p)
            with open(p, encoding="utf-8") as f:
                self.assertEqual(next(csv.reader(f)), list(lr.FIELDS))


class FeaturesTest(unittest.TestCase):
    def test_only_before_cutoff_and_discovery_sources(self):
        gigs = GIGS + [g("p1", date(2024, 1, 1), "다른 밴드 단독", [("e", "다른 밴드")], source="indiego")]
        f = lr.role_features(gigs, date(2024, 6, 1), sources={"indistreet"})
        self.assertEqual(f["a"], {"solo_count": 0.0, "headline_share": 0.0, "avg_lineup": 3.0,
                                  "support_to_headline": 0.0})
        self.assertNotIn("e", f)                                     # 발굴 출처가 아님
        f2 = lr.role_features(GIGS, date(2025, 1, 1), sources={"indistreet"})
        self.assertEqual(f2["a"]["support_to_headline"], 1.0)
        self.assertAlmostEqual(f2["a"]["solo_count"], 0.6931, places=3)   # ln(1+1)


class SurveyTest(unittest.TestCase):
    def test_order_survey(self):
        s = lr.order_survey(GIGS)
        self.assertEqual(s["multi_gigs"], 3)                         # u1·u3·u4 (페스티벌 제외)
        self.assertEqual(s["title_named_position"], {"first": 1})   # u4: 씨밴드가 첫 줄


class RawTest(unittest.TestCase):
    def test_load_raw_maps_names_to_team_keys(self):
        cols = ["collected_at", "source", "collector", "source_id", "gig_date", "gig_time", "title", "venue_text",
                "artist_text", "artist_source_id", "gig_url", "artist_url"]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "raw_kr_gig_2026-11-27_indistreet.csv"
            with open(p, "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=cols)
                w.writeheader()
                for name in ("에이 밴드", "Bee", "Bee"):
                    w.writerow({**dict.fromkeys(cols, ""), "source": "indistreet", "gig_date": "2026-11-01",
                                "title": "밤", "artist_text": name, "gig_url": "https://x/1"})
            gigs = lr.load_raw(Path(d), {"bee": "비밴드키"})
        self.assertEqual(len(gigs), 1)
        self.assertEqual([k for k, _ in gigs[0].acts], ["에이밴드", "비밴드키"])   # 연결표로 대표 키, 같은 팀 중복 제거


if __name__ == "__main__":
    unittest.main()
