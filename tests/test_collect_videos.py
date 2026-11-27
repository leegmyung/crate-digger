"""유튜브 무대 영상 수집기 테스트 — 실제 API 대신 가짜 HTTP 응답으로 (네트워크 안 씀)."""
import csv
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import collect_videos as cv  # noqa: E402

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 27, 21, 0, tzinfo=KST)
TEAMS = [
    ("사뮈", "사뮈 (Samui)"),
    ("로맨틱펀치", "로맨틱펀치"),
    ("카디", "카디"),
    ("사랑", "사랑"),          # 흔한 낱말 → 제외 목록
    ("air", "Air"),            # 흔한 영어 낱말 → 제외 목록
    ("향", "향"),              # 한 글자 → 제외
    ("57", "57"),              # 숫자만 → 제외
    ("새소년", "새소년"),
    ("투데이올드스니커즈", "투데이 올드 스니커즈"),
    ("세이수미", "세이수미 (Say Sue Me)"),
]


def video_item(vid, title, published, channel="채널", channel_id="UCxxxxxxxxxxxxxxxxxxxxxx"):
    return {"snippet": {"title": title, "channelTitle": channel, "channelId": channel_id,
                        "resourceId": {"videoId": vid}},
            "contentDetails": {"videoId": vid, "videoPublishedAt": published}}


def search_item(vid, title, published, channel="누군가"):
    return {"id": {"kind": "youtube#video", "videoId": vid},
            "snippet": {"title": title, "channelTitle": channel, "channelId": "UCyyyyyyyyyyyyyyyyyyyyyy",
                        "publishedAt": published}}


