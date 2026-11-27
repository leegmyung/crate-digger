"""export_venue_tiers: config/venue_capacity.json(공연장 체급) → docs/lab/data/venue_tiers.csv (앱이 읽게, docs/peer_rising.md)."""
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import export_venue_tiers as evt  # noqa: E402

CAP = {"tiers": [{"tier": "S", "max": 150}], "venues": {
    "Club 빵": {"capacity": 120, "tier": "S"}, "롤링홀": {"capacity": 800, "tier": "L"},
    "모름홀": {"capacity": None, "tier": None}, "이상한 줄": "문자열"}}


class ExportVenueTiersTest(unittest.TestCase):
    def test_writes_known_tiers_sorted(self):
        with tempfile.TemporaryDirectory() as d:
            cap, out = Path(d) / "cap.json", Path(d) / "out" / "venue_tiers.csv"
            cap.write_text(json.dumps(CAP, ensure_ascii=False), encoding="utf-8")
            n = evt.export(cap, out)
            with open(out, encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
        self.assertEqual(n, 2)
        self.assertEqual(rows, [{"venue": "Club 빵", "tier": "S"}, {"venue": "롤링홀", "tier": "L"}])

    def test_missing_config_writes_header_only(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "venue_tiers.csv"
            self.assertEqual(evt.export(Path(d) / "없음.json", out), 0)
            self.assertEqual(out.read_text(encoding="utf-8").strip(), "venue,tier")

    def test_main_uses_out_argument(self):
        with tempfile.TemporaryDirectory() as d:
            cap, out = Path(d) / "cap.json", Path(d) / "v.csv"
            cap.write_text(json.dumps(CAP, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(evt.main(["--capacity", str(cap), "--out", str(out)]), 0)
            self.assertTrue(out.exists())


if __name__ == "__main__":
    unittest.main()
