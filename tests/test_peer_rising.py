"""이웃 비교(peer_compare.sql)·떠오르는 팀 프리셋(rising_preset.sql)·순위 변화(rank_change.sql) — docs/peer_rising.md.

- 이웃 비교: 같은 발굴 단계(+장르를 아는 팀은 같은 장르) 안 점수·항목 백분위와 등급, 위아래 5팀. 장르 빈칸은 단계만으로.
- 떠오르는 팀: 신인(우리 규칙) × 유명 제외(기준일 시점 정보만) × 체급 상한 × 최근 30·90일 언급 증가.
- 순위 변화: 스냅샷으로 지난주·지난달 대비 ▲▼, 장르·지역 안 순위. 점수 그대로인데 순위만 바뀐 건 표시 안 함.
duckdb가 없으면 건너뛴다(.venv/bin/python -m unittest tests.test_peer_rising).
"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

try:
    import duckdb
except ImportError:  # 시스템 파이썬에는 없을 수 있음
    duckdb = None

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import lab_sql  # noqa: E402
from lab_sql import COLLABS_DDL, SNAPSHOTS_DDL, TEAM_CITIES_DDL, VENUE_TIERS_DDL, fill, read_sql  # noqa: E402

TEAM_COLS = ("team_key VARCHAR, display_name VARCHAR, first_seen DATE, first_release DATE, fan_count INTEGER, "
             "album_count INTEGER, profile_status VARCHAR, primary_genre VARCHAR, newcomer_check VARCHAR, "
             "genre_confidence VARCHAR")
SIGNAL_COLS = ("team_key VARCHAR, branch VARCHAR, source VARCHAR, program VARCHAR, stage_rank INTEGER, "
               "signal_date DATE, venue VARCHAR, role VARCHAR")
OUTCOME_COLS = ("team_key VARCHAR, program VARCHAR, program_label VARCHAR, tier VARCHAR, announced_date DATE, "
                "counted BOOLEAN, grade VARCHAR, weight INTEGER, same_house_scored BOOLEAN, same_house_sources VARCHAR")


def base_db(teams, signals, outcomes=()):
    """teams·signals·outcomes 행(튜플)으로 표를 만들고 features.sql 매크로를 올린 연결."""
    con = duckdb.connect()
    con.execute(f"CREATE TABLE teams({TEAM_COLS})")
    con.execute(f"CREATE TABLE signals({SIGNAL_COLS})")
    con.execute(f"CREATE TABLE outcomes({OUTCOME_COLS})")
    con.execute("CREATE TABLE programs(program VARCHAR, label VARCHAR, kind VARCHAR)")
    for ddl in (COLLABS_DDL, SNAPSHOTS_DDL, TEAM_CITIES_DDL, VENUE_TIERS_DDL):
        con.execute(ddl)
    if teams:
        con.executemany("INSERT INTO teams VALUES (?,?,?,?,?,?,?,?,?,?)", list(teams))
    if signals:
        con.executemany("INSERT INTO signals VALUES (?,?,?,?,?,?,?,?)", list(signals))
    if outcomes:
        con.executemany("INSERT INTO outcomes VALUES (?,?,?,?,?,?,?,?,?,?)", list(outcomes))
    con.execute(read_sql("features.sql"))
    return con


def run(con, name, **params):
    cur = con.execute(fill(read_sql(name), **params))
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def team(key, first_seen="2024-06-01", genre="", status="unknown", fans=None, first_release=None, conf=None):
    conf = conf if conf is not None else ("profile" if genre else "")
    return (key, key.upper(), first_seen, first_release, fans, None, status, genre, None, conf)


def gig(key, day, venue, role="discovery"):
    return (key, "공연", "indistreet", "", None, day, venue, role)


@unittest.skipIf(duckdb is None, "duckdb 없음")
class PeerCompareTest(unittest.TestCase):
    AS_OF = "'2025-01-01'"

    def setUp(self):
        teams, signals = [], []
        for k in range(1, 11):                      # p01..p10: 1단계(공연만), 장르 빈칸, 공연장 수 = k → 점수 차이
            key = f"p{k:02d}"
            teams.append(team(key))
            signals += [gig(key, f"2024-{(i % 9) + 1:02d}-1{i % 9}", f"클럽{i}") for i in range(k)]
        teams += [team("g1", genre="록·밴드"), team("g2", genre="록·밴드")]   # 1단계, 장르 앎 → 장르 안 2팀뿐
        signals += [gig("g1", "2024-05-01", "클럽0"), gig("g1", "2024-05-02", "클럽1"), gig("g2", "2024-05-03", "클럽0")]
        teams.append(team("s1", genre="미분류"))                               # '미분류'는 빈칸처럼 단계만
        signals.append(gig("s1", "2024-04-01", "클럽0"))
        teams.append(team("inf", genre="록·밴드", conf="inferred"))              # 추정 장르 → 단계로만 비교
        signals.append(gig("inf", "2024-04-02", "클럽0"))
        teams.append(team("two"))                                             # 2단계(공연+큐레이션) → 다른 단계
        signals += [gig("two", "2024-05-01", "클럽0"),
                    ("two", "큐레이션", "musicy", "musicy", None, "2024-06-01", "", "discovery")]
        self.con = base_db(teams, signals)

    def rows(self, **params):
        out = run(self.con, "peer_compare.sql", as_of=self.AS_OF, **params)
        return {r["team_key"]: r for r in out}

    def test_blank_genre_compares_within_stage_including_known_genres(self):
        r = self.rows(min_peers="3")
        self.assertEqual(r["p05"]["peer_scope"], "단계")
        self.assertEqual(r["p05"]["peer_n"], 14)          # p01~p10 + g1·g2 + s1 + inf (1단계 전체), 2단계 팀은 빠짐
        self.assertEqual(r["s1"]["peer_scope"], "단계")
        self.assertEqual(r["two"]["stage"], 2)
        self.assertEqual(r["two"]["peer_n"], 1)

    def test_inferred_genre_compares_within_stage_only(self):
        r = self.rows(min_peers="3")
        self.assertEqual(r["inf"]["peer_scope"], "단계")
        self.assertEqual(r["inf"]["peer_n"], 14)
        self.assertEqual(r["g1"]["peer_n"], 2)             # 추정 팀은 장르 무리(록·밴드)에 안 들어감

    def test_known_genre_compares_within_stage_and_genre(self):
        r = self.rows(min_peers="3")
        self.assertEqual(r["g1"]["peer_scope"], "단계+장르")
        self.assertEqual(r["g1"]["peer_n"], 2)
        self.assertEqual(r["g1"]["grade"], "비교군 작음")

    def test_grades_by_rank_share(self):
        r = self.rows(min_peers="3")
        self.assertEqual(r["p10"]["grade"], "탁월")       # 14팀 중 1등 → 상위 7%
        self.assertEqual(r["p08"]["grade"], "훌륭")       # 3등 → 21%
        self.assertEqual(r["p05"]["grade"], "평균")       # 6등 → 43%
        self.assertEqual(r["p01"]["grade"], "평균 이하")  # 공동 11등 → 89%
        self.assertEqual(r["p10"]["score_pct"], 1.0)
        self.assertGreater(r["p10"]["score_pct"], r["p01"]["score_pct"])
        self.assertEqual(r["p10"]["peer_rank"], 1)

    def test_ties_use_middle_of_tied_block(self):
        con = base_db([team(f"t{i}") for i in range(10)], [gig(f"t{i}", "2024-05-01", "클럽0") for i in range(10)])
        r = run(con, "peer_compare.sql", as_of=self.AS_OF, min_peers="3")
        self.assertEqual({x["grade"] for x in r}, {"평균"})   # 10팀 모두 동점 → 모두 '탁월'이 되면 안 됨(가운데 55%)
        self.assertEqual({x["top_share"] for x in r}, {0.55})

    def test_small_group_label_with_default_min_peers(self):
        r = self.rows()                                    # 기본 30팀 미만 → 모두 비교군 작음
        self.assertTrue(all(x["grade"] == "비교군 작음" for x in r.values()))

    def test_neighbors_five_above_and_below(self):
        r = self.rows(min_peers="3")
        mid = r["p05"]
        self.assertEqual(len(mid["neighbors_above"]), 5)
        self.assertEqual(len(mid["neighbors_below"]), 5)
        self.assertEqual(mid["neighbors_above"][-1], "P06")   # 바로 위 팀이 마지막
        self.assertNotIn("P05", mid["neighbors_above"] + mid["neighbors_below"])
        self.assertEqual(r["p10"]["neighbors_above"], [])

    def test_item_percentiles(self):
        r = self.rows(min_peers="3")
        self.assertGreater(r["p10"]["venues_pct"], r["p02"]["venues_pct"])
        for col in ("branch_pct", "stage_pct", "outlets_pct", "winner_pct", "context_pct", "gigs_pct"):
            self.assertIn(col, r["p10"])

    def test_team_filter_keeps_full_peer_group(self):
        out = run(self.con, "peer_compare.sql", as_of=self.AS_OF, team="'p03'")
        self.assertEqual([x["team_key"] for x in out], ["p03"])
        self.assertEqual(out[0]["peer_n"], 14)

    def test_stage_matches_discovery_stage_sql(self):
        mine = {k: v["stage"] for k, v in self.rows().items()}
        theirs = {r["team_key"]: r["stage"] for r in run(self.con, "discovery_stage.sql", as_of=self.AS_OF)}
        for k, s in mine.items():
            self.assertEqual(s, theirs[k], k)


@unittest.skipIf(duckdb is None, "duckdb 없음")
class RisingPresetTest(unittest.TestCase):
    AS_OF = "'2026-12-01'"

    def build(self):
        teams = [
            team("up"), team("flat"), team("big", first_seen="2026-08-01"), team("lateL", first_seen="2026-08-01"),
            team("old", first_seen="2015-01-01"), team("fam", first_seen="2026-08-01", status="famous"),
            team("fans", first_seen="2026-08-01", fans=50000), team("won", first_seen="2026-08-01"),
            team("slow", first_seen="2026-01-01"),
        ]
        sig = []
        for k in ("up", "big", "lateL", "old", "fam", "fans", "won"):     # 최근 30일 3건, 그 전 30일 0건
            sig += [gig(k, "2026-11-05", "클럽S"), gig(k, "2026-11-10", "클럽S"), gig(k, "2026-11-15", "클럽S")]
        # flat: 30일로는 보합(1 vs 1), 90일로는 3 vs 0 → 증가
        sig += [gig("flat", "2026-09-20", "클럽S"), gig("flat", "2026-10-15", "클럽S"), gig("flat", "2026-11-10", "클럽S")]
        sig += [gig("big", "2026-09-01", "홀L")]                          # 기준일 전 L급 → 체급 상한(M) 넘음
        sig += [gig("lateL", "2026-12-10", "홀L")]                        # L급은 기준일 뒤 → 상관없음
        sig += [gig("old", "2015-01-01", "클럽S")]
        # slow: 30일 보합(1 vs 1), 90일 4 vs 1 → 증가
        sig += [gig("slow", "2026-07-01", "클럽S"), gig("slow", "2026-09-10", "클럽S"), gig("slow", "2026-10-20", "클럽S"),
                gig("slow", "2026-10-25", "클럽S"), gig("slow", "2026-11-20", "클럽S")]
        outs = [("won", "kma_rookie", "한대음 신인", "final", "2026-10-01", True, "S", 3, False, "")]
        con = base_db(teams, sig, outs)
        con.execute("INSERT INTO venue_tiers VALUES ('클럽S','S'), ('홀L','L')")
        return con

    def keys(self, con, **params):
        return {r["team_key"]: r for r in run(con, "rising_preset.sql", **{"as_of": self.AS_OF, **params})}

    def test_preset_30_days(self):
        r = self.keys(self.build())
        self.assertIn("up", r)
        self.assertIn("lateL", r)                 # 기준일 뒤 큰 공연장은 모름
        for k in ("flat", "big", "old", "fam", "fans", "won", "slow"):
            self.assertNotIn(k, r, k)
        self.assertEqual((r["up"]["recent_n"], r["up"]["prev_n"]), (3, 0))
        self.assertEqual(r["up"]["max_tier"], "S")
        self.assertEqual(r["up"]["window_days"], 30)

    def test_preset_90_days(self):
        r = self.keys(self.build(), window_days="90")
        self.assertIn("slow", r)
        self.assertIn("flat", r)
        self.assertEqual((r["slow"]["recent_n"], r["slow"]["prev_n"]), (4, 1))

    def test_fame_and_fans_ignored_before_fame_known_date(self):
        con = self.build()
        con.execute("UPDATE signals SET signal_date = signal_date - INTERVAL 2 YEAR")
        con.execute("UPDATE teams SET first_seen = first_seen - INTERVAL 2 YEAR")
        r = self.keys(con, as_of="'2024-12-01'")
        self.assertIn("fam", r)                   # 지금 팬 수·유명 판정은 과거 기준일에 안 씀
        self.assertIn("fans", r)
        self.assertNotIn("big", r)                # 체급 상한은 그대로

    def test_max_tier_and_fans_parameters(self):
        r = self.keys(self.build(), max_tier="'L'", max_fans="100000")
        self.assertIn("big", r)
        self.assertIn("fans", r)

    def test_min_recent(self):
        self.assertNotIn("up", self.keys(self.build(), min_recent="4"))

    def test_sorted_by_growth(self):
        r = run(self.build(), "rising_preset.sql", as_of=self.AS_OF, window_days="90")
        growth = [x["growth"] for x in r]
        self.assertEqual(growth, sorted(growth, reverse=True))


@unittest.skipIf(duckdb is None, "duckdb 없음")
class RankChangeTest(unittest.TestCase):
    def setUp(self):
        teams = [team("a", genre="록·밴드"), team("b", genre="록·밴드"), team("c"), team("d"), team("n", genre="힙합")]
        self.con = base_db(teams, [])
        snaps = [
            ("2026-10-28", "b", 5.0, 1), ("2026-10-28", "a", 3.0, 2), ("2026-10-28", "c", 2.0, 3), ("2026-10-28", "d", 1.0, 4),
            ("2026-11-20", "b", 5.0, 1), ("2026-11-20", "c", 4.0, 2), ("2026-11-20", "a", 3.0, 3), ("2026-11-20", "d", 1.0, 4),
            ("2026-11-27", "a", 6.0, 1), ("2026-11-27", "b", 5.0, 2), ("2026-11-27", "c", 4.0, 3), ("2026-11-27", "n", 2.0, 4),
        ]
        self.con.executemany("INSERT INTO snapshots VALUES (?,?,?,?)", snaps)
        self.con.execute("INSERT INTO team_cities VALUES ('a','서울',1,'서울','','','',3), ('c','부산',1,'부산','','','',2),"
                         " ('b','서울',1,'서울','','','',4)")

    def rows(self, **params):
        return {r["team_key"]: r for r in run(self.con, "rank_change.sql", as_of="'2026-11-27'", **params)}

    def test_snapshot_dates(self):
        r = self.rows()
        self.assertEqual(str(r["a"]["snap_date"]), "2026-11-27")
        self.assertEqual(str(r["a"]["week_date"]), "2026-11-20")
        self.assertEqual(str(r["a"]["month_date"]), "2026-10-28")

    def test_rank_up_with_score_change(self):
        r = self.rows()
        self.assertEqual(r["a"]["week_change"], 2)
        self.assertEqual(r["a"]["week_label"], "▲2")
        self.assertEqual(r["a"]["month_label"], "▲1")

    def test_tie_move_without_score_change_is_hidden(self):
        r = self.rows()
        self.assertIsNone(r["b"]["week_change"])          # 점수 5.0 그대로, 1위→2위 → 표시 안 함
        self.assertEqual(r["b"]["week_label"], "")
        self.assertIsNone(r["c"]["week_change"])          # 4.0 그대로 2위→3위
        self.assertEqual(r["c"]["month_change"], 0)       # 2.0→4.0 점수 바뀜, 3위→3위
        self.assertEqual(r["c"]["month_label"], "–")

    def test_rank_down_with_score_change(self):
        self.con.execute("UPDATE snapshots SET score = 4.5 WHERE snap_date = '2026-11-27' AND team_key = 'b'")
        self.assertEqual(self.rows()["b"]["week_label"], "▼1")

    def test_new_entry(self):
        r = self.rows()
        self.assertEqual(r["n"]["week_label"], "NEW")
        self.assertIsNone(r["n"]["week_change"])
        self.assertNotIn("d", r)                           # 지금 스냅샷에 없는 팀은 줄 없음

    def test_genre_and_city_ranks(self):
        r = self.rows()
        self.assertEqual((r["a"]["genre_rank"], r["b"]["genre_rank"], r["b"]["genre_n"]), (1, 2, 2))
        self.assertIsNone(r["c"]["genre_rank"])           # 장르 빈칸 → 장르 안 순위 없음
        self.assertEqual(r["a"]["city"], "서울")
        self.assertEqual((r["a"]["city_rank"], r["b"]["city_rank"], r["c"]["city_rank"]), (1, 2, 1))
        self.assertIsNone(r["n"]["city_rank"])            # 도시 모름

    def test_genre_rank_change_hidden_when_score_same(self):
        r = self.rows()
        self.assertEqual(r["a"]["genre_week_change"], 1)  # 장르 안 2위→1위, 점수 올라감
        self.assertIsNone(r["b"]["genre_week_change"])    # 장르 안 1위→2위, 점수 그대로

    def test_no_snapshots_gives_no_rows(self):
        con = base_db([team("a")], [])
        self.assertEqual(run(con, "rank_change.sql", as_of="'2026-11-27'"), [])


@unittest.skipIf(duckdb is None, "duckdb 없음")
class ConnectExtrasTest(unittest.TestCase):
    def test_connect_loads_optional_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "signals.csv").write_text("team_key,branch,source,program,stage_rank,signal_date,venue,role\n"
                                           "a,공연,x,,,2024-06-01,클럽S,discovery\n", encoding="utf-8")
            (d / "teams.csv").write_text("team_key,display_name,first_seen,first_release,fan_count,album_count,"
                                         "profile_status,primary_genre\na,A,2024-06-01,,,,unknown,\n", encoding="utf-8")
            (d / "outcomes.csv").write_text("team_key,program,program_label,tier,announced_date,counted,grade,weight\n"
                                            "a,x,x,final,2030-01-01,true,S,3\n", encoding="utf-8")
            (d / "programs.csv").write_text("program,label,kind\nx,x,signal\n", encoding="utf-8")
            (d / "snapshots").mkdir()
            (d / "snapshots" / "2026-11-27.csv").write_text("team_key,score,rank\na,1.5,1\n", encoding="utf-8")
            cap = d / "cap.json"
            cap.write_text('{"venues": {"클럽S": {"tier": "S"}, "모름": {"tier": null}}}', encoding="utf-8")
            con = lab_sql.connect(d, capacity_path=cap)
            self.assertEqual(con.execute("SELECT snap_date::VARCHAR, team_key, score, rank FROM snapshots").fetchall(),
                             [("2026-11-27", "a", 1.5, 1)])
            self.assertEqual(con.execute("SELECT * FROM venue_tiers").fetchall(), [("클럽S", "S")])
            self.assertEqual(con.execute("SELECT COUNT(*) FROM team_cities").fetchone()[0], 0)
            shutil.rmtree(d / "snapshots")
            con2 = lab_sql.connect(d, capacity_path=d / "없음.json")
            self.assertEqual(con2.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0], 0)
            self.assertEqual(con2.execute("SELECT COUNT(*) FROM venue_tiers").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
