"""지방 공연장·지역 페스티벌 공연 기록 점검 — 서울 밖 공연장마다 최근 2년 공연 수·출연 팀 수.

    python3 scripts/collect_regional_audit.py                       # 표 출력 (최근 2년)
    python3 scripts/collect_regional_audit.py --json OUT.json       # 위 + JSON 저장 (전후 비교용)
    python3 scripts/collect_regional_audit.py --exclude regional    # 이름에 'regional' 이 든 원본을 빼고 셈 (= 보강 전)

왜: 지방 공연장은 인디스트릿·인디고에 올라오는 공연만 잡혀서 비어 보인다 (예: 세종 누리락 2건뿐).
어디가 비었는지 숫자로 보고, 지역 출처(scripts/collect_regional_gigs.py)로 채운 뒤 전후를 비교한다.

읽는 것: data/raw/raw_kr_gig_*.csv(공연 원본), raw_press_*.csv 의 공연장 인스타 라인업 글(venue_lineup), data/raw/state/venue_xref.json(공연장 표기 → 대표 이름),
config/venues_kr.json(공연장 마스터: 도시·종류·상태).
셈법: 공연 1건 = 같은 공연장·같은 날·같은 제목. 출연 팀 = normalize.artist_key 로 묶은 이름.
공연장 짝 맞추기는 scripts/venues_kr.py 의 match_our_venues 와 같다.
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

import venue_xref as vx
import venues_kr as vk
from normalize import artist_key

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
WINDOW_DAYS = 730          # 최근 2년
THIN_GIGS = 5              # 이보다 적으면 '기록 적음'
CLOSED = ("closed", "paused")


def press_lineup_row(r: dict) -> dict | None:
    """공연장 인스타 라인업 글(raw_press, pick_label=venue_lineup) → 공연 행 모양 (공연장 = 계정, 날짜 = 글 날짜)."""
    if r.get("pick_label") != "venue_lineup":
        return None
    return {"venue_text": r.get("outlet", ""), "gig_date": r.get("published_at", ""),
            "artist_text": r.get("artist_text", ""), "title": r.get("url", ""), "gig_url": r.get("url", "")}


def load_gig_rows(raw_dir: Path = RAW_DIR, exclude: str = "") -> List[dict]:
    """공연 원본 + 공연장 인스타 라인업 글 (venue_xref.collect_counts 와 같은 범위)."""
    rows: List[dict] = []
    for path in sorted(glob.glob(str(raw_dir / "raw_kr_gig_*.csv"))):
        if exclude and exclude in Path(path).name:
            continue
        with open(path, encoding="utf-8", newline="") as f:
            rows.extend(csv.DictReader(f))
    for path in sorted(glob.glob(str(raw_dir / "raw_press_*.csv"))):
        with open(path, encoding="utf-8", newline="") as f:
            rows.extend(g for g in map(press_lineup_row, csv.DictReader(f)) if g)
    return rows


def venue_stats(rows: Iterable[dict], xref: Dict[str, str], since: date) -> Dict[str, dict]:
    """{대표 공연장 이름: {gigs, teams, last, team_keys}} — since 이후 공연만."""
    gigs: Dict[str, set] = defaultdict(set)
    teams: Dict[str, set] = defaultdict(set)
    floor = since.isoformat()
    for r in rows:
        day = (r.get("gig_date") or "")[:10]
        if day < floor:
            continue
        detail = vx.gig_detail(r.get("venue_text", ""))
        if not detail:
            continue
        name = xref.get(detail, detail)
        gigs[name].add((day, (r.get("title") or "").strip()))
        key = artist_key(r.get("artist_text", "") or "")
        if key:
            teams[name].add(key)
    return {v: {"gigs": len(g), "teams": len(teams[v]), "last": max(d for d, _ in g), "team_keys": teams[v]}
            for v, g in gigs.items()}


def regional_table(master: Sequence[dict], stats: Dict[str, dict]) -> List[dict]:
    """서울 밖·운영 중(또는 확인 필요) 마스터 공연장마다 우리 기록 (공연 수 많은 순)."""
    match = vk.match_our_venues(master, stats)
    by_entry: Dict[int, List[str]] = defaultdict(list)
    for name, i in match.items():
        by_entry[i].append(name)
    out = []
    for i, e in enumerate(master):
        if e.get("city") in ("", None, vk.SEOUL) or e.get("status") in CLOSED:
            continue
        mine = [stats[n] for n in by_entry.get(i, [])]
        keys = set().union(*(m.get("team_keys", set()) for m in mine)) if mine else set()
        out.append({
            "name": e["name"], "city": e.get("city", ""), "province": e.get("province", ""),
            "type": e.get("type", ""), "gigs": sum(m["gigs"] for m in mine),
            "teams": len(keys) if keys else sum(m["teams"] for m in mine),
            "last": max((m["last"] for m in mine), default=""), "team_keys": keys,
        })
    return sorted(out, key=lambda r: (-r["gigs"], r["city"], r["name"]))


def city_summary(table: Iterable[dict]) -> List[dict]:
    """도시별 공연장 수·기록 없는 곳·공연 수·출연 팀 수(공연장마다 팀 이름이 있으면 겹침 없이)."""
    agg: Dict[str, dict] = defaultdict(lambda: {"venues": 0, "empty": 0, "gigs": 0, "teams_sum": 0, "keys": set()})
    for r in table:
        a = agg[r["city"]]
        a["venues"] += 1
        a["empty"] += 0 if r["gigs"] else 1
        a["gigs"] += r["gigs"]
        a["teams_sum"] += r["teams"]
        a["keys"] |= r.get("team_keys") or set()
    rows = [{"city": c, "venues": a["venues"], "empty": a["empty"], "gigs": a["gigs"],
             "teams": len(a["keys"]) if a["keys"] else a["teams_sum"]} for c, a in agg.items()]
    return sorted(rows, key=lambda r: (-r["gigs"], r["city"]))


def audit(raw_dir: Path = RAW_DIR, exclude: str = "", as_of: date | None = None) -> dict:
    as_of = as_of or date.today()
    since = as_of - timedelta(days=WINDOW_DAYS)
    master = (vk.load_json(vk.CONFIG, {}) or {}).get("venues", [])
    xref = vk.load_json(vx.XREF_PATH, {}) or {}
    table = regional_table(master, venue_stats(load_gig_rows(raw_dir, exclude), xref, since))
    return {"as_of": as_of.isoformat(), "since": since.isoformat(), "exclude": exclude,
            "venues": [{k: v for k, v in r.items() if k != "team_keys"} for r in table],
            "cities": city_summary(table)}


def render(result: dict) -> str:
    lines = [f"지방 공연장 점검 ({result['since']} ~ {result['as_of']}, 제외: {result['exclude'] or '없음'})", "",
             "도시 | 공연장 | 기록 없음 | 공연 수 | 출연 팀"]
    lines += [f"{c['city']} | {c['venues']} | {c['empty']} | {c['gigs']} | {c['teams']}" for c in result["cities"]]
    thin = [v for v in result["venues"] if v["gigs"] < THIN_GIGS]
    lines += ["", f"기록 적음(공연 {THIN_GIGS}건 미만) {len(thin)}곳:"]
    lines += [f"  {v['city']} {v['name']} ({v['type'] or '미정'}): 공연 {v['gigs']} · 팀 {v['teams']}" for v in thin]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="지방 공연장별 최근 2년 공연 수·출연 팀 수")
    ap.add_argument("--exclude", default="", help="파일 이름에 이 글자가 든 공연 원본은 빼고 셈")
    ap.add_argument("--as-of", default=date.today().isoformat())
    ap.add_argument("--json", type=Path, help="결과 JSON 저장 경로")
    args = ap.parse_args()
    result = audit(exclude=args.exclude, as_of=date.fromisoformat(args.as_of))
    if args.json:
        args.json.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(render(result))


if __name__ == "__main__":
    main()
