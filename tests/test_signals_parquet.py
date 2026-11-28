"""export_signals_parquet: signals.csv → signals.parquet (같은 행·같은 칸 모양, zstd). CSV 는 그대로 둔다(다른 도구 호환).
앱은 meta.json extras_rows['signals.parquet'] 행 수가 rows.signals 와 같을 때만 Parquet 을 읽는다."""
import csv
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
try:
    import duckdb  # noqa: F401
    import export_signals_parquet as esp  # noqa: E402
    HAVE_DUCKDB = True
except ImportError:      # duckdb 는 .venv 에만 있음
    HAVE_DUCKDB = False

CSV_TEXT = ("team_key,branch,source,program,stage_rank,signal_date,venue,role\n"
            "a,공연,indistreet,,1,2026-11-01,Club FF,discovery\n"
            "b,선정·지원,program,band_discovery,2,2026-10-02,,discovery\n"
            "c,공연,instagram,,1,2026-09-03,\"A, B 홀\",context\n")


@unittest.skipUnless(HAVE_DUCKDB, "duckdb 없음 (.venv/bin/python 으로 돌리기)")
class ExportTest(unittest.TestCase):
    def _write(self, d: Path) -> Path:
        p = d / "signals.csv"
        p.write_text(CSV_TEXT, encoding="utf-8")
        return p

    def test_same_rows_and_types(self):
        with tempfile.TemporaryDirectory() as d:
            src = self._write(Path(d))
            out = Path(d) / "signals.parquet"
            n = esp.export(src, out)
            self.assertEqual(n, 3)
            self.assertTrue(out.read_bytes().startswith(b"PAR1"))
            con = duckdb.connect()
            types = {r[0]: r[1] for r in con.sql(f"DESCRIBE SELECT * FROM read_parquet('{out}')").fetchall()}
            self.assertEqual(types["signal_date"], "DATE")
            self.assertEqual(types["stage_rank"], "BIGINT")
            rows = con.sql(f"SELECT team_key, venue FROM read_parquet('{out}') ORDER BY team_key").fetchall()
            self.assertEqual(rows[2], ("c", "A, B 홀"), "쉼표 든 칸도 그대로")
            self.assertEqual(src.read_text(encoding="utf-8"), CSV_TEXT, "CSV 는 안 건드림")

    def test_types_match_csv_reading(self):
        """앱(브라우저 DuckDB)이 CSV 를 read_csv_auto 로 읽을 때와 같은 칸 모양이어야 features.sql 이 똑같이 돈다."""
        with tempfile.TemporaryDirectory() as d:
            src = self._write(Path(d))
            out = Path(d) / "signals.parquet"
            esp.export(src, out)
            con = duckdb.connect()
            a = con.sql(f"DESCRIBE SELECT * FROM read_csv_auto('{src}', header=true)").fetchall()
            b = con.sql(f"DESCRIBE SELECT * FROM read_parquet('{out}')").fetchall()
            self.assertEqual([(r[0], r[1]) for r in a], [(r[0], r[1]) for r in b])

    def test_main_missing_csv(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(esp.main(["--data-dir", d]), 1)
            self.assertFalse((Path(d) / "signals.parquet").exists())

    def test_main_writes_next_to_csv(self):
        with tempfile.TemporaryDirectory() as d:
            self._write(Path(d))
            self.assertEqual(esp.main(["--data-dir", d]), 0)
            self.assertTrue((Path(d) / "signals.parquet").is_file())


if __name__ == "__main__":
    unittest.main()
