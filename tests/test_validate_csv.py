"""수집 CSV 검사기 테스트.

    python3 -m unittest discover -s tests
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import validate_csv  # noqa: E402

SAMPLES = ROOT / "data" / "samples"

RELEASE_HEADER = (
    "collected_at,source,collector,source_id,released_at,artist_text,artist_source_id,"
    "title,release_type,genre,label_text,track_count,release_url"
)
GOOD_RELEASE = (
    "2026-11-26T09:30:00+09:00,poclanos,script,1,2026-11-26,가상팀,,제목,EP,rock,,5,"
    "https://example.com/a/1"
)


def write_csv(dir_path, name, text, bom=False):
    path = Path(dir_path) / name
    data = ("﻿" if bom else "") + text + "\n"
    path.write_text(data, encoding="utf-8")
    return path


def errors(issues):
    return [i for i in issues if i.level == "error"]


class SampleFilesTest(unittest.TestCase):
    def test_all_sample_files_pass(self):
        files = sorted(SAMPLES.glob("raw_*.csv"))
        self.assertGreaterEqual(len(files), 4)
        for f in files:
            with self.subTest(file=f.name):
                self.assertEqual(errors(validate_csv.validate_file(f)), [])


class TableDetectionTest(unittest.TestCase):
    def test_table_from_file_name(self):
        self.assertEqual(validate_csv.table_for("raw_kr_release_2026-11-26_bugs.csv"), "raw_kr_release")
        self.assertEqual(validate_csv.table_for("raw_kr_gig_2026-11-26_indiego.csv"), "raw_kr_gig")

    def test_unknown_file_name_is_error(self):
        with tempfile.TemporaryDirectory() as d:
            p = write_csv(d, "something.csv", RELEASE_HEADER + "\n" + GOOD_RELEASE)
            issues = validate_csv.validate_file(p)
        self.assertEqual(len(errors(issues)), 1)
        self.assertIn("파일 이름", issues[0].message)


class RuleTest(unittest.TestCase):
    def check(self, header, row, name="raw_kr_release_2026-11-26_x.csv", bom=False):
        with tempfile.TemporaryDirectory() as d:
            p = write_csv(d, name, header + "\n" + row, bom=bom)
            return validate_csv.validate_file(p)

    def test_good_row_passes(self):
        self.assertEqual(errors(self.check(RELEASE_HEADER, GOOD_RELEASE)), [])

    def test_utf8_bom_is_accepted(self):
        self.assertEqual(errors(self.check(RELEASE_HEADER, GOOD_RELEASE, bom=True)), [])

    def test_missing_required_column(self):
        header = RELEASE_HEADER.replace(",artist_text", "")
        row = GOOD_RELEASE.replace(",가상팀", "")
        issues = errors(self.check(header, row))
        self.assertTrue(any(i.column == "artist_text" and i.row == 1 for i in issues))

    def test_empty_required_value_reports_line(self):
        issues = errors(self.check(RELEASE_HEADER, GOOD_RELEASE.replace(",가상팀,", ",,")))
        self.assertEqual([(i.row, i.column) for i in issues], [(2, "artist_text")])

    def test_collected_at_needs_timezone(self):
        row = GOOD_RELEASE.replace("2026-11-26T09:30:00+09:00", "2026-11-26 09:30:00")
        issues = errors(self.check(RELEASE_HEADER, row))
        self.assertEqual([i.column for i in issues], ["collected_at"])

    def test_partial_release_date_ok_but_slash_format_rejected(self):
        ok = GOOD_RELEASE.replace(",2026-11-26,", ",2026-11,")
        bad = GOOD_RELEASE.replace(",2026-11-26,", ",2026/11/26,")
        self.assertEqual(errors(self.check(RELEASE_HEADER, ok)), [])
        self.assertEqual([i.column for i in errors(self.check(RELEASE_HEADER, bad))], ["released_at"])

    def test_unknown_source_code_rejected(self):
        issues = errors(self.check(RELEASE_HEADER, GOOD_RELEASE.replace(",poclanos,", ",naver,")))
        self.assertEqual([i.column for i in issues], ["source"])

    def test_bad_url_and_track_count(self):
        row = GOOD_RELEASE.replace("https://example.com/a/1", "example.com/a/1").replace(",5,", ",다섯,")
        cols = sorted(i.column for i in errors(self.check(RELEASE_HEADER, row)))
        self.assertEqual(cols, ["release_url", "track_count"])

    def test_duplicate_key_rows(self):
        issues = errors(self.check(RELEASE_HEADER, GOOD_RELEASE + "\n" + GOOD_RELEASE))
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].row, 3)
        self.assertIn("중복", issues[0].message)

    def test_extra_column_is_warning_only(self):
        issues = self.check(RELEASE_HEADER + ",memo", GOOD_RELEASE + ",메모")
        self.assertEqual(errors(issues), [])
        self.assertTrue(any(i.level == "warning" and i.column == "memo" for i in issues))

    def test_press_is_pick_must_be_0_or_1(self):
        header = "collected_at,source,collector,outlet,published_at,title,url,artist_text,release_title,is_pick,pick_label"
        row = "2026-11-26T10:00:00+09:00,musicy,aside,음악취향Y,2026-11-24,t,https://example.com/r,팀,,yes,"
        issues = errors(self.check(header, row, name="raw_press_2026-11-26_musicy.csv"))
        self.assertEqual([i.column for i in issues], ["is_pick"])

    def test_press_instagram_handle_and_sponsored_flag(self):
        header = ("collected_at,source,collector,outlet,published_at,title,url,artist_text,release_title,"
                  "is_pick,pick_label,artist_handle,is_sponsored")
        good = ("2026-11-26T10:00:00+09:00,instagram,aside,@pushplay_mag,2026-11-25,소개,"
                "https://www.instagram.com/p/x/,정용찬,,1,,@jeong_yong_chan,0")
        self.assertEqual(errors(self.check(header, good, name="raw_press_2026-11-26_instagram.csv")), [])
        bad = good.replace("@jeong_yong_chan,0", "jeong yong chan,협찬")
        cols = sorted(i.column for i in errors(self.check(header, bad, name="raw_press_2026-11-26_instagram.csv")))
        self.assertEqual(cols, ["artist_handle", "is_sponsored"])

    def test_outcome_media_feature(self):
        header = "collected_at,source,collector,program,round,announced_at,result,artist_text,url,note"
        row = "2026-11-26T11:00:00+09:00,aside,aside,media_bandwagon,2026-11,2026-11-26,featured,팀,https://example.com/o,협찬 아님"
        issues = errors(self.check(header, row, name="raw_outcome_2026-11-26_aside.csv"))
        self.assertEqual(issues, [])

    def test_gig_time_format(self):
        header = ("collected_at,source,collector,source_id,gig_date,gig_time,title,venue_text,"
                  "artist_text,artist_source_id,gig_url,artist_url")
        row = "2026-11-26T10:10:00+09:00,indiego,aside,e1,2026-11-28,7시반,t,홀,팀,,https://example.com/e1,"
        issues = errors(self.check(header, row, name="raw_kr_gig_2026-11-26_indiego.csv"))
        self.assertEqual([i.column for i in issues], ["gig_time"])

    def test_outcome_program_code(self):
        header = "collected_at,source,collector,program,round,announced_at,result,artist_text,url,note"
        row = "2026-11-26T11:00:00+09:00,manual,manual,unknown_award,2026,2026-05,selected,팀,https://example.com/o,"
        issues = errors(self.check(header, row, name="raw_outcome_2026-11-26_manual.csv"))
        self.assertEqual([i.column for i in issues], ["program"])


class SelectionTest(unittest.TestCase):
    HEADER = "collected_at,source,collector,program,round,stage,announced_at,artist_text,url,note"
    ROW = "2026-11-26T12:00:00+09:00,mapoindie,aside,indiscovery,2026,challenger,2026-06,가상팀,https://example.com/s,"

    def check(self, row):
        with tempfile.TemporaryDirectory() as d:
            p = write_csv(d, "raw_kr_selection_2026-11-26_mapoindie.csv", self.HEADER + "\n" + row)
            return errors(validate_csv.validate_file(p))

    def test_good_selection_row(self):
        self.assertEqual(self.check(self.ROW), [])

    def test_selection_program_must_be_candidate_program_not_outcome(self):
        issues = self.check(self.ROW.replace(",indiscovery,", ",hello_rookie_year,"))
        self.assertEqual([i.column for i in issues], ["program"])

    def test_stage_code(self):
        issues = self.check(self.ROW.replace(",challenger,", ",1차,"))
        self.assertEqual([i.column for i in issues], ["stage"])


class SameProgramRuleTest(unittest.TestCase):
    def test_candidate_and_outcome_codes_do_not_overlap(self):
        import csv_schema
        self.assertEqual(csv_schema.SELECTION_PROGRAMS & csv_schema.PROGRAMS, set())

    def test_same_program_map_points_to_known_codes(self):
        import csv_schema
        for sel, outs in csv_schema.SAME_PROGRAM.items():
            self.assertIn(sel, csv_schema.SELECTION_PROGRAMS)
            self.assertTrue(outs and outs <= csv_schema.PROGRAMS, sel)

    def test_hello_rookie_applicants_exclude_hello_rookie_outcomes(self):
        import csv_schema
        self.assertEqual(csv_schema.excluded_outcomes("hello_rookie_applicant"),
                         {"hello_rookie", "hello_rookie_year"})
        self.assertEqual(csv_schema.excluded_outcomes("indiscovery"), set())


class CliTest(unittest.TestCase):
    def test_exit_code(self):
        good = sorted(SAMPLES.glob("raw_*.csv"))[0]
        self.assertEqual(validate_csv.main([str(good)]), 0)
        with tempfile.TemporaryDirectory() as d:
            bad = write_csv(d, "raw_kr_release_2026-11-26_x.csv", RELEASE_HEADER + "\n" + GOOD_RELEASE.replace(",가상팀,", ",,"))
            self.assertEqual(validate_csv.main([str(bad)]), 1)


if __name__ == "__main__":
    unittest.main()
