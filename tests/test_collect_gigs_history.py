"""인디스트릿 지난 공연 수집기(collect_gigs_history) 변환 로직 테스트 — aside 없이 가상 데이터로."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import collect_gigs_history as gh  # noqa: E402
import validate_csv  # noqa: E402

AT = "2026-11-26T18:00:00+09:00"

GIG = {
    "url": "https://indistreet.com/gigs/m3jdruv57j6ok0ihal03fk96",
    "name": "가상 단독 콘서트",
    "startDate": "2024-01-08T11:00:00.000Z",
    "venue": "가상홀",
    "address": "서울 마포구 가상로 1",
    "performers": [{"name": "가상밴드", "url": "https://indistreet.com/artists/gasang-band"}],
}

FESTIVAL = {
    "url": "https://indistreet.com/programs/gasang-festa-2025-abc",
    "title": "GASANG FESTA 2025",
    "days": [
        {"label": "DAY 1", "date": "2025-09-05",
         "artists": [{"name": "가상밴드", "url": "/ko/artists/gasang-band"},
                     {"name": "두번째팀", "url": ""}]},
        {"label": "DAY 2", "date": "2025-09-06",
         "artists": [{"name": "가상밴드", "url": "/ko/artists/gasang-band"}]},
    ],
}


class WeekTest(unittest.TestCase):
    def test_week_offset_counts_mondays_back_from_this_week(self):
        # 2026-11-26(목)이 속한 주 = 0, 2024-01-08이 속한 주 = -150 (사이트에서 확인한 값)
        self.assertEqual(gh.week_offset("2026-11-26", "2026-11-26"), 0)
        self.assertEqual(gh.week_offset("2026-11-16", "2026-11-26"), -1)
        self.assertEqual(gh.week_offset("2024-01-14", "2026-11-26"), -150)

    def test_weeks_between_lists_oldest_first_with_monday(self):
        weeks = gh.weeks_between("2024-01-03", "2024-01-15", "2026-11-26")
        self.assertEqual(weeks, [(-151, "2024-01-01"), (-150, "2024-01-08"), (-149, "2024-01-15")])


class TimeTest(unittest.TestCase):
    def test_utc_start_converted_to_kst(self):
        self.assertEqual(gh.to_kst("2024-01-08T11:00:00.000Z"), "2024-01-08T20:00:00+09:00")

    def test_after_midnight_kst_moves_date(self):
        self.assertEqual(gh.to_kst("2024-01-08T15:30:00Z"), "2024-01-09T00:30:00+09:00")

    def test_non_utc_or_date_only_left_alone(self):
        self.assertEqual(gh.to_kst("2024-01-08T19:00:00+09:00"), "2024-01-08T19:00:00+09:00")
        self.assertEqual(gh.to_kst("2024-01-08"), "2024-01-08")
        self.assertEqual(gh.to_kst(""), "")


class GigRowsTest(unittest.TestCase):
    def test_same_format_as_daily_collector_with_kst_time(self):
        r = gh.gig_rows(GIG, AT)[0]
        self.assertEqual((r["source"], r["collector"]), ("indistreet", "aside"))
        self.assertEqual((r["gig_date"], r["gig_time"]), ("2024-01-08", "20:00"))
        self.assertEqual(r["source_id"], "m3jdruv57j6ok0ihal03fk96")
        self.assertEqual(r["artist_source_id"], "gasang-band")
        self.assertEqual(r["venue_text"], "가상홀 (서울 마포구 가상로 1)")


class ProgramRowsTest(unittest.TestCase):
    def test_one_row_per_day_and_artist_with_festival_title(self):
        rows = gh.program_rows(FESTIVAL, AT, "2024-01-01", "2026-11-25")
        self.assertEqual(len(rows), 3)
        r = rows[0]
        self.assertEqual(r["title"], "[페스티벌] GASANG FESTA 2025 DAY 1")
        self.assertEqual(r["gig_date"], "2025-09-05")
        self.assertEqual(r["gig_url"], "https://indistreet.com/programs/gasang-festa-2025-abc#2025-09-05")
        self.assertEqual(r["source_id"], "gasang-festa-2025-abc#2025-09-05")
        self.assertEqual(r["artist_url"], "https://indistreet.com/artists/gasang-band")
        self.assertEqual(r["artist_source_id"], "gasang-band")
        self.assertEqual(rows[1]["artist_url"], "")

    def test_days_outside_range_dropped(self):
        rows = gh.program_rows(FESTIVAL, AT, "2025-09-06", "2026-11-25")
        self.assertEqual([r["gig_date"] for r in rows], ["2025-09-06"])

    def test_day_without_date_dropped(self):
        prog = dict(FESTIVAL, days=[dict(FESTIVAL["days"][0], date="")])
        self.assertEqual(gh.program_rows(prog, AT, "2024-01-01", "2026-11-25"), [])


class UrlTest(unittest.TestCase):
    def test_absolute_and_language_prefix_removed(self):
        self.assertEqual(gh.abs_url("/ko/programs/x-1"), "https://indistreet.com/programs/x-1")
        self.assertEqual(gh.abs_url("/gigs/abc"), "https://indistreet.com/gigs/abc")
        self.assertEqual(gh.abs_url("https://indistreet.com/en/artists/a"), "https://indistreet.com/artists/a")
        self.assertEqual(gh.abs_url(""), "")


class StateTest(unittest.TestCase):
    def test_round_trip_and_missing_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "state" / "s.json"
            st = gh.load_state(path)
            self.assertEqual(st, {"weeks_done": [], "gigs_done": [], "programs_done": []})
            st = gh.mark(st, "weeks_done", ["2024-01-01"])
            gh.save_state(path, st)
            self.assertEqual(gh.load_state(path)["weeks_done"], ["2024-01-01"])

    def test_mark_does_not_mutate_and_dedups(self):
        st = {"weeks_done": ["a"], "gigs_done": [], "programs_done": []}
        new = gh.mark(st, "weeks_done", ["a", "b"])
        self.assertEqual(st["weeks_done"], ["a"])
        self.assertEqual(new["weeks_done"], ["a", "b"])


class OutputTest(unittest.TestCase):
    def test_written_file_passes_validator(self):
        rows = gh.gig_rows(GIG, AT) + gh.program_rows(FESTIVAL, AT, "2024-01-01", "2026-11-25")
        with tempfile.TemporaryDirectory() as d:
            writer = gh.CsvAppender(Path(d), "2026-11-26")
            writer.write(rows)
            writer.close()
            self.assertEqual(writer.path.name, "raw_kr_gig_2026-11-26_indistreet_history.csv")
            errs = [i for i in validate_csv.validate_file(writer.path) if i.level == "error"]
        self.assertEqual(errs, [])

    def test_existing_file_not_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            first = gh.CsvAppender(Path(d), "2026-11-26")
            first.write(gh.gig_rows(GIG, AT))
            first.close()
            second = gh.CsvAppender(Path(d), "2026-11-26")
            second.close()
            self.assertNotEqual(first.path, second.path)
            self.assertTrue(second.path.name.startswith("raw_kr_gig_2026-11-26_indistreet_history_"))


class ReplResultTest(unittest.TestCase):
    def test_reuses_daily_parser(self):
        out = json.dumps({"run": {"content": [{"type": "text", "text": "RESULT [1]"}], "error": None}})
        self.assertEqual(gh.parse_repl_output(out), [1])


class RangeBoundaryTest(unittest.TestCase):
    """범위 밖 공연·경계 주는 '끝남'으로 적지 않는다 — 나중에 더 이른 --since로 되짚을 때 빠지지 않게."""

    def test_week_fully_inside_only_when_all_seven_days_in_range(self):
        self.assertTrue(gh.week_fully_inside("2023-12-04", "2023-12-01", "2023-12-31"))
        self.assertFalse(gh.week_fully_inside("2023-11-27", "2023-12-01", "2023-12-31"))
        self.assertFalse(gh.week_fully_inside("2023-12-25", "2023-12-01", "2023-12-30"))

    def test_out_of_range_gig_not_marked_done(self):
        inside = dict(GIG, url="https://indistreet.com/gigs/in", startDate="2024-01-08T11:00:00.000Z")
        outside = dict(GIG, url="https://indistreet.com/gigs/out", startDate="2023-12-30T11:00:00.000Z")
        original = gh.run_with_retry
        gh.run_with_retry = lambda js, label: [inside, outside]
        try:
            with tempfile.TemporaryDirectory() as d:
                old_state_path = gh.STATE_PATH
                gh.STATE_PATH = Path(d) / "s.json"
                try:
                    writer = gh.CsvAppender(Path(d), "2026-11-28")
                    stats = {"gigs": 0, "no_performer": 0, "failed": 0, "not_found": 0}
                    st = gh._process_gigs([inside["url"], outside["url"]], gh.load_state(gh.STATE_PATH),
                                          writer, stats, "2024-01-01", "2024-01-31")
                    writer.close()
                finally:
                    gh.STATE_PATH = old_state_path
        finally:
            gh.run_with_retry = original
        self.assertEqual(st["gigs_done"], [inside["url"]])
        self.assertEqual(stats["gigs"], 1)


if __name__ == "__main__":
    unittest.main()
