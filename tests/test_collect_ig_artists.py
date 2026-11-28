"""인스타 아티스트 프로필 수집기 변환 로직 테스트 — aside 없이 가상 데이터로."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import collect_ig_artists as ig  # noqa: E402
import validate_csv  # noqa: E402

AT = "2026-11-26T22:00:00+09:00"
META_KO = "팔로워 1.2만명, 팔로잉 213명, 게시물 59개 - 새벽정류장 Saebyeok Bus (@saebyeok.bus)님의 Instagram 계정: '서울의 4인조 밴드\n새 싱글 out now'"
META_EN = '12.3K Followers, 210 Following, 88 Posts - See Instagram photos and videos from Sally Everywhere (@sally_ew)'
META_EN_BIO = '1,234 Followers, 10 Following, 5 Posts - Neon Club (@neonclub_seoul) on Instagram: "Live music club in Hongdae"'


class CountTest(unittest.TestCase):
    def test_korean_man_unit(self):
        self.assertEqual(ig.parse_count("1.2만"), 12000)

    def test_k_and_m_units(self):
        self.assertEqual(ig.parse_count("12.3K"), 12300)
        self.assertEqual(ig.parse_count("1.2M"), 1200000)

    def test_commas(self):
        self.assertEqual(ig.parse_count("6,007"), 6007)

    def test_garbage(self):
        self.assertIsNone(ig.parse_count("많음"))


class MetaTest(unittest.TestCase):
    def test_korean_meta(self):
        m = ig.parse_meta(META_KO, "saebyeok.bus")
        self.assertEqual(m["followers"], 12000)
        self.assertEqual(m["name"], "새벽정류장 Saebyeok Bus")
        self.assertIn("4인조 밴드", m["bio"])

    def test_korean_meta_with_k_unit(self):   # 실제 인스타: '팔로워 54K명'
        m = ig.parse_meta("팔로워 54K명, 팔로잉 3명, 게시물 155개 - 小山田壮平 (@oyamada_sohei)님의 Instagram 계정: 'x'", "oyamada_sohei")
        self.assertEqual(m["followers"], 54000)

    def test_english_meta(self):
        m = ig.parse_meta(META_EN, "sally_ew")
        self.assertEqual(m["followers"], 12300)
        self.assertEqual(m["name"], "Sally Everywhere")
        self.assertEqual(m["bio"], "")

    def test_english_meta_with_bio(self):
        m = ig.parse_meta(META_EN_BIO, "neonclub_seoul")
        self.assertEqual(m["followers"], 1234)
        self.assertEqual(m["bio"], "Live music club in Hongdae")

    def test_empty_name_falls_back_to_handle(self):
        m = ig.parse_meta("팔로워 10명, 팔로잉 1명, 게시물 2개 - (@abc)님의 Instagram 계정", "abc")
        self.assertEqual(m["name"], "abc")

    def test_unparseable_meta(self):
        self.assertIsNone(ig.parse_meta("", "abc"))


class LinkTest(unittest.TestCase):
    def test_unwraps_instagram_redirect(self):
        url = "https://l.instagram.com/?u=https%3A%2F%2Flinktr.ee%2Fsaebyeok&e=AUA"
        self.assertEqual(ig.unwrap(url), "https://linktr.ee/saebyeok")

    def test_classifies_music_links(self):
        links = ig.music_links([
            "https://l.instagram.com/?u=https%3A%2F%2Fopen.spotify.com%2Fartist%2F123&e=x",
            "https://www.melon.com/artist/timeline.htm?artistId=999",
            "https://www.instagram.com/stories/highlights/1/",
            "youtube.com/@saebyeokbus",
        ])
        kinds = {l["kind"] for l in links}
        self.assertEqual(kinds, {"spotify", "melon", "youtube"})

    def test_youtube_channel_only(self):
        self.assertEqual(ig.youtube_channel([{"kind": "youtube", "url": "https://youtu.be/abc"}]), "")
        self.assertEqual(ig.youtube_channel([{"kind": "youtube", "url": "https://www.youtube.com/@band"}]),
                         "https://www.youtube.com/@band")


class NonArtistTest(unittest.TestCase):
    def test_venue_bio(self):
        self.assertTrue(ig.looks_non_artist("Neon Club", "Live music club in Hongdae"))
        self.assertTrue(ig.looks_non_artist("푸시 플레이 매거진", ""))
        self.assertTrue(ig.looks_non_artist("Some Records", "indie label"))

    def test_artist_bio(self):
        self.assertFalse(ig.looks_non_artist("새벽정류장", "서울의 4인조 밴드 새 싱글 out now"))
        self.assertFalse(ig.looks_non_artist("Olive", "singer"))   # 'live'가 다른 낱말 안에 있으면 무시


class NonArtistFalsePositiveTest(unittest.TestCase):
    """2026-11-28 연결 점검(docs/link_audit_2026-11-28.md)에서 찾은 오판: 밴드 계정이 '레이블'·공연 일정 속 클럽 이름 때문에 아티스트 아님으로."""

    def test_band_with_label_mention_is_artist(self):
        bio = "South Korea\nGwangju City Punk Rock Band\n@member1 \n@member2\nLabel - @victimrecords"
        self.assertFalse(ig.looks_non_artist("TWOFIVE 투파이브", bio))

    def test_gig_schedule_lines_do_not_make_a_venue(self):
        bio = "Surviving isn't enough. Want more.\n12/04 금 Club FF\n12/12 토 프리버드\n1/16 토 에머겐자"
        self.assertFalse(ig.looks_non_artist("Julywantsmore", bio))

    def test_clear_venue_or_label_bio_beats_artist_words(self):
        self.assertTrue(ig.looks_non_artist("고요의 방", "싱어송라이터를 위한 공연장이자 카페 그리고 펍"))
        self.assertTrue(ig.looks_non_artist("雨模様Amemoyo", "Indie Music Label from Asia"))
        self.assertFalse(ig.looks_non_artist("雪国", "We are Yukiguni,indie rock band based in Tokyo."))
        self.assertFalse(ig.looks_non_artist("우륵과 풍각쟁이들", "국악 기반 아방가르드 밴드입니다."))

    def test_venue_words_in_name_still_non_artist(self):
        self.assertTrue(ig.looks_non_artist("Club FF", "홍대 라이브 클럽"))
        self.assertTrue(ig.looks_non_artist("Pushplay", "Seoul live club & bar"))   # 소개만 있어도 아티스트 낱말이 없으면


class InputTest(unittest.TestCase):
    def test_targets_skip_seen_outlets_and_dupes(self):
        press = [{"artist_handle": "@a.band"}, {"artist_handle": "@pushplay_mag"}, {"artist_handle": "@a.band"},
                 {"artist_handle": ""}, {"artist_handle": "@done_one"}]
        got = ig.targets(press, {"b_band": 2, "a.band": 1}, seen={"done_one"}, outlets={"pushplay_mag"})
        self.assertEqual(got, ["a.band", "b_band"])


class RevisitTest(unittest.TestCase):
    """--handles-file: 관찰 목록 계정을 이미 봤어도 7일마다 다시 열어 팔로워 수를 날짜별로 남긴다 (docs/followers_plan.md)."""

    def test_last_fetched_from_rows(self):
        rows = [{"artist_source_id": "aa", "collected_at": "2026-11-20T10:00:00+09:00"},
                {"artist_source_id": "aa", "collected_at": "2026-11-26T10:00:00+09:00"},
                {"artist_source_id": "bb", "collected_at": "2026-11-27T10:00:00+09:00"}]
        self.assertEqual(ig.last_fetched(rows), {"aa": "2026-11-26", "bb": "2026-11-27"})

    def test_revisit_due_after_7_days_and_skips_outlets(self):
        last = {"aa": "2026-11-20", "bb": "2026-11-27"}
        got = ig.revisit_targets(["aa", "bb", "cc", "mag", "aa"], last, "2026-11-28", outlets={"mag"})
        self.assertEqual(got, ["cc", "aa"])                 # 처음 보는 계정 먼저, 그다음 오래된 순 · bb 는 1일 전이라 아직


class EmailDomainTest(unittest.TestCase):
    def test_email_domain_is_not_a_handle(self):   # 'abc@gmail.com' 캡션에서 잘못 잡힌 태그
        self.assertEqual(ig.targets([{"artist_handle": "@gmail.com"}, {"artist_handle": "@naver.com"}], {}, set(), set()), [])


class RowTest(unittest.TestCase):
    def test_row_and_csv_valid(self):
        page = {"meta": META_KO, "header": "새벽정류장\nyoutube.com/@saebyeokbus",
                "links": ["https://l.instagram.com/?u=https%3A%2F%2Fwww.melon.com%2Fartist%2Fdetail.htm%3FartistId%3D1&e=x"]}
        result = ig.interpret("saebyeok.bus", page)
        self.assertEqual(result["status"], "artist")
        row = ig.to_row("saebyeok.bus", result, AT)
        self.assertEqual(row["fan_count"], "12000")
        self.assertEqual(row["url"], "https://www.instagram.com/saebyeok.bus/")
        self.assertEqual(row["artist_key"], "새벽정류장saebyeokbus")
        self.assertEqual(row["youtube_url"], "https://youtube.com/@saebyeokbus")
        with tempfile.TemporaryDirectory() as d:
            path = ig.write_csv([row], Path(d), "2026-11-26")
            self.assertEqual(path.name, "raw_artist_profile_2026-11-26_instagram.csv")
            errs = [i for i in validate_csv.validate_file(path) if i.level == "error"]
            self.assertEqual(errs, [])

    def test_rewrites_same_file_within_run(self):   # 묶음마다 저장해도 파일이 늘지 않음
        row = ig.to_row("abc", {"name": "abc", "followers": 1, "links": []}, AT)
        with tempfile.TemporaryDirectory() as d:
            first = ig.write_csv([row], Path(d), "2026-11-26")
            again = ig.write_csv([row, dict(row, artist_source_id="def")], Path(d), "2026-11-26", first)
            self.assertEqual(first, again)
            self.assertEqual(len(list(Path(d).iterdir())), 1)
            self.assertEqual(len(again.read_text(encoding="utf-8").splitlines()), 3)

    def test_login_wall_and_gone(self):
        self.assertEqual(ig.interpret("x", {"meta": "", "login_wall": True})["status"], "login_wall")
        self.assertEqual(ig.interpret("x", {"meta": "", "gone": True})["status"], "gone")
        self.assertEqual(ig.interpret("x", {"meta": META_EN_BIO})["status"], "non_artist")


class WallStreakTest(unittest.TestCase):
    def test_streak_counts_consecutive_walls(self):
        self.assertEqual(ig.wall_streak(["artist", "login_wall", "login_wall"], 0), 2)
        self.assertEqual(ig.wall_streak(["login_wall", "artist"], 2), 0)
        self.assertEqual(ig.wall_streak(["login_wall"], 2), 3)


if __name__ == "__main__":
    unittest.main()
