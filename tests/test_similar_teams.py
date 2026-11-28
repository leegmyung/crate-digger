"""docs/lab/sql/similar_teams.sql — '비슷한 팀'(Chartmetric similar artists처럼) 유사도 %.
같은 무대 · 같은 출처 · 같은 장르 · 비슷한 활동 체급만 쓰고 정답(outcomes)은 쓰지 않는다.
duckdb 가 없으면 건너뛴다.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_lab_sql import duckdb, fixture_db, rows  # noqa: F401  (같은 가짜 데이터)


def similar(con, team="a", as_of="2026-11-28"):
    out = rows(con, "similar_teams.sql", team_key=f"'{team}'", as_of=f"DATE '{as_of}'")
    return {r["related_team"]: r for r in out}, [r["related_team"] for r in out]


@unittest.skipIf(duckdb is None, "duckdb 없음")
class SimilarTeamsTest(unittest.TestCase):
    def setUp(self):
        self.con = fixture_db()
        self.con.execute("ALTER TABLE teams ADD COLUMN genre_confidence VARCHAR DEFAULT 'profile'")   # 확인된 장르(멜론 프로필)

    def test_shared_stage_and_shared_source_teams_ranked_by_similarity(self):
        by, order = similar(self.con)
        self.assertNotIn("a", order)                         # 자기 자신 빼기
        self.assertEqual(order[:2], ["b", "g"])              # b: 같은 무대 1번, g: 같은 출처(밴드 디스커버리)
        self.assertEqual(by["b"]["shared_stages"], 1)
        self.assertEqual(by["g"]["shared_sources"], 1)
        self.assertIn("band_discovery", by["g"]["source_names"])
        self.assertEqual(by["b"]["sim_pct"], 23)             # 0.4·(1/3) + 0.15·(1 + 1/3)/2 = 0.233
        self.assertEqual(by["g"]["sim_pct"], 18)             # 0.25·(1/2) + 0.15·(0 + 2/3)/2 = 0.175
        self.assertNotIn("f", order)                         # 겹치는 무대·출처 없음

    def test_parts_add_up_to_total(self):
        by, _ = similar(self.con)
        for r in by.values():
            parts = r["part_stage"] + r["part_source"] + r["part_genre"] + r["part_level"]
            self.assertAlmostEqual(parts, r["sim_pct"], delta=2)

    def test_same_genre_raises_similarity_but_review_genre_does_not(self):
        base, _ = similar(self.con)
        self.con.execute("UPDATE teams SET primary_genre = '록·밴드' WHERE team_key = 'b'")
        by, _ = similar(self.con)
        self.assertTrue(by["b"]["same_genre"])
        self.assertEqual(by["b"]["sim_pct"], base["b"]["sim_pct"] + 20)
        self.con.execute("UPDATE teams SET genre_confidence = 'review' WHERE team_key = 'b'")
        by2, _ = similar(self.con)
        self.assertFalse(by2["b"]["same_genre"])            # 매체 리뷰 장르는 분석에 안 씀

    def test_signals_after_as_of_are_ignored(self):
        _, order = similar(self.con, as_of="2025-12-31")
        self.assertIn("b", order)
        self.assertNotIn("g", order)                         # g 의 신호는 모두 2026년

    def test_does_not_use_outcomes(self):
        before, _ = similar(self.con)
        self.con.execute("DROP TABLE outcomes")
        after, _ = similar(self.con)                         # 정답 표가 없어도 같은 결과
        self.assertEqual({k: v["sim_pct"] for k, v in before.items()}, {k: v["sim_pct"] for k, v in after.items()})

    def test_excluded_role_signals_do_not_count(self):
        self.con.execute("UPDATE signals SET role = 'excluded' WHERE team_key = 'g' AND branch = '선정·지원'")
        _, order = similar(self.con)
        self.assertNotIn("g", order)


if __name__ == "__main__":
    unittest.main()
