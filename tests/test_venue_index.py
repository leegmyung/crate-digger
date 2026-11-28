"""venue_index: venue_profiles.json(약 600KB) → venue_index.json(이름 → 도시·크기만, 약 18KB).
앱 팀 '공연' 탭이 공연장 도시·크기만 쓰는데 큰 프로필을 통째로 받던 것을 줄인다 (첫 진입 속도 점검 2026-11-28)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import venue_index as vi  # noqa: E402

PROFILES = {
    "as_of": "2026-11-28",
    "venues": {
        "Club FF": {"city": "서울", "tier": "M", "capacity": 400, "monthly": {"2026-11": 11}, "lat": 37.5},
        "A.O.R": {"city": "서울", "tier": "s", "nights": 55},
        "모르는곳": {"city": "", "tier": ""},
        "부산홀": {"city": "부산"},
        "이상한": "깨진 값",
    },
}


class BuildTest(unittest.TestCase):
    def test_keeps_only_city_and_tier(self):
        got = vi.build(PROFILES)
        self.assertEqual(got["as_of"], "2026-11-28")
        self.assertEqual(got["venues"]["Club FF"], {"city": "서울", "tier": "M"})
        self.assertEqual(got["venues"]["A.O.R"], {"city": "서울", "tier": "S"}, "크기는 대문자로")
        self.assertEqual(got["venues"]["부산홀"], {"city": "부산"}, "빈 칸은 빼기")
        self.assertNotIn("모르는곳", got["venues"], "도시·크기 둘 다 없으면 빼기")
        self.assertNotIn("이상한", got["venues"])

    def test_much_smaller_than_profiles(self):
        big = {"as_of": "x", "venues": {f"v{i}": {**PROFILES["venues"]["Club FF"], "before": [["a", 1]] * 20}
                                        for i in range(50)}}
        self.assertLess(len(json.dumps(vi.build(big))), len(json.dumps(big)) / 5)

    def test_bad_input(self):
        self.assertEqual(vi.build({}), {"as_of": "", "venues": {}})
        self.assertEqual(vi.build({"venues": []})["venues"], {})


class MainTest(unittest.TestCase):
    def test_writes_file(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "venue_profiles.json").write_text(json.dumps(PROFILES, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(vi.main(["--data-dir", d]), 0)
            out = json.loads((Path(d) / "venue_index.json").read_text(encoding="utf-8"))
        self.assertEqual(len(out["venues"]), 3)

    def test_missing_profiles_is_error(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(vi.main(["--data-dir", d]), 1)
            self.assertFalse((Path(d) / "venue_index.json").exists())


if __name__ == "__main__":
    unittest.main()
