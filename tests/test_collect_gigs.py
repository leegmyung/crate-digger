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


TIMETABLE_DESC = """금요일 밤 메탈 공연!
𝐓𝐢𝐦𝐞 𝐓𝐚𝐛𝐥𝐞
coffin girl - 07:00 ~ 07:40
NGTTG - 07:40 ~ 08:20
CrossX - 08:20 ~ 09:00
Noiz Place - 09:00 ~ 09:40
RNHN - 09:40 ~ 10:20
Goyō - 10:20 ~ 11:00
DJ-CEЯEBRUM - 11:00 ~ 11:40"""

LINEUP_DETAIL = {
    "url": "https://www.indiego.co.kr/events/1805-coffin-maiden-and-the-grave",
    "name": "Coffin, Maiden, and the Grave", "startDate": "2026-11-27T19:00:00+09:00",
    "venue": "인피니티클럽", "address": "서울 서대문구",
    "description": TIMETABLE_DESC,
    "performers": [{"name": n, "url": ""} for n in
                   ("NGTTG", "Noiz Place", "하늘 (RNHN)", "고요 (Goyō)", "coffin girl", "CrossX")],
}


class LineupTest(unittest.TestCase):
    """출연 순서: 페이지의 출연 팀 목록 순서는 실제 순서가 아닐 수 있어(인디고 예: 목록 첫 팀 ≠ 첫 무대), 설명의 타임테이블에서만 읽는다."""

    def test_timetable_order_and_times(self):
        names = [p["name"] for p in LINEUP_DETAIL["performers"]]
        got = cg.lineup_positions(names, TIMETABLE_DESC, "19:00")
        self.assertEqual(got["coffin girl"], (1, "19:00"))
        self.assertEqual(got["NGTTG"], (2, "19:40"))
        self.assertEqual(got["하늘 (RNHN)"], (5, "21:40"))      # 괄호 속 영문 이름으로도 찾음
        self.assertEqual(got["고요 (Goyō)"], (6, "22:20"))
        self.assertEqual(len(got), 6)

    def test_no_timetable_means_no_order(self):
        self.assertEqual(cg.lineup_positions(["A밴드", "B밴드"], "멋진 공연입니다", "19:00"), {})
        self.assertEqual(cg.lineup_positions(["A밴드", "B밴드"], "", ""), {})

    def test_single_match_is_not_an_order(self):
        self.assertEqual(cg.lineup_positions(["A밴드", "B밴드"], "A밴드 19:30 단독 무대", "19:00"), {})

    def test_24h_times_kept(self):
        got = cg.lineup_positions(["A밴드", "B밴드"], "19:30 A밴드\n20:20 B밴드", "19:00")
        self.assertEqual(got, {"A밴드": (1, "19:30"), "B밴드": (2, "20:20")})

    def test_rows_carry_lineup_columns(self):
        rows = cg.to_rows("indiego", LINEUP_DETAIL, AT)
        by = {r["artist_text"]: r for r in rows}
        self.assertEqual({r["lineup_size"] for r in rows}, {"6"})
        self.assertEqual((by["coffin girl"]["lineup_order"], by["coffin girl"]["lineup_time"]), ("1", "19:00"))
        self.assertEqual(by["CrossX"]["lineup_order"], "3")

    def test_rows_without_timetable_have_blank_order(self):
        rows = cg.to_rows("indiego", INDIEGO_DETAIL, AT)
        self.assertEqual({(r["lineup_order"], r["lineup_time"], r["lineup_size"]) for r in rows}, {("", "", "2")})

    def test_detail_js_reads_description(self):
        self.assertIn("description", cg.DETAIL_JS)

    def test_written_file_passes_validation_and_old_header_still_ok(self):
        with tempfile.TemporaryDirectory() as d:
            path = cg.write_csv(cg.to_rows("indiego", LINEUP_DETAIL, AT), Path(d), "indiego", "2026-11-27")
            self.assertFalse([i for i in validate_csv.validate_file(path) if i.level == "error"])
            old = Path(d) / "raw_kr_gig_2026-11-20_indiego.csv"
            old_cols = [c for c in cg.COLUMNS if not c.startswith("lineup_")]
            old.write_text(",".join(old_cols) + "\n" + ",".join(
                {"collected_at": AT, "source": "indiego", "collector": "aside", "gig_date": "2026-11-20",
                 "artist_text": "A", "gig_url": "https://x/1"}.get(c, "") for c in old_cols) + "\n", encoding="utf-8")
            self.assertFalse([i for i in validate_csv.validate_file(old) if i.level == "error"])


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

    def test_utc_start_converted_to_korea_time(self):
        # 인디스트릿은 시작 시각을 UTC(Z)로 줌 → 오후 8시 공연이 11:00으로 적히던 문제 (2026-11-26)
        r = cg.to_rows("indiego", dict(INDIEGO_DETAIL, startDate="2026-11-26T11:00:00.000Z"), AT)[0]
        self.assertEqual((r["gig_date"], r["gig_time"]), ("2026-11-26", "20:00"))
        r = cg.to_rows("indiego", dict(INDIEGO_DETAIL, startDate="2026-11-26T16:30:00Z"), AT)[0]
        self.assertEqual((r["gig_date"], r["gig_time"]), ("2026-11-27", "01:30"))   # 자정 넘으면 날짜도
        r = cg.to_rows("indiego", dict(INDIEGO_DETAIL, startDate="2026-11-26T19:00:00+09:00"), AT)[0]
        self.assertEqual(r["gig_time"], "19:00")                                     # 이미 한국 시간이면 그대로

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

    def test_unicode_line_separator_inside_result_kept(self):
        # 인스타 캡션의 U+2028 문자를 줄바꿈으로 잘못 보고 결과가 잘리던 문제 (2026-11-26)
        payload = {"og": "첫 줄 둘째 줄 셋째"}
        text = "RESULT " + json.dumps(payload, ensure_ascii=False)
        out = json.dumps({"run": {"content": [{"type": "text", "text": text}], "error": None}})
        self.assertEqual(cg.parse_repl_output(out), payload)

    def test_broken_result_raises_runtime_error(self):
        out = json.dumps({"run": {"content": [{"type": "text", "text": 'RESULT {"a": "잘림'}], "error": None}})
        with self.assertRaises(RuntimeError):
            cg.parse_repl_output(out)

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


