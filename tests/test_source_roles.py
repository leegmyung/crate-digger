"""데이터 출처 역할 분류표(config/source_roles.json) 검사.

- 모든 신호 역할이 4가지(발굴·맥락·제외·검증 대기) 중 하나인지, 정답 등급이 S/A/B이고 가중치가 정수인지.
- 랩 데이터(docs/lab/data/signals.csv)에 나오는 모든 '갈래:출처'(선정·지원은 '갈래:프로그램')가
  분류표에 적혀 있는지. 새 출처가 생기면 이 테스트가 실패한다 → 사람이 역할을 정해 분류표에 적는다
  (default_role 은 분류 전 임시 처리일 뿐, 누락을 덮지 않게 한다).
"""
import csv
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import daily_note as dn  # noqa: E402

ROLES = ("discovery", "context", "excluded", "pending")
GRADE_WEIGHT = {"S": 3, "A": 2, "B": 1}
CONFIG = ROOT / "config" / "source_roles.json"
SIGNALS = ROOT / "docs" / "lab" / "data" / "signals.csv"


def _config():
    return json.loads(CONFIG.read_text(encoding="utf-8"))


class ConfigShapeTest(unittest.TestCase):
    def test_default_and_signal_roles_are_one_of_four(self):
        cfg = _config()
        self.assertIn(cfg["default_role"], ROLES)
        for key, v in cfg["signals"].items():
            self.assertIn(v["role"], ROLES, key)
            self.assertTrue(v.get("reason"), f"{key}: 근거(reason)가 비어 있음")

    def test_signal_keys_are_branch_colon_source(self):
        for key in _config()["signals"]:
            branch, _, source = key.partition(":")
            self.assertIn(branch, ("공연", "큐레이션", "선정·지원", "발매"), key)
            self.assertTrue(source, key)

    def test_outcome_grades_and_integer_weights(self):
        for prog, v in _config()["outcomes"].items():
            if prog.startswith("_"):
                continue
            self.assertIn(v["grade"], GRADE_WEIGHT, prog)
            self.assertIsInstance(v["weight"], int, prog)
            self.assertEqual(v["weight"], GRADE_WEIGHT[v["grade"]], f"{prog}: 등급과 가중치가 안 맞음")


class CoverageTest(unittest.TestCase):
    def test_every_source_in_lab_signals_is_classified(self):
        if not SIGNALS.exists():
            self.skipTest("docs/lab/data/signals.csv 없음 (python3 scripts/export_lab_data.py 로 만듦)")
        with open(SIGNALS, encoding="utf-8") as f:
            missing = dn.unclassified_sources(csv.DictReader(f), _config())
        self.assertEqual(missing, [], "분류표(config/source_roles.json)에 없는 새 출처 — 역할을 정해 적어 주세요: "
                         + ", ".join(missing))


class KeyTest(unittest.TestCase):
    def test_selection_uses_program_others_use_source(self):
        self.assertEqual(dn.source_key({"branch": "선정·지원", "source": "yjh", "program": "yoojaeha_finalist"}),
                         "선정·지원:yoojaeha_finalist")
        self.assertEqual(dn.source_key({"branch": "공연", "source": "indistreet", "program": ""}), "공연:indistreet")
        self.assertEqual(dn.source_key({"branch": "", "source": "", "program": ""}), "")

    def test_unclassified_lists_new_keys_once_sorted(self):
        rows = [{"branch": "공연", "source": "indistreet", "program": ""},
                {"branch": "공연", "source": "newvenue", "program": ""},
                {"branch": "공연", "source": "newvenue", "program": ""},
                {"branch": "큐레이션", "source": "anewzine", "program": ""}]
        cfg = {"signals": {"공연:indistreet": {"role": "discovery"}}}
        self.assertEqual(dn.unclassified_sources(rows, cfg), ["공연:newvenue", "큐레이션:anewzine"])


if __name__ == "__main__":
    unittest.main()
