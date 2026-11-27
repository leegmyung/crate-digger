"""아티스트 메타데이터(멜론 아티스트 페이지) 수집기 테스트 — aside 없이 실제 페이지 구조를 줄인 가짜 데이터로."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import collect_artists as ca  # noqa: E402
import validate_csv  # noqa: E402

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
                             "first_release_date": "2007-03-15", "youtube_url": "https://www.youtube.com/@epitone"})

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
             ["111", "산보 (Sanbo)", "대한민국/남성/솔로 음악장르 트로트"],
             ["222", "산보라", "대한민국/여성/솔로"]]

    def test_name_keys_include_alias(self):
        self.assertEqual(ca.name_keys("BØJEONG(비공정)"), {"bjeong", "비공정"} | {ca.artist_key("BØJEONG")})
        self.assertEqual(ca.name_keys("피치트럭 하이재커스(Peach Truck Hijackers)"), {"피치트럭하이재커스", "peachtruckhijackers"})

    def test_exact_key_match_and_namesake_flag(self):
        m = ca.match_candidate("산보", self.CANDS)
        self.assertEqual((m["id"], m["namesakes"]), ("3940959", 2))   # '산보 (Sanbo)'도 키가 같음 → 동명 2팀

    def test_alias_match(self):
        m = ca.match_candidate("피치트럭 하이재커스(Peach Truck Hijackers)", [["9", "Peach Truck Hijackers", ""]])
        self.assertEqual(m["id"], "9")

    def test_no_match(self):
        self.assertIsNone(ca.match_candidate("없는팀", self.CANDS))

    def test_placeholder_ids_are_never_matched(self):   # 멜론 '여러 아티스트' 같은 공용 번호(0, 1)
        self.assertIsNone(ca.match_candidate("Various Artists", [["1", "Various Artists", ""], ["0", "Various Artists", ""]]))
        self.assertEqual(ca.match_candidate("산보", [["0", "산보", ""]] + self.CANDS)["id"], "3940959")


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
        matches, attempts = self.run_collect(["새팀"], {}, None, "2026-11-28", results={"새팀": [["7", "새팀", ""]]})
        self.assertEqual(self.searched, ["새팀"])
        self.assertEqual(matches["새팀"]["id"], "7")
        self.assertEqual(attempts, {"새팀": "2026-11-28"})

    def test_existing_null_without_date_is_only_dated_on_first_run(self):
        # 기록 없는 '못 찾음'은 오늘 날짜만 남기고 검색하지 않음 → 30일 뒤부터 나눠서 재시도
        matches, attempts = self.run_collect(["옛팀"], {"옛팀": None}, None, "2026-11-28")
        self.assertEqual(self.searched, [])
        self.assertEqual(attempts["옛팀"], "2026-11-28")
        self.assertIsNone(matches["옛팀"])

    def test_null_retried_after_retry_days_and_found(self):
        matches, attempts = self.run_collect(["옛팀"], {"옛팀": None}, {"옛팀": "2026-10-20"}, "2026-11-28",
                                             results={"옛팀": [["9", "옛팀", ""]]})
        self.assertEqual(self.searched, ["옛팀"])
        self.assertEqual(matches["옛팀"]["id"], "9")
        self.assertEqual(attempts["옛팀"], "2026-11-28")

    def test_null_not_retried_within_retry_days_and_found_never_retried(self):
        self.run_collect(["옛팀", "찾은팀"], {"옛팀": None, "찾은팀": {"id": "5", "name": "찾은팀"}},
                         {"옛팀": "2026-11-10", "찾은팀": "2020-01-01"}, "2026-11-28")
        self.assertEqual(self.searched, [])

    def test_failed_search_is_not_an_attempt(self):
        # aside 가 바빠 검색 자체가 실패하면 시도로 치지 않음 → 다음 실행에 바로 다시
        matches, attempts = self.run_collect(["새팀"], {}, None, "2026-11-28", failed=("새팀",))
        self.assertNotIn("새팀", matches)
        self.assertNotIn("새팀", attempts)

    def test_alias_search_also_records_attempt(self):
        matches, attempts = self.run_collect(["피치트럭(Peach Truck)"], {}, None, "2026-11-28",
                                             results={"Peach Truck": [["3", "Peach Truck", ""]]})
        self.assertEqual(self.searched, ["피치트럭", "Peach Truck"])
        self.assertEqual(matches["피치트럭(Peach Truck)"]["id"], "3")
        self.assertEqual(attempts["피치트럭(Peach Truck)"], "2026-11-28")

    def test_shares_constants_with_melon_names(self):
        import melon_names
        self.assertIs(ca.due_for_search, melon_names.due_for_search)
        self.assertEqual(ca.ATTEMPTS_STATE, melon_names.ATTEMPTS)
        self.assertEqual(ca.MATCH_STATE, melon_names.MATCHES)


if __name__ == "__main__":
    unittest.main()
