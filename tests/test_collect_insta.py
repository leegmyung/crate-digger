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

    def test_promoter_label_event_accounts_are_lineup_too(self):
        # 기획·크루, 레이블, 행사 계정도 라인업 공지라 '공연'으로 센다 (평론 픽 아님)
        post = {"url": "https://www.instagram.com/p/V2/", "og": OG}
        for role in ("promoter_showcase", "label_showcase", "event_showcase"):
            rows, _ = ci.to_rows("somecrew", post, AT, role=role)
            self.assertEqual({(r["is_pick"], r["pick_label"]) for r in rows}, {("0", "venue_lineup")}, role)

    def test_config_roles_are_known(self):
        accounts = ci._load_json(ci.CONFIG, {})["accounts"]
        known = ("magazine", "venue_showcase", "promoter_showcase", "label_showcase", "event_showcase", "artist")
        self.assertTrue(all(a.get("role") in known for a in accounts))   # artist = 팀 본인 계정(수집 안 함)
        venues = {a["handle"] for a in accounts if a["role"] == "venue_showcase"}
        self.assertTrue({"senggistudio", "hongdaeff", "rollinghall"} <= venues)
        events = {a["handle"] for a in accounts if a["role"] == "event_showcase"}
        self.assertIn("liveclubday", events)

    def test_caption_without_mentions_goes_to_review(self):
        post = {"url": "https://www.instagram.com/p/X/", "og": 'a on November 1, 2026: "이번 달 앨범: 삼월생, 강연우"'}
        rows, unparsed = ci.to_rows("bdbd.wav", post, AT)
        self.assertEqual(rows, [])
        self.assertEqual(unparsed["url"], "https://www.instagram.com/p/X/")


class ArtistRoleTest(unittest.TestCase):
    def test_artist_accounts_not_collected(self):
        # 팀 본인 계정(role=artist)의 글을 '매체 큐레이션'으로 모으면 다른 팀에 가짜 신호가 생긴다
        accounts = [{"handle": "pushplay_mag", "role": "magazine"}, {"handle": "theseosroom", "role": "artist"},
                    {"handle": "clubbbang", "role": "venue_showcase"}]
        self.assertEqual([a["handle"] for a in ci.collectable_accounts(accounts)], ["pushplay_mag", "clubbbang"])


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


class CheckpointTest(unittest.TestCase):
    """중간 저장: 수집이 도중에 멈춰도(2026-11-26 실제 사례) 앞에서 본 계정의 상태·행은 남아야 한다."""

    def test_state_and_rows_saved_every_checkpoint_even_if_later_crash(self):
        import json as _json
        import tempfile as _tf
        accounts = [{"handle": f"acc{i}", "role": "magazine", "every_days": 1} for i in range(5)]
        row = {c: "" for c in ci.COLUMNS}
        calls = []

        def fake_collect(handle, seen, collected_at, oldest, role="magazine"):
            calls.append(handle)
            if handle == "acc3":
                raise SystemExit("aside 가 통째로 죽음")              # 계정 하나 실패가 아니라 실행 자체가 끊김
            return [dict(row, outlet=handle, artist_text="팀", url=f"https://x/{handle}", source="instagram",
                         published_at="2026-11-27", title="t", is_pick="1")], [], [f"p_{handle}"]

        with _tf.TemporaryDirectory() as d:
            d = Path(d)
            cfg, state = d / "cfg.json", d / "state.json"
            cfg.write_text(_json.dumps({"accounts": accounts}), encoding="utf-8")
            old = (ci.CONFIG, ci.STATE, ci.RAW_DIR, ci._collect_account, ci.CHECKPOINT_EVERY)
            ci.CONFIG, ci.STATE, ci.RAW_DIR, ci._collect_account, ci.CHECKPOINT_EVERY = cfg, state, d, fake_collect, 2
            try:
                with self.assertRaises(SystemExit):
                    ci.collect()
            finally:
                ci.CONFIG, ci.STATE, ci.RAW_DIR, ci._collect_account, ci.CHECKPOINT_EVERY = old
            saved = _json.loads(state.read_text(encoding="utf-8"))
            files = sorted(d.glob("raw_press_*_instagram*.csv"))
        self.assertEqual(sorted(saved["seen"]), ["acc0", "acc1", "acc2"])   # 2개마다 저장 → acc0·acc1, 그리고 acc2 까지 (멈추기 직전 저장)
        self.assertTrue(files)


class CollabDuplicateTest(unittest.TestCase):
    """두 계정이 함께 올린 공동 게시물은 같은 (게시물 주소, 팀)이 두 번 나온다 → 한 번만 쓴다 (2026-11-27 형식 검사 실패 3파일)."""

    def test_dedupe_rows_by_url_and_artist_across_run(self):
        row = {c: "" for c in ci.COLUMNS}
        a = dict(row, outlet="@acc1", url="https://www.instagram.com/p/X/", artist_text="@team")
        b = dict(row, outlet="@acc2", url="https://www.instagram.com/p/X/", artist_text="@team")
        c = dict(row, outlet="@acc2", url="https://www.instagram.com/p/X/", artist_text="@other")
        written = set()
        first = ci.dedupe_rows([a, b, c], written)
        self.assertEqual([r["outlet"] + r["artist_text"] for r in first], ["@acc1@team", "@acc2@other"])
        self.assertEqual(ci.dedupe_rows([dict(b)], written), [])          # 다음 중간 저장에서도 다시 안 씀


class BackoffTest(unittest.TestCase):
    """공연장 주기 4일, 그리고 연속 0행 계정은 주기를 늘린다 (2026-11-28 운영 개선)."""

    def test_venue_accounts_every_4_days_in_config(self):
        import json as _json
        accounts = _json.loads(ci.CONFIG.read_text(encoding="utf-8"))["accounts"]
        venues = [a for a in accounts if a.get("tier") == "venue"]
        self.assertTrue(venues)
        self.assertTrue(all(int(a.get("every_days", 1)) >= 4 for a in venues))

    def test_effective_every_grows_with_zero_streak(self):
        a = {"handle": "v", "every_days": 4}
        self.assertEqual(ci.effective_every(a, 0), 4)
        self.assertEqual(ci.effective_every(a, ci.ZERO_STREAK_STEP - 1), 4)
        self.assertEqual(ci.effective_every(a, ci.ZERO_STREAK_STEP), 8)        # 3회 연속 0행 → 2배
        self.assertEqual(ci.effective_every(a, ci.ZERO_STREAK_STEP * 2), 16)
        self.assertEqual(ci.effective_every(a, 99), ci.MAX_EVERY_DAYS)          # 상한

    def test_due_accounts_uses_zero_streak(self):
        accounts = [{"handle": "busy", "every_days": 4}, {"handle": "quiet", "every_days": 4}]
        last = {"busy": "2026-11-20", "quiet": "2026-11-20"}
        streak = {"quiet": ci.ZERO_STREAK_STEP}
        got = ci.due_accounts(accounts, last, "2026-11-25", zero_streak=streak)
        self.assertEqual([a["handle"] for a in got], ["busy"])                 # quiet 은 8일 주기라 아직

    def test_update_streak(self):
        self.assertEqual(ci.update_streak({"a": 2}, "a", 0), {"a": 3})
        self.assertEqual(ci.update_streak({"a": 2}, "a", 5), {"a": 0})
