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
    if "-- lab:press_genres" in sql:
        return _csv(PRESS_GENRES)
    raise AssertionError(sql[:80])


PRESS_GENRES = [   # 매체 리뷰 1건 × 팀 (장르는 새 원본의 genre 칸, 비면 참고 파일 press_genres.csv)
    {"team_key": "xyz", "url": "http://musicy.kr/?ix=1", "genre": ""},
    {"team_key": "abc", "url": "https://overtone.kr/comment/a", "genre": "ROCK"},
]


class PressGenreTest(unittest.TestCase):
    """매체 리뷰 장르(음악취향Y·overtone·VISLA) → 확신도 press (docs/genre_fill.md)."""

    def test_press_genres_by_team_uses_row_then_reference(self):
        got = ex.press_genres_by_team(PRESS_GENRES + [{"team_key": "xyz", "url": "u2", "genre": "포크"}],
                                      {"http://musicy.kr/?ix=1": "록"})
        self.assertEqual(got, {"xyz": "록|포크", "abc": "ROCK"})

    def test_export_uses_press_genre_reference(self):
        with tempfile.TemporaryDirectory() as d:
            ex.export(Path(d), run=fake_run, today="2026-11-27", extra_refs=None, raw_videos=None, image_cache=None,
                      press_genre_ref=lambda: {"http://musicy.kr/?ix=1": "포크"})
            with open(Path(d) / "teams.csv", encoding="utf-8") as f:
                rows = {r["team_key"]: r for r in csv.DictReader(f)}
        # 리뷰 장르는 review(press 아래) — xyz 는 리드머 출처 힌트(press 힙합)가 먼저
        self.assertEqual((rows["xyz"]["primary_genre"], rows["xyz"]["genre_confidence"]), ("힙합", "press"))
        self.assertEqual((rows["abc"]["primary_genre"], rows["abc"]["genre_confidence"]), ("록·밴드", "press"))


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

    def test_candidate_excluded_teams_are_dropped_from_team_table(self):
        roles = {"candidate_rules": {"excluded_teams": {TEAMS[0]["team_key"]: "팀이 아님"}}}
        keys = [r["team_key"] for r in ex.team_rows(TEAMS, roles)]
        self.assertNotIn(TEAMS[0]["team_key"], keys)
        self.assertIn(TEAMS[1]["team_key"], keys)


