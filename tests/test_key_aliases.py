"""팀 대표 키가 바뀐 뒤 옛 키 → 새 키 표 (scripts/key_aliases.py → docs/lab/data/key_aliases.csv)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import key_aliases as ka  # noqa: E402

RESOLVE = {"thevolunteers": "더발룬티어스", "the volunteers": "더발룬티어스", "sole": "쏠", "강형호": "pitta"}.get


class BuildTest(unittest.TestCase):
    def test_old_keys_resolve_to_current_keys(self):
        old = {"thevolunteers": "The Volunteers", "sole": "SOLE", "강형호": "강형호", "칩포스트갱": "칩 포스트 갱",
               "hiveparkkr": "hivepark_kr"}
        cur = {"더발룬티어스", "쏠", "pitta", "칩포스트갱"}
        out = ka.build_aliases(old, cur, lambda s: RESOLVE(s.lower()) or RESOLVE(s) or s)
        self.assertEqual(out, {"thevolunteers": "더발룬티어스", "sole": "쏠", "강형호": "pitta"})   # 그대로인 키·사라진 키는 없음

    def test_display_name_used_when_key_does_not_resolve(self):
        out = ka.build_aliases({"xvol": "The Volunteers"}, {"더발룬티어스"}, lambda s: RESOLVE(s.lower()) or s)
        self.assertEqual(out, {"xvol": "더발룬티어스"})

    def test_merge_keeps_old_rows_and_follows_chains(self):
        existing = {"a1": "a2", "z": "gone"}           # a1 → a2 였는데 이번에 a2 → a3
        new = {"a2": "a3"}
        out = ka.merge_aliases(existing, new, {"a3", "b"})
        self.assertEqual(out, {"a1": "a3", "a2": "a3"})  # 대상이 사라진 줄(z)은 버림

    def test_merge_drops_rows_whose_old_key_is_current_again(self):
        self.assertEqual(ka.merge_aliases({"x": "y"}, {}, {"x", "y"}), {})


class SnapshotTest(unittest.TestCase):
    def test_remap_snapshot_keeps_best_rank_on_collision(self):
        rows = [{"team_key": "thevolunteers", "score": "3.1", "rank": "5"},
                {"team_key": "더발룬티어스", "score": "2.0", "rank": "40"},
                {"team_key": "칩포스트갱", "score": "7.5", "rank": "1"}]
        out, changed = ka.remap_snapshot_rows(rows, {"thevolunteers": "더발룬티어스"})
        self.assertTrue(changed)
        self.assertEqual([(r["team_key"], r["rank"]) for r in out], [("더발룬티어스", "5"), ("칩포스트갱", "1")])
        self.assertEqual(rows[0]["team_key"], "thevolunteers")    # 원래 줄은 그대로

    def test_unchanged_snapshot(self):
        rows = [{"team_key": "a", "score": "1", "rank": "1"}]
        out, changed = ka.remap_snapshot_rows(rows, {"b": "c"})
        self.assertFalse(changed)
        self.assertEqual(out, rows)


class CsvTest(unittest.TestCase):
    def test_round_trip(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "key_aliases.csv"
            ka.write_aliases({"sole": "쏠", "thevolunteers": "더발룬티어스"}, p)
            self.assertEqual(p.read_text(encoding="utf-8").splitlines()[0], "old_key,new_key")
            self.assertEqual(ka.read_aliases(p), {"sole": "쏠", "thevolunteers": "더발룬티어스"})
            self.assertEqual(ka.read_aliases(Path(d) / "없음.csv"), {})


if __name__ == "__main__":
    unittest.main()
