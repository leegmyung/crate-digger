"""스포티파이 발매 이력 수집기 테스트 — 실제 API 대신 가짜 HTTP 응답으로."""
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import collect_spotify as cs  # noqa: E402

AT = "2026-11-26T23:00:00+09:00"


def artist(i, name):
    return {"id": i, "name": name, "type": "artist"}


def album(date, kind="single"):
    return {"release_date": date, "album_type": kind, "id": date + kind}


class FakeHttp:
    """(method, url 일부) → 응답 목록. 호출 기록을 남긴다."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, method, url, headers=None, data=None):
        self.calls.append((method, url, headers or {}))
        for part, responses in self.routes:
            if part in url:
                resp = responses.pop(0) if len(responses) > 1 else responses[0]
                return resp
        raise AssertionError("예상 못한 요청: " + url)


def ok(body):
    return 200, {}, body


TOKEN = ("accounts.spotify.com", [ok({"access_token": "T", "expires_in": 3600})])


def client(routes, sleeps=None):
    fake = FakeHttp([TOKEN] + routes)
    slept = sleeps if sleeps is not None else []
    return cs.SpotifyClient("id", "secret", http=fake, sleep=slept.append), fake


class EnvTest(unittest.TestCase):
    def test_reads_env_file_without_overriding_environment(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / ".env"
            p.write_text('# 주석\nSPOTIFY_CLIENT_ID="abc"\nSPOTIFY_CLIENT_SECRET=xyz\n', encoding="utf-8")
            env = cs.load_env(p, environ={"SPOTIFY_CLIENT_SECRET": "from_env"})
        self.assertEqual(env["SPOTIFY_CLIENT_ID"], "abc")
        self.assertEqual(env["SPOTIFY_CLIENT_SECRET"], "from_env")

    def test_missing_file_is_fine(self):
        self.assertEqual(cs.load_env(Path("/없는/.env"), environ={}), {})


class MatchTest(unittest.TestCase):
    def test_accepts_only_same_key_and_counts_namesakes(self):
        items = [artist("a", "gongwon"), artist("b", "공원소녀"), artist("c", "공원"), artist("d", "공원 ")]
        m = cs.pick_match("공원", items)
        self.assertEqual(m, {"id": "c", "name": "공원", "namesakes": 2})

    def test_alias_key_also_accepted(self):
        m = cs.pick_match("피치트럭 하이재커스(Peach Truck Hijackers)", [artist("x", "Peach Truck Hijackers")])
        self.assertEqual(m["id"], "x")

    def test_no_hit(self):
        self.assertIsNone(cs.pick_match("실리카겔", [artist("a", "HANRORO")]))

    def test_keeps_search_result_photo_so_no_extra_request_is_needed(self):
        item = dict(artist("c", "공원"), images=[{"url": "https://i.scdn.co/image/big", "width": 640},
                                                 {"url": "https://i.scdn.co/image/mid", "width": 320}])
        self.assertEqual(cs.pick_match("공원", [item])["image"], "https://i.scdn.co/image/mid")
        self.assertNotIn("image", cs.pick_match("공원", [dict(artist("c", "공원"), images=[])]))


class ReleaseSummaryTest(unittest.TestCase):
    def test_earliest_partial_date_and_ignores_zero_dates(self):
        s = cs.summarize([album("2024-03-01"), album("2023-11", "album"), album("2023"), album("0000")], total=4)
        self.assertEqual(s, {"first_release_date": "2023", "album_count": "4"})

    def test_empty(self):
        self.assertEqual(cs.summarize([], total=0), {"first_release_date": "", "album_count": "0"})


class ClientTest(unittest.TestCase):
    def test_search_sends_korean_locale_and_limit_10(self):
        c, fake = client([("/v1/search", [ok({"artists": {"items": [artist("a", "실리카겔")]}})])])
        items = c.search_artists("실리카겔")
        self.assertEqual(items[0]["id"], "a")
        method, url, headers = fake.calls[-1]
        self.assertIn("limit=10", url)
        self.assertIn("market=KR", url)
        self.assertIn("type=artist", url)
        self.assertTrue(headers["Accept-Language"].startswith("ko"))
        self.assertEqual(headers["Authorization"], "Bearer T")

    def test_retries_after_429_with_retry_after(self):
        sleeps = []
        c, fake = client([("/v1/search", [(429, {"Retry-After": "3"}, {}), ok({"artists": {"items": []}})])], sleeps)
        self.assertEqual(c.search_artists("x"), [])
        self.assertIn(3, sleeps)

    def test_too_long_retry_after_stops(self):
        c, _ = client([("/v1/search", [(429, {"Retry-After": "86400"}, {})])])
        with self.assertRaises(cs.RateLimited):
            c.search_artists("x")

    def test_refreshes_token_once_on_401(self):
        c, fake = client([("/v1/search", [(401, {}, {}), ok({"artists": {"items": []}})])])
        c.search_artists("x")
        self.assertEqual(sum("accounts.spotify.com" in u for _, u, _ in fake.calls), 2)

    def test_small_catalog_one_page(self):
        c, fake = client([("/albums", [ok({"total": 2, "next": None, "items": [album("2025-01-02"), album("2024-05-01")]})])])
        self.assertEqual(c.release_summary("A"), {"first_release_date": "2024-05-01", "album_count": "2"})
        self.assertEqual(sum("/albums" in u for _, u, _ in fake.calls), 1)

    def test_big_catalog_reads_last_page_of_each_group(self):
        routes = [
            ("include_groups=album&", [ok({"total": 12, "items": [album("2026-01-01", "album")]}),
                                       ok({"total": 12, "items": [album("2016-10-12", "album")]})]),
            ("include_groups=single&", [ok({"total": 3, "items": [album("2019-02-02")]})]),
            ("include_groups=album%2Csingle", [ok({"total": 15, "next": "more", "items": [album("2026-01-01", "album")]})]),
        ]
        c, fake = client(routes)
        s = c.release_summary("A")
        self.assertEqual(s, {"first_release_date": "2016-10-12", "album_count": "15"})
        self.assertTrue(any("include_groups=album&" in u and "offset=2" in u for _, u, _ in fake.calls))


class InputNamesTest(unittest.TestCase):
    def _write(self, d, name, header, rows):
        with open(Path(d) / name, "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(header)
            w.writerows(rows)

    def test_collects_and_filters_names(self):
        with tempfile.TemporaryDirectory() as d:
            self._write(d, "raw_kr_release_x.csv", ["artist_text"], [["실리카겔"], ["실리카 겔"]])
            self._write(d, "raw_kr_selection_x.csv", ["announced_at", "artist_text"],
                        [["2023-05-01", "옛날팀"], ["2024", "새팀"]])
            self._write(d, "raw_kr_gig_x.csv", ["source", "source_id", "gig_date", "artist_text"],
                        [["indiego", "1", "2025-07-01", "두번팀"], ["indiego", "2", "2025-08-01", "두번팀"],
                         ["indiego", "1", "2025-07-01", "한번팀"], ["indiego", "1", "2025-07-01", "한번팀"],
                         ["indiego", "3", "2024-01-01", "옛공연팀"], ["indiego", "4", "2024-02-01", "옛공연팀"]])
            self._write(d, "raw_press_x.csv", ["artist_text"], [["기사팀"]])
            self._write(d, "raw_outcome_x.csv", ["artist_text"], [["정답팀(Answer)"]])
            names = cs.input_names(Path(d))
        self.assertEqual(sorted(names), sorted(["실리카겔", "새팀", "두번팀", "기사팀", "정답팀(Answer)"]))

    def test_priority_names_come_first_without_duplicates(self):
        with tempfile.TemporaryDirectory() as d:
            self._write(d, "raw_kr_release_x.csv", ["artist_text"], [["실리카겔"], ["기사팀"]])
            names = cs.input_names(Path(d), priority=["상위팀", "기사 팀", ""])
        self.assertEqual(names, ["상위팀", "기사 팀", "실리카겔"])


class RunTest(unittest.TestCase):
    def test_end_to_end_writes_valid_csv_and_state(self):
        import validate_csv
        routes = [
            ("q=%EC%A0%95%EB%8B%B5%ED%8C%80&", [ok({"artists": {"items": []}})]),          # '정답팀' 없음
            ("q=Answer", [ok({"artists": {"items": [artist("sp1", "Answer")]}})]),              # 별칭으로 찾음
            ("q=%EC%97%86%EB%8A%94%ED%8C%80", [ok({"artists": {"items": [artist("z", "딴팀")]}})]),
            ("/albums", [ok({"total": 1, "next": None, "items": [album("2025-04")]})]),
        ]
        c, _ = client(routes)
        with tempfile.TemporaryDirectory() as d:
            raw = Path(d)
            res = cs.run(c, ["정답팀(Answer)", "없는팀"], raw, "2026-11-26", AT, delay=0)
            path = res["path"]
            errs = [i for i in validate_csv.validate_file(path) if i.level == "error"]
            with open(path, encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
            match = json.loads((raw / "state" / "spotify_match.json").read_text(encoding="utf-8"))
            seen = json.loads((raw / "state" / "spotify_seen.json").read_text(encoding="utf-8"))
            # 다시 돌리면 이미 찾은 이름은 건너뛴다
            res2 = cs.run(c, ["정답팀(Answer)", "없는팀"], raw, "2026-11-26", AT, delay=0)
        bad = [e for e in errs if "spotify" not in e.message]
        self.assertEqual(bad, [])
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual((r["source"], r["collector"], r["artist_source_id"], r["artist_text"]),
                         ("spotify", "script", "sp1", "Answer"))
        self.assertEqual((r["first_release_date"], r["album_count"], r["fan_count"], r["debut_date"]), ("2025-04", "1", "", ""))
        self.assertEqual(r["url"], "https://open.spotify.com/artist/sp1")
        self.assertEqual(r["artist_key"], "answer")
        self.assertEqual(match["정답팀(Answer)"], {"id": "sp1", "name": "Answer", "namesakes": 1})
        self.assertIsNone(match["없는팀"])
        self.assertEqual(seen, ["sp1"])
        self.assertEqual((res["queried"], res["matched"]), (2, 1))
        self.assertEqual((res2["queried"], res2["path"]), (0, None))

    def test_rate_limit_midway_keeps_rows_and_resumes(self):
        routes = [
            ("q=%EC%B2%AB%ED%8C%80", [ok({"artists": {"items": [artist("s1", "첫팀")]}})]),
            ("q=%EB%91%98%ED%8C%80", [(429, {"Retry-After": "86400"}, {})]),
            ("/albums", [ok({"total": 1, "next": None, "items": [album("2024-01-01")]})]),
        ]
        c, _ = client(routes)
        with tempfile.TemporaryDirectory() as d:
            raw = Path(d)
            res = cs.run(c, ["첫팀", "둘팀"], raw, "2026-11-26", AT, delay=0)
            match = json.loads((raw / "state" / "spotify_match.json").read_text(encoding="utf-8"))
            # 지난번에 짝만 맞추고 앨범을 못 받은 팀은 다음 실행에서 먼저 받는다
            (raw / "state" / "spotify_seen.json").write_text("[]", encoding="utf-8")
            c2, _ = client([("q=", [ok({"artists": {"items": []}})]),
                            ("/albums", [ok({"total": 2, "next": None, "items": [album("2023")]})])])
            res2 = cs.run(c2, ["첫팀", "둘팀"], raw, "2026-11-26", AT, delay=0)
        self.assertEqual((res["rows"], bool(res["stopped"])), (1, True))
        self.assertIsNotNone(res["path"])
        self.assertEqual(list(match), ["첫팀"])
        self.assertEqual((res2["rows"], res2["queried"]), (1, 1))


if __name__ == "__main__":
    unittest.main()
