"""멜론 프로필 '고른 큐' 만들기 → data/raw/state/profile_queue.txt (한 줄에 팀 이름 하나)

    .venv/bin/python scripts/profile_queue.py            # 큐 다시 만들기 + 진행 숫자
    .venv/bin/python scripts/profile_queue.py --dry-run  # 숫자만

왜: 신인 판정(멜론 프로필 첫 발매일)을 정답 팀·상위 후보 위주로 받아서 과거 성적이 부풀었다
(docs/score_leak_audit_2026-11-28.md, 0.827 vs 같은 기준 0.788). 정답 여부와 상관없이 후보 풀 전체에 프로필을 받는다.

- 대상(후보 풀): 과거 기준일 6개(score_tune.CUTOFFS) + 오늘 기준일에 신호 기간(3년) 안 신호가 있는 팀
  (score_tune.features 와 같은 조건이되 **신인 판정은 빼고** — 프로필은 팀을 풀에서 빼기도 하지만, 첫 발매일이
  우리 첫 등장보다 늦으면 넣기도 한다: 과거 풀 46행·정답 7행이 이렇게 들어옴) 중 프로필 없는 팀(profile_status='unknown').
- 순서: 팀 키의 SHA-1 해시 순. **정답·점수·순위를 보지 않는다** — 그래서 큐를 어디까지 받았든 받은 팀은
  풀에서 고르게 뽑은 표본이고, 중간에 score_leak_audit 를 다시 돌려도 한쪽으로 기울지 않는다.
- 빼는 팀: 이미 프로필을 받은 팀(멜론 번호가 artist_profile_seen.json 에 있음 — teams.csv 가 아직 안 바뀌었어도),
  못 찾아서 재검색 기간(멜론 결과 0건 7일 · 이름 불일치 30일, melon_names.due_for_search)이 안 지난 팀.
  번호는 찾았는데 프로필을 아직 못 받은 팀은 넣는다(수집기가 검색 없이 바로 받음).
- 받기: collect_artists.py --names-file data/raw/state/profile_queue.txt --limit 250 (하루 250 이름 검색).
  2026-11-28 첫 회차: 검색 약 300번째에서 멜론 검색 페이지가 '페이지를 찾을 수 없습니다'로 막힘(차트·프로필은 정상) →
  매일 명단(melon_names.py) 검색과 합쳐 하루 300 안쪽으로. 막히면 검색 실패로 남아(시도로 안 침) 다음 날 다시 한다.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from melon_names import ATTEMPTS, MATCHES, MISSES, PROFILE_SEEN, due_for_search  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TEAMS_CSV = ROOT / "docs" / "lab" / "data" / "teams.csv"
QUEUE = ROOT / "data" / "raw" / "state" / "profile_queue.txt"
NO_PROFILE = "unknown"
ANY_NEWCOMER = "2099-12-31"   # 풀 계산용: 이 날짜를 첫 발매일로 두면 신인 조건(첫 발매 >= 기준일 - 3년)을 모두 통과


def hash_order(keys: Iterable[str]) -> List[str]:
    """팀 키 SHA-1 해시 순 (입력 순서·정답·점수와 무관하고, 날마다 같은 순서)."""
    return sorted(set(keys), key=lambda k: (hashlib.sha1(k.encode("utf-8")).hexdigest(), k))


def build_queue(pool: Iterable[str], teams: Mapping[str, Mapping], matches: Mapping, attempts: Mapping,
                misses: Mapping, profiled: Set[str], today: str) -> Tuple[List[str], Dict[str, int]]:
    """후보 풀 팀 키 → (받을 이름 목록, 숫자). 정답 정보는 받지 않는다."""
    profiled = {str(p) for p in profiled}
    keys = hash_order(pool)
    stats = {"pool": len(keys), "has_profile": 0, "no_name": 0, "miss_waiting": 0, "fetch_only": 0, "duplicate": 0}
    names: List[str] = []
    seen: Set[str] = set()
    for key in keys:
        team = teams.get(key) or {}
        name = (team.get("display_name") or "").strip()
        if not name:
            stats["no_name"] += 1
            continue
        match = matches.get(name)
        has_id = isinstance(match, dict) and bool(match.get("id"))
        if team.get("profile_status", NO_PROFILE) != NO_PROFILE or (has_id and str(match["id"]) in profiled):
            stats["has_profile"] += 1
            continue
        if name in seen:
            stats["duplicate"] += 1
            continue
        seen.add(name)
        if has_id:
            stats["fetch_only"] += 1
        elif not due_for_search(name, matches, attempts, today, misses):
            stats["miss_waiting"] += 1
            continue
        names.append(name)
    stats["queued"] = len(names)
    return names, stats


def progress(pool: Iterable[str], teams: Mapping[str, Mapping]) -> Dict[str, object]:
    """풀 중 프로필이 있는 팀 비율 (teams.csv 기준)."""
    keys = set(pool)
    done = sum(1 for k in keys if (teams.get(k) or {}).get("profile_status", NO_PROFILE) != NO_PROFILE)
    return {"pool": len(keys), "profiled": done, "share": round(done / len(keys), 3) if keys else 0.0}


def write_queue(path: Path, names: List[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{n}\n" for n in names), encoding="utf-8")
    return path


# ---------- 읽기 (DuckDB 랩 연결 필요: .venv/bin/python) ----------

def pool_keys(today: str) -> Dict[str, Set[str]]:
    """{기준일: 후보 팀 키} — 과거 기준일 6개 + 오늘. score_tune.features 와 같은 풀에서 신인 판정만 끈 것
    (메모리 연결에서 first_release 를 먼 미래로 → 모두 신인 조건 통과). 점수·정답 열은 안 쓴다."""
    import lab_sql
    import score_tune as st
    con = lab_sql.connect()
    con.execute(f"UPDATE teams SET first_release = DATE '{ANY_NEWCOMER}'")
    return {c: {r["team_key"] for r in st.features(con, c)} for c in [*st.CUTOFFS, today]}


def _json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _teams() -> Dict[str, dict]:
    with open(TEAMS_CSV, encoding="utf-8") as fh:
        return {r["team_key"]: r for r in csv.DictReader(fh)}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="멜론 프로필 고른 큐 (정답 여부를 보지 않는 순서)")
    ap.add_argument("--dry-run", action="store_true", help="파일은 안 쓰고 숫자만")
    ap.add_argument("--today", default=date.today().isoformat())
    args = ap.parse_args(argv)
    try:
        pools = pool_keys(args.today)
    except Exception as e:   # noqa: BLE001 — DuckDB·랩 데이터 문제를 한 줄로 알리고 실패 코드
        print(f"⚠️ 후보 풀 읽기 실패: {e}")
        return 1
    teams = _teams()
    pool = set().union(*pools.values())
    names, stats = build_queue(pool, teams, _json(MATCHES, {}), _json(ATTEMPTS, {}), _json(MISSES, {}),
                               set(_json(PROFILE_SEEN, [])), args.today)
    past = set().union(*(v for c, v in pools.items() if c != args.today))
    print(f"후보 풀 {stats['pool']}팀 (과거 기준일 {len(past)} · 오늘 {len(pools[args.today])}) · "
          f"프로필 있음 {stats['has_profile']} · 이름 없음 {stats['no_name']} · 같은 이름 {stats['duplicate']} · "
          f"재검색 대기 {stats['miss_waiting']} · 번호만 있음 {stats['fetch_only']} → 큐 {stats['queued']}팀")
    for label, keys in (("과거 기준일 풀", past), ("오늘 후보", pools[args.today])):
        p = progress(keys, teams)
        print(f"  {label}: 프로필 있음 {p['profiled']}/{p['pool']} ({p['share']:.1%})")
    if not args.dry_run:
        print(f"✅ 큐 → {write_queue(QUEUE, names).relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