# ---------- 인디고 공연장별 과거 목록 (일반 HTTP, aside 없이) ----------

VENUE_HTML = (
    '<script>self.__next_f.push([1,"{\\"venue\\":{\\"name\\":\\"가상클럽\\",\\"public_id\\":176,'
    '\\"comment_count\\":0},\\"events\\":[{\\"id\\":\\"a\\",\\"name\\":\\"지난 공연\\",'
    '\\"public_id\\":1609,\\"series_id\\":null,\\"start_date\\":\\"2026-11-01\\"},'
    '{\\"id\\":\\"b\\",\\"public_id\\":1700,\\"start_date\\":\\"2026-12-24\\"},'
    '{\\"id\\":\\"c\\",\\"public_id\\":1500,\\"start_date\\":\\"2026-10-01\\"}]}"])</script>'
)


def _event_html(pid, date, performers=(("가상밴드", 3388),)):
    ld = {"@context": "https://schema.org", "@type": "MusicEvent", "name": f"공연 {pid}",
          "url": f"https://www.indiego.co.kr/events/{pid}-x", "startDate": f"{date}T19:00:00+09:00",
          "location": {"@type": "Place", "name": "가상클럽",
                       "address": {"@type": "PostalAddress", "streetAddress": "부산 금정구 가상로 1"}},
          "performer": [{"@type": "MusicGroup", "name": n, "url": f"https://www.indiego.co.kr/artists/{i}-x"}
                        for n, i in performers]}
    return f'<html><script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script></html>'