class TeamOverrideTest(unittest.TestCase):
    """config/debut_overrides.json(사람이 확인한 데뷔일) · config/genre_overrides.json(사람이 확인한 장르)."""
    EV = {"reason": "근거", "evidence": ["https://example.com"], "checked": "2026-11-27"}

    def test_debut_override_takes_earlier_of_override_and_profile(self):
        overrides = {"abc": {"debut": "2016-07-02", **self.EV},          # 프로필 첫 발매 없음 → 덮어쓰기 날짜
                     "xyz": {"debut": "2025-05-01", **self.EV}}          # 프로필(2024-01-01)이 더 이름 → 그대로
        rows = {r["team_key"]: r for r in ex.team_rows(TEAMS, debut_overrides=overrides)}
        self.assertEqual(rows["abc"]["first_release"], "2016-07-02")
        self.assertEqual(rows["xyz"]["first_release"], "2024-01-01")
        earlier = ex.team_rows(TEAMS, debut_overrides={"xyz": {"debut": "2019-03-01", **self.EV}})
        self.assertEqual(earlier[1]["first_release"], "2019-03-01")

    def test_genre_override_replaces_inferred_genre(self):
        rows = ex.team_rows(TEAMS, genre_overrides={"abc": {"genre": "metal", **self.EV}})
        self.assertEqual(rows[0]["primary_genre"], "메탈·하드코어")
        self.assertEqual(rows[1]["primary_genre"], "힙합")   # 덮어쓰기 없는 팀은 그대로

    def _load(self, kind, entry):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "o.json"
            p.write_text(json.dumps({"_설명": "x", "teams": {"abc": entry}}, ensure_ascii=False), encoding="utf-8")
            return ex.load_team_overrides(p, kind)

    def test_loader_accepts_valid_entries(self):
        self.assertEqual(self._load("debut", {"debut": "2016-07-02", **self.EV})["abc"]["debut"], "2016-07-02")
        self.assertEqual(self._load("genre", {"genre": "rock", **self.EV})["abc"]["genre"], "rock")

    def test_loader_requires_evidence_and_valid_values(self):
        broken = [("debut", {"debut": "2016-07-02", "reason": "r", "evidence": [], "checked": "2026-11-27"}),
                  ("debut", {"debut": "2016-07-02", "reason": "r", "evidence": ["https://e"]}),           # 확인 날짜 없음
                  ("debut", {"debut": "2016/07/02", **self.EV}),
                  ("debut", {"debut": "2016-13-40", **self.EV}),
                  ("genre", {"genre": "kpop-idol", **self.EV}),                                         # 장르 지도에 없는 갈래
                  ("genre", {"genre": "rock", "evidence": ["https://e"], "checked": "2026-11-27"})]       # 이유 없음
        for kind, entry in broken:
            with self.assertRaises(ValueError, msg=entry):
                self._load(kind, entry)

    def test_missing_file_means_no_overrides(self):
        self.assertEqual(ex.load_team_overrides(Path("/nonexistent/overrides.json"), "debut"), {})

    def test_repo_override_files_are_valid_and_cover_review_teams(self):
        debut = ex.load_team_overrides(ex.DEBUT_OVERRIDES_FILE, "debut")
        genre = ex.load_team_overrides(ex.GENRE_OVERRIDES_FILE, "genre")
        for key in ("클라프", "콘트라젤리", "에이틴에이프릴", "티어드랍", "신스네이크", "애니멀다이버스", "놀플라워", "바림",
                    "하즈", "세일러허니문"):   # docs/top_candidates_review.md R1
            self.assertIn(key, debut)
            self.assertLess(debut[key]["debut"], "2023-11-27", key)   # 모두 표본 기준일 3년 전보다 이른 데뷔
        self.assertEqual(genre["하즈"]["genre"], "metal")

    def test_export_applies_repo_overrides(self):
        fake_teams = [{**TEAMS[0], "team_key": "클라프", "display_name": "클라프"}]

        def run(sql):
            return _csv(fake_teams) if "-- lab:teams" in sql else fake_run(sql)
        with tempfile.TemporaryDirectory() as d:
            ex.export(Path(d), run=run, today="2026-11-27", extra_refs=None, raw_videos=None, image_cache=None)
            with open(Path(d) / "teams.csv", encoding="utf-8") as f:
                row = next(csv.DictReader(f))
        self.assertEqual(row["first_release"], "2016-07-02")


