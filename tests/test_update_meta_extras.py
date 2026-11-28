"""update_meta_extras: meta.json 에 앱 보조 데이터 파일 목록(extras)·행 수(extras_rows)를 적는다 — 다른 칸은 그대로."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import update_meta_extras as um  # noqa: E402

META = {"prev_rows": {"signals": 1}, "generated_at": "2026-11-27T19:13:16+09:00", "data_end": "2026-11-27",
        "rows": {"signals": 10, "teams": 5}, "scene_communities": 3}


def _setup(d: Path) -> Path:
    (d / "meta.json").write_text(json.dumps(META, ensure_ascii=False, indent=2), encoding="utf-8")
    (d / "team_cities.csv").write_text("team_key,home_city\na,서울\nb,부산\n", encoding="utf-8")
    (d / "lineup_roles.csv").write_text("team_key,role\n", encoding="utf-8")            # 머리말만 → 0행
    (d / "venue_profiles.json").write_text('{"venues": {}}', encoding="utf-8")
    (d / "city_profiles.json").write_text("{깨진", encoding="utf-8")                     # 잘못된 JSON → 빼기
    return d / "meta.json"


class ScanTest(unittest.TestCase):
    def test_counts_rows_and_json(self):
        with tempfile.TemporaryDirectory() as d:
            _setup(Path(d))
            got = um.scan(Path(d))
        self.assertEqual(got["team_cities.csv"], 2)
        self.assertEqual(got["lineup_roles.csv"], 0)
        self.assertIs(got["venue_profiles.json"], True)
        self.assertNotIn("city_profiles.json", got)          # 깨진 JSON
        self.assertNotIn("event_stars.csv", got)             # 없는 파일

    def test_players_listed_when_present(self):
        """바로 듣기 표(players.csv)도 보조 파일 — 행이 있으면 앱이 받고, 없으면 404 를 내지 않게 목록에서 빠진다."""
        self.assertIn("players.csv", um.EXTRAS)
        with tempfile.TemporaryDirectory() as d:
            _setup(Path(d))
            (Path(d) / "players.csv").write_text("team_key,kind,id,title,source\na,youtube,abcdefghijk,t,s\n",
                                                 encoding="utf-8")
            got = um.scan(Path(d))
        self.assertEqual(got["players.csv"], 1)
        self.assertIn("players", um.app_list(got))

    def test_quoted_newlines_not_counted_as_rows(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "event_stars.csv").write_text('a,b\n1,"두\n줄"\n2,x\n', encoding="utf-8")
            self.assertEqual(um.scan(Path(d))["event_stars.csv"], 2)


class UpdateTest(unittest.TestCase):
    def test_writes_extras_and_keeps_other_fields(self):
        with tempfile.TemporaryDirectory() as d:
            meta_path = _setup(Path(d))
            um.update(meta_path, um.scan(Path(d)), now="2026-11-28T00:10:00+09:00")
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        self.assertEqual(meta["generated_at"], META["generated_at"])        # 캐시 키 — 건드리지 않음
        self.assertEqual(meta["rows"], META["rows"])
        self.assertEqual(meta["prev_rows"], META["prev_rows"])
        self.assertEqual(meta["scene_communities"], 3)
        self.assertEqual(list(meta)[:5], list(META))                         # 원래 칸 순서 유지
        self.assertEqual(meta["extras"], ["team_cities", "venue_profiles"])  # 앱이 읽는 배열(0행·깨진 파일 빼고)
        self.assertEqual(meta["extras_rows"], {"lineup_roles.csv": 0, "team_cities.csv": 2,
                                               "venue_profiles.json": True})
        self.assertEqual(meta["extras_updated_at"], "2026-11-28T00:10:00+09:00")

    def test_app_rule_matches(self):
        """앱 docs/app/db.js labExtraListed: extras.includes(name) || extras.includes(`${name}.csv`)."""
        listed = um.app_list({"team_cities.csv": 3, "venue_profiles.json": True, "event_stars.csv": 0})
        self.assertIn("team_cities", listed)
        self.assertIn("venue_profiles", listed)
        self.assertNotIn("event_stars", listed)

    def test_rerun_replaces_old_extras(self):
        with tempfile.TemporaryDirectory() as d:
            meta_path = _setup(Path(d))
            um.update(meta_path, {"old.csv": 5}, now="t1")
            um.update(meta_path, {"team_cities.csv": 2}, now="t2")
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        self.assertEqual(meta["extras"], ["team_cities"])
        self.assertEqual(meta["extras_rows"], {"team_cities.csv": 2})

    def test_missing_meta_is_error_and_not_created(self):
        with tempfile.TemporaryDirectory() as d:
            rc = um.main(["--data-dir", d])
            self.assertEqual(rc, 1)
            self.assertFalse((Path(d) / "meta.json").exists())

    def test_main_runs(self):
        with tempfile.TemporaryDirectory() as d:
            _setup(Path(d))
            self.assertEqual(um.main(["--data-dir", d]), 0)
            meta = json.loads((Path(d) / "meta.json").read_text(encoding="utf-8"))
            self.assertIn("team_cities", meta["extras"])


if __name__ == "__main__":
    unittest.main()
