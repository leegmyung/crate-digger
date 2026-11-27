"""사운드 지도(씬 관계도) 데이터 → docs/lab/data/scene_map.json (공개: 팀 키·이름·공연장·숫자만)

    python3 scripts/build_scene_map.py

- 연결: 최근 WINDOW_DAYS(1년) 안의 발굴 신호 공연(signals branch='공연', role='discovery')에서 같은 날·같은 공연장에
  함께 선 팀끼리 잇는다. 가중치 = 함께 선 횟수. 출연 팀이 MAX_EVENT_TEAMS 보다 많은 공연(페스티벌)은 모두를 잇게 돼
  지도가 뭉개지므로 뺀다.
- 묶음: 라벨 전파(이웃 중 가중치 합이 가장 큰 라벨을 따름, 동점은 사전순 — 외부 라이브러리 없이, 매번 같은 결과).
  가중치는 함께 선 횟수의 REPEAT_POWER 제곱 — 한 번 같이 선 연결(우연일 수 있음)이 많으면 홍대 전체가 한 묶음이 되므로
  반복해서 같이 서는 관계를 강하게 따르게 한다 (실측: 그대로 926팀짜리 묶음 → 세제곱 442팀, 지도에 들어가는 팀 수는 거의 같음).
  MIN_COMMUNITY 팀 미만 묶음은 버린다.
- 묶음마다: 대표 공연장(묶음 팀들의 공연 수), 상위 후보(최신 점수 스냅샷 순위), 허브 팀(묶음 안 연결 많은 팀).
- 시각화는 앱이 한다. nodes·edges(가중치 MIN_EDGE_WEIGHT 이상)도 함께 넣는다.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
LAB = ROOT / "docs" / "lab" / "data"
OUT = LAB / "scene_map.json"
WINDOW_DAYS = 365          # 최근 1년 — 씬은 빨리 바뀌므로
MAX_EVENT_TEAMS = 12       # 이보다 큰 공연은 페스티벌로 보고 연결에서 뺌 (1년 공연 중 99% 이상이 12팀 이하)
REPEAT_POWER = 3           # 묶음 계산용 가중치 = 횟수³ (반복 공동 출연 우대)
MAX_ITER = 30              # 라벨 전파 반복 상한 (보통 10번 안에 멈춤)
MIN_COMMUNITY = 3          # 3팀 미만 묶음은 씬이라 보기 어려워 버림
MIN_EDGE_WEIGHT = 2        # 내보내는 연결선은 두 번 이상 같이 선 팀끼리만 (한 번은 우연일 수 있음)
TOP_VENUES, TOP_CANDIDATES, TOP_HUBS = 3, 5, 5
SKIP_VENUES = {"", "공연장 미정"}


def build_edges(rows: List[dict], as_of: str) -> Tuple[Dict[Tuple[str, str], int], Dict[Tuple[str, str], set]]:
    """신호 행 → ({(팀A, 팀B): 함께 선 횟수}, {(날짜, 공연장): 팀 집합})."""
    start = (date.fromisoformat(as_of) - timedelta(days=WINDOW_DAYS)).isoformat()
    events: Dict[Tuple[str, str], set] = defaultdict(set)
    for r in rows:
        day, venue = str(r.get("signal_date") or "")[:10], (r.get("venue") or "").strip()
        if (r.get("branch") == "공연" and r.get("role") == "discovery" and venue not in SKIP_VENUES
                and start <= day <= as_of and r.get("team_key")):
            events[(day, venue)].add(r["team_key"])
    edges: Dict[Tuple[str, str], int] = Counter()
    kept = {}
    for key, teams in events.items():
        if len(teams) > MAX_EVENT_TEAMS:
            continue
        kept[key] = teams
        ordered = sorted(teams)
        for i, u in enumerate(ordered):
            for v in ordered[i + 1:]:
                edges[(u, v)] += 1
    return dict(edges), kept


def _adjacency(edges: Dict[Tuple[str, str], int]) -> Dict[str, Dict[str, int]]:
    adj: Dict[str, Dict[str, int]] = defaultdict(dict)
    for (u, v), w in edges.items():
        adj[u][v] = adj[u].get(v, 0) + w
        adj[v][u] = adj[v].get(u, 0) + w
    return adj


def label_propagation(edges: Dict[Tuple[str, str], int]) -> Dict[str, str]:
    """팀 → 묶음 라벨. 사전순으로 돌며 이웃 라벨의 가중치 합이 가장 큰 것을 따름(동점은 사전순으로 앞선 라벨)."""
    adj = _adjacency(edges)
    labels = {n: n for n in adj}
    for _ in range(MAX_ITER):
        changed = False
        for n in sorted(adj):
            score: Dict[str, int] = Counter()
            for m, w in adj[n].items():
                score[labels[m]] += w
            best = min(score, key=lambda lab: (-score[lab], lab))
            if best != labels[n]:
                labels[n], changed = best, True
        if not changed:
            break
    return labels


def build(rows: List[dict], teams: Dict[str, dict], snapshot: Dict[str, Tuple[float, int]], as_of: str) -> dict:
    edges, events = build_edges(rows, as_of)
    labels = label_propagation({k: w ** REPEAT_POWER for k, w in edges.items()})
    adj = _adjacency(edges)
    groups: Dict[str, List[str]] = defaultdict(list)
    for team, lab in labels.items():
        groups[lab].append(team)
    kept = sorted((g for g in groups.values() if len(g) >= MIN_COMMUNITY), key=lambda g: (-len(g), min(g)))
    name = lambda k: (teams.get(k) or {}).get("display_name") or k   # noqa: E731
    communities, community_of = [], {}
    for i, members in enumerate(kept, 1):
        mset = set(members)
        for m in members:
            community_of[m] = i
        venues = Counter(v for (d, v), ts in events.items() if ts & mset)
        cands = sorted((m for m in members if m in snapshot), key=lambda m: snapshot[m][1])[:TOP_CANDIDATES]
        inner = {m: sum(w for n, w in adj[m].items() if n in mset) for m in members}
        hubs = sorted(members, key=lambda m: (-inner[m], m))[:TOP_HUBS]
        communities.append({
            "id": i, "size": len(members),
            "internal_links": sum(1 for (u, v) in edges if u in mset and v in mset),
            "top_venues": [{"venue": v, "events": n} for v, n in sorted(venues.items(), key=lambda x: (-x[1], x[0]))[:TOP_VENUES]],
            "top_candidates": [{"team_key": m, "name": name(m), "rank": snapshot[m][1], "score": snapshot[m][0]} for m in cands],
            "hubs": [{"team_key": m, "name": name(m), "links": inner[m]} for m in hubs],
        })
    nodes = [{"team_key": m, "name": name(m), "community": community_of[m],
              "degree": len(adj[m]), "rank": snapshot[m][1] if m in snapshot else None} for m in sorted(community_of)]
    out_edges = [{"source": u, "target": v, "weight": w} for (u, v), w in sorted(edges.items())
                 if w >= MIN_EDGE_WEIGHT and u in community_of and v in community_of]
    start = (date.fromisoformat(as_of) - timedelta(days=WINDOW_DAYS)).isoformat()
    return {"as_of": as_of, "window": {"from": start, "to": as_of},
            "params": {"max_event_teams": MAX_EVENT_TEAMS, "min_community": MIN_COMMUNITY, "min_edge_weight": MIN_EDGE_WEIGHT},
            "n_events": len(events), "n_teams": len(adj), "n_links": len(edges),
            "communities": communities, "nodes": nodes, "edges": out_edges}


def write_json(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def update_meta(meta_path: Path, data: dict) -> None:
    """meta.json 에 씬 묶음 수를 적는다 (앱 첫 화면 카드용). meta.json 이 없으면 건너뜀."""
    if not meta_path.exists():
        return
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["scene_communities"] = len(data.get("communities") or [])
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def _csv(path: Path) -> List[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> int:
    meta = json.loads((LAB / "meta.json").read_text(encoding="utf-8")) if (LAB / "meta.json").exists() else {}
    as_of = meta.get("data_end") or date.today().isoformat()
    teams = {t["team_key"]: t for t in _csv(LAB / "teams.csv")}
    snaps = sorted((LAB / "snapshots").glob("????-??-??.csv"))
    snapshot = {r["team_key"]: (float(r["score"]), int(r["rank"])) for r in _csv(snaps[-1])} if snaps else {}
    data = build(_csv(LAB / "signals.csv"), teams, snapshot, as_of)
    write_json(OUT, data)
    update_meta(LAB / "meta.json", data)
    sizes = [c["size"] for c in data["communities"]]
    print(f"✅ 사운드 지도 → {OUT.relative_to(ROOT)} (공연 {data['n_events']:,} · 팀 {data['n_teams']:,} · 연결 {data['n_links']:,} · "
          f"씬 묶음 {len(sizes)}개, 큰 순 {sizes[:5]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
