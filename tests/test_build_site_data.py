"""진행판용 공개 데이터(docs/data/collect.json) 만들기 테스트."""
import csv
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_site_data as bsd  # noqa: E402

COLS = ["collected_at", "source", "collector", "source_id", "released_at", "artist_text",
        "artist_source_id", "title", "release_type", "genre", "label_text", "track_count", "release_url"]


def row(**kw):
    base = dict.fromkeys(COLS, "")
    base.update(collected_at="2026-11-26T15:00:00+09:00", source="poclanos", collector="script",
                released_at="2026-11-26", artist_text="A", title="T", release_url="https://example.com/1",
                label_text="비공개해도 되는 값", genre="rock")
    base.update(kw)
    return base


def write(dir_path, name, rows):
    path = Path(dir_path) / name
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    return path


def write_rows(dir_path, name, cols, rows):
    path = Path(dir_path) / name
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    return path


class BuildTest(unittest.TestCase):
    def test_counts_per_day_and_source_and_public_fields_only(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "raw_kr_release_2026-11-25_poclanos.csv", [row(collected_at="2026-11-25T15:00:00+09:00")])
            write(d, "raw_kr_release_2026-11-26_poclanos.csv",
                  [row(), row(artist_text="B", release_url="https://example.com/2", released_at="2026-11-25")])
            data = bsd.build(Path(d), recent_limit=10)
        self.assertEqual(data["runs"], [
            {"date": "2026-11-26", "source": "poclanos", "table": "raw_kr_release", "rows": 2, "file_ok": True,
             "prev_rows": 1},
            {"date": "2026-11-25", "source": "poclanos", "table": "raw_kr_release", "rows": 1, "file_ok": True,
             "prev_rows": None},
        ])
        recent = data["recent_releases"]
        self.assertEqual([r["artist"] for r in recent], ["A", "B"])          # 발매일 최신순
        self.assertEqual(set(recent[0]), {"released_at", "artist", "title", "type", "source", "url"})

    def test_same_release_from_two_files_listed_once(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "raw_kr_release_2026-11-25_poclanos.csv", [row()])
            write(d, "raw_kr_release_2026-11-26_poclanos.csv", [row()])
            data = bsd.build(Path(d), recent_limit=10)
        self.assertEqual(len(data["recent_releases"]), 1)

    def test_invalid_file_is_flagged_not_published(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "raw_kr_release_2026-11-26_poclanos.csv", [row(artist_text="")])
            data = bsd.build(Path(d), recent_limit=10)
        self.assertFalse(data["runs"][0]["file_ok"])
        self.assertEqual(data["recent_releases"], [])

    def test_gigs_grouped_per_gig_with_artists(self):
        gig_cols = ["collected_at", "source", "collector", "source_id", "gig_date", "gig_time", "title",
                    "venue_text", "artist_text", "artist_source_id", "gig_url", "artist_url"]
        base = dict.fromkeys(gig_cols, "")
        base.update(collected_at="2026-11-26T18:00:00+09:00", source="indiego", collector="aside",
                    gig_date="2026-11-27", gig_time="19:30", title="밤", venue_text="클럽 빵 (서울 마포구 어딘가)",
                    gig_url="https://example.com/e/1")
        rows = [dict(base, artist_text="A"), dict(base, artist_text="B"),
                dict(base, gig_date="2026-11-26", gig_url="https://example.com/e/2", artist_text="C")]
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "raw_kr_gig_2026-11-26_indiego.csv"
            with open(path, "w", encoding="utf-8", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=gig_cols)
                w.writeheader()
                w.writerows(rows)
            data = bsd.build(Path(d), recent_limit=10)
        gigs = data["upcoming_gigs"]
        self.assertEqual([g["artists"] for g in gigs], [["C"], ["A", "B"]])   # 날짜순
        self.assertEqual(gigs[1]["venue"], "클럽 빵")                          # 주소는 공개하지 않음
        self.assertEqual(set(gigs[0]), {"date", "time", "venue", "title", "artists", "source", "url"})

    def test_venue_name_keeps_branch_from_paren(self):
        # 상상마당 옛 표기: 지점이 괄호에 있으면 주소처럼 잘려 나가지 않게 '건물 + 홀'로 (venue_xref 와 같은 규칙)
        self.assertEqual(bsd._venue_name("라이브홀 (KT&amp;G 상상마당 홍대)"), "KT&G 상상마당 홍대 라이브홀")
        self.assertEqual(bsd._venue_name("클럽 빵 (서울 마포구 어딘가)"), "클럽 빵")
        self.assertEqual(bsd._venue_name(None), "")

    def test_empty_folder(self):
        with tempfile.TemporaryDirectory() as d:
            data = bsd.build(Path(d), recent_limit=10)
        self.assertEqual((data["runs"], data["recent_releases"]), ([], []))
        self.assertEqual((data["selections"], data["cross_branch"]), ([], []))

    def test_same_day_rerun_files_merged_into_one_run(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "raw_kr_release_2026-11-26_poclanos.csv", [row()])
            write(d, "raw_kr_release_2026-11-26_poclanos_201156.csv", [row(artist_text="B", release_url="https://example.com/2")])
            data = bsd.build(Path(d), recent_limit=10)
        self.assertEqual(data["runs"], [
            {"date": "2026-11-26", "source": "poclanos", "table": "raw_kr_release", "rows": 2, "file_ok": True,
             "prev_rows": None}])

    def test_selections_and_cross_branch_summary(self):
        sel_cols = ["collected_at", "source", "collector", "program", "round", "stage", "announced_at", "artist_text", "url", "note"]
        gig_cols = ["collected_at", "source", "collector", "source_id", "gig_date", "gig_time", "title", "venue_text",
                    "artist_text", "artist_source_id", "gig_url", "artist_url"]
        with tempfile.TemporaryDirectory() as d:
            write_rows(d, "raw_kr_selection_2026-11-26_busan.csv", sel_cols, [
                dict(collected_at="2026-11-26T20:00:00+09:00", source="busanrock", collector="script", program="burock_rookies",
                     round="2026", stage="selected", announced_at="2026-08", artist_text="천둥오리", url="https://example.com/s", note="TOP 10")])
            write_rows(d, "raw_kr_gig_2026-11-26_indiego.csv", gig_cols, [
                dict(collected_at="2026-11-26T18:00:00+09:00", source="indiego", collector="aside", source_id="1", gig_date="2026-11-28",
                     gig_time="19:00", title="밤", venue_text="클럽 빵 (주소)", artist_text="천둥 오리", artist_source_id="",
                     gig_url="https://example.com/g", artist_url="")])
            write(d, "raw_kr_release_2026-11-26_poclanos.csv", [row(artist_text="혼자팀")])
            data = bsd.build(Path(d), recent_limit=10)
        self.assertEqual(data["selections"], [{"program": "burock_rookies", "round": "2026", "stage": "selected",
                                               "announced_at": "2026-08", "artist": "천둥오리", "url": "https://example.com/s"}])
        self.assertEqual(data["cross_branch"], [{"artist": "천둥오리", "branches": ["공연", "선정·지원"]}])


class PrevRowsTest(unittest.TestCase):
    def test_each_run_gets_previous_run_rows_of_same_source(self):
        runs = bsd._merge_runs([
            {"date": "2026-11-25", "table": "raw_kr_gig", "source": "x", "rows": 100, "file_ok": True},
            {"date": "2026-11-26", "table": "raw_kr_gig", "source": "x", "rows": 10, "file_ok": True},
            {"date": "2026-11-26", "table": "raw_press", "source": "y", "rows": 5, "file_ok": True},
        ])
        by = {(r["date"], r["source"]): r for r in runs}
        self.assertEqual(by[("2026-11-26", "x")]["prev_rows"], 100)
        self.assertIsNone(by[("2026-11-25", "x")]["prev_rows"])
        self.assertIsNone(by[("2026-11-26", "y")]["prev_rows"])


if __name__ == "__main__":
    unittest.main()
