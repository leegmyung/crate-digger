"""사운드 지도(build_scene_map): 같은 무대(날짜·공연장) 공동 출연 연결망 → 라벨 전파로 씬 묶음 → 대표 공연장·상위 후보."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_scene_map as sm  # noqa: E402


def gig(team, day, venue, role="discovery", branch="공연"):
    return {"team_key": team, "branch": branch, "signal_date": day, "venue": venue, "role": role}


class EdgeTest(unittest.TestCase):
    def test_same_day_same_venue_pairs_with_weights(self):
        rows = [gig("a", "2026-05-01", "클럽1"), gig("b", "2026-05-01", "클럽1"), gig("c", "2026-05-01", "클럽1"),
                gig("a", "2026-06-01", "클럽1"), gig("b", "2026-06-01", "클럽1"),
                gig("a", "2026-06-01", "클럽2")]                       # 같은 날 다른 공연장 → 안 이음
        edges, events = sm.build_edges(rows, "2026-11-27")
        self.assertEqual(edges[("a", "b")], 2)
        self.assertEqual(edges[("a", "c")], 1)
        self.assertNotIn(("a", "a"), edges)
        self.assertEqual(len(events), 3)

    def test_filters_window_role_branch_venue_and_big_events(self):
        big = [gig(f"t{i}", "2026-07-01", "페스티벌") for i in range(sm.MAX_EVENT_TEAMS + 1)]
        rows = big + [
            gig("a", "2025-01-01", "클럽1"), gig("b", "2025-01-01", "클럽1"),            # 1년 밖
            gig("a", "2026-05-01", "클럽1", role="pending"), gig("b", "2026-05-01", "클럽1"),   # 발굴 신호 아님
            gig("a", "2026-05-02", ""), gig("b", "2026-05-02", ""),                      # 공연장 없음
            gig("a", "2026-05-03", "공연장 미정"), gig("b", "2026-05-03", "공연장 미정"),
            gig("a", "2026-05-04", "클럽1", branch="큐레이션"), gig("b", "2026-05-04", "클럽1"),
            gig("a", "2026-12-01", "클럽1"), gig("b", "2026-12-01", "클럽1"),            # 기준일 뒤 (예정 공연)
        ]
        edges, _ = sm.build_edges(rows, "2026-11-27")
        self.assertEqual(edges, {})


class CommunityTest(unittest.TestCase):
    def test_two_dense_groups_joined_by_weak_link(self):
        edges = {}
        for grp in (("a", "b", "c", "d"), ("w", "x", "y", "z")):
            for i, u in enumerate(grp):
                for v in grp[i + 1:]:
                    edges[(u, v)] = 3
        edges[("d", "w")] = 1
        labels = sm.label_propagation(edges)
        self.assertEqual(len({labels[t] for t in "abcd"}), 1)
        self.assertEqual(len({labels[t] for t in "wxyz"}), 1)
        self.assertNotEqual(labels["a"], labels["z"])
        self.assertEqual(labels, sm.label_propagation(dict(reversed(list(edges.items())))))   # 순서와 무관 (결정적)


class SummaryTest(unittest.TestCase):
    def test_communities_with_venues_candidates_and_hubs(self):
        rows = []
        for day in ("2026-05-01", "2026-06-01", "2026-07-01"):
            rows += [gig(t, day, "클럽1") for t in ("a", "b", "c")]
        rows += [gig(t, "2026-08-01", "클럽2") for t in ("a", "b")]
        rows += [gig(t, "2026-05-05", "홀") for t in ("x", "y")]       # 2팀짜리 → 최소 크기 미만
        teams = {k: {"display_name": k.upper()} for k in "abcxy"}
        snapshot = {"b": (5.0, 3), "c": (2.0, 10)}
        out = sm.build(rows, teams, snapshot, "2026-11-27")
        self.assertEqual(len(out["communities"]), 1)
        com = out["communities"][0]
        self.assertEqual(com["size"], 3)
        self.assertEqual(com["top_venues"][0], {"venue": "클럽1", "events": 3})
        self.assertEqual([c["team_key"] for c in com["top_candidates"]], ["b", "c"])
        self.assertEqual(com["top_candidates"][0]["rank"], 3)
        self.assertEqual(com["hubs"][0]["name"] in ("A", "B"), True)
        self.assertEqual(out["window"], {"from": "2025-11-27", "to": "2026-11-27"})
        self.assertEqual(out["n_teams"], 5)
        self.assertIn("community", out["nodes"][0])
        self.assertTrue(all(e["weight"] >= sm.MIN_EDGE_WEIGHT for e in out["edges"]))

    def test_meta_gets_scene_community_count(self):
        # 앱 첫 화면 씬 카드가 scene_map.json 을 안 내려받고도 묶음 수를 보이게
        import json
        with tempfile.TemporaryDirectory() as d:
            meta = Path(d) / "meta.json"
            meta.write_text(json.dumps({"data_end": "2026-11-27"}), encoding="utf-8")
            sm.update_meta(meta, {"communities": [{"size": 3}, {"size": 2}]})
            got = json.loads(meta.read_text(encoding="utf-8"))
        self.assertEqual(got, {"data_end": "2026-11-27", "scene_communities": 2})

    def test_write_json(self):
        with tempfile.TemporaryDirectory() as d:
            p = sm.write_json(Path(d) / "scene_map.json", {"communities": []})
            self.assertEqual(json.loads(p.read_text(encoding="utf-8")), {"communities": []})


if __name__ == "__main__":
    unittest.main()
