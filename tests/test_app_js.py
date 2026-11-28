"""앱 순수 함수(브라우저·DuckDB 없이 도는 것) 검사 — node 로 tests/js/*.test.mjs 를 돌린다. node 가 없으면 건너뜀."""
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JS_DIR = ROOT / "tests" / "js"


@unittest.skipUnless(shutil.which("node"), "node 가 없음")
class AppJsTest(unittest.TestCase):
    def test_js_files(self):
        files = sorted(JS_DIR.glob("*.test.mjs"))
        self.assertTrue(files, "tests/js 에 검사 파일이 없음")
        for f in files:
            with self.subTest(file=f.name):
                r = subprocess.run(["node", "--test", str(f)], cwd=ROOT, capture_output=True, text=True, timeout=120)
                self.assertEqual(r.returncode, 0, f"{f.name}\n{r.stdout[-3000:]}\n{r.stderr[-3000:]}")


if __name__ == "__main__":
    unittest.main()
