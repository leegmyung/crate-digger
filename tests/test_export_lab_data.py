"""export_lab_data: PostgreSQL 결과 → 랩(docs/lab) CSV. psql 대신 가짜 run 함수로 시험한다."""
import csv
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import export_lab_data as ex  # noqa: E402


def _csv(rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


SIGNALS = [
    {"team_key": "abc", "branch": "공연", "source": "indistreet", "program": "", "stage_rank": "",
     "signal_date": "2024-05-01", "venue": "Club FF"},
    {"team_key": "abc", "branch": "선정·지원", "source": "ssm", "program": "band_discovery", "stage_rank": "2",
     "signal_date": "2023-12-31", "venue": ""},
    {"team_key": "xyz", "branch": "큐레이션", "source": "rhythmer", "program": "rhythmer", "stage_rank": "",
     "signal_date": "2025-02-01", "venue": ""},
]
TEAMS = [
    {"team_key": "abc", "display_name": "에이비씨", "first_seen": "2023-12-31", "first_release": "",
     "fan_count": "", "album_count": "", "profile_status": "", "raw_genres": "", "press_sources": "",
     "sel_programs": "band_discovery"},
    {"team_key": "xyz", "display_name": "엑스", "first_seen": "2025-02-01", "first_release": "2024-01-01",
     "fan_count": "20000", "album_count": "3", "profile_status": "famous", "raw_genres": "",
     "press_sources": "rhythmer", "sel_programs": ""},
]
OUTCOMES = [
    {"team_key": "abc", "program": "kma_rookie", "tier": "final", "announced_date": "2025-02-20", "counted": "t"},
]


def fake_run(sql):
    if "to_regclass" in sql:
        return "t\nref.artist_xref\n"
    if "-- lab:signals" in sql:
        return _csv(SIGNALS)
    if "-- lab:teams" in sql:
        return _csv(TEAMS)
    if "-- lab:links" in sql:
        return _csv([{"team_key": "abc", "platform": "melon", "ref": "1273629"}])
    if "-- lab:outcomes" in sql:
        return _csv(OUTCOMES)
    raise AssertionError(sql[:80])


class TeamRowsTest(unittest.TestCase):
    def test_genre_inferred_from_selection_program_when_no_raw_genre(self):
        self.assertEqual(ex.team_rows(TEAMS)[0]["primary_genre"], "록·밴드")

    def test_genre_inferred_from_rhythmer_press(self):
        self.assertEqual(ex.team_rows(TEAMS)[1]["primary_genre"], "힙합")

    def test_missing_profile_status_becomes_unknown(self):
        rows = ex.team_rows(TEAMS)
        self.assertEqual(rows[0]["profile_status"], "unknown")
        self.assertEqual(rows[1]["profile_status"], "famous")

    def test_helper_columns_are_dropped(self):
        self.assertEqual(list(ex.team_rows(TEAMS)[0]), ex.TEAM_FIELDS)


class OutcomeRowsTest(unittest.TestCase):
    def test_label_and_boolean(self):
        row = ex.outcome_rows(OUTCOMES)[0]
        self.assertEqual(row["program_label"], "한대음 올해의 신인")
        self.assertEqual(row["counted"], "true")


class LinkRowsTest(unittest.TestCase):
    def test_platform_ids_become_artist_page_urls(self):
        rows = ex.link_rows([
            {"team_key": "a", "platform": "melon", "ref": "1273629"},
            {"team_key": "a", "platform": "genie", "ref": "80123"},
            {"team_key": "a", "platform": "bugs", "ref": "20198207"},
            {"team_key": "a", "platform": "spotify", "ref": "40Gp1pozXyDoTKNkxTbZKQ"},
            {"team_key": "a", "platform": "instagram", "ref": "@samui_band"},
            {"team_key": "a", "platform": "youtube", "ref": "https://www.youtube.com/@3amui"},
        ])
        urls = {r["platform"]: r["url"] for r in rows}
        self.assertEqual(urls["melon"], "https://www.melon.com/artist/detail.htm?artistId=1273629")
        self.assertEqual(urls["genie"], "https://www.genie.co.kr/detail/artistInfo?xxnm=80123")
        self.assertEqual(urls["bugs"], "https://music.bugs.co.kr/artist/20198207")
        self.assertEqual(urls["spotify"], "https://open.spotify.com/artist/40Gp1pozXyDoTKNkxTbZKQ")
        self.assertEqual(urls["instagram"], "https://www.instagram.com/samui_band/")
        self.assertEqual(urls["youtube"], "https://www.youtube.com/@3amui")

    def test_full_urls_kept_and_duplicates_removed(self):
        rows = ex.link_rows([
            {"team_key": "a", "platform": "melon", "ref": "https://www.melon.com/artist/detail.htm?artistId=1"},
            {"team_key": "a", "platform": "melon", "ref": "1"},
            {"team_key": "a", "platform": "instagram", "ref": "https://www.instagram.com/x_y/"},
            {"team_key": "a", "platform": "instagram", "ref": "x_y"},
        ])
        self.assertEqual(len(rows), 2)

    def test_unsafe_or_empty_refs_are_dropped(self):
        rows = ex.link_rows([
            {"team_key": "a", "platform": "melon", "ref": ""},
            {"team_key": "a", "platform": "youtube", "ref": "javascript:alert(1)"},
            {"team_key": "a", "platform": "instagram", "ref": "bad handle!"},
            {"team_key": "a", "platform": "unknown", "ref": "123"},
        ])
        self.assertEqual(rows, [])

    def test_spotify_matches_only_unambiguous_names(self):
        refs = ex.spotify_refs({"공원": {"id": "AAA", "namesakes": 2}, "김승주": {"id": "BBB", "namesakes": 1},
                                "없음": None}, key_of=lambda n: {"공원": "공원", "김승주": "김승주"}.get(n, n))
        self.assertEqual(refs, [{"team_key": "김승주", "platform": "spotify", "ref": "BBB"}])


class ExportTest(unittest.TestCase):
    def test_writes_all_files_with_meta(self):
        with tempfile.TemporaryDirectory() as d:
            meta = ex.export(Path(d), run=fake_run, today="2026-11-27", extra_refs=None)
            for name in ("signals.csv", "teams.csv", "outcomes.csv", "programs.csv", "links.csv", "meta.json"):
                self.assertTrue((Path(d) / name).exists(), name)
            self.assertEqual(meta["rows"]["signals"], 3)
            self.assertEqual(meta["rows"]["links"], 1)
            self.assertEqual(meta["data_end"], "2026-11-27")
            self.assertTrue(meta["uses_artist_xref"])
            saved = json.loads((Path(d) / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["rows"]["teams"], 2)

    def test_programs_list_marks_outcome_and_signal_kinds(self):
        with tempfile.TemporaryDirectory() as d:
            ex.export(Path(d), run=fake_run, today="2026-11-27", extra_refs=None)
            with open(Path(d) / "programs.csv", encoding="utf-8") as f:
                kinds = {r["program"]: r["kind"] for r in csv.DictReader(f)}
            self.assertEqual(kinds["band_discovery"], "signal")
            self.assertEqual(kinds["kma_rookie"], "outcome")


if __name__ == "__main__":
    unittest.main()