class FakeHttp:
    """URL에 들어 있는 글자 → 응답(dict) 또는 응답 목록(차례로). 호출 기록을 남긴다."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        for part, resp in self.routes.items():
            if part in url:
                if isinstance(resp, list):
                    return 200, resp.pop(0) if len(resp) > 1 else resp[0]
                return 200, resp
        return 404, {"error": {"errors": [{"reason": "notFound"}]}}


def client(routes, budget=5000):
    http = FakeHttp(routes)
    return cv.YouTubeClient("테스트키", http=http, quota=cv.Quota(budget)), http


class TitleMatcherTest(unittest.TestCase):
    def setUp(self):
        self.m = cv.TitleMatcher(TEAMS)

    def keys(self, title):
        return [k for k, _ in self.m.match(title)]

    def test_whole_token_match(self):
        self.assertEqual(self.keys("[it's Live] 로맨틱펀치 - 파라다이스"), ["로맨틱펀치"])

    def test_no_partial_token(self):
        # '카디'가 '카디건' 안에 들어 있어도 낱말이 아니면 안 잡는다
        self.assertEqual(self.keys("카디건 입고 부르는 노래"), [])

    def test_alias_and_case(self):
        self.assertEqual(self.keys("SAMUI - live clip"), ["사뮈"])
        self.assertEqual(self.keys("say sue me | Old Town"), ["세이수미"])

    def test_stoplist_short_and_digits(self):
        self.assertEqual(self.keys("사랑 - 밴드 라이브"), [])
        self.assertEqual(self.keys("Air - session"), [])
        self.assertEqual(self.keys("향 - 노래"), [])
        self.assertEqual(self.keys("57 - 노래"), [])

    def test_multi_token_name(self):
        self.assertEqual(self.keys("투데이 올드 스니커즈 - 사랑의 노래 | 딩고"), ["투데이올드스니커즈"])

    def test_short_name_needs_credit_position(self):
        # 두 글자 한글 이름은 맨 앞이나 구분 기호 옆에 있을 때만
        self.assertEqual(self.keys("[딩고] 카디 - 노래"), ["카디"])
        self.assertEqual(self.keys("오늘의 카디 노래 모음"), [])
        self.assertEqual(self.keys("노래 | 카디"), ["카디"])
        # 제목 가운데의 '[...' 안은 작품 이름일 때가 많아 짧은 이름은 인정하지 않는다
        self.assertEqual(self.keys("뮤지컬 [카디 앤 클라이드] 배우 - 노래"), [])

    def test_longest_match_wins(self):
        self.assertEqual(self.keys("새소년 - 난춘"), ["새소년"])

    def test_names_for_team(self):
        self.assertEqual(self.m.match("SAMUI 라이브", only="사뮈"), [("사뮈", "사뮈 (Samui)")])
        self.assertEqual(self.m.match("로맨틱펀치 라이브", only="사뮈"), [])

    def test_original_artist_credit_ignored(self):
        # '(원곡: 팀)'·'cover by' 처럼 원곡자로만 나온 이름은 출연이 아니다
        self.assertEqual(self.keys("이찬원 - 여행을 떠나요 (원곡: 로맨틱펀치) | KBS"), [])
        self.assertEqual(self.keys("노래 (Original by 새소년) | 커버"), [])

    def test_program_tag_words_stoplisted(self):
        m = cv.TitleMatcher([("하이라이트", "하이라이트"), ("화이트", "화이트")])
        self.assertEqual(m.match("[하이라이트] 누군가 - 노래"), [])
        self.assertEqual(m.match("컨파인드 화이트 - 노래"), [])

    def test_ambiguous_name_dropped(self):
        m = cv.TitleMatcher([("a1", "블루문"), ("a2", "블루문")])
        self.assertEqual(m.match("블루문 - 노래"), [])


class UrlParseTest(unittest.TestCase):
    def test_parse(self):
        p = cv.parse_youtube_url
        self.assertEqual(p("https://www.youtube.com/@3amui"), ("handle", "@3amui"))
        self.assertEqual(p("https://www.youtube.com/@%EC%9E%A5%EB%B2%94%EC%A4%80"), ("handle", "@장범준"))
        self.assertEqual(p("https://youtube.com/@123areswimming?si=abc"), ("handle", "@123areswimming"))
        self.assertEqual(p("https://www.youtube.com/@sim.O/featured"), ("handle", "@sim.O"))
        self.assertEqual(p("https://www.youtube.com/channel/UC2KmG_o7JZcPr052P87GdsQ"),
                         ("id", "UC2KmG_o7JZcPr052P87GdsQ"))
        self.assertEqual(p("https://www.youtube.com/c/IDIOTAPE/"), ("custom", "IDIOTAPE"))
        self.assertEqual(p("https://www.youtube.com/user/foo"), ("user", "foo"))
        self.assertEqual(p("https://www.youtube.com/yunsaemusic"), ("custom", "yunsaemusic"))
        self.assertIsNone(p("https://www.instagram.com/x/"))
        self.assertIsNone(p("https://www.youtube.com/watch?v=abc"))

    def test_video_id(self):
        self.assertTrue(cv.valid_video_id("dQw4w9WgXcQ"))
        self.assertFalse(cv.valid_video_id("short"))
        self.assertFalse(cv.valid_video_id("dQw4w9WgXcQ<"))


class QuotaTest(unittest.TestCase):
    def test_budget_stop_before_overspend(self):
        q = cv.Quota(150)
        q.spend(100)
        with self.assertRaises(cv.QuotaExceeded):
            q.spend(100)
        self.assertEqual(q.used, 100)
        self.assertTrue(q.can(50))

    def test_api_quota_error_raises(self):
        yt, _ = client({})
        yt._http = lambda url: (403, {"error": {"errors": [{"reason": "quotaExceeded"}]}})
        with self.assertRaises(cv.QuotaExceeded):
            yt.get("channels", {"id": "x"}, cost=1)

    def test_run_stops_gracefully_and_saves_state(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            ranked = ["로맨틱펀치", "새소년", "카디"]
            yt, http = client({"search": {"items": [search_item("AAAAAAAAAAA", "새소년 라이브", "2026-10-01T00:00:00Z")]}},
                              budget=250)
            state = {}
            rows = cv.run_search(yt, cv.TitleMatcher(TEAMS), ranked, state, NOW, n=40)
            # 100단위씩 → 250 예산이면 2번만 검색하고 멈춘다
            self.assertEqual(sum("search?" in c for c in http.calls), 2)
            self.assertEqual(yt.quota.used, 200)
            self.assertEqual(sorted(state["searched"]), ["로맨틱펀치", "새소년"])
            self.assertEqual([r["team_key"] for r in rows], ["새소년"])
            path = d / "state.json"
            cv.save_state(path, state)
            self.assertEqual(cv.load_state(path)["searched"]["새소년"], NOW.date().isoformat())


class StateResumeTest(unittest.TestCase):
    def test_seven_day_skip(self):
        state = {"searched": {"로맨틱펀치": (NOW.date() - timedelta(days=3)).isoformat(),
                              "새소년": (NOW.date() - timedelta(days=8)).isoformat()}}
        picked = cv.pick_search_teams(["로맨틱펀치", "새소년", "카디", "사랑"], state, NOW.date(),
                                      n=40, matcher=cv.TitleMatcher(TEAMS))
        # 3일 전에 찾은 팀은 건너뛰고, 제외 목록 이름(사랑)은 검색 비용을 아끼려 뺀다
        self.assertEqual(picked, ["새소년", "카디"])

    def test_missing_state_file(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(cv.load_state(Path(d) / "없음.json"), {})

    def test_sweep_pages_until_last_seen(self):
        ch = {"handle": "@dingo", "uploads": "UUabc", "name": "딩고"}
        page1 = {"items": [video_item("AAAAAAAAAAA", "카디 - 노래", "2026-11-26T10:00:00Z"),
                           video_item("BBBBBBBBBBB", "아무개 - 노래", "2026-11-20T10:00:00Z")],
                 "nextPageToken": "P2"}
        page2 = {"items": [video_item("CCCCCCCCCCC", "로맨틱펀치 - 노래", "2026-11-01T10:00:00Z")],
                 "nextPageToken": "P3"}
        yt, http = client({"pageToken=P2": page2, "playlistItems": page1})
        state = {"channels": {"@dingo": {"last_published": "2026-11-10T00:00:00Z"}}}
        rows = cv.sweep_channel(yt, ch, cv.TitleMatcher(TEAMS), state, NOW)
        # 2쪽에서 지난번보다 오래된 영상을 만나면 3쪽은 안 부른다
        self.assertEqual(sum("playlistItems" in c for c in http.calls), 2)
        self.assertEqual([(r["team_key"], r["kind"]) for r in rows], [("카디", "stage")])
        self.assertEqual(state["channels"]["@dingo"]["last_published"], "2026-11-26T10:00:00Z")

    def test_sweep_skips_fancams(self):
        ch = {"handle": "@kbs", "uploads": "UUabc", "name": "KBS"}
        page = {"items": [video_item("AAAAAAAAAAA", "[K-Fancam] 로맨틱펀치 직캠 'X' @뮤직뱅크", "2026-11-26T10:00:00Z"),
                          video_item("BBBBBBBBBBB", "카디 - 노래 [더 시즌즈]", "2026-11-25T10:00:00Z")]}
        yt, _ = client({"playlistItems": page})
        rows = cv.sweep_channel(yt, ch, cv.TitleMatcher(TEAMS), {}, NOW)
        self.assertEqual([r["team_key"] for r in rows], ["카디"])

    def test_sweep_interrupted_keeps_old_mark(self):
        ch = {"handle": "@dingo", "uploads": "UUabc", "name": "딩고"}
        page1 = {"items": [video_item("AAAAAAAAAAA", "카디 - 노래", "2026-11-26T10:00:00Z")],
                 "nextPageToken": "P2"}
        yt, _ = client({"playlistItems": page1}, budget=1)
        state = {"channels": {"@dingo": {"last_published": "2026-11-10T00:00:00Z"}}}
        with self.assertRaises(cv.QuotaExceeded) as ctx:
            cv.sweep_channel(yt, ch, cv.TitleMatcher(TEAMS), state, NOW)
        # 끝까지 못 훑었으면 표시를 옮기지 않아 다음 날 다시 훑는다 (찾은 행은 예외에 실어 보낸다)
        self.assertEqual(state["channels"]["@dingo"]["last_published"], "2026-11-10T00:00:00Z")
        self.assertEqual([r["team_key"] for r in ctx.exception.rows], ["카디"])


class OfficialTest(unittest.TestCase):
    def test_official_kinds_and_resolve_cache(self):
        uploads = {"items": [video_item("AAAAAAAAAAA", "사뮈 - 노래 (LIVE CLIP)", "2026-11-01T00:00:00Z"),
                             video_item("BBBBBBBBBBB", "사뮈 - 노래 MV", "2026-10-01T00:00:00Z"),
                             video_item("bad", "깨진 ID", "2026-10-01T00:00:00Z")]}
        chan = {"items": [{"id": "UC3amui0000000000000000", "snippet": {"title": "사뮈"},
                           "contentDetails": {"relatedPlaylists": {"uploads": "UU3amui0000000000000000"}}}]}
        yt, http = client({"channels": chan, "playlistItems": uploads})
        state = {}
        rows = cv.official_videos(yt, "사뮈", "사뮈 (Samui)", "https://www.youtube.com/@3amui", state, NOW)
        self.assertEqual([(r["video_id"], r["kind"]) for r in rows],
                         [("AAAAAAAAAAA", "official_live"), ("BBBBBBBBBBB", "official")])
        self.assertEqual(state["resolved"]["https://www.youtube.com/@3amui"], "UU3amui0000000000000000")
        cv.official_videos(yt, "사뮈", "사뮈 (Samui)", "https://www.youtube.com/@3amui", state, NOW)
        self.assertEqual(sum("channels?" in c for c in http.calls), 1)   # 두 번째는 저장된 값 사용

    def test_channel_id_url_needs_no_lookup(self):
        yt, http = client({"playlistItems": {"items": []}})
        state = {}
        cv.official_videos(yt, "x", "x", "https://www.youtube.com/channel/UC2KmG_o7JZcPr052P87GdsQ", state, NOW)
        self.assertFalse(any("channels?" in c for c in http.calls))
        self.assertIn("playlistId=UU2KmG_o7JZcPr052P87GdsQ", http.calls[0])


class CsvTest(unittest.TestCase):
    def row(self, team, vid, kind="stage"):
        return {"collected_at": NOW.isoformat(), "team_key": team, "display_name": team, "video_id": vid,
                "title": "t", "channel_title": "c", "channel_id": "UC", "published_at": "2026-11-01T00:00:00Z",
                "kind": kind, "source_channel_handle": "@x"}

    def test_dedupe_and_merge_existing(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "raw_video_2026-11-27.csv"
            cv.write_rows(path, [self.row("카디", "AAAAAAAAAAA")])
            cv.write_rows(path, [self.row("카디", "AAAAAAAAAAA", "search"), self.row("카디", "BBBBBBBBBBB"),
                                 self.row("새소년", "AAAAAAAAAAA"), self.row("카디", "bad")])
            with open(path, encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
            self.assertEqual(list(rows[0].keys()), cv.COLUMNS)
            self.assertEqual([(r["team_key"], r["video_id"], r["kind"]) for r in rows],
                             [("카디", "AAAAAAAAAAA", "stage"), ("카디", "BBBBBBBBBBB", "stage"),
                              ("새소년", "AAAAAAAAAAA", "stage")])


class EnvTest(unittest.TestCase):
    def test_env_file_and_override(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / ".env"
            p.write_text("# 주석\nYOUTUBE_API_KEY='abc'\nOTHER=1\n", encoding="utf-8")
            self.assertEqual(cv.load_env(p, {})["YOUTUBE_API_KEY"], "abc")
            self.assertEqual(cv.load_env(p, {"YOUTUBE_API_KEY": "env"})["YOUTUBE_API_KEY"], "env")


if __name__ == "__main__":
    unittest.main()
