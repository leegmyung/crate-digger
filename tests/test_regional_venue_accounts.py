"""지방 공연장 인스타 계정(2026-11-28 추가) — 수집 목록(config/insta_accounts.json)과 공연장 연결(config/venues_kr.json instagram 칸)."""
import json
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ACCOUNTS = json.loads((ROOT / "config" / "insta_accounts.json").read_text(encoding="utf-8"))["accounts"]
VENUES = json.loads((ROOT / "config" / "venues_kr.json").read_text(encoding="utf-8"))["venues"]

# 계정 → 공연장 (골목다방은 가게 계정 — 'golvang'은 사장(밴드 SINK TO RISE 보컬) 개인 계정이라 넣지 않음)
REGIONAL = {
    "comonmusicpub": "커먼 뮤직 펍",
    "uzupa_theuniversewave": "우주파",
    "gnstone22": "강릉스톤",
    "kim.anchor": "로얄앵커",
    "jijik.kr": "지직",
    "live_cafe_golvang_kendama": "골목다방",
}


class RegionalVenueAccountsTest(unittest.TestCase):
    def test_accounts_follow_regional_venue_format(self):
        by_handle = {a["handle"]: a for a in ACCOUNTS}
        for handle in REGIONAL:
            with self.subTest(handle=handle):
                a = by_handle.get(handle)
                self.assertIsNotNone(a, f"{handle} 없음")
                self.assertEqual((a["tier"], a["every_days"], a["role"]), ("venue", 4, "venue_showcase"))
                self.assertTrue(a["name"])

    def test_personal_account_is_not_collected(self):
        self.assertNotIn("golvang", {a["handle"] for a in ACCOUNTS})

    def test_no_duplicate_handles(self):
        dup = [h for h, n in Counter(a["handle"].lower() for a in ACCOUNTS).items() if n > 1]
        self.assertEqual(dup, [])

    def test_each_account_is_linked_to_its_venue(self):
        insta = {(v.get("instagram") or "").lower(): v["name"] for v in VENUES if v.get("instagram")}
        for handle, venue in REGIONAL.items():
            with self.subTest(handle=handle):
                self.assertEqual(insta.get(handle.lower()), venue)


if __name__ == "__main__":
    unittest.main()
