"""쉬운 말 검사 (docs/ux_simplify_2026-11-28.md ⑥) — 앱 화면 글자에 안쪽 용어 8개가 남지 않았는지 훑는다.

- 검증 화면(정답·같은 집안 같은 말을 일부러 쓰는 곳), 주석, 데이터 파일은 뺀다.
- 화면 글자만 본다: 식별자는 영어라 한국어는 문자열·주석에만 나온다. 주석 줄과 줄 끝 ' // ' 주석은 지우고 본다.
- '정답'은 검증 화면으로 가는 링크 이름(같은 줄에 verify)·기술 표기(outcomeWithTech)에서만 허용.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "docs" / "app"

# 안쪽 용어 → 바꿀 쉬운 말 (실패 메시지에 같이 보여 줌)
TERMS = {
    "백지": "언급 전",
    "갈래": "신호 종류",
    "맥락 매체": "큰 매거진",
    "발굴 매체": "신인 소개 매체",
    "같은 집안": "같은 주최 (검증 화면에서만)",
    "추정·약함": "추정",
    "체급": "공연장 크기",
    "정답": "수상·선정 (검증 화면에서만)",
}

# 검증 화면 · 데이터 품질 라벨 · 다른 작업자 파일(관계망·지도)
SKIP_FILES = {
    "views/verify.js", "views/backtest.js", "views/scorecard.js", "views/quality.js", "views/sql.js",
    "views/signals.js", "views/evidence.js", "db.js", "score_fairness.js",
    "components/region_map.js", "views/venues_list.js", "views/city.js",
    "easy_terms.js",   # 옛 말 → 쉬운 말 바꾸기 표 자체
}
SKIP_PREFIX = ("views/graph", "data/")
# 검증 화면에서만 쓰는 함수 (ui.js) — 이 함수 안은 '정답' 허용
VERIFY_FUNCS = ("renderOutcomeGradeGuideHtml",)

COMMENT_LINE = re.compile(r"^\s*(//|\*|/\*)")
TRAIL_COMMENT = re.compile(r"\s//\s.*$")


def visible_lines(path: Path):
    """(줄 번호, 주석 뺀 줄) — 검증 전용 함수 안은 건너뜀"""
    in_verify_func = False
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.startswith("export function") or line.startswith("function "):
            in_verify_func = any(f"function {f}(" in line for f in VERIFY_FUNCS)
        if in_verify_func or COMMENT_LINE.match(line):
            continue
        yield i, TRAIL_COMMENT.sub("", line)


def allowed(term: str, line: str) -> bool:
    if term == "정답":
        return "verify" in line or "outcomeWithTech" in line
    return False


class UxTermsScanTest(unittest.TestCase):
    def test_no_inner_terms_on_screen(self):
        found = []
        for path in sorted(APP.rglob("*.js")):
            rel = path.relative_to(APP).as_posix()
            if rel in SKIP_FILES or rel.startswith(SKIP_PREFIX):
                continue
            for no, line in visible_lines(path):
                for term, easy in TERMS.items():
                    if term in line and not allowed(term, line):
                        found.append(f"{rel}:{no} '{term}' → '{easy}': {line.strip()[:120]}")
        self.assertEqual(found, [], "\n" + "\n".join(found))

    def test_scanner_skips_comments_and_verify_links(self):
        self.assertTrue(allowed("정답", "<a href=\"#/verify/grades\">정답 규칙 →</a>"))
        self.assertFalse(allowed("정답", "'새 정답'"))
        self.assertIsNotNone(COMMENT_LINE.match("  // 백지 단계"))
        self.assertEqual(TRAIL_COMMENT.sub("", "candTier: '', // 가장 큰 무대 체급"), "candTier: '',")
        self.assertEqual(TRAIL_COMMENT.sub("", "'https://x.y/정답'"), "'https://x.y/정답'")


if __name__ == "__main__":
    unittest.main()
