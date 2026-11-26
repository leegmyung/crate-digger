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


class BuildTest(unittest.TestCase):
    def test_counts_per_day_and_source_and_public_fields_only(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "raw_kr_release_2026-11-25_poclanos.csv", [row(collected_at="2026-11-25T15:00:00+09:00")])
            write(d, "raw_kr_release_2026-11-26_poclanos.csv",
                  [row(), row(artist_text="B", release_url="https://example.com/2", released_at="2026-11-25")])
            data = bsd.build(Path(d), recent_limit=10)
        self.assertEqual(data["runs"], [
            {"date": "2026-11-26", "source": "poclanos", "table": "raw_kr_release", "rows": 2, "file_ok": True},
            {"date": "2026-11-25", "source": "poclanos", "table": "raw_kr_release", "rows": 1, "file_ok": True},
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

    def test_empty_folder(self):
        with tempfile.TemporaryDirectory() as d:
            data = bsd.build(Path(d), recent_limit=10)
        self.assertEqual((data["runs"], data["recent_releases"]), ([], []))


if __name__ == "__main__":
    unittest.main()
