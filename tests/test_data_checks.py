"""매일 데이터 검사(data_checks): 랩 데이터·수집 기록·(읽기 전용) PostgreSQL을 보고 규칙 위반을 찾아 점검표로."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import data_checks as dc  # noqa: E402
import data_checks_extra as dx  # noqa: E402

TODAY = "2026-11-27"


def sig(team, branch="공연", source="indistreet", date="2026-11-20", program=""):
    return {"team_key": team, "branch": branch, "source": source, "program": program, "signal_date": date}


def team(key, status="unknown", first_release="", genre=""):
    return {"team_key": key, "profile_status": status, "first_release": first_release, "primary_genre": genre}


class FreshnessTest(unittest.TestCase):
    def test_collect_freshness_warns_on_stale_source_and_fails_on_very_old(self):
        runs = [{"date": "2026-11-27", "source": "a", "table": "raw_press", "rows": 5},
                {"date": "2026-11-24", "source": "b", "table": "raw_press", "rows": 5},
                {"date": "2026-11-27", "source": "b", "table": "raw_press", "rows": 0}]
        c = dc.check_collect_freshness(runs, TODAY)
        self.assertEqual(c.status, "warn")
        self.assertIn("b", c.value)
        runs.append({"date": "2026-11-10", "source": "z", "table": "raw_kr_gig", "rows": 3})
        self.assertEqual(dc.check_collect_freshness(runs, TODAY).status, "fail")

    def test_collect_freshness_passes_when_all_recent_and_skips_without_runs(self):
        runs = [{"date": "2026-11-26", "source": "a", "table": "raw_press", "rows": 5}]
        self.assertEqual(dc.check_collect_freshness(runs, TODAY).status, "pass")
        self.assertEqual(dc.check_collect_freshness([], TODAY).status, "skip")

    def test_signal_recency_ignores_selection_branch_and_future_dates(self):
        signals = [sig("a", "선정·지원", "yjh", "2020-01-01"), sig("b", "공연", "indistreet", "2026-11-26"),
                   sig("c", "큐레이션", "weiv", "2026-12-30")]
        c = dc.check_signal_recency(signals, TODAY)
        self.assertEqual(c.status, "fail")      # weiv: 미래 날짜만 있음 → 오늘 이전 신호 없음
        signals = [sig("a", "선정·지원", "yjh", "2020-01-01"), sig("b", "큐레이션", "weiv", "2026-11-05")]
        c = dc.check_signal_recency(signals, TODAY)
        self.assertEqual(c.status, "warn")
        self.assertIn("weiv", c.value)
        self.assertEqual(dc.check_signal_recency([sig("b", date="2026-11-26")], TODAY).status, "pass")


class RowCountTest(unittest.TestCase):
    def test_row_change_fails_on_big_drop_and_warns_on_big_jump(self):
        meta = {"prev_rows": {"signals": 1000, "teams": 100}, "rows": {"signals": 500, "teams": 100}}
        self.assertEqual(dc.check_row_change(meta).status, "fail")
        meta = {"prev_rows": {"signals": 1000}, "rows": {"signals": 1700}}
        self.assertEqual(dc.check_row_change(meta).status, "warn")
        meta = {"prev_rows": {"signals": 1000, "collabs": 0}, "rows": {"signals": 1010, "collabs": 3}}
        self.assertEqual(dc.check_row_change(meta).status, "pass")

    def test_row_change_skips_without_previous_day(self):
        self.assertEqual(dc.check_row_change({"prev_rows": {}, "rows": {"signals": 5}}).status, "skip")

    def test_row_change_ignores_small_tables(self):
        meta = {"prev_rows": {"programs": 10}, "rows": {"programs": 2}}
        self.assertEqual(dc.check_row_change(meta).status, "pass")

    def test_meta_rows_must_match_csv_rows(self):
        meta = {"rows": {"signals": 3, "teams": 2}}
        self.assertEqual(dc.check_meta_rows(meta, {"signals": 3, "teams": 2}).status, "pass")
        c = dc.check_meta_rows(meta, {"signals": 4, "teams": 2})
        self.assertEqual(c.status, "fail")
        self.assertIn("signals", c.value)

    def test_meta_fresh(self):
        self.assertEqual(dc.check_meta_fresh({"generated_at": "2026-11-27T21:40:00+09:00"}, TODAY).status, "pass")
        self.assertEqual(dc.check_meta_fresh({"generated_at": "2026-11-25T21:40:00+09:00"}, TODAY).status, "fail")
        self.assertEqual(dc.check_meta_fresh({}, TODAY).status, "fail")


class LinkageTest(unittest.TestCase):
    def test_orphan_signals_excludes_listed_teams(self):
        signals = [sig("a"), sig("x"), sig("x")]
        self.assertEqual(dc.check_orphan_signals(signals, {"a"}, {"x"}).status, "pass")
        c = dc.check_orphan_signals(signals + [sig("ghost")], {"a"}, {"x"})
        self.assertEqual(c.status, "fail")
        self.assertIn("1", c.value)

    def test_orphan_side_tables_warn_over_threshold(self):
        tables = {"links": [{"team_key": "a"}, {"team_key": "b"}], "images": [{"team_key": "a"}]}
        self.assertEqual(dc.check_orphan_side(tables, {"a", "b"}, set()).status, "pass")
        c = dc.check_orphan_side(tables, {"a"}, set())
        self.assertEqual(c.status, "warn")
        self.assertIn("links", c.value)

    def test_future_signals_outside_gigs_are_flagged(self):
        signals = [sig("a", "공연", date="2026-12-20"), sig("b", "선정·지원", "busanrock", "2027-03-01")]
        c = dc.check_future_signals(signals, TODAY)
        self.assertEqual(c.status, "warn")
        self.assertIn("busanrock", c.value)
        self.assertEqual(dc.check_future_signals([sig("a", "공연", date="2026-12-20")], TODAY).status, "pass")

    def test_far_future_gig_is_flagged(self):
        c = dc.check_future_signals([sig("a", "공연", date="2028-01-01")], TODAY)
        self.assertEqual(c.status, "warn")

    def test_duplicate_names_finds_spacing_case_and_the_prefix(self):
        c = dc.check_duplicate_names(["moss", "themoss", "새소년", "새 소년", "혁오", "ㄹㄹ", "ㅈ"])
        self.assertEqual(c.status, "warn")
        self.assertIn("moss", c.value)
        self.assertIn("새소년", c.value)
        self.assertNotIn("ㅈ", c.value)
        self.assertEqual(dc.check_duplicate_names(["혁오", "새소년"]).status, "pass")

    def test_squash_keeps_korean_jamo_distinct(self):
        self.assertNotEqual(dc.squash("ㄹㄹ"), dc.squash("ㅈ"))

    def test_variant_norm_folds_common_spelling_wobble(self):
        for a, b in (("웬디소블루", "웬디쏘블루"), ("퓨처피어클럽", "퓨쳐피어클럽"), ("러브이스사이클", "러브이즈사이클"),
                     ("마인드애틱", "마인드에틱"), ("멧차파티", "멧챠파티"), ("플레이버대쉬", "플레이버대시"),
                     ("나인라인즈", "더나인라인즈"), ("릴체리x골드부다", "릴체리골드부다")):
            self.assertEqual(dc.variant_norm(a), dc.variant_norm(b), (a, b))
        self.assertNotEqual(dc.variant_norm("허클베리피"), dc.variant_norm("허클베리핀"))
        self.assertNotEqual(dc.variant_norm("더더"), dc.variant_norm("더"))    # 짧은 이름의 '더'는 떼지 않음

    def test_romanize_hangul(self):
        self.assertEqual(dc.romanize("양홍원"), "yanghongwon")
        self.assertEqual(dc.romanize("한결"), "hangyeol")
        self.assertEqual(dc.romanize("로얄44"), "royal44")

    def test_one_edit_apart(self):
        self.assertTrue(dc.one_edit_apart("초춘목밴드", "최춘목밴드"))
        self.assertTrue(dc.one_edit_apart("bugokhawaii", "bukokhawaii"))
        self.assertTrue(dc.one_edit_apart("오이스터", "오이스터즈"))
        self.assertFalse(dc.one_edit_apart("abcd", "abdc"))
        self.assertFalse(dc.one_edit_apart("같음", "같음"))

    def test_duplicate_candidates_kinds(self):
        keys = ["moss", "themoss", "웬디소블루", "웬디쏘블루", "양홍원", "yanghongwon", "초춘목밴드", "최춘목밴드",
                "aeil", "veil", "밴드1호", "밴드2호", "추다혜차지스"]
        links = [{"team_key": "추다혜차지스", "url": "https://www.instagram.com/x/"},
                 {"team_key": "chudahyechagis추다혜차지스", "url": "https://www.instagram.com/x/"}]
        got = {(k, a, b) for k, a, b, _ in dc.duplicate_candidates(keys, links)}
        kinds = {(a, b): k for k, a, b in got}
        self.assertEqual(kinds[("moss", "themoss")], "띄어쓰기·대소문자·the")
        self.assertEqual(kinds[("웬디소블루", "웬디쏘블루")], "표기 흔들림")
        self.assertEqual(kinds[("양홍원", "yanghongwon")], "로마자 표기")
        self.assertEqual(kinds[("초춘목밴드", "최춘목밴드")], "한 글자 차이")
        self.assertEqual(kinds[("chudahyechagis추다혜차지스", "추다혜차지스")], "같은 링크 주소")
        self.assertNotIn(("aeil", "veil"), kinds)        # 짧은 영문 이름은 한 글자 차이로 안 봄 (잡음)
        self.assertNotIn(("밴드1호", "밴드2호"), kinds)    # 숫자만 다르면 다른 팀

    def test_short_names_spelling_wobble_is_low(self):
        got = {(a, b): k for k, a, b, _ in dc.duplicate_candidates(["오왠", "오웬", "김재호", "김제호"])}
        self.assertEqual(got[("오왠", "오웬")], "짧은 이름 표기 흔들림")
        self.assertEqual(dc.DUP_PRIORITY["짧은 이름 표기 흔들림"], "낮음")

    def test_duplicate_candidates_skip_curated_pairs(self):
        curated = {"aliases": [{"main": "웬디쏘블루", "aliases": ["웬디소블루"]}],
                   "distinct": [{"names": ["허클베리 피", "허클베리핀"]}]}
        got = dc.duplicate_candidates(["웬디소블루", "웬디쏘블루", "허클베리피", "허클베리핀"], [], curated)
        self.assertEqual(got, [])

    def test_check_duplicate_names_lists_details_by_priority(self):
        c = dc.check_duplicate_names(["moss", "themoss", "초춘목밴드", "최춘목밴드"])
        self.assertEqual(c.status, "warn")
        self.assertTrue(c.details[0].startswith("높음"))
        self.assertTrue(any("최춘목밴드" in d for d in c.details))

    def test_check_duplicate_names_low_only_passes(self):
        c = dc.check_duplicate_names(["초춘목밴드", "최춘목밴드"])
        self.assertEqual(c.status, "pass")     # 한 글자 차이(낮음)만 있으면 목록만 보여 주고 통과
        self.assertTrue(c.details)


class OutcomeTest(unittest.TestCase):
    def test_counted_follows_five_year_rule_for_filtered_programs(self):
        teams = {"old": team("old", first_release="2015-01-01"), "new": team("new", first_release="2023-01-01"),
                 "nofr": team("nofr")}
        good = [{"team_key": "old", "program": "mucon", "announced_date": "2025-06-01", "counted": "false"},
                {"team_key": "new", "program": "mucon", "announced_date": "2025-06-01", "counted": "true"},
                {"team_key": "nofr", "program": "mucon", "announced_date": "2025-06-01", "counted": "false"},
                {"team_key": "old", "program": "kma_rookie", "announced_date": "2025-06-01", "counted": "true"},
                {"team_key": "unseen", "program": "mucon", "announced_date": "2025-06-01", "counted": "true"}]
        c = dc.check_counted(good, teams, {"mucon"}, 5)
        self.assertEqual(c.status, "pass")
        self.assertIn("1", c.value)    # 팀 표에 없어 확인 못 한 1건
        bad = good + [{"team_key": "old", "program": "mucon", "announced_date": "2025-07-01", "counted": "true"},
                      {"team_key": "new", "program": "kma_rookie", "announced_date": "2025-07-01", "counted": "false"}]
        c = dc.check_counted(bad, teams, {"mucon"}, 5)
        self.assertEqual(c.status, "fail")
        self.assertIn("2", c.value)

    def test_b_grade_programs_should_be_career_filtered(self):
        roles = {"outcomes": {"mucon": {"grade": "B"}, "hello_rookie": {"grade": "B"}, "kma_rookie": {"grade": "S"},
                              "_설명": "x"}}
        c = dc.check_b_grade_rule(roles, {"mucon"})
        self.assertEqual(c.status, "warn")
        self.assertIn("hello_rookie", c.value)
        self.assertEqual(dc.check_b_grade_rule(roles, {"mucon", "hello_rookie"}).status, "pass")

    def test_same_house_flags_consistent(self):
        roles = {"same_house": [{"apply": True, "outcomes": ["a"], "sources": ["공연:x"]}]}
        rows = [{"same_house_sources": "공연:x", "same_house_scored": "true"},
                {"same_house_sources": "", "same_house_scored": "false"}]
        c = dc.check_same_house(rows, roles)
        self.assertEqual(c.status, "pass")
        self.assertIn("1", c.value)
        rows.append({"same_house_sources": "", "same_house_scored": "true"})
        self.assertEqual(dc.check_same_house(rows, roles).status, "fail")
        self.assertEqual(dc.check_same_house([rows[1]], roles).status, "warn")   # 규칙은 켜졌는데 표시 0


class CoverageTest(unittest.TestCase):
    def test_genre_unclassified_among_profiled_teams(self):
        teams = [team("a", "newcomer", genre="밴드"), team("b", "newcomer"), team("c")]
        c = dc.check_genre(teams)
        self.assertEqual(c.status, "warn")    # 프로필 있는 팀 중 50% 미분류
        self.assertEqual(dc.check_genre([team("a", "newcomer", genre="밴드"), team("c")]).status, "pass")

    def test_first_release_coverage_among_profiled_teams(self):
        teams = [team("a", "newcomer", "2024-01-01"), team("b", "famous"), team("c")]
        self.assertEqual(dc.check_first_release(teams).status, "fail")
        self.assertEqual(dc.check_first_release([team("a", "newcomer", "2024-01-01"), team("c")]).status, "pass")

    def test_url_shapes(self):
        links = [{"platform": "melon", "url": "https://www.melon.com/artist/detail.htm?artistId=1"},
                 {"platform": "youtube", "url": "https://youtube.com/@x"}]
        images = [{"source": "spotify", "url": "https://i.scdn.co/image/abc"}]
        self.assertEqual(dc.check_url_shapes(links, images).status, "pass")
        links.append({"platform": "melon", "url": "http://evil.example/x"})
        c = dc.check_url_shapes(links, images)
        self.assertEqual(c.status, "fail")
        self.assertIn("1", c.value)

    def test_top_profile_missing_ratio(self):
        snap = [{"team_key": f"t{i}", "rank": str(i + 1)} for i in range(10)]
        teams = {f"t{i}": team(f"t{i}", "newcomer" if i < 8 else "unknown") for i in range(10)}
        self.assertEqual(dc.check_top_profile(snap, teams, top=10).status, "pass")
        teams = {f"t{i}": team(f"t{i}", "newcomer" if i < 5 else "unknown") for i in range(10)}
        self.assertEqual(dc.check_top_profile(snap, teams, top=10).status, "warn")
        self.assertEqual(dc.check_top_profile([], teams).status, "skip")

    def test_snapshot_consistency(self):
        snap = [{"team_key": "a", "rank": "1"}, {"team_key": "x", "rank": "2"}]
        c = dc.check_snapshot(["2026-11-27"], snap, TODAY, {"a"}, {"x"})
        self.assertEqual(c.status, "warn")    # 제외 목록 팀이 스냅샷에
        self.assertIn("x", c.value)
        self.assertEqual(dc.check_snapshot(["2026-11-26"], snap[:1], TODAY, {"a"}, set()).status, "warn")
        self.assertEqual(dc.check_snapshot(["2026-11-27"], snap[:1], TODAY, {"a"}, set()).status, "pass")
        self.assertEqual(dc.check_snapshot([], [], TODAY, {"a"}, set()).status, "skip")


class PgTest(unittest.TestCase):
    def fake_run(self, answers):
        def run(sql):
            for marker, text in answers.items():
                if marker in sql:
                    return text
            raise AssertionError(f"unexpected query: {sql[:80]}")
        return run

    def answers(self, **over):
        base = {"dc:sync": "n\n100\n", "dc:unknown_programs": "program,n\n",
                "dc:no_artist": "total,no_artist,no_date\n1000,2,0\n",
                "dc:career": "program\nmucon\n",
                "dc:own_release": "n,has_all,has_own,diff3y,own_earlier\n100,98,90,2,0\n"}
        base.update(over)
        return base

    def test_own_release_coverage_and_big_differences(self):
        run = self.fake_run(self.answers(**{"dc:own_release": "n,has_all,has_own,diff3y,own_earlier\n796,787,65,11,0\n"}))
        c = {c.key: c for c in dc.pg_checks(run, lab_signals=100, career_filtered={"mucon"})}["pg_own_release"]
        self.assertEqual(c.status, "warn")          # 보유율 8% < 50%
        self.assertIn("65/796", c.value)
        self.assertIn("11", c.value)
        run = self.fake_run(self.answers(**{"dc:own_release": "n,has_all,has_own,diff3y,own_earlier\n100,98,90,2,3\n"}))
        c = {c.key: c for c in dc.pg_checks(run, lab_signals=100, career_filtered={"mucon"})}["pg_own_release"]
        self.assertEqual(c.status, "warn")          # 본인 음반이 전체보다 이르면 계산 오류

    def test_pg_checks_pass_on_clean_db(self):
        checks = dc.pg_checks(self.fake_run(self.answers()), lab_signals=100, career_filtered={"mucon"})
        self.assertTrue(all(c.status == "pass" for c in checks), [(c.key, c.status, c.value) for c in checks])

    def test_pg_checks_flag_problems(self):
        run = self.fake_run(self.answers(**{"dc:sync": "n\n150\n", "dc:unknown_programs": "program,n\nnew_award,4\n",
                                            "dc:no_artist": "total,no_artist,no_date\n1000,50,3\n",
                                            "dc:career": "program\nmucon\nkma_genre\n"}))
        by_key = {c.key: c for c in dc.pg_checks(run, lab_signals=100, career_filtered={"mucon"})}
        self.assertEqual(by_key["pg_sync"].status, "warn")
        self.assertEqual(by_key["pg_unknown_programs"].status, "fail")
        self.assertIn("new_award", by_key["pg_unknown_programs"].value)
        self.assertEqual(by_key["pg_no_artist"].status, "warn")
        self.assertEqual(by_key["pg_career"].status, "fail")

    def test_pg_unavailable_gives_one_skip(self):
        def run(sql):
            raise RuntimeError("connection refused")
        checks = dc.pg_checks(run, lab_signals=100, career_filtered=set())
        self.assertEqual([c.status for c in checks], ["skip"])


class ReportTest(unittest.TestCase):
    def test_render_puts_problems_summary_first(self):
        checks = [dc.Check("a", "검사 가", "기준", "값1", "pass", "고칠 것 없음"),
                  dc.Check("b", "검사 나", "기준", "값2", "fail", "이렇게 고친다"),
                  dc.Check("c", "검사 다", "기준", "값3", "warn", "저렇게 본다")]
        md = dc.render(checks, TODAY, {"generated_at": "2026-11-27T21:40:00+09:00", "data_end": TODAY})
        self.assertIn("실패 1", md)
        self.assertIn("경고 1", md)
        summary = md.index("## 먼저 볼 것")
        self.assertLess(summary, md.index("## 전체 검사"))
        self.assertLess(md.index("검사 나"), md.index("검사 다"))   # 실패가 경고보다 먼저
        self.assertNotIn("/Users/", md)

    def test_render_adds_detail_section(self):
        c = dc.Check("dup", "같은 팀 중복 의심", "기준", "값", "warn", "고침", ("높음 · 표기 흔들림 · a ↔ b",))
        md = dc.render([c], TODAY, {})
        self.assertIn("## 자세히: 같은 팀 중복 의심", md)
        self.assertIn("- 높음 · 표기 흔들림 · a ↔ b", md)

    def test_render_all_pass(self):
        md = dc.render([dc.Check("a", "검사 가", "기준", "값", "pass", "-")], TODAY, {})
        self.assertIn("모든 검사 통과", md)
        self.assertNotIn("## 먼저 볼 것", md)

    def test_summary_line(self):
        checks = [dc.Check("a", "가", "", "", "pass", ""), dc.Check("b", "나", "", "", "warn", "")]
        self.assertEqual(dc.summary_line(checks), "통과 1 · 경고 1 · 실패 0")


class RunAllTest(unittest.TestCase):
    def test_run_all_on_small_lab_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            lab = d / "docs" / "lab" / "data"
            (lab / "snapshots").mkdir(parents=True)
            (d / "docs" / "data").mkdir(parents=True)
            (d / "config").mkdir()
            (lab / "signals.csv").write_text("team_key,branch,source,program,stage_rank,signal_date,venue,role\n"
                                             "a,공연,indistreet,,,2026-11-26,클럽,discovery\n", encoding="utf-8")
            (lab / "teams.csv").write_text("team_key,display_name,first_seen,first_release,fan_count,album_count,"
                                           "profile_status,primary_genre,agency,newcomer_check,genre_confidence\n"
                                           "a,에이,,2024-01-01,,,newcomer,밴드,,verified,profile\n",
                                           encoding="utf-8")
            for name in dx.EXTRAS:      # 앱 보조 데이터 8개
                (lab / name).write_text("{}" if name.endswith(".json") else "team_key\na\n", encoding="utf-8")
            (lab / "venue_profiles.json").write_text(json.dumps({"venues": {"클럽": {"lat": 37.5, "tier": "S"}}}),
                                                     encoding="utf-8")
            (lab / "outcomes.csv").write_text("team_key,program,announced_date,counted,same_house_sources,same_house_scored\n",
                                              encoding="utf-8")
            for name in ("links", "images", "videos", "collabs", "programs"):
                (lab / f"{name}.csv").write_text("team_key,platform,url,source\n", encoding="utf-8")
            (lab / "meta.json").write_text(json.dumps({"generated_at": "2026-11-27T21:40:00+09:00", "data_end": TODAY,
                                                       "rows": {"signals": 1, "teams": 1}, "prev_rows": {},
                                                       "extras": [n.split(".")[0] for n in dx.EXTRAS]}), encoding="utf-8")
            (lab / "snapshots" / "index.json").write_text(json.dumps({"dates": [TODAY]}), encoding="utf-8")
            (lab / "snapshots" / f"{TODAY}.csv").write_text("team_key,score,rank\na,1,1\n", encoding="utf-8")
            (d / "docs" / "data" / "collect.json").write_text(json.dumps({"runs": [
                {"date": TODAY, "source": "indistreet", "table": "raw_kr_gig", "rows": 1}]}), encoding="utf-8")
            (d / "config" / "source_roles.json").write_text(json.dumps({"outcomes": {}}), encoding="utf-8")
            checks = dc.run_all(d, TODAY, run=None)
            keys = [c.key for c in checks]
            self.assertIn("meta_rows", keys)
            self.assertIn("pg", keys)          # DB 없이 돌리면 건너뜀 한 줄
            self.assertFalse([c for c in checks if c.status == "fail"], [(c.key, c.value) for c in checks])


if __name__ == "__main__":
    unittest.main()
