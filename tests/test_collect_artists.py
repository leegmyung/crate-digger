"""아티스트 메타데이터(멜론 아티스트 페이지) 수집기 테스트 — aside 없이 실제 페이지 구조를 줄인 가짜 데이터로."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import collect_artists as ca  # noqa: E402
import validate_csv  # noqa: E402

_MODULE_TMP = None
_MODULE_PATCHES = []


def setUpModule():
    """수집 흐름 테스트가 실제 상태 파일(못 찾은 이유 기록)을 쓰거나 실제 트랙제로·링크 번호를 읽지 않게 모듈 전체에서 막는다.
    필요한 테스트는 안에서 다시 덮어쓴다."""
    from unittest import mock
    global _MODULE_TMP
    _MODULE_TMP = tempfile.TemporaryDirectory()
    _MODULE_PATCHES[:] = [mock.patch.object(ca, "MISSES_STATE", Path(_MODULE_TMP.name) / "misses.json"),
                          mock.patch.object(ca, "GENRE_SEEN_STATE", Path(_MODULE_TMP.name) / "genre_first_seen.json"),
                          mock.patch.object(ca, "_known_melon_ids", return_value={})]
    for p in _MODULE_PATCHES:
        p.start()


def tearDownModule():
    for p in _MODULE_PATCHES:
        p.stop()
    _MODULE_TMP.cleanup()


AT = "2026-11-26T21:00:00+09:00"
INFO = """<div class="wrap_atist_info"> <p class="title_atist"><strong class="none">아티스트명</strong>에피톤&nbsp;프로젝트</p>
<dl class="atist_info clfix"> <dt>데뷔</dt> <dd> <span class="gubun">2006.12.12</span> <a href="#" class="btn_play_song"> <span class="icon_play">곡재생</span>
<span class="songname12">좋았던 순간은 늘 잔인하다</span> </a> </dd> <dt>활동유형</dt> <dd>솔로</dd> <dt>소속사</dt> <dd>(주)인터파크</dd> </dl></div>"""
DETAIL_DL = ["데뷔 2006.12.12 활동년대 2000, 2010, 2020 년대 유형 솔로 |남성 장르 인디음악, 발라드, 록/메탈 소속사명 (주)인터파크", "국적 대한민국"]
PAGE = {"info": INFO, "fan": "33,496", "dl": DETAIL_DL + ["SNS 페이스북 트위터 YouTube https://www.youtube.com/@epitone"],
        "albums": "앨범(46)", "album_dates": ["2026.11.26", "2008.05.01", "2007.03.15"]}
GROUP = {"info": """<div class="wrap_atist_info"><p class="title_atist"><strong class="none">아티스트명</strong>고고학 (Gogohawk)</p>
<dl class="atist_info"><dt>활동유형</dt><dd>그룹</dd></dl></div>""", "fan": "1,162", "albums": "앨범(15)",
         "dl": ["유형 그룹 장르 인디음악, 록/메탈, 재즈", "아티스트명 강전호 대한민국/남성/솔로 음악장르 팬맺기 9 아티스트명 하범석 대한민국/남성/솔로 음악장르 인디음악|포크/블루스",
                "국적 대한민국 YouTube https://www.youtube.com/channel/UC123"],
         "album_dates": ["2023.09.26", "2022.12.22", "2022.12.04"]}
NEWBIE = {"info": """<div class="wrap_atist_info"><p class="title_atist"><strong class="none">아티스트명</strong>새벽정류장</p>
<dl class="atist_info"><dt>데뷔</dt><dd><span class="gubun">2026.03</span></dd><dt>활동유형</dt><dd>그룹</dd></dl></div>""",
          "fan": "0", "dl": [], "albums": "앨범(2)"}


class MelonArtistTest(unittest.TestCase):
    def test_full_profile(self):
        p = ca.parse_melon_artist(PAGE)
        self.assertEqual(p, {"artist_text": "에피톤 프로젝트", "debut_date": "2006-12-12", "debut_title": "좋았던 순간은 늘 잔인하다",
                             "activity_type": "솔로", "agency_text": "(주)인터파크", "genre": "인디음악|발라드|록/메탈",
                             "nationality": "대한민국", "fan_count": "33496", "album_count": "46",
                             "first_release_date": "2007-03-15", "first_release_own": "",   # 본인 음반 목록이 없는 옛 페이지
                             "youtube_url": "https://www.youtube.com/@epitone"})

    def test_member_list_and_sns_do_not_leak_into_genre_or_nationality(self):
        p = ca.parse_melon_artist(GROUP)
        self.assertEqual((p["genre"], p["nationality"], p["youtube_url"], p["first_release_date"], p["debut_date"]),
                         ("인디음악|록/메탈|재즈", "대한민국", "https://www.youtube.com/channel/UC123", "2022-12-04", ""))

    def test_partial_debut_and_missing_fields(self):
        p = ca.parse_melon_artist(NEWBIE)
        self.assertEqual((p["artist_text"], p["debut_date"], p["agency_text"], p["fan_count"], p["album_count"]),
                         ("새벽정류장", "2026-03", "", "0", "2"))

    def test_empty_page(self):
        self.assertEqual(ca.parse_melon_artist({})["artist_text"], "")


class TargetsTest(unittest.TestCase):
    def test_new_melon_artist_ids_from_release_rows(self):
        rows = [{"source": "melon", "artist_source_id": "181716", "artist_text": "에피톤 프로젝트"},
                {"source": "melon", "artist_source_id": "181716", "artist_text": "에피톤 프로젝트"},
                {"source": "melon", "artist_source_id": "", "artist_text": "번호 없음"},
                {"source": "bugs", "artist_source_id": "20026154", "artist_text": "오존"},
                {"source": "melon", "artist_source_id": "999", "artist_text": "이미 봄"}]
        self.assertEqual(ca.targets(rows, seen={"999"}), ["181716"])


class RowTest(unittest.TestCase):
    def test_row_and_validator(self):
        rows = [ca.to_row("181716", ca.parse_melon_artist(PAGE), AT), ca.to_row("5", ca.parse_melon_artist(NEWBIE), AT)]
        self.assertEqual(rows[0]["url"], "https://www.melon.com/artist/detail.htm?artistId=181716")
        self.assertEqual(rows[0]["artist_key"], "에피톤프로젝트")
        with tempfile.TemporaryDirectory() as d:
            path = ca.write_csv(rows, Path(d), "2026-11-26")
            errs = [i for i in validate_csv.validate_file(path) if i.level == "error"]
        self.assertEqual(path.name, "raw_artist_profile_2026-11-26_melon.csv")
        self.assertEqual(errs, [])

    def test_page_without_name_gives_no_row(self):
        self.assertIsNone(ca.to_row("1", ca.parse_melon_artist({}), AT))


class MatchTest(unittest.TestCase):
    CANDS = [["3940959", "산보", "대한민국/혼성/그룹 음악장르 인디음악"],
             ["1110001", "산보 (Sanbo)", "대한민국/남성/솔로 음악장르 트로트"],
             ["2220002", "산보라", "대한민국/여성/솔로"]]

    def test_name_keys_include_alias(self):
        self.assertEqual(ca.name_keys("BØJEONG(비공정)"), {"bjeong", "비공정"} | {ca.artist_key("BØJEONG")})
        self.assertEqual(ca.name_keys("피치트럭 하이재커스(Peach Truck Hijackers)"), {"피치트럭하이재커스", "peachtruckhijackers"})

    def test_exact_key_match_and_namesake_flag(self):
        m = ca.match_candidate("산보", self.CANDS)
        self.assertEqual((m["id"], m["namesakes"]), ("3940959", 2))   # '산보 (Sanbo)'도 키가 같음 → 동명 2팀

    def test_alias_match(self):
        m = ca.match_candidate("피치트럭 하이재커스(Peach Truck Hijackers)", [["3000009", "Peach Truck Hijackers", ""]])
        self.assertEqual(m["id"], "3000009")

    def test_no_match(self):
        self.assertIsNone(ca.match_candidate("없는팀", self.CANDS))

    def test_placeholder_ids_are_never_matched(self):   # 멜론 '여러 아티스트' 같은 공용 번호(0, 1)
        self.assertIsNone(ca.match_candidate("Various Artists", [["1", "Various Artists", ""], ["0", "Various Artists", ""]]))
        self.assertEqual(ca.match_candidate("산보", [["0", "산보", ""]] + self.CANDS)["id"], "3940959")


class SearchIdTest(unittest.TestCase):
    """멜론 검색 결과 링크에서 번호 읽기 — 이름 속 숫자를 번호로 잘못 읽던 버그 (12BH→12 등)."""
    HREF = "javascript:searchLog('web_artist','ARTIST','AR','{name}','');melon.link.goArtistDetail('{id}');"

    def test_id_from_goartistdetail_not_first_number(self):
        for name, mid in (("12BH", "3201955"), ("D82", "2876543"), ("닥터코어911", "2765432"), ("9B2", "3456789"),
                          ("hathaw9y", "3012345")):
            self.assertEqual(ca.melon_id_from_href(self.HREF.format(name=name, id=mid)), mid, name)

    def test_short_or_placeholder_ids_rejected(self):
        self.assertEqual(ca.melon_id_from_href("javascript:melon.link.goArtistDetail('12');"), "")
        self.assertEqual(ca.melon_id_from_href("javascript:melon.link.goArtistDetail('1');"), "")
        self.assertEqual(ca.melon_id_from_href("javascript:void(0)"), "")
        self.assertFalse(ca.valid_melon_id("911"))
        self.assertTrue(ca.valid_melon_id("2140277"))

    def test_search_js_uses_goartistdetail_pattern(self):
        js = ca._search_js(["12BH"])
        self.assertIn("goArtistDetail\\(", js)                          # 첫 숫자가 아니라 goArtistDetail( 뒤 숫자

    def test_match_candidate_ignores_short_ids(self):
        self.assertIsNone(ca.match_candidate("12BH", [["12", "12BH", ""]]))
        self.assertEqual(ca.match_candidate("12BH", [["12", "12BH", ""], ["3201955", "12BH", ""]])["id"], "3201955")


class ProfileFallbackTest(unittest.TestCase):
    """2026-11-28: 멜론 아티스트 상세(detail.htm)가 '페이지를 찾을 수 없습니다'로 바뀜 → 정보 상자가 비면 아티스트 채널(timeline.htm)로
    다시 읽는다 (이름·팬 수·활동유형·데뷔는 나오고, 소속사·장르·국적은 채널에 없어 빈칸)."""

    def test_profile_js_falls_back_to_timeline_when_info_is_empty(self):
        js = ca._js(["3810290"])
        self.assertIn(ca.ARTIST_FALLBACK_URL, js)
        self.assertIn("if (!p.info)", js)
        self.assertIn("timeline.htm", ca.ARTIST_FALLBACK_URL)

    def test_timeline_page_parses_to_a_row(self):
        page = {"info": """<div class="wrap_atist_info"><p class="title_atist"><strong class="none">아티스트명</strong>오예본</p>