class NewcomerCheckTest(unittest.TestCase):
    """teams.csv newcomer_check: verified(첫 발매 있음·덮어쓰기 포함) / unverified(첫 발매 없음 + 그 팀을 처음 본 출처의
    수집 시작일 + 90일 안에 처음 봄 — 그 전부터 활동했을 수 있음) / first_seen(첫 발매 없음, 그 뒤에 처음 봄)."""
    SIG = [{"team_key": "old", "source": "indistreet", "signal_date": "2024-01-04"},    # 출처 시작일 = 2024-01-04
           {"team_key": "early", "source": "indistreet", "signal_date": "2024-03-01"},  # 시작 + 57일
           {"team_key": "early", "source": "musicy", "signal_date": "2025-01-01"},
           {"team_key": "late", "source": "indistreet", "signal_date": "2024-09-01"},   # 시작 + 241일
           {"team_key": "late", "source": "musicy", "signal_date": "2023-01-02"},       # 하지만 처음 본 건 musicy(시작일 그날)
           {"team_key": "mid", "source": "musicy", "signal_date": "2023-06-01"},        # musicy 시작 + 150일
           {"team_key": "rel", "source": "indistreet", "signal_date": "2024-01-10"}]

    def _teams(self, *keys, release=""):
        return [{"team_key": k, "first_release": release if k == "rel" else ""} for k in keys]

    def test_three_states(self):
        teams = ex.with_newcomer_check(self._teams("old", "early", "late", "mid", "rel", release="2020-01-01"), self.SIG)
        got = {t["team_key"]: t["newcomer_check"] for t in teams}
        self.assertEqual(got, {"old": "unverified", "early": "unverified", "late": "unverified",
                               "mid": "first_seen", "rel": "verified"})

    def test_window_boundary_is_90_days(self):
        sig = [{"team_key": "s", "source": "x", "signal_date": "2024-01-01"},
               {"team_key": "in", "source": "x", "signal_date": "2024-03-31"},    # +90일 → 미확인
               {"team_key": "out", "source": "x", "signal_date": "2024-04-01"}]   # +91일 → first_seen
        got = {t["team_key"]: t["newcomer_check"] for t in ex.with_newcomer_check(self._teams("in", "out"), sig)}
        self.assertEqual(got, {"in": "unverified", "out": "first_seen"})

    def test_does_not_mutate_input_and_team_without_signals_is_first_seen(self):
        teams = self._teams("nosig")
        out = ex.with_newcomer_check(teams, self.SIG)
        self.assertNotIn("newcomer_check", teams[0])
        self.assertEqual(out[0]["newcomer_check"], "first_seen")

    def test_export_writes_column(self):
        with tempfile.TemporaryDirectory() as d:
            ex.export(Path(d), run=fake_run, today="2026-11-27", extra_refs=None, raw_videos=None, image_cache=None)
            with open(Path(d) / "teams.csv", encoding="utf-8") as f:
                got = {r["team_key"]: r["newcomer_check"] for r in csv.DictReader(f)}
        self.assertEqual(got, {"abc": "unverified", "xyz": "verified"})   # abc: 선정 신호가 그 출처 첫 기록


class OwnReleasePartnerTest(unittest.TestCase):
    """협업 파트너 기성 판정도 본인 음반 첫 발매(first_release_own)가 있으면 그걸 쓴다 (없으면 예전 칸)."""

    def test_own_release_makes_partner_not_established(self):
        old = {"first_release_date": "2010-01-01", "album_count": "3"}
        self.assertTrue(ex._is_established("p", old, "2025-06-30", set(), {}))
        self.assertFalse(ex._is_established("p", {**old, "first_release_own": "2024-01-01"}, "2025-06-30", set(), {}))


class OutcomeRowsTest(unittest.TestCase):
    def test_label_and_boolean(self):
        row = ex.outcome_rows(OUTCOMES, ROLES)[0]
        self.assertEqual(row["program_label"], "한대음 올해의 신인")
        self.assertEqual(row["counted"], "true")


class SameHouseTest(unittest.TestCase):
    ROLES = {"signals": {"큐레이션:musicy": {"role": "discovery"}, "큐레이션:hiphople": {"role": "pending"}},
             "same_house": [{"sources": ["큐레이션:musicy"], "outcomes": ["musicy_rookie"], "apply": True},
                            {"sources": ["큐레이션:hiphople"], "outcomes": ["khha_rookie"], "apply": True},
                            {"sources": ["큐레이션:izm"], "outcomes": ["kma_rookie"], "apply": False}]}

    def _sig(self, team, src, d):
        branch, name = src.split(":")
        return {"team_key": team, "branch": branch, "source": name, "program": "", "signal_date": d}

    def test_paired_signal_before_announcement_marks_outcome(self):
        outs = [{"team_key": "a", "program": "musicy_rookie", "announced_date": "2025-12-01"},
                {"team_key": "b", "program": "khha_rookie", "announced_date": "2025-12-01"},
                {"team_key": "c", "program": "musicy_rookie", "announced_date": "2025-12-01"},
                {"team_key": "d", "program": "kma_rookie", "announced_date": "2025-12-01"}]
        sigs = [self._sig("a", "큐레이션:musicy", "2025-06-01"), self._sig("b", "큐레이션:hiphople", "2025-06-01"),
                self._sig("c", "큐레이션:musicy", "2026-01-05"), self._sig("d", "큐레이션:izm", "2025-06-01")]
        got = {r["team_key"]: (r["same_house_sources"], r["same_house_scored"])
               for r in ex.same_house_flags(outs, sigs, self.ROLES)}
        self.assertEqual(got["a"], ("큐레이션:musicy", "true"))      # 점수에 쓰는 출처 → 점수 검증에서도 뺌
        self.assertEqual(got["b"], ("큐레이션:hiphople", "false"))   # 검증 대기 출처 → 성적표에서만 뺌
        self.assertEqual(got["c"], ("", "false"))                    # 정답 뒤에 나온 신호는 상관없음
        self.assertEqual(got["d"], ("", "false"))                    # 표시만 하는 약한 짝은 적용 안 함


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


