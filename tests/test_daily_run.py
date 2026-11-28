"""scripts/daily_run.sh 순서 점검 — 장르 처음 확인한 날(genre_seen.py)이 랩 데이터 내보내기 뒤에 돌고 자동 커밋에 실리는지."""
import re
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "daily_run.sh"


class DailyRunGenreSeenTest(unittest.TestCase):
    def setUp(self):
        self.lines = SCRIPT.read_text(encoding="utf-8").splitlines()

    def _index(self, needle: str) -> int:
        hits = [i for i, line in enumerate(self.lines) if needle in line and not line.lstrip().startswith("#")]
        self.assertEqual(len(hits), 1, f"{needle} 줄이 정확히 한 번 있어야 함")
        return hits[0]

    def test_genre_seen_runs_after_lab_export_and_before_app_extras(self):
        seen = self._index("scripts/genre_seen.py")
        self.assertLess(self._index("scripts/export_lab_data.py"), seen)     # teams.csv·signals.csv 를 읽으니 내보내기 뒤
        self.assertLess(seen, self._index("scripts/build_app_extras.sh"))

    def test_genre_seen_failure_does_not_stop_the_run(self):
        line = self.lines[self._index("scripts/genre_seen.py")]
        self.assertRegex(line, r'\|\| echo "⚠️ ')

    def test_key_aliases_after_export_before_snapshot(self):
        """팀 키가 바뀌면 옛 키→새 키 표를 만들고 지난 스냅샷 키를 고친 뒤에 오늘 스냅샷을 찍는다 (지난주 ▲▼ 비교가 '새로'로 깨지지 않게)."""
        k = self._index("scripts/key_aliases.py")
        self.assertLess(self._index("scripts/export_lab_data.py"), k)
        self.assertLess(k, self._index("scripts/lab_snapshot.py"))
        self.assertRegex(self.lines[k], r'\|\| echo "⚠️ ')

    def test_auto_commit_includes_lab_data_folder(self):
        add = next(line for line in self.lines if line.startswith("git add "))
        self.assertIn(" docs/lab/data ", f" {add} ")                         # docs/lab/data/genre_seen.csv 가 같이 실림
        self.assertIsNone(re.search(r"data/raw|records/", add))               # 원본·개인 기록은 커밋 안 함


class DailyRunCollectorsTest(unittest.TestCase):
    """수집 전수 점검(docs/source_coverage_2026-11-28.md 7절)에서 빠져 있던 수집기 3개가 매일 돌고, 실패해도 다음 단계로 넘어가는지."""

    def setUp(self):
        self.lines = SCRIPT.read_text(encoding="utf-8").splitlines()

    def _hits(self, pred):
        return [i for i, line in enumerate(self.lines) if pred(line) and not line.lstrip().startswith("#")]

    def _one(self, needle):
        hits = self._hits(lambda line: needle in line)
        self.assertEqual(len(hits), 1, f"{needle} 줄이 정확히 한 번 있어야 함")
        return hits[0]

    def test_webzines_and_ssm_shows_run_daily_without_aside_before_validation(self):
        aside_if = self._one("command -v aside")
        validate = self._one("scripts/validate_csv.py")
        for needle in ("scripts/collect_webzines.py", "scripts/collect_ssm_shows.py"):
            i = self._one(needle)
            self.assertLess(i, aside_if)                       # 공개 API·JSON이라 aside 묶음 밖(앞)
            self.assertLess(i, validate)                       # 이번 실행이 만든 원본은 형식 검사를 받는다
            self.assertFalse(self.lines[i].startswith(" "))    # 요일 조건 안이 아니라 매일
            self.assertRegex(self.lines[i], r'\|\| echo "⚠️ ')

    def test_ig_artists_new_tags_daily_after_insta_inside_aside_block(self):
        aside_if = self._one("command -v aside")
        aside_else = next(i for i in range(aside_if, len(self.lines)) if self.lines[i].strip() == "else")
        insta = self._one("scripts/collect_insta.py")
        plain = self._hits(lambda line: "scripts/collect_ig_artists.py" in line and "--handles-file" not in line)
        self.assertEqual(len(plain), 1, "새로 태그된 계정용 collect_ig_artists.py 줄이 한 번 있어야 함")
        i = plain[0]
        self.assertTrue(insta < i < aside_else)                # 그날 인스타 글의 새 태그를 읽고, aside 묶음 안
        self.assertIn("--limit", self.lines[i])                # 인스타 차단 위험 관리: 하루 상한
        self.assertRegex(self.lines[i], r'\|\| echo "⚠️ ')
        monday = self._one('date +%u)" = 1 ]; then   # 월요일: 팔로워')
        monday_end = next(j for j in range(monday, len(self.lines)) if self.lines[j].strip() == "fi")
        self.assertFalse(monday < i < monday_end)              # 월요일만이 아니라 매일


if __name__ == "__main__":
    unittest.main()