<dl class="atist_info clfix"><dt>활동유형</dt><dd>솔로</dd></dl></div>""", "fan": "47",
                "dl": ["활동유형 솔로 수상이력 2024 유재하 음악경연대회|동상 더보기"], "albums": "앨범(2)",
                "album_dates": ["2025.03.21", "2024.06.12"]}
        row = ca.to_row("3810290", ca.parse_melon_artist(page), AT)
        self.assertEqual((row["artist_text"], row["first_release_date"], row["fan_count"]), ("오예본", "2024-06-12", "47"))


class OwnReleaseTest(unittest.TestCase):
    """앨범 목록의 가장 오래된 날짜가 남의 음반(참여·피처링·소속 밴드 음반)이면 첫 발매일이 실제보다 훨씬 이르게 잡힌다
    (예: 인디 성현 — 본인 EP 2025-10-22, 소속 밴드 검은잎들 음반 2016~). 앨범의 아티스트 링크에 그 팀 번호가 있는 음반만
    '본인 음반'으로 보고 first_release_own 에 따로 저장한다."""

    def test_own_first_release_ignores_other_artists_albums(self):
        page = {**NEWBIE, "album_dates": ["2026.09.08", "2025.10.22", "2016.11.16"],
                "own_dates": ["2026.09.08", "2025.10.22"]}
        prof = ca.parse_melon_artist(page)
        self.assertEqual(prof["first_release_date"], "2016-11-16")     # 예전 칸은 그대로 (전체 앨범 기준)
        self.assertEqual(prof["first_release_own"], "2025-10-22")

    def test_old_pages_without_own_dates_leave_own_blank(self):
        self.assertEqual(ca.parse_melon_artist(PAGE)["first_release_own"], "")

    def test_album_js_collects_own_dates_by_artist_id(self):
        js = ca._js(["4633954"])
        self.assertIn("own_dates", js)
        self.assertIn("goArtistDetail", js)

    def test_row_with_own_release_validates(self):
        page = {**PAGE, "own_dates": ["2007.03.15"]}
        row = ca.to_row("100", ca.parse_melon_artist(page), AT)
        self.assertEqual(row["first_release_own"], "2007-03-15")
        with tempfile.TemporaryDirectory() as d:
            path = ca.write_csv([row], Path(d), "2026-11-28")
            self.assertEqual([i for i in validate_csv.validate_file(path) if i.level == "error"], [])


class IdsFileTest(unittest.TestCase):
    """--ids-file: 번호 목록의 프로필을 다시 받기 (본인 음반 첫 발매일 의심 사례 재수집 — data/raw/review/own_release_refetch_ids.txt)."""

    def test_ids_file_refetches_listed_ids(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "ids.txt"
            f.write_text("4633954\n\n 1234567 \nabc\n", encoding="utf-8")
            with mock.patch.object(ca, "refresh_profiles", return_value=2) as rp:
                self.assertEqual(ca.main(["--ids-file", str(f)]), 0)
            rp.assert_called_once_with(["4633954", "1234567"])   # 숫자 번호만, 순서 유지


class ResilienceTest(unittest.TestCase):
    def test_failed_batch_is_skipped_and_reported(self):
        from unittest import mock
        calls = []
        def fake(js):
            calls.append(js)
            if len(calls) == 2:
                raise RuntimeError("aside 출력 해석 실패")
            return {"팀1": [["1", "팀1", ""]]} if len(calls) == 1 else {"팀3": [["3", "팀3", ""]]}
        names = [f"팀{i}" for i in range(1, 4)]
        with mock.patch.object(ca, "BATCH", 1), mock.patch.object(ca, "_run_batch", side_effect=fake):
            found, failed = ca.search_artists(names)
        self.assertEqual(sorted(found), ["팀1", "팀3"])
        self.assertEqual(failed, ["팀2"])


class KnownIdSeedTest(unittest.TestCase):
    """대책 1: 이미 가진 멜론 번호(트랙제로 '연관 아티스트' 번호·우리 링크)를 검색 없이 매칭에 넣기 — 이름 키가 같을 때만."""
    KNOWN = {"칩포스트갱": {"id": "4627173", "name": "칩 포스트 갱", "source": "trackzero"},
             "이날치": {"id": "2760294", "name": "이날치", "source": "trackzero"}}

    def test_fills_missing_or_not_found_names_with_high_confidence(self):
        matches = {"칩포스트갱": None}
        out, seeded = ca.seed_known_ids(matches, ["칩포스트갱", "이날치", "모르는팀"], self.KNOWN)
        self.assertEqual(out["칩포스트갱"], {"id": "4627173", "name": "칩 포스트 갱", "desc": "trackzero 번호",
                                         "namesakes": 1, "confidence": "high", "source": "trackzero"})
        self.assertEqual(out["이날치"]["id"], "2760294")
        self.assertNotIn("모르는팀", out)
        self.assertEqual(sorted(seeded), ["이날치", "칩포스트갱"])
        self.assertIsNone(matches["칩포스트갱"])                     # 입력은 바꾸지 않음

    def test_existing_found_match_is_kept(self):
        out, seeded = ca.seed_known_ids({"이날치": {"id": "999999", "name": "이날치"}}, ["이날치"], self.KNOWN)
        self.assertEqual(out["이날치"]["id"], "999999")
        self.assertEqual(seeded, [])

    def test_null_keys_already_in_matches_are_seeded_even_if_not_listed(self):
        out, _ = ca.seed_known_ids({"칩포스트갱": None}, [], self.KNOWN)
        self.assertEqual(out["칩포스트갱"]["source"], "trackzero")

    def test_known_index_by_name_key_drops_ambiguous_keys_and_blocked_ids(self):
        tz = {"melon_ids": {"칩 포스트 갱": "4627173", "동명": "1111111", "동 명": "2222222", "성현": "4491308"}}
        links = [{"team_key": "하즈", "platform": "melon", "url": "https://www.melon.com/artist/detail.htm?artistId=3333333"}]
        teams = [{"team_key": "하즈", "display_name": "하즈"}]
        known = ca.known_melon_ids(tz, links, teams, blocked={"4491308"})
        self.assertEqual(known["칩포스트갱"]["id"], "4627173")
        self.assertNotIn("동명", known)                               # 같은 키에 번호가 둘 → 동명 위험, 안 씀
        self.assertNotIn("성현", known)                               # 다른 아티스트로 확인된 번호(platform_ids not)
        self.assertEqual(known["하즈"], {"id": "3333333", "name": "하즈", "source": "links"})


class MissKindTest(unittest.TestCase):
    """대책 2: '못 찾음'을 결과 0건 / 이름 불일치(후보 저장)로 나누고, 불일치는 느슨한 키로 한 번 더 맞춰 본다."""

    def test_classify(self):
        self.assertEqual(ca.miss_kind([]), "empty")
        self.assertEqual(ca.miss_kind([["3000001", "다른팀", ""]]), "mismatch")

    def test_loose_match_uses_english_alias_and_slash_parts(self):
        cands = [["3000001", "CHIP POST GANG", ""], ["3000002", "남", ""]]
        self.assertIsNone(ca.match_candidate("칩포스트갱", cands))
        got = ca.loose_match("칩포스트갱", cands, aliases=["Chip Post Gang"])
        self.assertEqual((got["id"], got["loose"]), ("3000001", True))
        self.assertEqual(ca.loose_match("하즈", [["3000003", "HASE / 하즈", ""]])["id"], "3000003")
        self.assertIsNone(ca.loose_match("하즈", [["3000004", "하즈베리", ""]]))   # 앞부분만 같은 이름은 아님


class RetryTest(unittest.TestCase):
    """멜론 검색 시도 날짜 기록과 '못 찾음' 이름의 30일 뒤 재검색 (aside 없이 가짜 검색)."""

    def run_collect(self, names, matches, attempts, today, results=None, failed=()):
        import json
        from unittest import mock
        self.searched = []

        def fake_search(qs):
            self.searched.extend(qs)
            return ({q: (results or {}).get(q, []) for q in qs if q not in failed}, [q for q in qs if q in failed])
        with tempfile.TemporaryDirectory() as d:
            m, a, st = Path(d) / "m.json", Path(d) / "a.json", Path(d) / "seen.json"
            m.write_text(json.dumps(matches, ensure_ascii=False), encoding="utf-8")
            if attempts is not None:
                a.write_text(json.dumps(attempts, ensure_ascii=False), encoding="utf-8")
            with mock.patch.object(ca, "MATCH_STATE", m), mock.patch.object(ca, "ATTEMPTS_STATE", a), \
                    mock.patch.object(ca, "STATE", st), mock.patch.object(ca, "search_artists", side_effect=fake_search), \
                    mock.patch.object(ca, "fetch_profiles", return_value={}):
                ca.collect_from_outcomes(10, names, today=today)
            return json.loads(m.read_text(encoding="utf-8")), json.loads(a.read_text(encoding="utf-8"))

    def test_new_names_are_searched_and_attempt_dates_recorded(self):
        matches, attempts = self.run_collect(["새팀"], {}, None, "2026-11-28", results={"새팀": [["3000007", "새팀", ""]]})
        self.assertEqual(self.searched, ["새팀"])
        self.assertEqual(matches["새팀"]["id"], "3000007")
        self.assertEqual(attempts, {"새팀": "2026-11-28"})

    def test_existing_null_without_date_is_only_dated_on_first_run(self):
        # 기록 없는 '못 찾음'은 오늘 날짜만 남기고 검색하지 않음 → 30일 뒤부터 나눠서 재시도
        matches, attempts = self.run_collect(["옛팀"], {"옛팀": None}, None, "2026-11-28")
        self.assertEqual(self.searched, [])
        self.assertEqual(attempts["옛팀"], "2026-11-28")
        self.assertIsNone(matches["옛팀"])

    def test_null_retried_after_retry_days_and_found(self):
        matches, attempts = self.run_collect(["옛팀"], {"옛팀": None}, {"옛팀": "2026-10-20"}, "2026-11-28",
                                             results={"옛팀": [["3000009", "옛팀", ""]]})
        self.assertEqual(self.searched, ["옛팀"])
        self.assertEqual(matches["옛팀"]["id"], "3000009")
        self.assertEqual(attempts["옛팀"], "2026-11-28")

    def test_null_not_retried_within_retry_days_and_found_never_retried(self):
        self.run_collect(["옛팀", "찾은팀"], {"옛팀": None, "찾은팀": {"id": "3000005", "name": "찾은팀"}},
                         {"옛팀": "2026-11-10", "찾은팀": "2020-01-01"}, "2026-11-28")
        self.assertEqual(self.searched, [])

    def test_failed_search_is_not_an_attempt(self):
        # aside 가 바빠 검색 자체가 실패하면 시도로 치지 않음 → 다음 실행에 바로 다시
        matches, attempts = self.run_collect(["새팀"], {}, None, "2026-11-28", failed=("새팀",))
        self.assertNotIn("새팀", matches)
        self.assertNotIn("새팀", attempts)

    def test_misses_are_recorded_with_kind_and_candidates(self):
        import json
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            miss = Path(d) / "miss.json"
            with mock.patch.object(ca, "MISSES_STATE", miss), mock.patch.object(ca, "_known_melon_ids", return_value={}):
                self.run_collect(["빈팀", "다른팀"], {}, None, "2026-11-28",
                                 results={"다른팀": [["3000011", "다른 팀 아님", "설명"]]})
            got = json.loads(miss.read_text(encoding="utf-8"))
        self.assertEqual(got["빈팀"], {"kind": "empty", "date": "2026-11-28", "candidates": []})
        self.assertEqual(got["다른팀"]["kind"], "mismatch")
        self.assertEqual(got["다른팀"]["candidates"], [["3000011", "다른 팀 아님", "설명"]])

    def test_known_ids_are_seeded_before_search(self):
        from unittest import mock
        known = {"칩포스트갱": {"id": "4627173", "name": "칩 포스트 갱", "source": "trackzero"}}
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(ca, "MISSES_STATE", Path(d) / "miss.json"), \
                    mock.patch.object(ca, "_known_melon_ids", return_value=known):
                matches, _ = self.run_collect(["칩포스트갱"], {"칩포스트갱": None}, {"칩포스트갱": "2026-11-27"}, "2026-11-28")
        self.assertEqual(self.searched, [])
        self.assertEqual((matches["칩포스트갱"]["id"], matches["칩포스트갱"]["source"]), ("4627173", "trackzero"))

    def test_alias_search_also_records_attempt(self):
        matches, attempts = self.run_collect(["피치트럭(Peach Truck)"], {}, None, "2026-11-28",
                                             results={"Peach Truck": [["3000003", "Peach Truck", ""]]})
        self.assertEqual(self.searched, ["피치트럭", "Peach Truck"])
        self.assertEqual(matches["피치트럭(Peach Truck)"]["id"], "3000003")
        self.assertEqual(attempts["피치트럭(Peach Truck)"], "2026-11-28")

    def test_profiles_of_listed_names_are_fetched_first(self):
        # 받을 프로필이 상한(MAX_PROFILES_PER_RUN)보다 많으면 명단 순서(0순위 = 후보 점검 b 팀)대로 먼저 받음
        import json
        from unittest import mock
        matches = {f"옛{i}": {"id": str(3000000 + i), "name": f"옛{i}"} for i in range(5)}
        matches["딕펑스"] = {"id": "454254", "name": "딕펑스"}
        got = []
        with tempfile.TemporaryDirectory() as d:
            m, a, st = Path(d) / "m.json", Path(d) / "a.json", Path(d) / "seen.json"
            m.write_text(json.dumps(matches, ensure_ascii=False), encoding="utf-8")
            with mock.patch.object(ca, "MATCH_STATE", m), mock.patch.object(ca, "ATTEMPTS_STATE", a), \
                    mock.patch.object(ca, "STATE", st), mock.patch.object(ca, "MAX_PROFILES_PER_RUN", 2), \
                    mock.patch.object(ca, "search_artists", return_value=({}, [])), \
                    mock.patch.object(ca, "fetch_profiles", side_effect=lambda ids: got.extend(ids) or {}):
                ca.collect_from_outcomes(10, ["딕펑스", "옛3"], today="2026-11-28")
        self.assertEqual(got, ["454254", "3000003"])

    def test_profiles_are_saved_chunk_by_chunk(self):
        # 오래 걸리는 수집이 중간에 끊겨도 받은 만큼은 남게, 묶음마다 저장·상태 갱신
        import json
        from unittest import mock
        matches = {f"팀{i}": {"id": str(3000000 + i), "name": f"팀{i}"} for i in range(5)}
        calls = []

        def fake_fetch(ids):
            calls.append(list(ids))
            if len(calls) == 2:
                raise KeyboardInterrupt   # 두 번째 묶음에서 끊김
            return {i: {} for i in ids}

        with tempfile.TemporaryDirectory() as d:
            m, a, st = Path(d) / "m.json", Path(d) / "a.json", Path(d) / "seen.json"
            m.write_text(json.dumps(matches, ensure_ascii=False), encoding="utf-8")
            with mock.patch.object(ca, "MATCH_STATE", m), mock.patch.object(ca, "ATTEMPTS_STATE", a), \
                    mock.patch.object(ca, "STATE", st), mock.patch.object(ca, "SAVE_EVERY", 2), \
                    mock.patch.object(ca, "RAW_DIR", Path(d)), \
                    mock.patch.object(ca, "search_artists", return_value=({}, [])), \
                    mock.patch.object(ca, "parse_melon_artist", return_value={"name": "x"}), \
                    mock.patch.object(ca, "to_row", side_effect=lambda i, prof, now: {"artist_source_id": i}), \
                    mock.patch.object(ca, "write_csv", return_value=Path(d) / "out.csv"), \
                    mock.patch.object(ca, "fetch_profiles", side_effect=fake_fetch):
                with self.assertRaises(KeyboardInterrupt):
                    ca.collect_from_outcomes(10, list(matches), today="2026-11-28")
            self.assertEqual(sorted(json.loads(st.read_text(encoding="utf-8"))), ["3000000", "3000001"])

    def test_shares_constants_with_melon_names(self):
        import melon_names
        self.assertIs(ca.due_for_search, melon_names.due_for_search)
        self.assertEqual(ca.ATTEMPTS_STATE, melon_names.ATTEMPTS)
        self.assertEqual(ca.MATCH_STATE, melon_names.MATCHES)


if __name__ == "__main__":
    unittest.main()


class RefreshTest(unittest.TestCase):
    """--refresh: 관찰 목록의 멜론 프로필을 마지막으로 받은 지 7일 지난 것만 다시 받는다 (팬 수 날짜별 기록용)."""

    def test_watch_ids_order_and_mapping(self):
        team_ids = {"a": ["1"], "b": ["2", "3"], "w": ["9"]}
        ids = ca.watch_ids(audit_keys=["b"], top_keys=["a", "b", "x"], winner_keys=["w", "a"], team_ids=team_ids)
        self.assertEqual(ids, ["2", "3", "1", "9"])                     # 점검 b → 상위 → 정답 순, 겹침 없음

    def test_last_fetched_takes_latest_of_files_and_state(self):
        rows = [{"artist_source_id": "1", "collected_at": "2026-11-20T10:00:00+09:00"},
                {"artist_source_id": "1", "collected_at": "2026-11-26T10:00:00+09:00"},
                {"artist_source_id": "2", "collected_at": "2026-11-10T10:00:00+09:00"}]
        last = ca.last_fetched(rows, {"2": "2026-11-25"})
        self.assertEqual(last, {"1": "2026-11-26", "2": "2026-11-25"})

    def test_due_for_refresh_only_after_days_and_only_fetched_before(self):
        last = {"1": "2026-11-20", "2": "2026-11-25"}
        due = ca.due_for_refresh(["1", "2", "3"], last, "2026-11-27", days=7)
        self.assertEqual(due, ["1"])                                     # 2는 2일 전, 3은 한 번도 안 받음(일반 수집이 맡음)

    def test_refresh_saves_state_without_touching_seen(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            seen_path, state_path = d / "seen.json", d / "refreshed.json"
            seen_path.write_text('["1"]', encoding="utf-8")
            pages = {"1": PAGE}
            n = ca.refresh_profiles(["1"], fetch=lambda ids: {i: pages[i] for i in ids}, out_dir=d,
                                    state_path=state_path, today="2026-11-27", now=AT)
            self.assertEqual(n, 1)
            self.assertEqual(seen_path.read_text(encoding="utf-8"), '["1"]')
            self.assertEqual(ca._load_json(state_path, {}), {"1": "2026-11-27"})
            self.assertEqual(len(list(d.glob("raw_artist_profile_*_melon*.csv"))), 1)

class GenreFirstSeenTest(unittest.TestCase):
    """확인된 장르 = 사후 수집 편향(docs/methods.md) 대책: 프로필에서 새 장르 태그를 처음 본 날을 상태 파일에 남긴다
    (data/raw/state/genre_first_seen.json, {멜론 번호: {artist_text, genres: {태그: 날짜}}} — scripts/genre_seen.py 가 읽음)."""

    def test_record_genre_seen_keeps_first_date(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "genre_first_seen.json"
            row = ca.to_row("1", ca.parse_melon_artist(PAGE), AT)
            self.assertEqual(ca.record_genre_seen([row], path), 3)          # 인디음악·발라드·록/메탈
            later = dict(row, collected_at="2026-11-30T10:00:00+09:00", genre="록/메탈|포크/블루스")
            self.assertEqual(ca.record_genre_seen([later], path), 1)        # 포크/블루스만 새로
            genres = ca._load_json(path, {})["1"]["genres"]
            self.assertEqual(genres["록/메탈"], "2026-11-26")
            self.assertEqual(genres["포크/블루스"], "2026-11-30")

    def test_refresh_records_genres_next_to_its_state(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            state_path = d / "refreshed.json"
            ca.refresh_profiles(["1"], fetch=lambda ids: {i: PAGE for i in ids}, out_dir=d,
                                state_path=state_path, today="2026-11-26", now=AT)
            seen = ca._load_json(d / "genre_first_seen.json", {})
            self.assertEqual(seen["1"]["genres"], {"인디음악": "2026-11-26", "발라드": "2026-11-26", "록/메탈": "2026-11-26"})

