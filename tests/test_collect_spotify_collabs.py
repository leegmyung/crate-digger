"""스포티파이 협업 수집기 테스트 — 실제 API 대신 가짜 HTTP 응답으로."""
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import collect_spotify as cs  # noqa: E402
import collect_spotify_collabs as cc  # noqa: E402

AT = "2026-11-27T21:00:00+09:00"
DAY = "2026-11-27"


def ar(i, name=None):
    return {"id": i, "name": name or i}


def album(aid, artists, kind="single", group=None, date="2024-05", precision="month"):
    a = {"id": aid, "name": "앨범" + aid, "album_type": kind, "artists": [ar(x) for x in artists],
         "release_date": date, "release_date_precision": precision}
    if group:
        a["album_group"] = group
    return a


def track(tid, artists):
    return {"id": tid, "name": "곡" + tid, "artists": [ar(x) for x in artists]}


def ok(body):
    return 200, {}, body


class Router:
    """url 일부 → 응답 함수. 요청 기록을 남긴다."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, method, url, headers=None, data=None):
        self.calls.append(url)
        if "accounts.spotify.com" in url:
            return ok({"access_token": "T"})
        for part, resp in self.routes.items():
            if part in url:
                return resp(url) if callable(resp) else resp
        raise AssertionError("예상 못한 요청: " + url)


def page(items):
    return ok({"items": items, "total": len(items), "next": None})


TARGETS = {"OUR": {"name": "우리팀", "id": "OUR"}}


class RoleTest(unittest.TestCase):
    def test_roles(self):
        own = album("A", ["OUR"])
        self.assertEqual(cc.classify_role("OUR", "P", track("t", ["OUR", "P"]), own), "feat_on_own")
        other = album("B", ["P"])
        self.assertEqual(cc.classify_role("OUR", "P", track("t", ["P", "OUR"]), other), "guest_on_partner")
        both = album("C", ["OUR", "P"])
        self.assertEqual(cc.classify_role("OUR", "P", track("t", ["P", "OUR"]), both), "co_lead")
        third = album("D", ["X"])
        self.assertEqual(cc.classify_role("OUR", "P", track("t", ["X", "P", "OUR"]), third), "co_guest")


class EdgeTest(unittest.TestCase):
    def test_appears_on_track_makes_guest_edge_with_date_passthrough(self):
        alb = {**album("B", ["P"], group="appears_on", date="2019", precision="year"), "_listed_for": "OUR"}
        rows = cc.edges_from_album(alb, [track("t1", ["P", "OUR"]), track("t2", ["P"])], TARGETS, AT)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual((r["partner_spotify_id"], r["role"], r["album_group"]), ("P", "guest_on_partner", "appears_on"))
        self.assertEqual((r["release_date"], r["release_date_precision"]), ("2019", "year"))
        self.assertEqual(r["artist_name"], "우리팀")

    def test_solo_tracks_make_no_edges_and_duplicates_collapse(self):
        alb = album("A", ["OUR"], group="single")
        tracks = [track("t1", ["OUR"]), track("t2", ["OUR", "P", "P"]), track("t2", ["OUR", "P"])]
        rows = cc.edges_from_album(alb, tracks, TARGETS, AT)
        self.assertEqual([(r["track_id"], r["partner_spotify_id"]) for r in rows], [("t2", "P")])

    def test_both_targets_on_one_track_get_rows(self):
        targets = {**TARGETS, "OUR2": {"name": "둘째", "id": "OUR2"}}
        rows = cc.edges_from_album(album("A", ["OUR"]), [track("t", ["OUR", "OUR2"])], targets, AT)
        self.assertEqual({(r["artist_spotify_id"], r["role"]) for r in rows},
                         {("OUR", "feat_on_own"), ("OUR2", "guest_on_partner")})

    def test_skip_compilation_and_various_artists(self):
        self.assertTrue(cc.skip_album(album("C", ["X"], kind="compilation")))
        self.assertTrue(cc.skip_album({**album("V", []), "artists": [ar("va", "Various Artists")]}))
        self.assertFalse(cc.skip_album(album("A", ["OUR"])))


class TargetTest(unittest.TestCase):
    def test_uses_unique_matches_and_searches_unmatched_lab_names(self):
        spotify = {"우리팀": {"id": "OUR", "name": "우리팀", "namesakes": 1},
                   "흔한이름": {"id": "C", "name": "흔한이름", "namesakes": 3}, "없음": None}
        targets, to_search = cc.base_targets(spotify, {"이미찾음": None}, ["우리 팀", "새팀", "없음", "이미찾음", "흔한이름"])
        self.assertEqual([t["id"] for t in targets], ["OUR"])
        self.assertEqual(targets[0]["name"], "우리 팀")
        self.assertEqual(to_search, ["새팀", "없음"])

    def test_lab_names_reads_newest_snapshot_and_counted_outcomes(self):
        with tempfile.TemporaryDirectory() as d:
            lab = Path(d)
            (lab / "snapshots").mkdir()
            (lab / "teams.csv").write_text("team_key,display_name\n품바21,품바 21\n가,가팀\n", encoding="utf-8")
            (lab / "snapshots" / "2026-01-01.csv").write_text("team_key,score,rank\n옛,1,1\n", encoding="utf-8")
            (lab / "snapshots" / "2026-02-01.csv").write_text("team_key,score,rank\n품바21,1,1\n나,1,2\n",
                                                              encoding="utf-8")
            (lab / "outcomes.csv").write_text("team_key,counted\n가,true\n다,false\n", encoding="utf-8")
            self.assertEqual(cc.lab_names(lab, top=1), ["품바 21", "가팀"])


def read(path):
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def setup_raw(d, spotify_match):
    raw = Path(d)
    (raw / "state").mkdir()
    (raw / "state" / "spotify_match.json").write_text(json.dumps(spotify_match), encoding="utf-8")
    return raw


class RunTest(unittest.TestCase):
    def make(self, max_requests, routes):
        router = Router(routes)
        counter = cc.CountingHttp(router, max_requests)
        return cs.SpotifyClient("id", "secret", http=counter, sleep=lambda s: None), counter, router

    def routes(self):
        return {
            "/artists/OUR/albums": page([album("A", ["OUR"], group="single"),
                                         album("B", ["P"], group="appears_on"),
                                         album("C", ["X"], kind="compilation", group="appears_on")]),
            "/albums/A/tracks": page([track("a1", ["OUR", "P"])]),
            "/albums/B/tracks": page([track("b1", ["P", "OUR"])]),
            "/albums/C/tracks": lambda url: (_ for _ in ()).throw(AssertionError("컴필레이션은 안 읽음")),
            "/artists/P/albums": ok({"items": [{"release_date": "2010-01-01"}], "total": 7, "next": None}),
        }

    def test_full_run_writes_edges_and_partner_profiles(self):
        with tempfile.TemporaryDirectory() as d:
            raw = setup_raw(d, {"우리팀": {"id": "OUR", "name": "우리팀", "namesakes": 1}})
            client, counter, _ = self.make(100, self.routes())
            res = cc.run(client, [], raw, DAY, AT, counter=counter)
            self.assertEqual(res["edges"], 2)
            rows = read(raw / f"raw_collab_{DAY}.csv")
            self.assertEqual({r["role"] for r in rows}, {"feat_on_own", "guest_on_partner"})
            prof = read(raw / f"raw_collab_partner_{DAY}.csv")
            self.assertEqual((prof[0]["partner_spotify_id"], prof[0]["first_release_date"], prof[0]["album_count"],
                              prof[0]["edge_count"]), ("P", "2010-01-01", "7", "2"))

    def test_budget_stop_then_resume_without_refetching(self):
        with tempfile.TemporaryDirectory() as d:
            raw = setup_raw(d, {"우리팀": {"id": "OUR", "name": "우리팀", "namesakes": 1}})
            # 토큰1 + 앨범목록1 + 수록곡A 1 = 3번에서 멈춤
            client, counter, _ = self.make(3, self.routes())
            res = cc.run(client, [], raw, DAY, AT, counter=counter)
            self.assertIn("한도", res["stopped"])
            self.assertEqual(res["edges"], 1)
            state = json.loads((raw / "state" / cc.STATE_FILE).read_text(encoding="utf-8"))
            self.assertEqual(state["done_albums"], ["A"])
            self.assertEqual(state["done_artists"], [])

            client, counter, router = self.make(100, self.routes())
            res = cc.run(client, [], raw, DAY, AT, counter=counter)
            self.assertEqual(res["stopped"], "")
            self.assertFalse(any("/albums/A/tracks" in u for u in router.calls))
            rows = read(raw / f"raw_collab_{DAY}.csv")
            self.assertEqual(sorted(r["track_id"] for r in rows), ["a1", "b1"])

            client, counter, router = self.make(100, self.routes())
            res = cc.run(client, [], raw, DAY, AT, counter=counter)
            self.assertEqual((res["edges"], res["profiles"]), (0, 0))
            self.assertEqual(router.calls, [])  # 다 끝났으면 요청 없음

    def test_failed_album_is_retried_next_run(self):
        with tempfile.TemporaryDirectory() as d:
            raw = setup_raw(d, {"우리팀": {"id": "OUR", "name": "우리팀", "namesakes": 1}})
            routes = {**self.routes(), "/albums/B/tracks": (403, {}, {})}
            client, counter, _ = self.make(100, routes)
            res = cc.run(client, [], raw, DAY, AT, counter=counter)
            self.assertEqual(len(res["failures"]), 1)
            state = json.loads((raw / "state" / cc.STATE_FILE).read_text(encoding="utf-8"))
            self.assertNotIn("B", state["done_albums"])
            self.assertEqual(state["done_artists"], [])

    def test_rate_limit_stops_gracefully(self):
        with tempfile.TemporaryDirectory() as d:
            raw = setup_raw(d, {"우리팀": {"id": "OUR", "name": "우리팀", "namesakes": 1}})
            client, counter, _ = self.make(100, {"/artists/OUR/albums": (429, {"Retry-After": "99999"}, {})})
            res = cc.run(client, [], raw, DAY, AT, counter=counter)
            self.assertIn("요청 한도", res["stopped"])
            self.assertTrue((raw / "state" / cc.STATE_FILE).exists())

    def test_track_page_falls_back_to_dev_mode_limit(self):
        def tracks(url):
            if "limit=50" in url:
                return 400, {}, {}
            return page([track("a1", ["OUR", "P"])])
        client, _, router = self.make(100, {"/albums/A/tracks": tracks})
        f = cc.Fetcher(client)
        self.assertEqual(len(f.tracks("A")), 1)
        self.assertEqual(f.track_limit, cs.PAGE_LIMIT)

    def test_unmatched_lab_name_is_searched_and_cached_separately(self):
        with tempfile.TemporaryDirectory() as d:
            raw = setup_raw(d, {})
            routes = {"/search": ok({"artists": {"items": [{"id": "NEW", "name": "새팀"}]}}), "/artists/NEW/albums": page([])}
            client, counter, _ = self.make(100, routes)
            res = cc.run(client, ["새팀"], raw, DAY, AT, counter=counter)
            self.assertEqual(res["targets"], 1)
            cache = json.loads((raw / "state" / cc.MATCH_FILE).read_text(encoding="utf-8"))
            self.assertEqual(cache["새팀"]["id"], "NEW")
            self.assertEqual(json.loads((raw / "state" / "spotify_match.json").read_text()), {})


if __name__ == "__main__":
    unittest.main()
