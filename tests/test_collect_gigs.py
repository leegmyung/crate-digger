"""공연 수집기(인디고·인디스트릿) 변환 로직 테스트 — aside 없이 가상 데이터로."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import collect_gigs as cg  # noqa: E402
import validate_csv  # noqa: E402

AT = "2026-11-26T18:00:00+09:00"

INDIEGO_DETAIL = {
    "url": "https://www.indiego.co.kr/events/2001-thursday-vibes",
    "name": "Thursday Vibes",
    "startDate": "2026-11-26T19:00:00+09:00",
    "venue": "클럽FF",
    "address": "서울 마포구 와우산로17길 12",
    "performers": [
        {"name": "사양", "url": "https://www.indiego.co.kr/artists/3394-사양"},
        {"name": "레고 REGO", "url": "https://www.indiego.co.kr/artists/1210-레고"},
        {"name": "레고 REGO", "url": "https://www.indiego.co.kr/artists/1210-레고"},
    ],
}

INDISTREET_DETAIL = {
    "url": "https://indistreet.com/gigs/2026-11-28-night-pt20-abc123",
    "name": "Night! pt.20",
    "startDate": "2026-11-28T19:30:00+09:00",
    "venue": "채널1969",
    "address": "서울 마포구",
    "performers": [{"name": "가상밴드", "url": "https://indistreet.com/artists/gasang-band"}],
}


class ToRowsTest(unittest.TestCase):
    def test_indiego_one_row_per_unique_performer(self):
        rows = cg.to_rows("indiego", INDIEGO_DETAIL, AT)
        self.assertEqual([r["artist_text"] for r in rows], ["사양", "레고 REGO"])
        r = rows[0]
        self.assertEqual((r["source"], r["collector"]), ("indiego", "aside"))
        self.assertEqual(r["source_id"], "2001")
        self.assertEqual(r["artist_source_id"], "3394")
        self.assertEqual((r["gig_date"], r["gig_time"]), ("2026-11-26", "19:00"))
        self.assertEqual(r["venue_text"], "클럽FF (서울 마포구 와우산로17길 12)")

    def test_indistreet_ids_from_slug(self):
        r = cg.to_rows("indistreet", INDISTREET_DETAIL, AT)[0]
        self.assertEqual(r["source_id"], "2026-11-28-night-pt20-abc123")
        self.assertEqual(r["artist_source_id"], "gasang-band")

    def test_no_performers_gives_no_rows(self):
        self.assertEqual(cg.to_rows("indiego", dict(INDIEGO_DETAIL, performers=[]), AT), [])

    def test_bad_start_date_keeps_date_drops_time(self):
        r = cg.to_rows("indiego", dict(INDIEGO_DETAIL, startDate="2026-11-26"), AT)[0]
        self.assertEqual((r["gig_date"], r["gig_time"]), ("2026-11-26", ""))

    def test_written_file_passes_validator(self):
        other = dict(INDISTREET_DETAIL, url="https://www.indiego.co.kr/events/9-x")
        rows = cg.to_rows("indiego", INDIEGO_DETAIL, AT) + cg.to_rows("indiego", other, AT)
        with tempfile.TemporaryDirectory() as d:
            path = cg.write_csv(rows, Path(d), "indiego", "2026-11-26")
            self.assertEqual(path.name, "raw_kr_gig_2026-11-26_indiego.csv")
            errs = [i for i in validate_csv.validate_file(path) if i.level == "error"]
        self.assertEqual(errs, [])


class ReplOutputTest(unittest.TestCase):
    def test_extracts_result_payload_from_aside_json(self):
        payload = {"items": [1, 2]}
        out = json.dumps({"run": {"content": [{"type": "text", "text": "noise"},
                                              {"type": "text", "text": "RESULT " + json.dumps(payload)}],
                                  "error": None}})
        self.assertEqual(cg.parse_repl_output(out), payload)

    def test_missing_result_raises(self):
        with self.assertRaises(RuntimeError):
            cg.parse_repl_output(json.dumps({"run": {"content": [], "error": "boom"}}))


class ListFilterTest(unittest.TestCase):
    def test_korean_date_in_list_text(self):
        self.assertEqual(cg.list_date("2026년 11월 26일 (목) 19:00 · 클럽FF · 사양"), "2026-11-26")
        self.assertEqual(cg.list_date("2026년 1월 5일 (월)"), "2026-01-05")
        self.assertEqual(cg.list_date("날짜 없음"), "")

    def test_filter_keeps_window_and_undated(self):
        items = [
            {"url": "https://www.indiego.co.kr/events/1-a", "text": "2026년 11월 26일 (목) 19:00"},
            {"url": "https://www.indiego.co.kr/events/2-b", "text": "2026년 12월 20일 (일) 19:00"},
            {"url": "https://www.indiego.co.kr/events/3-c", "text": ""},
            {"url": "https://indistreet.com/gigs/2026-11-27-x-1", "text": ""},
            {"url": "https://indistreet.com/gigs/2026-10-01-y-2", "text": ""},
        ]
        urls = cg.filter_listed(items, "2026-11-26", "2026-12-03")
        self.assertEqual(urls, ["https://www.indiego.co.kr/events/1-a", "https://www.indiego.co.kr/events/3-c",
                                "https://indistreet.com/gigs/2026-11-27-x-1"])


class DateWindowTest(unittest.TestCase):
    def test_in_window(self):
        self.assertTrue(cg.in_window("2026-11-26T19:00:00+09:00", "2026-11-26", "2026-12-03"))
        self.assertFalse(cg.in_window("2026-11-25T19:00:00+09:00", "2026-11-26", "2026-12-03"))
        self.assertFalse(cg.in_window("", "2026-11-26", "2026-12-03"))


if __name__ == "__main__":
    unittest.main()
