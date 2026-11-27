"""장르 빈칸 채우기(scripts/genre_fill.py) — docs/genre_fill.md.

확신도(genre_confidence): profile(멜론·발매 장르·사람 확인) > press(확실한 출처 힌트: 리드머·밴드 디스커버리) > inferred
(같은 무대 팀 다수결 → 공연장 성향 → 약한 출처 힌트). 투표는 profile·press 팀만 한다(추정한 장르로 다시 추정하지 않음 — 순환 방지).
정답(검증용) 정보는 쓰지 않는다.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import export_lab_data as ex  # noqa: E402
import genre_fill as gf  # noqa: E402

ROCK, FOLK, HIPHOP = "록·밴드", "포크·싱어송라이터", "힙합"


def t(key, genre="", conf=None):
    return {"team_key": key, "display_name": key, "primary_genre": genre,
            "genre_confidence": conf if conf is not None else ("profile" if genre else "")}


def g(key, day, venue, role="discovery"):
    return {"team_key": key, "branch": "공연", "signal_date": day, "venue": venue, "role": role}


class BaseGenreTest(unittest.TestCase):
    def test_profile_press_blank(self):
        self.assertEqual(gf.base_genre("록/메탈", "", ""), (ROCK, "profile"))
        self.assertEqual(gf.base_genre("", "rhythmer", ""), (HIPHOP, "press"))
        self.assertEqual(gf.base_genre("", "", "band_discovery"), (ROCK, "press"))
        self.assertEqual(gf.base_genre("", "izm", ""), ("", ""))

    def test_team_rows_carry_confidence(self):
        rows = ex.team_rows([
            {"team_key": "a", "raw_genres": "포크/블루스"}, {"team_key": "b", "press_sources": "rhythmer"},
            {"team_key": "c"}, {"team_key": "d", "raw_genres": "록/메탈"}],
            genre_overrides={"d": {"genre": "folk"}, "c": {"genre": "jazz"}})
        got = {r["team_key"]: (r["primary_genre"], r["genre_confidence"]) for r in rows}
        self.assertEqual(got["a"], (FOLK, "profile"))
        self.assertEqual(got["b"], (HIPHOP, "press"))
        self.assertEqual(got["c"], ("재즈", "profile"))     # 사람이 확인한 장르 = profile
        self.assertEqual(got["d"], (FOLK, "profile"))
        self.assertIn("genre_confidence", ex.TEAM_FIELDS)


class WeakHintsTest(unittest.TestCase):
    def test_weak_hints_from_signal_sources_only(self):
        rows = [{"team_key": "h", "press_sources": "izm|hiphople"}, {"team_key": "y", "sel_programs": "yoojaeha_finalist"},
                {"team_key": "o", "sel_programs": "khha_rookie"},       # 정답 프로그램 → 힌트 아님
                {"team_key": "n", "press_sources": "musicy"}]
        self.assertEqual(gf.weak_hints(rows), {"h": HIPHOP, "y": FOLK})


class FillGenresTest(unittest.TestCase):
    def setUp(self):
        self.teams = [t("r1", ROCK), t("r2", ROCK), t("r3", ROCK), t("f1", FOLK),
                      t("x"), t("y"), t("lone"), t("mix"), t("p", HIPHOP, "press")]
        self.sig = [g("x", "2024-01-01", "클럽A"), g("r1", "2024-01-01", "클럽A"), g("r2", "2024-01-01", "클럽A"),
                    g("x", "2024-02-01", "클럽B"), g("r3", "2024-02-01", "클럽B"), g("f1", "2024-02-01", "클럽B"),
                    g("y", "2024-03-01", "클럽C"), g("x", "2024-03-01", "클럽C"),          # y 는 추정된 x 와만 같은 무대
                    g("lone", "2024-04-01", "클럽D"), g("r1", "2024-04-01", "클럽D"),       # 같은 무대 투표 1표뿐
                    g("mix", "2024-05-01", "클럽E"), g("r1", "2024-05-01", "클럽E"), g("f1", "2024-05-01", "클럽E"),
                    g("p", "2024-05-01", "클럽E")]

    def rows(self, teams=None, sig=None, hints=None):
        return {r["team_key"]: (r["primary_genre"], r["genre_confidence"])
                for r in gf.fill_genres(teams or self.teams, sig or self.sig, hints or {})}

    def test_neighbor_majority(self):
        self.assertEqual(self.rows()["x"], (ROCK, "inferred"))   # 록 3표 · 포크 1표 → 75%

    def test_inferred_teams_do_not_vote(self):
        self.assertEqual(self.rows()["y"], ("", ""))

    def test_needs_two_votes_and_sixty_percent(self):
        r = self.rows()
        self.assertEqual(r["lone"], ("", ""))                   # 1표
        self.assertEqual(r["mix"], ("", ""))                    # 록1·포크1·힙합1 → 33%

    def test_known_teams_unchanged_and_input_not_mutated(self):
        before = [dict(x) for x in self.teams]
        r = self.rows()
        self.assertEqual(r["r1"], (ROCK, "profile"))
        self.assertEqual(r["p"], (HIPHOP, "press"))
        self.assertEqual(self.teams, before)

    def test_excluded_and_unknown_venue_ignored(self):
        sig = [g("z", "2024-01-01", "공연장 미정"), g("r1", "2024-01-01", "공연장 미정"), g("r2", "2024-01-01", "공연장 미정"),
               g("z", "2024-02-01", "클럽A"), g("r1", "2024-02-01", "클럽A", role="excluded"),
               g("r2", "2024-02-01", "클럽A", role="excluded")]
        self.assertEqual(self.rows([t("z"), t("r1", ROCK), t("r2", ROCK)], sig)["z"], ("", ""))

    def test_venue_tendency_when_no_neighbor_vote(self):
        teams = [t("v1", FOLK), t("v2", FOLK), t("v3", FOLK), t("v4", FOLK), t("v5", ROCK), t("z"), t("w")]
        sig = [g(k, f"2024-0{i + 1}-01", "포크클럽") for i, k in enumerate(["v1", "v2", "v3", "v4", "v5"])]
        sig += [g("z", "2024-09-01", "포크클럽")]                 # 혼자 선 날 → 같은 무대 투표 없음
        sig += [g(k, f"2024-0{i + 1}-02", "작은클럽") for i, k in enumerate(["v1", "v2", "v3"])] + [g("w", "2024-09-02", "작은클럽")]
        r = self.rows(teams, sig)
        self.assertEqual(r["z"], (FOLK, "inferred"))            # 공연장 투표자 5팀 중 포크 80%
        self.assertEqual(r["w"], ("", ""))                      # 투표자 5팀 미만 공연장은 안 씀

    def test_weak_hint_last(self):
        r = self.rows(hints={"y": HIPHOP, "x": HIPHOP})
        self.assertEqual(r["y"], (HIPHOP, "inferred"))          # 투표 없음 → 약한 힌트
        self.assertEqual(r["x"], (ROCK, "inferred"))            # 같은 무대 다수결이 먼저


class EvaluateTest(unittest.TestCase):
    def test_leave_one_out_on_profile_teams(self):
        teams = [t("a", ROCK), t("b", ROCK), t("c", ROCK), t("d", FOLK)]
        sig = [g(k, "2024-01-01", "클럽A") for k in "abcd"]
        rep = gf.evaluate(teams, sig, {})
        # a·b·c: 나머지 투표 록2·포크1(67%) → 록 맞음. d: 록3 → 틀림
        self.assertEqual(rep["neighbor"], {"n": 4, "correct": 3})
        self.assertEqual(rep["all"], {"n": 4, "correct": 3})


if __name__ == "__main__":
    unittest.main()
