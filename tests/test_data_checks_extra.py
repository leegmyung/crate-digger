"""매일 데이터 검사 — 2026-11-28에 생긴 데이터 쪽(data_checks_extra): 공연장 좌표·체급, venues_kr 짝, 앱 보조 데이터, 알림, 팀 표 새 칸."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import data_checks_extra as dx  # noqa: E402

TODAY = "2026-11-27"


def sig(team, branch="공연", source="indistreet", date="2026-11-20", program=""):
    return {"team_key": team, "branch": branch, "source": source, "program": program, "signal_date": date}


class NewDataTest(unittest.TestCase):
    """2026-11-28에 생긴 데이터: 공연장 좌표·체급, venues_kr 짝, 앱 보조 데이터, 알림, 팀 표 새 칸."""

    def gigs(self):
        return [sig("a", "공연", date="2026-11-01") | {"venue": "클럽A"}, sig("b", "공연", date="2026-11-01") | {"venue": "클럽A"},
                sig("a", "공연", date="2026-11-02") | {"venue": "클럽B"}, sig("c", "공연", date="2026-11-03") | {"venue": "공연장 미정"},
                sig("a", "큐레이션", "izm", "2026-11-04")]

    def test_venue_coverage_counts_gig_nights(self):
        prof = {"클럽A": {"lat": 37.5, "tier": "S"}, "클럽B": {"lat": 37.5, "tier": "M"}}
        c = dx.check_venue_coverage(self.gigs(), prof)
        self.assertEqual(c.status, "pass")
        self.assertIn("2/2", c.value)                   # 공연 밤 2개(클럽A 11-01 한 번, 클럽B 11-02), '공연장 미정' 제외
        c = dx.check_venue_coverage(self.gigs(), {"클럽A": {"lat": 37.5}})
        self.assertEqual(c.status, "fail")              # 체급 0/2

    def test_venue_master_unmatched(self):
        match = lambda names: {n: 0 for n in names if n == "클럽A"}
        c = dx.check_venue_master(self.gigs(), match)
        self.assertEqual(c.status, "warn")              # 클럽B 1밤 / 2밤 = 50%
        self.assertIn("클럽B", c.value)
        self.assertEqual(dx.check_venue_master(self.gigs(), lambda names: {n: 0 for n in names}).status, "pass")

    def test_venue_master_skips_non_venue_names(self):
        """기획·레이블·행사 인스타 계정('@계정')과 not_venue 이름은 분모·분자 모두에서 뺀다 (대소문자 무시)."""
        gigs = self.gigs() + [sig("d", "공연", date="2026-11-05") | {"venue": "@Promo_Crew"},
                              sig("e", "공연", date="2026-11-06") | {"venue": "온라인 중계"}]
        match = lambda names: {n: 0 for n in names if n == "클럽A"}
        c = dx.check_venue_master(gigs, match, skip={"@promo_crew", "온라인 중계"})
        self.assertIn("1/2", c.value)                   # 클럽B 1밤 / (클럽A·클럽B 2밤) — 빠진 2밤은 안 셈
        self.assertNotIn("Promo_Crew", c.value)
        self.assertIn("공연장 아님 2밤 뺌", c.value)

    def test_non_venue_skip_names_from_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            (root / "config" / "insta_accounts.json").write_text(
                '{"accounts": [{"handle": "Promo_Crew", "role": "promoter_showcase"},'
                ' {"handle": "club_x", "role": "venue_showcase"}]}', encoding="utf-8")
            (root / "config" / "venue_capacity.json").write_text(
                '{"venues": {"온라인 중계": {"not_venue": true}, "클럽A": {"capacity": 100}}}', encoding="utf-8")
            self.assertEqual(dx._non_venue_skip(root), {"@promo_crew", "온라인 중계"})
            self.assertEqual(dx._non_venue_skip(Path(tmp) / "none"), set())

    def test_extras_all_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            lab = Path(tmp)
            for name in dx.EXTRAS:
                (lab / name).write_text("x\n1\n", encoding="utf-8")
            meta = {"extras": [n.split(".")[0] for n in dx.EXTRAS], "extras_rows": {n: 1 for n in dx.EXTRAS}}
            self.assertEqual(dx.check_extras(meta, lab).status, "pass")
            (lab / dx.EXTRAS[0]).unlink()
            c = dx.check_extras(meta, lab)
            self.assertEqual(c.status, "fail")
            self.assertIn(dx.EXTRAS[0], c.value)
            self.assertEqual(dx.check_extras({}, lab).status, "fail")

    def test_alerts_future_and_duplicates(self):
        doc = {"as_of": TODAY, "alerts": [
            {"type": "new_gig", "team_key": "a", "date": "2026-12-01"},
            {"type": "big_venue_first", "team_key": "a", "date": "2026-12-01"},
            {"type": "new_outcome", "team_key": "b", "date": "2026-11-01"}]}
        self.assertEqual(dx.check_alerts(doc).status, "pass")   # 공연 기반 알림은 미래 날짜가 정상
        doc["alerts"].append({"type": "new_outcome", "team_key": "c", "date": "2027-01-01"})
        doc["alerts"].append({"type": "new_gig", "team_key": "a", "date": "2026-12-01"})
        c = dx.check_alerts(doc)
        self.assertEqual(c.status, "warn")
        self.assertIn("new_outcome", c.value)
        self.assertIn("중복 1", c.value)
        self.assertEqual(dx.check_alerts({}).status, "skip")

    def test_team_labels_distribution(self):
        teams = [{"newcomer_check": "verified", "genre_confidence": "profile"},
                 {"newcomer_check": "first_seen", "genre_confidence": ""}]
        c = dx.check_team_labels(teams)
        self.assertEqual(c.status, "pass")
        self.assertIn("verified 1", c.value)
        c = dx.check_team_labels(teams + [{"newcomer_check": "maybe", "genre_confidence": "guess"}])
        self.assertEqual(c.status, "warn")
        self.assertIn("maybe", c.value)


if __name__ == "__main__":
    unittest.main()
