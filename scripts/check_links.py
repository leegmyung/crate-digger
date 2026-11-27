"""문서 링크 검사: README.md 와 docs/ 아래 마크다운(일일 기록 docs/log 제외)의 상대 링크가 실제 파일을 가리키는지.

    python3 scripts/check_links.py      # 깨진 링크가 있으면 목록을 보여 주고 1로 끝남

- 외부 주소(http·https·mailto), 같은 문서 안 앵커(#…), 코드 블록·인라인 코드 안의 링크는 검사하지 않는다.
- 'docs/methods.md#정의' 처럼 앵커가 붙은 링크는 파일만 확인한다 (앵커 이름은 렌더러마다 달라서).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List, Tuple
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = ("docs/log",)            # 일일 기록은 자동 생성·양이 많아 제외
LINK = re.compile(r"!?\[[^\]]*\]\(\s*(<[^>]+>|[^)\s]+)(?:\s+\"[^\"]*\")?\s*\)")
EXTERNAL = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|//)", re.I)


def _strip_code(text: str) -> str:
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    return re.sub(r"`[^`\n]*`", "", text)


def find_links(text: str) -> List[str]:
    out = []
    for m in LINK.finditer(_strip_code(text)):
        target = m.group(1).strip("<>").strip()
        if target and not target.startswith("#") and not EXTERNAL.match(target):
            out.append(target)
    return out


def markdown_files(root: Path = ROOT) -> List[Path]:
    files = [root / "README.md"] if (root / "README.md").exists() else []
    docs = root / "docs"
    if docs.is_dir():
        files += sorted(p for p in docs.rglob("*.md")
                        if not any(str(p.relative_to(root)).startswith(s + "/") for s in SKIP_DIRS))
    return files


def broken_links(files: List[Path], root: Path = ROOT) -> List[Tuple[Path, str]]:
    out = []
    for f in files:
        for target in find_links(f.read_text(encoding="utf-8")):
            path = unquote(target.split("#", 1)[0].split("?", 1)[0])
            if path and not (f.parent / path).exists():
                out.append((f, target))
    return out


def main() -> int:
    files = markdown_files()
    broken = broken_links(files)
    for f, t in broken:
        print(f"❌ {f.relative_to(ROOT)} → {t}")
    print(f"{'✅' if not broken else '⚠️'} 문서 {len(files)}개 검사, 깨진 링크 {len(broken)}개")
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
