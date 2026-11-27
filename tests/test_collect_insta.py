"""인스타 음악 매거진 수집기 변환 로직 테스트 — aside 없이 가상 데이터로."""
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import collect_insta as ci  # noqa: E402
import validate_csv  # noqa: E402

AT = "2026-11-26T21:00:00+09:00"
OG = ('1,234 likes, 12 comments - pushplay_mag on November 25, 2026: "오늘 소개할 아티스트는 정용찬(@jeong_yong_chan)입니다. '
      '첫 더블 싱글 「Project 1」 🎧 함께한 밴드 새벽정류장 (@saebyeok.bus) 도 확인하세요 #인디 #신곡"')


class ParseTest(unittest.TestCase):
    def test_parse_og_description(self):
        p = ci.parse_og(OG)
        self.assertEqual(p["date"], "2026-11-25")
        self.assertTrue(p["caption"].startswith("오늘 소개할 아티스트는"))

    def test_parse_og_without_likes(self):
        p = ci.parse_og('kindiemagazine on January 5, 2026: "Rising Artist 샐리에브리웨어 @sally_ew"')
        self.assertEqual(p["date"], "2026-01-05")

    def test_parse_og_dash_format(self):  # 2026-11 실제 인스타 형식
        p = ci.parse_og('19 likes, 0 comments - pushplay_mag - November 25, 2026: "Sarah Julia - Bigger Picture @sarahjulia"')
        self.assertEqual(p["date"], "2026-11-25")
        self.assertEqual(p["caption"], "Sarah Julia - Bigger Picture @sarahjulia")

    def test_parse_og_unknown_format(self):
        self.assertEqual(ci.parse_og("그냥 문장"), {"date": "", "caption": "그냥 문장"})

    def test_mentions_with_names(self):
        m = ci.mentions(ci.parse_og(OG)["caption"], own_handle="pushplay_mag")
        self.assertEqual(m, [("정용찬", "@jeong_yong_chan"), ("새벽정류장", "@saebyeok.bus")])

    def test_mention_without_name_uses_handle(self):
        self.assertEqual(ci.mentions("이번 주 @lumen.garden 소개", own_handle="x"), [("lumen.garden", "@lumen.garden")])

    def test_own_handle_and_trailing_dot_ignored(self):
        self.assertEqual(ci.mentions("by @pushplay_mag. 그리고 A(@a_b.)", own_handle="pushplay_mag"), [("A", "@a_b")])

    def test_price_or_shared_name_falls_back_to_handle(self):
        # '33,000원 (@a) (@b)' 처럼 가격이 이름 자리에 오던 문제 (2026-11-26 실제 캡션)
        m = ci.mentions("티켓 33,000원 (@unplugged_stage) 출연 진(@jin_a) 진(@jin_b)", own_handle="x")
        self.assertEqual(m, [("unplugged_stage", "@unplugged_stage"), ("jin_a", "@jin_a"), ("jin_b", "@jin_b")])

    def test_sponsored(self):
        self.assertTrue(ci.is_sponsored("좋은 곡 #제작지원"))
        self.assertTrue(ci.is_sponsored("유료 광고 포함"))
        self.assertFalse(ci.is_sponsored("광고 없이 소개합니다 #인디"))  # '광고 없이'는 협찬 아님


class RowsTest(unittest.TestCase):
    def test_rows_and_validator(self):
        post = {"url": "https://www.instagram.com/p/ABC123/", "og": OG}
        rows, unparsed = ci.to_rows("pushplay_mag", post, AT)
        self.assertEqual(unparsed, None)
        self.assertEqual([r["artist_handle"] for r in rows], ["@jeong_yong_chan", "@saebyeok.bus"])
        r = rows[0]
        self.assertEqual((r["source"], r["outlet"], r["published_at"], r["is_pick"], r["is_sponsored"]),
                         ("instagram", "@pushplay_mag", "2026-11-25", "1", "0"))
        with tempfile.TemporaryDirectory() as d:
            path = ci.write_csv(rows, Path(d), "2026-11-26")
            errs = [i for i in validate_csv.validate_file(path) if i.level == "error"]
        self.assertEqual(path.name, "raw_press_2026-11-26_instagram.csv")
        self.assertEqual(errs, [])

    def test_venue_account_marked_as_lineup_not_pick(self):
        post = {"url": "https://www.instagram.com/p/V1/", "og": OG}
        rows, _ = ci.to_rows("rollinghall", post, AT, role="venue_showcase")
        self.assertEqual({(r["is_pick"], r["pick_label"]) for r in rows}, {("0", "venue_lineup")})
        rows, _ = ci.to_rows("pushplay_mag", post, AT)
        self.assertEqual({(r["is_pick"], r["pick_label"]) for r in rows}, {("1", "")})

    def test_config_roles_are_known(self):
        accounts = ci._load_json(ci.CONFIG, {})["accounts"]
        self.assertTrue(all(a.get("role") in ("magazine", "venue_showcase") for a in accounts))
        venues = {a["handle"] for a in accounts if a["role"] == "venue_showcase"}
        self.assertTrue({"senggistudio", "hongdaeff", "rollinghall", "liveclubday"} <= venues)

    def test_caption_without_mentions_goes_to_review(self):
        post = {"url": "https://www.instagram.com/p/X/", "og": 'a on November 1, 2026: "이번 달 앨범: 삼월생, 강연우"'}
        rows, unparsed = ci.to_rows("bdbd.wav", post, AT)
        self.assertEqual(rows, [])
        self.assertEqual(unparsed["url"], "https://www.instagram.com/p/X/")


class DueTest(unittest.TestCase):
    def test_due_accounts(self):
        accounts = [{"handle": "a", "every_days": 1}, {"handle": "b", "every_days": 3}]
        last = {"b": "2026-11-25"}
        self.assertEqual([a["handle"] for a in ci.due_accounts(accounts, last, "2026-11-26")], ["a"])
        self.assertEqual([a["handle"] for a in ci.due_accounts(accounts, last, "2026-11-28")], ["a", "b"])

    def test_limit_takes_most_overdue_first(self):
        accounts = [{"handle": h, "every_days": 1} for h in "abc"]
        last = {"a": "2026-11-25", "b": "2026-11-20", "c": "2026-11-24"}
        got = ci.due_accounts(accounts, last, "2026-11-26", limit=2)
        self.assertEqual([a["handle"] for a in got], ["b", "c"])

    def test_stagger_spreads_new_accounts_over_their_cycle(self):
        accounts = [{"handle": f"s{i}", "every_days": 7} for i in range(14)] + [{"handle": "old", "every_days": 7}]
        last = ci.stagger(accounts, {"old": "2026-11-26"}, "2026-11-27")
        self.assertEqual(last["old"], "2026-11-26")                      # 이미 본 계정은 그대로
        first_due = {}                                                   # 계정마다 처음 볼 때가 되는 날
        days = [(date(2026, 11, 27) + timedelta(days=i)).isoformat() for i in range(7)]
        for d in days:
            for a in ci.due_accounts(accounts, last, d):
                first_due.setdefault(a["handle"], d)
        old_due = first_due.pop("old")
        per_day = [list(first_due.values()).count(d) for d in days]
        self.assertEqual(per_day, [2] * 7)                               # 새 계정 14개를 7일에 나눠 → 하루 2개
        self.assertEqual(old_due, "2026-12-03")                          # 기존 계정은 원래 주기대로


if __name__ == "__main__":
    unittest.main()