def _v(team, vid, title, channel="스페이스 공감", kind="stage", date="2026-01-01T00:00:00Z"):
    return {"team_key": team, "video_id": vid, "title": title, "channel_title": channel,
            "published_at": date, "kind": kind}


class MusicBrainzRefsTest(unittest.TestCase):
    def test_hits_become_link_refs_and_misses_are_ignored(self):
        state = {"pj": {"checked": "2026-11-28", "mbid": "m1", "urls": {
                     "youtube": ["https://www.youtube.com/channel/UCALPByojGBk2ngqNeOb-nqg"],
                     "spotify": ["4Z8W4fKeB5YxbusRsdQVPb"], "instagram": ["poseridiott"]}},
                 "cd": {"checked": "2026-11-28", "mbid": None}}
        refs = ex.musicbrainz_refs(state)
        self.assertEqual(sorted((r["platform"], r["ref"]) for r in refs),
                         [("instagram", "poseridiott"), ("spotify", "4Z8W4fKeB5YxbusRsdQVPb"),
                          ("youtube", "https://www.youtube.com/channel/UCALPByojGBk2ngqNeOb-nqg")])
        links = ex.link_rows(refs)
        self.assertEqual(len(links), 3)
        self.assertIn({"team_key": "pj", "platform": "spotify",
                       "url": "https://open.spotify.com/artist/4Z8W4fKeB5YxbusRsdQVPb"}, links)


class VideoRowsTest(unittest.TestCase):
    def test_drops_interviews_shorts_and_non_live_kbs_clips(self):
        rows = ex.video_rows([
            _v("a", "AAAAAAAAAAA", "에이 - 노래 [스페이스 공감]"),
            _v("a", "BBBBBBBBBBB", "(ENG)[MusicBank Interview Cam] 에이", channel="KBS Kpop"),
            _v("a", "CCCCCCCCCCC", "에이 셀캠 #shorts", channel="it's Live"),
            _v("a", "DDDDDDDDDDD", "에이 - 노래 [더 시즌즈-성시경의 고막남친] | KBS", channel="KBS Kpop"),
            _v("a", "EEEEEEEEEEE", "에이 근황 토크", channel="KBS Kpop"),
        ])
        self.assertEqual([r["video_id"] for r in rows], ["AAAAAAAAAAA", "DDDDDDDDDDD"])

    def test_orders_by_kind_then_recency_and_caps_per_team(self):
        raw = [_v("a", f"{i:011d}", f"에이 live {i}", kind="search", date=f"2026-01-{i + 1:02d}T00:00:00Z")
               for i in range(8)]
        raw.append(_v("a", "STAGEVIDEO1", "에이 [it's Live]", date="2025-01-01T00:00:00Z"))
        rows = ex.video_rows(raw, per_team=3)
        self.assertEqual([r["video_id"] for r in rows], ["STAGEVIDEO1", "00000000007", "00000000006"])

    def test_invalid_ids_and_duplicates_removed(self):
        rows = ex.video_rows([_v("a", "bad", "에이 live"), _v("a", "AAAAAAAAAAA", "에이 live"),
                              _v("a", "AAAAAAAAAAA", "에이 live")])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["published_at"], "2026-01-01")