class VenueHistoryParseTest(unittest.TestCase):
    def test_venue_events_reads_public_id_and_date_but_not_venue_id(self):
        self.assertEqual(cg.venue_events(VENUE_HTML),
                         [{"public_id": 1609, "start_date": "2026-11-01"}, {"public_id": 1700, "start_date": "2026-12-24"},
                          {"public_id": 1500, "start_date": "2026-10-01"}])

    def test_parse_event_page_gives_detail_like_aside(self):
        d = cg.parse_event_page(_event_html(1609, "2026-11-01"), "https://www.indiego.co.kr/events/1609")
        self.assertEqual(d["url"], "https://www.indiego.co.kr/events/1609-x")
        self.assertEqual((d["venue"], d["address"]), ("가상클럽", "부산 금정구 가상로 1"))
        self.assertEqual(d["performers"], [{"name": "가상밴드", "url": "https://www.indiego.co.kr/artists/3388-x"}])
        self.assertIsNone(cg.parse_event_page("<html>없음</html>", "u"))

    def test_history_targets_regional_skips_seoul_and_missing_url(self):
        cfg = {"venues": [{"name": "A", "city": "서울", "indiego_url": "https://www.indiego.co.kr/venues/1-a"},
                          {"name": "B", "city": "부산", "indiego_url": "https://www.indiego.co.kr/venues/2-b"},
                          {"name": "C", "city": "광주"}]}
        self.assertEqual(cg.history_targets(cfg, "regional"), [("B", "https://www.indiego.co.kr/venues/2-b")])
        self.assertEqual(len(cg.history_targets(cfg, "all")), 2)


class RedirectTest(unittest.TestCase):
    def test_opener_follows_308_like_307(self):
        # 인디고 /events/<번호> 는 308 로 /events/<번호>-<제목> 에 보냄 — 파이썬 3.9 기본 처리기는 308 을 오류로 냄
        handler = cg.Redirect308Handler()
        self.assertTrue(hasattr(handler, "http_error_308"))
        import urllib.request
        req = urllib.request.Request("https://www.indiego.co.kr/events/1609", headers={"User-Agent": "x"})
        new = handler.redirect_request(req, None, 308, "Permanent Redirect", {},
                                       "https://www.indiego.co.kr/events/1609-x")
        self.assertEqual(new.full_url, "https://www.indiego.co.kr/events/1609-x")


class VenueHistoryCollectTest(unittest.TestCase):
    def test_collects_only_past_unseen_events_and_writes_valid_csv(self):
        pages = {"https://www.indiego.co.kr/venues/2-b": VENUE_HTML,
                 "https://www.indiego.co.kr/events/1609": _event_html(1609, "2026-11-01", (("가상밴드", 1), ("둘째팀", 2))),
                 "https://www.indiego.co.kr/events/1500": _event_html(1500, "2026-10-01")}
        fetched = []

        def fake_fetch(url):
            fetched.append(url)
            return pages[url]

        with tempfile.TemporaryDirectory() as d:
            path, rows, st = cg.collect_venue_history([("B", "https://www.indiego.co.kr/venues/2-b")], Path(d),
                                                      "2026-11-27", seen={"1500"}, fetch=fake_fetch, delay=0)
            errs = [i for i in validate_csv.validate_file(path) if i.level == "error"]
            self.assertEqual(path.name, "raw_kr_gig_2026-11-27_indiego_history.csv")
        self.assertEqual(errs, [])
        self.assertNotIn("https://www.indiego.co.kr/events/1700", fetched)   # 예정 공연은 매일 수집이 맡음
        self.assertNotIn("https://www.indiego.co.kr/events/1500", fetched)   # 이미 받은 공연
        self.assertEqual([r["artist_text"] for r in rows], ["가상밴드", "둘째팀"])
        self.assertEqual({(r["source"], r["collector"]) for r in rows}, {("indiego", "script")})
        self.assertEqual((st["venues"], st["events_past"], st["skipped_seen"], st["fetched"]), (1, 2, 1, 1))

    def test_failed_page_is_counted_not_raised(self):
        def boom(url):
            raise OSError("down")
        with tempfile.TemporaryDirectory() as d:
            path, rows, st = cg.collect_venue_history([("B", "https://www.indiego.co.kr/venues/2-b")], Path(d),
                                                      "2026-11-27", seen=set(), fetch=boom, delay=0)
        self.assertIsNone(path)
        self.assertEqual(st["failed_venues"], 1)

    def test_seen_ids_read_from_existing_indiego_files(self):
        with tempfile.TemporaryDirectory() as d:
            cg.write_csv(cg.to_rows("indiego", INDIEGO_DETAIL, AT), Path(d), "indiego", "2026-11-26")
            cg.write_csv(cg.to_rows("indistreet", INDISTREET_DETAIL, AT), Path(d), "indistreet", "2026-11-26")
            self.assertEqual(cg.seen_indiego_ids(Path(d)), {"2001"})


if __name__ == "__main__":
    unittest.main()
