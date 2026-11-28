"""장르 처음 확인한 날 되짚기 (scripts/genre_seen.py) — 확인된 장르 = 사후 수집 편향(docs/methods.md) 대책."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import genre_seen as gs  # noqa: E402


def ev(team, labels, seen, known=None, source="profile:melon", kind="profile"):
    return gs.Evidence(team, tuple(labels), seen, known or seen, source, kind)


class MergeStateTest(unittest.TestCase):
    """collect_artists.py 가 프로필을 받을 때마다 부르는 상태 갱신: 처음 본 장르 태그의 날짜만 남긴다."""

    def test_new_tags_get_date_and_old_dates_kept(self):
        state = {"1": {"artist_text": "팀1", "genres": {"록/메탈": "2026-11-20"}}}
        rows = [{"artist_source_id": "1", "artist_text": "팀1", "genre": "록/메탈|인디음악",
                 "collected_at": "2026-11-27T10:00:00+09:00"},
                {"artist_source_id": "2", "artist_text": "팀2", "genre": "",
                 "collected_at": "2026-11-27T10:00:00+09:00"},
                {"artist_source_id": "3", "artist_text": "팀3", "genre": "랩/힙합",
                 "collected_at": "2026-11-27T10:00:00+09:00"}]
        new, added = gs.merge_genre_seen(state, rows)
        self.assertEqual(added, 2)                                        # 팀1 인디음악 + 팀3 랩/힙합
        self.assertEqual(new["1"]["genres"], {"록/메탈": "2026-11-20", "인디음악": "2026-11-27"})
        self.assertEqual(new["3"], {"artist_text": "팀3", "genres": {"랩/힙합": "2026-11-27"}})
        self.assertNotIn("2", new)                                        # 장르 없는 프로필은 안 남김
        self.assertEqual(state["1"]["genres"], {"록/메탈": "2026-11-20"})  # 원래 dict 는 그대로 (새 dict 반환)

    def test_earlier_row_moves_date_back(self):
        state = {"1": {"artist_text": "팀1", "genres": {"록/메탈": "2026-11-27"}}}
        rows = [{"artist_source_id": "1", "artist_text": "팀1", "genre": "록/메탈", "collected_at": "2026-11-26T09:00:00+09:00"}]
        new, added = gs.merge_genre_seen(state, rows)
        self.assertEqual(added, 0)
        self.assertEqual(new["1"]["genres"]["록/메탈"], "2026-11-26")

    def test_state_rows_turn_back_into_profile_rows(self):
        state = {"1": {"artist_text": "팀1", "genres": {"록/메탈": "2026-11-20", "인디음악": "2026-11-27"}}}
        rows = sorted(gs.state_rows(state), key=lambda r: r["collected_at"])
        self.assertEqual(rows, [{"artist_text": "팀1", "genre": "록/메탈", "collected_at": "2026-11-20", "source": "state"},
                                {"artist_text": "팀1", "genre": "인디음악", "collected_at": "2026-11-27", "source": "state"}])


class EvidenceTest(unittest.TestCase):
    def test_profile_rows_seen_is_known(self):
        rows = [{"artist_text": "칩 포스트 갱", "genre": "록/메탈|월드뮤직", "collected_at": "2026-11-27T11:00:00+09:00",
                 "source": "melon"}]
        out = list(gs.profile_evidence(rows, key_of=lambda n: n.replace(" ", "")))
        self.assertEqual(out, [gs.Evidence("칩포스트갱", ("록·밴드", "실험·기타"), "2026-11-27", "2026-11-27",
                                           "profile:melon", "profile")])

    def test_release_known_from_release_date_but_not_after_seen(self):
        rows = [{"artist_text": "a", "genre": "포크/어쿠스틱", "collected_at": "2026-11-28T01:00:00+09:00",
                 "released_at": "2019-05-03", "source": "poclanos"},
                {"artist_text": "b", "genre": "포크/어쿠스틱", "collected_at": "2026-11-26T01:00:00+09:00",
                 "released_at": "2026-12-01", "source": "melon"},                 # 예정 발매: 수집일로 자름
                {"artist_text": "c", "genre": "인디", "collected_at": "2026-11-26T01:00:00+09:00",
                 "released_at": "2020-01-01", "source": "melon"}]                 # 판 표시뿐 → 장르 없음
        out = list(gs.release_evidence(rows, key_of=str))
        self.assertEqual([(e.team_key, e.seen, e.known, e.source) for e in out],
                         [("a", "2026-11-28", "2019-05-03", "release:poclanos"),
                          ("b", "2026-11-26", "2026-11-26", "release:melon")])

    def test_press_known_from_signal_date_seen_from_collected(self):
        signals = [{"team_key": "r1", "branch": "큐레이션", "source": "rhythmer", "program": "", "signal_date": "2021-03-02"},
                   {"team_key": "r1", "branch": "큐레이션", "source": "rhythmer", "program": "", "signal_date": "2019-03-02"},
                   {"team_key": "b1", "branch": "선정·지원", "source": "sangsangmadang", "program": "band_discovery",
                    "signal_date": "2012-07-16"},
                   {"team_key": "x", "branch": "큐레이션", "source": "izm", "program": "", "signal_date": "2020-01-01"}]
        collected = {"r1": "2026-11-26", "b1": "2026-11-26"}
        out = sorted(gs.press_evidence(signals, collected), key=lambda e: (e.team_key, e.known))
        self.assertEqual([(e.team_key, e.labels, e.seen, e.known, e.kind) for e in out],
                         [("b1", ("록·밴드",), "2026-11-26", "2012-07-16", "press"),
                          ("r1", ("힙합",), "2026-11-26", "2019-03-02", "press"),
                          ("r1", ("힙합",), "2026-11-26", "2021-03-02", "press")])

    def test_override_uses_checked_date(self):
        ov = {"하즈": {"genre": "metal", "checked": "2026-11-27"}}
        self.assertEqual(list(gs.override_evidence(ov)),
                         [gs.Evidence("하즈", ("메탈·하드코어",), "2026-11-27", "2026-11-27", "override", "profile")])


class FirstSeenTableTest(unittest.TestCase):
    TEAMS = [{"team_key": "a", "primary_genre": "록·밴드", "genre_confidence": "profile"},
             {"team_key": "b", "primary_genre": "힙합", "genre_confidence": "press"},
             {"team_key": "c", "primary_genre": "포크·싱어송라이터", "genre_confidence": "profile"},
             {"team_key": "d", "primary_genre": "록·밴드", "genre_confidence": "inferred"},   # 추정은 안 냄
             {"team_key": "e", "primary_genre": "재즈", "genre_confidence": "profile"}]

    def test_earliest_matching_evidence_per_team(self):
        evidence = [ev("a", ["록·밴드"], "2026-11-27"),
                    ev("a", ["록·밴드"], "2026-11-28", known="2019-01-01", source="release:poclanos"),
                    ev("a", ["포크·싱어송라이터"], "2026-11-26"),                       # 다른 장르 → 대표 장르 근거 아님
                    ev("b", ["힙합"], "2026-11-26", known="2019-03-02", source="press:rhythmer", kind="press"),
                    ev("b", ["힙합"], "2026-11-25"),                                    # profile 근거는 press 팀에 안 씀
                    ev("c", ["록·밴드"], "2026-11-27")]                                 # 맞는 장르가 없으면 아무 장르로
        rows = {r["team_key"]: r for r in gs.first_seen_table(self.TEAMS, evidence)}
        self.assertEqual(set(rows), {"a", "b", "c", "e"})
        self.assertEqual((rows["a"]["first_seen"], rows["a"]["first_seen_source"]), ("2026-11-27", "profile:melon"))
        self.assertEqual((rows["a"]["known_from"], rows["a"]["known_from_source"]), ("2019-01-01", "release:poclanos"))
        self.assertEqual(rows["a"]["match"], "genre")
        self.assertEqual((rows["b"]["first_seen"], rows["b"]["known_from"]), ("2026-11-26", "2019-03-02"))
        self.assertEqual(rows["c"]["match"], "any")
        self.assertEqual((rows["e"]["first_seen"], rows["e"]["known_from"], rows["e"]["match"]), ("", "", "none"))
        self.assertEqual(list(rows["a"]), list(gs.COLUMNS))

    def test_point_in_time_counts(self):
        table = [{"team_key": "a", "first_seen": "2026-11-27", "known_from": "2019-01-01"},
                 {"team_key": "b", "first_seen": "2026-11-26", "known_from": "2024-03-02"},
                 {"team_key": "e", "first_seen": "", "known_from": ""}]
        counts = gs.point_in_time_counts(table, ["2024-01-01", "2025-01-01"])
        self.assertEqual(counts, [{"cutoff": "2024-01-01", "by_first_seen": 0, "by_known_from": 1, "total": 3},
                                  {"cutoff": "2025-01-01", "by_first_seen": 0, "by_known_from": 2, "total": 3}])

    def test_pool_counts_rows_and_hits(self):
        table = [{"team_key": "a", "first_seen": "2026-11-27", "known_from": "2019-01-01"},
                 {"team_key": "b", "first_seen": "2026-11-26", "known_from": "2024-03-02"}]
        pool = {"2024-01-01": [{"team_key": "a", "is_hit": 1}, {"team_key": "b", "is_hit": 1}, {"team_key": "z", "is_hit": 0}]}
        out = gs.pool_counts(table, pool)
        self.assertEqual(out, [{"cutoff": "2024-01-01", "rows": 3, "hits": 2, "confirmed_now": 2, "confirmed_now_hits": 2,
                                "known_then": 1, "known_then_hits": 1, "seen_then": 0}])


if __name__ == "__main__":
    unittest.main()