class VideoRecheckTest(unittest.TestCase):
    def test_common_word_and_short_name_rows_rechecked(self):
        # 원본 raw_video 는 그대로 두고 내보낼 때 video_match 규칙으로 다시 거른다
        def v(team, display, vid, title, kind="stage"):
            return dict(_v(team, vid, title, kind=kind), display_name=display)
        rows = ex.video_rows([
            v("글로벌", "글로벌", "AAAAAAAAAAA", "원호 - BLUE │ 글로벌 대세 원호의 라이브"),
            v("day", "Day", "BBBBBBBBBBB", "조이 - Day By Day"),
            v("day", "Day", "CCCCCCCCCCC", "Day - 첫 노래 [LIVE]"),
            v("day", "Day", "DDDDDDDDDDD", "연습 브이로그", kind="official"),
            v("실리카겔", "실리카겔", "EEEEEEEEEEE", "부산에서 만난 실리카겔 LIVE"),
        ])
        self.assertEqual(sorted(r["video_id"] for r in rows), ["DDDDDDDDDDD", "EEEEEEEEEEE"])


class ImageRowsTest(unittest.TestCase):
    def test_only_https_scdn_images_with_url(self):
        rows = ex.image_rows({"a": {"url": "https://i.scdn.co/image/x", "source": "spotify"},
                              "b": {"url": None, "source": "spotify"},
                              "c": {"url": "http://i.scdn.co/image/y", "source": "spotify"}})
        self.assertEqual(rows, [{"team_key": "a", "url": "https://i.scdn.co/image/x", "source": "spotify",
                                 "page_url": ""}])

    def test_youtube_avatar_fills_teams_without_spotify_photo(self):
        spotify = {"a": {"url": "https://i.scdn.co/image/x", "source": "spotify", "spotify_id": "A" * 22},
                   "b": {"url": None, "source": "spotify"}}
        yt = {"a": {"channel_id": "UC" + "a" * 22, "avatar": "https://yt3.ggpht.com/aaa=s240"},
              "b": {"channel_id": "UC" + "b" * 22, "avatar": "https://yt3.ggpht.com/bbb=s240"},
              "c": {"channel_id": "UC" + "c" * 22, "avatar": "https://evil.example/c.jpg"},
              "d": {"channel_id": "", "avatar": ""}}
        rows = ex.image_rows(spotify, yt)
        self.assertEqual([(r["team_key"], r["source"]) for r in rows], [("a", "spotify"), ("b", "youtube")])
        self.assertEqual(rows[0]["page_url"], "https://open.spotify.com/artist/" + "A" * 22)
        self.assertEqual(rows[1]["page_url"], "https://www.youtube.com/channel/UC" + "b" * 22)


class FreshChannelsTest(unittest.TestCase):
    def test_channels_older_than_30_days_are_dropped(self):
        teams = {"a": {"checked": "2026-11-01"}, "b": {"checked": "2026-10-28"}, "c": {}}
        self.assertEqual(sorted(ex.fresh_channels(teams, "2026-11-28")), ["a"])


