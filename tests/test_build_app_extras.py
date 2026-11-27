"""build_app_extras.sh: 앱 데이터 생성 묶음 — 순서·실패해도 다음으로·단계별 시간 (가짜 파이썬으로 실행 순서만 확인)."""
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "build_app_extras.sh"


def _run(extra_args=(), fail_on=""):
    with tempfile.TemporaryDirectory() as d:
        log = Path(d) / "calls.log"
        stub = Path(d) / "python"
        stub.write_text("#!/bin/bash\n"
                        f"echo \"$*\" >> '{log}'\n"
                        f"case \"$1\" in *{fail_on or '__none__'}*) exit 1;; esac\n"
                        "exit 0\n", encoding="utf-8")
        stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
        proc = subprocess.run(["bash", str(SCRIPT), *extra_args], capture_output=True, text=True,
                              env={**os.environ, "PY": str(stub)}, timeout=60)
        calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return proc, calls


class BuildAppExtrasTest(unittest.TestCase):
    def test_syntax(self):
        self.assertEqual(subprocess.run(["bash", "-n", str(SCRIPT)]).returncode, 0)

    def test_order_and_arguments(self):
        proc, calls = _run()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(calls, ["scripts/export_venue_tiers.py",
                                 "scripts/venue_ladder.py --json-only", "scripts/venue_profiles.py",
                                 "scripts/city_profiles.py --data-only", "scripts/festival_profiles.py --no-doc",
                                 "scripts/lineup_roles.py --data-only",
                                 "scripts/event_stars.py", "scripts/build_alerts.py"])
        self.assertIn("✅ venue_ladder", proc.stdout)
        self.assertIn("✅ venue_tiers", proc.stdout)
        self.assertRegex(proc.stdout, r"✅ build_alerts\s+\d+초")

    def test_with_export_runs_export_first(self):
        _, calls = _run(["--with-export"])
        self.assertEqual(calls[0], "scripts/export_lab_data.py")
        self.assertEqual(len(calls), 9)

    def test_failure_continues_and_exit_code_nonzero(self):
        proc, calls = _run(fail_on="venue_profiles")
        self.assertEqual(len(calls), 8)                       # 실패한 뒤에도 끝까지
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("⚠️ venue_profiles 실패", proc.stdout)
        self.assertIn("실패: venue_profiles", proc.stdout)


if __name__ == "__main__":
    unittest.main()
