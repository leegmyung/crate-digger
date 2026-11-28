"""점수 입력의 사후 수집 편향 점검 (scripts/score_leak_audit.py) — 순수 함수."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import score_leak_audit as sla  # noqa: E402


class UntargetedInputTest(unittest.TestCase):
    """이름 묶기 연결표를 '팀을 고르지 않은 출처'로만: 공연·선정·발매·기사 이름 + 발매 플랫폼 번호."""

    def test_names_keep_only_signal_tables(self):
        names = [{"table": "gig", "name": "a"}, {"table": "profile", "name": "b"},
                 {"table": "outcome", "name": "c"}, {"table": "press", "name": "d"},
                 {"table": "selection", "name": "e"}, {"table": "release", "name": "f"}]
        self.assertEqual([n["name"] for n in sla.untargeted_names(names)], ["a", "d", "e", "f"])

    def test_platform_ids_only_from_release_rows(self):
        rows = [{"source": "melon", "artist_text": "팀", "artist_source_id": "123456"},
                {"source": "bugs", "artist_text": "팀", "artist_source_id": "999"},
                {"source": "melon", "artist_text": "공용", "artist_source_id": "0"},
                {"source": "melon", "artist_text": "", "artist_source_id": "222222"}]
        self.assertEqual(sla.release_platform_ids(rows),
                         [{"name": "팀", "platform": "melon", "id": "123456", "confidence": "high"}])


class MappingTest(unittest.TestCase):
    FULL = {"갤럭시익스프레스": "갤럭시익스프레스", "galaxyexpress": "갤럭시익스프레스", "a": "a"}
    UNT = {"갤럭시익스프레스": "갤럭시익스프레스", "galaxyexpress": "galaxyexpress", "a": "a"}

    def key_full(self, text):
        return self.FULL.get(text, text)

    def key_unt(self, text):
        return self.UNT.get(text, text)

    def test_raw_rows_to_key_sets(self):
        raw = [{"branch": "공연", "source": "indistreet", "date": "2024-03-01", "artist_text": "galaxyexpress"},
               {"branch": "공연", "source": "indistreet", "date": "2024-03-01", "artist_text": "a"},
               {"branch": "큐레이션", "source": "izm", "date": "2024-05", "artist_text": "갤럭시익스프레스"},
               {"branch": "공연", "source": "indiego", "date": "2024-03-01", "artist_text": "galaxyexpress"}]   # 점수 안 쓰는 출처
        scored = {("공연", "indistreet"), ("큐레이션", "izm")}
        m = sla.key_map(raw, scored, self.key_full, self.key_unt, split=lambda t: [t])
        self.assertEqual(m, {("갤럭시익스프레스", "공연", "indistreet", "2024-03-01"): {"galaxyexpress"},
                             ("a", "공연", "indistreet", "2024-03-01"): {"a"},
                             ("갤럭시익스프레스", "큐레이션", "izm", "2024-05"): {"갤럭시익스프레스"}})

    def test_reassign_moves_copies_and_keeps(self):
        signals = [{"team_key": "g", "branch": "공연", "source": "indistreet", "signal_date": "2024-03-01", "venue": "v"},
                   {"team_key": "g", "branch": "큐레이션", "source": "izm", "signal_date": "2024-05-31", "venue": ""},
                   {"team_key": "h", "branch": "공연", "source": "indistreet", "signal_date": "2024-04-01", "venue": "v"},
                   {"team_key": "k", "branch": "공연", "source": "indistreet", "signal_date": "2024-04-02", "venue": "v"}]
        mapping = {("g", "공연", "indistreet", "2024-03-01"): {"g_en"},          # 통째로 다른 팀으로
                   ("g", "큐레이션", "izm", "2024-05"): {"g"},                    # 월만 아는 날짜도 맞춤, 그대로
                   ("h", "공연", "indistreet", "2024-04-01"): {"h", "h2"}}         # 남고 복사본 하나
        out, stats = sla.reassign(signals, mapping)
        self.assertEqual(sorted((r["team_key"], r["signal_date"]) for r in out),
                         [("g", "2024-05-31"), ("g_en", "2024-03-01"), ("h", "2024-04-01"), ("h2", "2024-04-01"),
                          ("k", "2024-04-02")])
        self.assertEqual(stats, {"moved": 1, "copied": 1, "kept": 2, "unmatched": 1})
        self.assertEqual(signals[0]["team_key"], "g")                             # 원래 줄은 그대로

    def test_lost_signal_teams_by_cutoff(self):
        signals = [{"team_key": "g", "branch": "공연", "source": "indistreet", "signal_date": "2024-03-01"}]
        mapping = {("g", "공연", "indistreet", "2024-03-01"): {"g_en"}}
        self.assertEqual(sla.lost_teams(signals, mapping, ["2024-01-01", "2024-07-01"]),
                         {"2024-01-01": set(), "2024-07-01": {"g"}})


class ConcentrationTest(unittest.TestCase):
    def test_share_of_hits_vs_others(self):
        pool = {"c1": [{"team_key": "a", "is_hit": 1}, {"team_key": "b", "is_hit": 0}, {"team_key": "c", "is_hit": 0}],
                "c2": [{"team_key": "a", "is_hit": 1}, {"team_key": "d", "is_hit": 1}, {"team_key": "e", "is_hit": 0}]}
        out = sla.concentration(pool, {"c1": {"a", "b"}, "c2": {"zz"}})
        self.assertEqual(out, {"rows": 6, "hits": 3, "flag_rows": 2, "flag_hits": 1,
                               "hit_share": 1 / 3, "other_share": 1 / 3, "rate_flag": 0.5, "rate_rest": 0.5})

    def test_mean_auc_skips_none(self):
        self.assertAlmostEqual(sla.mean_auc({"c1": {"auc": 0.8}, "c2": {"auc": None}, "c3": {"auc": 0.6}}), 0.7)



class UntargetedDebutTest(unittest.TestCase):
    """판 D: 첫 발매일을 '팀 안 고른' 발매 원본(새 발매 목록·포크라노스 날짜 되짚기)의 가장 이른 발매일로 — 모든 팀에 같은 기준."""

    def test_earliest_release_per_team(self):
        rows = [{"artist_text": "A", "released_at": "2021-05-03"}, {"artist_text": "a", "released_at": "2020-02-01"},
                {"artist_text": "B", "released_at": ""}, {"artist_text": "", "released_at": "2020-01-01"},
                {"artist_text": "C", "released_at": "2022-07"}]
        self.assertEqual(sla.untargeted_debut(rows, key_of=str.lower), {"a": "2020-02-01", "c": "2022-07-01"})


if __name__ == "__main__":
    unittest.main()