class PlayersExportTest(unittest.TestCase):
    def test_export_writes_players_from_links_and_all_filtered_videos(self):
        def v(vid, title, kind="stage", date="2026-01-01T00:00:00Z"):
            return {"team_key": "abc", "display_name": "에이비씨", "video_id": vid, "title": title,
                    "channel_title": "딩고 뮤직", "published_at": date, "kind": kind}
        # 무대 영상 7개(videos.csv 는 6개로 자름) + 7번째로 밀리는 공식 MV — 대표는 공식 MV
        raw = [v(f"STAGE{i:06d}", f"에이비씨 - 노래 {i} [it's Live]") for i in range(7)]
        raw.append(v("OFFICIALMV1", "에이비씨 'Song' Official MV", kind="official", date="2024-01-01T00:00:00Z"))
        with tempfile.TemporaryDirectory() as d:
            meta = ex.export(Path(d), run=fake_run, today="2026-11-27", extra_refs=None, raw_videos=lambda: raw,
                             image_cache=None, video_views=lambda: {})
            with open(Path(d) / "players.csv", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
        self.assertEqual([(r["team_key"], r["kind"], r["id"], r["source"]) for r in rows],
                         [("abc", "youtube", "OFFICIALMV1", "official")])
        self.assertEqual(meta["rows"]["players"], 1)


ROLES = {"default_role": "pending",
         "signals": {"공연:indistreet": {"role": "discovery"}, "큐레이션:izm": {"role": "context"},
                     "선정·지원:dmz_lineup": {"role": "excluded"}},
         "outcomes": {"kma_rookie": {"grade": "S", "weight": 3}}}


class RoleTest(unittest.TestCase):
    def test_signal_role_uses_program_for_selection_and_source_otherwise(self):
        self.assertEqual(ex.signal_role({"branch": "공연", "source": "indistreet", "program": ""}, ROLES), "discovery")
        self.assertEqual(ex.signal_role({"branch": "큐레이션", "source": "izm", "program": "izm"}, ROLES), "context")
        self.assertEqual(ex.signal_role({"branch": "선정·지원", "source": "x", "program": "dmz_lineup"}, ROLES), "excluded")
        self.assertEqual(ex.signal_role({"branch": "발매", "source": "melon", "program": ""}, ROLES), "pending")

    def test_outcome_grade_and_weight_default_b(self):
        rows = ex.outcome_rows([{"team_key": "a", "program": "kma_rookie", "tier": "final", "announced_date": "2025-01-01",
                                 "counted": "t"},
                                {"team_key": "b", "program": "new_prog", "tier": "mid", "announced_date": "2025-01-01",
                                 "counted": "t"}], ROLES)
        self.assertEqual((rows[0]["grade"], rows[0]["weight"]), ("S", 3))
        self.assertEqual((rows[1]["grade"], rows[1]["weight"]), ("B", 1))

    def test_nominee_is_one_grade_lower_and_winner_kept(self):
        roles = {**ROLES, "outcome_rules": {"lower_results": ["nominee", "shortlist"]},
                 "outcomes": {"kma_rookie": {"grade": "S", "weight": 3}, "musicy": {"grade": "A", "weight": 2},
                              "kma_genre": {"grade": "B", "weight": 1}}}
        base = {"tier": "final", "announced_date": "2025-01-01", "counted": "t"}
        rows = ex.outcome_rows([{**base, "team_key": "a", "program": "kma_rookie", "result": "winner"},
                                {**base, "team_key": "b", "program": "kma_rookie", "result": "nominee"},
                                {**base, "team_key": "c", "program": "musicy", "result": "shortlist"},
                                {**base, "team_key": "d", "program": "kma_genre", "result": "nominee"}], roles)
        got = {r["team_key"]: (r["grade"], r["weight"], r["result"]) for r in rows}
        self.assertEqual(got["a"], ("S", 3, "winner"))
        self.assertEqual(got["b"], ("A", 2, "nominee"))
        self.assertEqual(got["c"], ("B", 1, "shortlist"))
        self.assertEqual(got["d"], ("B", 1, "nominee"))   # B 아래는 없음

    def test_same_award_nominee_and_winner_keeps_best_row(self):
        roles = {**ROLES, "outcome_rules": {"lower_results": ["nominee"]}}
        base = {"team_key": "a", "program": "kma_rookie", "tier": "final", "announced_date": "2025-01-01", "counted": "t"}
        rows = ex.outcome_rows([{**base, "result": "nominee"}, {**base, "result": "winner"}], roles)
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["grade"], rows[0]["result"]), ("S", "winner"))

    def test_excluded_teams_are_dropped(self):
        roles = {**ROLES, "outcome_rules": {"excluded_teams": {"투어스": "대형 기획사 아이돌"}}}
        base = {"program": "kma_rookie", "tier": "final", "announced_date": "2025-01-01", "counted": "t"}
        rows = ex.outcome_rows([{**base, "team_key": "투어스"}, {**base, "team_key": "인디팀"}], roles)
        self.assertEqual([r["team_key"] for r in rows], ["인디팀"])


