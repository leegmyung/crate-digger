"""문서 링크 검사(check_links): README·docs 마크다운의 상대 링크가 실제 파일을 가리키는지."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import check_links as cl  # noqa: E402

TEXT = """# 제목
[방법론](docs/methods.md) · [앵커](docs/methods.md#정의) · [외부](https://example.com/x.md) · [메일](mailto:a@b.c)
[같은 문서 안](#한계) · ![그림](img/a.png "제목") · [꺾쇠](<docs/with space.md>)
`[코드 안](nope.md)` 는 무시
```
[코드 블록](also-nope.md)
```
[없는 파일](docs/missing.md)
"""


class FindTest(unittest.TestCase):
    def test_relative_links_only_outside_code(self):
        self.assertEqual(cl.find_links(TEXT), ["docs/methods.md", "docs/methods.md#정의", "img/a.png",
                                               "docs/with space.md", "docs/missing.md"])


class BrokenTest(unittest.TestCase):
    def test_reports_missing_targets_relative_to_file(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "docs").mkdir()
            (root / "img").mkdir()
            (root / "docs" / "methods.md").write_text("[위로](../README.md) [옆](source_roles.md)", encoding="utf-8")
            (root / "docs" / "with space.md").write_text("", encoding="utf-8")
            (root / "img" / "a.png").write_bytes(b"")
            (root / "README.md").write_text(TEXT, encoding="utf-8")
            broken = cl.broken_links(cl.markdown_files(root), root)
            self.assertEqual([(str(p.relative_to(root)), t) for p, t in broken],
                             [("README.md", "docs/missing.md"), ("docs/methods.md", "source_roles.md")])

    def test_markdown_files_skip_daily_logs(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for rel in ("README.md", "docs/a.md", "docs/sql/README.md", "docs/log/2026-11-27.md", "notes/x.md"):
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text("", encoding="utf-8")
            names = sorted(str(p.relative_to(root)) for p in cl.markdown_files(root))
            self.assertEqual(names, ["README.md", "docs/a.md", "docs/sql/README.md"])


class RepoTest(unittest.TestCase):
    def test_repo_docs_have_no_broken_links(self):
        broken = cl.broken_links(cl.markdown_files(ROOT), ROOT)
        self.assertEqual([f"{p.relative_to(ROOT)} → {t}" for p, t in broken], [])


if __name__ == "__main__":
    unittest.main()
