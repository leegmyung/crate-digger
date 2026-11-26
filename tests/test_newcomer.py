"""1.5단계 신인 판별 테스트 — 가짜 데이터로."""
import csv
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import newcomer as nc  # noqa: E402

AS_OF = "2026-11-26"


def prof(**kw):
    row = {"source": "melon", "artist_source_id": "1", "artist_text": "가상팀", "debut_date": "",
           "first_release_date": "", "album_count": "", "agency_text": "", "collected_at": "2026-11-26T21:00:00+09:00"}
    row.update(kw)
    return row


class JudgeTest(unittest.TestCase):
    def test_recent_debut_few_albums_is_newcomer(self):
        r = nc.judge(prof(debut_date="2025-06-01", album_count="3"), AS_OF)
        self.assertEqual(r["status"], "newcomer")
        self.assertEqual(r["years_since_first"], 1.5)
        self.assertEqual(r["albums"], 3)

    def test_old_debut_is_established(self):
        r = nc.judge(prof(debut_date="2016-12-21", first_release_date="2016-12-21", album_count="20"), AS_OF)
        self.assertEqual(r["status"], "established")

    def test_many_albums_is_established_even_if_recent(self):
        r = nc.judge(prof(first_release_date="2025-01-10", album_count="8"), AS_OF)
        self.assertEqual(r["status"], "established")
        self.assertIn("앨범", r["reason"])

    def test_earliest_of_debut_and_first_release(self):
        # 데뷔일은 최근이지만 앨범 목록에 더 오래된 발매가 있으면 그쪽이 첫 발매
        r = nc.judge(prof(debut_date="2025-12-01", first_release_date="2020-03-01", album_count="2"), AS_OF)
        self.assertEqual(r["status"], "established")
        self.assertEqual(r["years_since_first"], 6.7)

    def test_partial_date_reads_start_of_period(self):
        # '2024' → 2024-01-01 (기간 첫날 = 연차를 길게 보는 쪽)
        r = nc.judge(prof(debut_date="2024", album_count="1"), AS_OF)
        self.assertEqual(r["years_since_first"], 2.9)
        self.assertEqual(r["status"], "established")

    def test_boundary_exactly_two_years_is_newcomer(self):
        r = nc.judge(prof(first_release_date="2024-11-26", album_count="5"), AS_OF)
        self.assertEqual(r["status"], "newcomer")

    def test_missing_album_count_with_recent_debut_is_unknown(self):
        r = nc.judge(prof(first_release_date="2026-01-01", album_count=""), AS_OF)
        self.assertEqual(r["status"], "unknown")
        self.assertIsNone(r["albums"])
        self.assertIn("앨범 수", r["reason"])

    def test_missing_album_count_but_old_debut_is_established(self):
        r = nc.judge(prof(first_release_date="2010-01-01"), AS_OF)
        self.assertEqual(r["status"], "established")

    def test_no_dates_few_albums_is_unknown(self):
        r = nc.judge(prof(album_count="2"), AS_OF)
        self.assertEqual(r["status"], "unknown")
        self.assertIsNone(r["years_since_first"])

    def test_no_dates_many_albums_is_established(self):
        r = nc.judge(prof(album_count="12"), AS_OF)
        self.assertEqual(r["status"], "established")

    def test_thresholds_are_parameters(self):
        r = nc.judge(prof(first_release_date="2024-01-01", album_count="4"), AS_OF, max_years=3, max_albums=5)
        self.assertEqual(r["status"], "newcomer")
        r = nc.judge(prof(first_release_date="2026-01-01", album_count="4"), AS_OF, max_albums=3)
        self.assertEqual(r["status"], "established")

    def test_first_release_after_as_of_counts_as_newcomer(self):
        # 백테스트: 기준일 뒤에 첫 발매한 팀은 그 시점엔 아직 발매 전 → 0년
        r = nc.judge(prof(first_release_date="2027-03-01", album_count="1"), AS_OF)
        self.assertEqual(r["status"], "newcomer")
        self.assertEqual(r["years_since_first"], 0.0)


REL_COLS = ["collected_at", "source", "collector", "source_id", "released_at", "artist_text", "artist_source_id",
            "title", "release_type", "genre", "label_text", "track_count", "release_url", "distributor_text",
            "artist_key", "title_key"]
GIG_COLS = ["collected_at", "source", "collector", "source_id", "gig_date", "gig_time", "title", "venue_text",
            "artist_text", "artist_source_id", "gig_url", "artist_url"]
SEL_COLS = ["collected_at", "source", "collector", "program", "round", "stage", "announced_at", "artist_text", "url", "note"]
PRESS_COLS = ["collected_at", "source", "collector", "outlet", "published_at", "title", "url", "artist_text",
              "release_title", "is_pick", "pick_label", "artist_handle", "is_sponsored"]
PROF_COLS = ["collected_at", "source", "collector", "artist_source_id", "artist_text", "debut_date", "debut_title",
             "activity_type", "agency_text", "genre", "nationality", "fan_count", "album_count", "first_release_date",
             "youtube_url", "url", "artist_key"]


def write(path, cols, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})


class JudgeAllTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        write(d / "raw_kr_release_2026-11-26_melon.csv", REL_COLS, [
            # 멜론 번호로 프로필과 연결 (이름 표기가 달라도)
            {"source": "melon", "released_at": "2026-11-26", "artist_text": "새싹밴드", "artist_source_id": "900",
             "title": "첫곡", "release_url": "https://x/1"},
            # 이름 키로 프로필과 연결 (번호 없음)
            {"source": "melon", "released_at": "2026-11-26", "artist_text": "고참 (Veteran)", "title": "열번째",
             "release_url": "https://x/2"},
        ])
        write(d / "raw_kr_release_2026-11-26_poclanos.csv", REL_COLS, [
            # 프로필 없음, 우리 기록상 발매가 최근 → 약한 추정, unknown
            {"source": "poclanos", "released_at": "2026-11-20", "artist_text": "무명씨", "title": "a", "release_url": "https://p/1"},
            # 프로필 없음, 우리 기록에 3년 전 발매 → 적어도 3년 차 = established
            {"source": "poclanos", "released_at": "2023-05-01", "artist_text": "오래된팀", "title": "b", "release_url": "https://p/2"},
            {"source": "poclanos", "released_at": "2026-11-01", "artist_text": "오래된팀", "title": "c", "release_url": "https://p/3"},
        ])
        write(d / "raw_kr_gig_2026-11-26_indiego.csv", GIG_COLS, [
            {"source": "indiego", "gig_date": "2026-11-28", "artist_text": "공연만팀", "gig_url": "https://g/1"},
            {"source": "indiego", "gig_date": "2026-11-28", "artist_text": "고참", "gig_url": "https://g/1"},
        ])
        write(d / "raw_kr_selection_2026-11-26_yjh.csv", SEL_COLS, [
            {"source": "yjh", "program": "yoojaeha_finalist", "round": "37회", "stage": "selected",
             "announced_at": "2026-09", "artist_text": "선정만팀", "url": "https://s/1"},
            # 발매 기록은 없지만 20년 전에 선정된 팀 → 우리 수집 범위 밖에서 활동했을 것, 신인 아님
            {"source": "yjh", "program": "yoojaeha_finalist", "round": "17회", "stage": "selected",
             "announced_at": "2006", "artist_text": "옛선정팀", "url": "https://s/2"},
        ])
        write(d / "raw_press_2026-11-26_instagram.csv", PRESS_COLS, [
            {"source": "instagram", "outlet": "@mag", "published_at": "2026-11-25", "title": "t", "url": "https://i/1",
             "artist_text": "언급만팀", "is_pick": "1"},
        ])
        write(d / "raw_artist_profile_2026-11-26_melon.csv", PROF_COLS, [
            {"source": "melon", "artist_source_id": "900", "artist_text": "Sprout Band",
             "first_release_date": "2026-03-01", "album_count": "2", "url": "https://m/900"},
            {"source": "melon", "artist_source_id": "901", "artist_text": "고참 (Veteran)", "debut_date": "2012-01-01",
             "album_count": "30", "url": "https://m/901"},
        ])
        self.res = {r["artist_key"]: r for r in nc.judge_all(d, AS_OF)}

    def tearDown(self):
        self.tmp.cleanup()

    def test_profile_matched_by_melon_artist_id(self):
        self.assertEqual(self.res["새싹밴드"]["status"], "newcomer")
        self.assertEqual(self.res["새싹밴드"]["albums"], 2)

    def test_profile_matched_by_name_key_and_sources_merged(self):
        r = self.res["고참"]
        self.assertEqual(r["status"], "established")
        self.assertEqual(r["sources"], "release|gig")

    def test_gig_only_without_profile_is_newcomer(self):
        self.assertEqual(self.res["공연만팀"]["status"], "newcomer")
        self.assertEqual(self.res["공연만팀"]["reason"], "발매 기록 없음·공연/선정만")
        self.assertEqual(self.res["선정만팀"]["status"], "newcomer")

    def test_old_selection_without_release_is_not_newcomer(self):
        r = self.res["옛선정팀"]
        self.assertEqual(r["status"], "established")
        self.assertIn("첫 활동", r["reason"])
        self.assertEqual(r["years_since_first"], 20.9)   # '2006' → 2006-01-01

    def test_press_only_is_unknown(self):
        self.assertEqual(self.res["언급만팀"]["status"], "unknown")

    def test_release_without_profile_is_weak_unknown(self):
        r = self.res["무명씨"]
        self.assertEqual(r["status"], "unknown")
        self.assertIn("약한 추정", r["reason"])
        self.assertEqual(r["years_since_first"], 0.0)

    def test_old_release_in_our_data_is_established(self):
        r = self.res["오래된팀"]
        self.assertEqual(r["status"], "established")
        self.assertEqual(r["albums"], 2)

    def test_every_candidate_artist_appears_once(self):
        self.assertEqual(sorted(self.res), sorted(["새싹밴드", "고참", "무명씨", "오래된팀", "공연만팀", "선정만팀", "언급만팀", "옛선정팀"]))

    def test_write_csv_and_counts(self):
        rows = list(self.res.values())
        out = Path(self.tmp.name) / "derived" / "newcomer_x.csv"
        nc.write_csv(rows, out)
        with open(out, encoding="utf-8") as fh:
            back = list(csv.DictReader(fh))
        self.assertEqual(len(back), 8)
        self.assertEqual(list(back[0]), nc.OUT_COLUMNS)
        by_status, by_table = nc.counts(rows)
        self.assertEqual(by_status["newcomer"], 3)
        self.assertEqual(by_table["gig"]["newcomer"], 1)
        self.assertEqual(by_table["gig"]["established"], 1)


if __name__ == "__main__":
    unittest.main()