class CollabDateTest(unittest.TestCase):
    def test_partial_dates_become_last_day_of_period(self):
        # 시점 누수 방지: 연도만 알면 그해 마지막 날, 연·월만 알면 그 달 마지막 날
        self.assertEqual(ex.period_end_date("2024", "year"), "2024-12-31")
        self.assertEqual(ex.period_end_date("2024-02", "month"), "2024-02-29")
        self.assertEqual(ex.period_end_date("2023-02", "month"), "2023-02-28")
        self.assertEqual(ex.period_end_date("2024-05-03", "day"), "2024-05-03")
        self.assertEqual(ex.period_end_date("2024-05", ""), "2024-05-31")       # precision 없어도 모양으로 판단
        self.assertEqual(ex.period_end_date("", "day"), "")
        self.assertEqual(ex.period_end_date("2024-13", "month"), "")


def _collab(artist, partner, date, prec="day", role="feat_on_own"):
    return {"artist_name": artist, "artist_spotify_id": "A" * 22, "partner_spotify_id": f"P-{partner}",
            "partner_name": partner, "track_id": f"t-{artist}-{partner}-{date}", "release_date": date,
            "release_date_precision": prec, "role": role}


class CollabRowsTest(unittest.TestCase):
    TEAMS = [{"team_key": "유명팀", "profile_status": "famous"}, {"team_key": "신인", "profile_status": "unknown"}]
    OUTCOMES = [{"team_key": "수상팀", "announced_date": "2024-03-01", "counted": "true"},
                {"team_key": "늦은수상", "announced_date": "2025-06-01", "counted": "true"},
                {"team_key": "안센정답", "announced_date": "2023-01-01", "counted": "false"}]
    PARTNERS = [{"partner_spotify_id": "P-오래된", "first_release_date": "2015-05-01", "album_count": "3"},
                {"partner_spotify_id": "P-앨범많음", "first_release_date": "2023-01-01", "album_count": "15"},
                {"partner_spotify_id": "P-새팀", "first_release_date": "2022-01-01", "album_count": "4"}]

    def rows(self, collabs):
        key = lambda n: n.replace(" ", "").lower()   # noqa: E731  (가짜 canonical_key)
        return {r["partner_key"]: r for r in ex.collab_rows(collabs, self.PARTNERS, self.TEAMS, self.OUTCOMES, key)}

    def test_established_rules(self):
        got = self.rows([_collab("우리 팀", p, "2024-06-01") for p in
                         ("오래된", "앨범많음", "새팀", "유명팀", "수상팀", "늦은수상", "안센정답", "모르는팀")])
        self.assertEqual(got["오래된"]["partner_established"], "true")     # 첫 발매가 9년 앞섬 (≥5년)
        self.assertEqual(got["앨범많음"]["partner_established"], "true")   # 앨범 15개 이상
        self.assertEqual(got["새팀"]["partner_established"], "false")      # 2년 앞섬, 앨범 4
        self.assertEqual(got["유명팀"]["partner_established"], "true")     # teams 에서 famous
        self.assertEqual(got["수상팀"]["partner_established"], "true")     # 협업 전에 센 정답
        self.assertEqual(got["늦은수상"]["partner_established"], "false")  # 정답이 협업 뒤 → 그때는 몰랐음
        self.assertEqual(got["안센정답"]["partner_established"], "false")  # 안 센 정답은 무시
        self.assertEqual(got["모르는팀"]["partner_established"], "false")  # 정보 없음

    def test_five_year_boundary_uses_collab_date(self):
        partners = [{"partner_spotify_id": "P-x", "first_release_date": "2019-06-01", "album_count": "1"}]
        key = lambda n: n   # noqa: E731
        early = ex.collab_rows([_collab("a", "x", "2024-05-31")], partners, [], [], key)
        late = ex.collab_rows([_collab("a", "x", "2024-06-01")], partners, [], [], key)
        self.assertEqual((early[0]["partner_established"], late[0]["partner_established"]), ("false", "true"))

    def test_keys_dates_and_columns(self):
        rows = ex.collab_rows([_collab("우리 팀", "새 팀", "2024", "year", "guest_on_partner")],
                              self.PARTNERS, self.TEAMS, self.OUTCOMES, lambda n: n.replace(" ", ""))
        self.assertEqual(rows, [{"team_key": "우리팀", "partner_key": "새팀", "partner_name": "새 팀",
                                 "release_date": "2024-12-31", "role": "guest_on_partner",
                                 "partner_established": "false"}])
        self.assertEqual(list(rows[0]), ex.COLLAB_FIELDS)

    def test_skips_bad_rows_self_and_duplicates(self):
        key = lambda n: n   # noqa: E731
        rows = ex.collab_rows([_collab("a", "b", ""), _collab("a", "a", "2024-01-01"),
                               _collab("a", "b", "2024-01-01"), _collab("a", "b", "2024-01-01"),
                               _collab("", "b", "2024-01-01")], [], [], [], key)
        self.assertEqual(len(rows), 1)

    def test_uses_artist_xref_canonical_key_by_default(self):
        rows = ex.collab_rows([_collab("피치 트럭 하이재커스(Peach Truck Hijackers)", "다브다 (Dabda)", "2024-01-01")],
                              [], [], [], key_of=None, xref_index={"by_key": {}})
        self.assertEqual((rows[0]["team_key"], rows[0]["partner_key"]), ("피치트럭하이재커스", "다브다"))


class ExportTest(unittest.TestCase):
    def test_writes_all_files_with_meta(self):
        with tempfile.TemporaryDirectory() as d:
            meta = ex.export(Path(d), run=fake_run, today="2026-11-27", extra_refs=None, raw_videos=None, image_cache=None)
            for name in ("signals.csv", "teams.csv", "outcomes.csv", "programs.csv", "links.csv", "meta.json",
                         "source_roles.json"):
                self.assertTrue((Path(d) / name).exists(), name)
            self.assertEqual(meta["rows"]["signals"], 3)
            self.assertEqual(meta["rows"]["links"], 1)
            self.assertEqual(meta["data_end"], "2026-11-27")
            self.assertTrue(meta["uses_artist_xref"])
            saved = json.loads((Path(d) / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["rows"]["teams"], 2)

    def test_collabs_csv_written_with_meta_count(self):
        fake = lambda: ([_collab("에이", "비", "2024-03")], [])   # noqa: E731
        with tempfile.TemporaryDirectory() as d:
            meta = ex.export(Path(d), run=fake_run, today="2026-11-27", extra_refs=None, raw_videos=None,
                             image_cache=None, raw_collabs=fake)
            self.assertEqual(meta["rows"]["collabs"], 1)
            with open(Path(d) / "collabs.csv", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(rows[0]["release_date"], "2024-03-31")

    def test_collabs_csv_header_only_when_no_data(self):
        with tempfile.TemporaryDirectory() as d:
            meta = ex.export(Path(d), run=fake_run, today="2026-11-27", extra_refs=None, raw_videos=None,
                             image_cache=None, raw_collabs=None)
            self.assertEqual(meta["rows"]["collabs"], 0)
            text = (Path(d) / "collabs.csv").read_text(encoding="utf-8").strip()
            self.assertEqual(text, ",".join(ex.COLLAB_FIELDS))

    def test_meta_keeps_previous_run_counts(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "meta.json").write_text(json.dumps({"rows": {"signals": 2, "videos": 5}}), encoding="utf-8")
            meta = ex.export(Path(d), run=fake_run, today="2026-11-27", extra_refs=None, raw_videos=None,
                             image_cache=None)
            self.assertEqual(meta["prev_rows"], {"signals": 2, "videos": 5})
            again = ex.export(Path(d), run=fake_run, today="2026-11-27", extra_refs=None, raw_videos=None,
                              image_cache=None)
            self.assertEqual(again["prev_rows"], {"signals": 2, "videos": 5})   # 같은 날 재실행 → 어제 값 유지

    def test_programs_list_marks_outcome_and_signal_kinds(self):
        with tempfile.TemporaryDirectory() as d:
            ex.export(Path(d), run=fake_run, today="2026-11-27", extra_refs=None, raw_videos=None, image_cache=None)
            with open(Path(d) / "programs.csv", encoding="utf-8") as f:
                kinds = {r["program"]: r["kind"] for r in csv.DictReader(f)}
            self.assertEqual(kinds["band_discovery"], "signal")
            self.assertEqual(kinds["kma_rookie"], "outcome")


if __name__ == "__main__":
    unittest.main()
