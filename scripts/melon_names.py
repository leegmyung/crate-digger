"""멜론 프로필 보강 명단 만들기 → data/raw/review/melon_names_<오늘>.txt (한 줄에 팀 이름 하나, 최대 1,000줄)

    python3 scripts/melon_names.py

매일 21시 실행에서 collect_artists.py --names-file 이 이 명단을 하루 한도 없이 명단 전체를 받는다.
프로필(첫 발매일·팬 수)이 없는 팀(profile_status='unknown')을 '중요한 순서'로 줄 세운다:
  ⓪ 최신 후보 점검(data/raw/review/candidate_audit_<날짜>.csv)의 (b) '기성인데 프로필이 없어 신인으로 잡힘' 팀 — 순위 순.
     멜론 번호는 찾았지만 프로필을 아직 못 받은 팀도 넣는다 (수집기가 명단 순서대로 프로필을 먼저 받음)
  ① 최신 점수 스냅샷(docs/lab/data/snapshots/<날짜>.csv) 상위 300팀 — 점수 순
  ①' 발매 신호만 있고 첫 발매일이 없는 팀 중 최근 RELEASE_DAYS일 안에 발매한 팀 — 최근 발매 순
     (프로필로 첫 발매일이 생기면 '갓 데뷔 > 아직 언급 없음' 팀이 보이기 시작함, docs/debut_cohort.md)
  ② 센 정답(counted)을 받은 팀 — 정답 팀의 연차를 알아야 신인 기준을 검증할 수 있음
  ③ 다가오는 공연(오늘 이후)이 있는 팀 — 공연 날짜가 가까운 순
이미 찾아본 이름(data/raw/state/outcome_melon_match.json)은 뺀다. 못 찾았던 이름(값 null)은 마지막 시도가
RETRY_DAYS 일 지났을 때만 다시 넣는다(시도 날짜를 모르면 뺀다 — 날짜 기록: melon_match_attempts.json, 있으면 사용).
오래된 명단 파일은 최근 KEEP_FILES 개만 남긴다.
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
LAB = ROOT / "docs" / "lab" / "data"
SNAPSHOT_DIR = LAB / "snapshots"
MATCHES = ROOT / "data" / "raw" / "state" / "outcome_melon_match.json"
ATTEMPTS = ROOT / "data" / "raw" / "state" / "melon_match_attempts.json"   # {이름: 마지막 시도 날짜} (있을 때만)
PROFILE_SEEN = ROOT / "data" / "raw" / "state" / "artist_profile_seen.json"   # 이미 받은 멜론 프로필 번호 목록
OUT_DIR = ROOT / "data" / "raw" / "review"
SNAPSHOT_TOP = 300     # 점수 상위 몇 팀까지 볼지
LIMIT = 1000           # 명단 최대 줄 수 (하루 한도 없이 한 번에 받음)
RETRY_DAYS = 30        # 못 찾았던 이름은 30일 뒤 다시 (멜론에 새로 등록됐을 수 있음)
KEEP_FILES = 7         # 명단 파일은 최근 7개만
RELEASE_DAYS = 90      # '발매 신호만 있는 팀'은 최근 90일 안 발매만 (갓 데뷔 후보가 될 만한 팀)


def due_for_search(name: str, matches: dict, attempts: dict, today: str) -> bool:
    """멜론에서 (다시) 찾아볼 이름인가: 처음 보는 이름, 또는 못 찾았고(null) 마지막 시도가 RETRY_DAYS 지난 이름.
    collect_artists.py 도 이 함수로 검색할 이름을 고른다 (명단과 수집기가 같은 규칙)."""
    if name not in matches:
        return True
    if matches[name] is not None:          # 이미 찾음
        return False
    tried = attempts.get(name)
    if not tried:                          # 못 찾았는데 언제 시도했는지 모름 → 빼기
        return False
    try:
        return date.fromisoformat(today) - date.fromisoformat(str(tried)[:10]) >= timedelta(days=RETRY_DAYS)
    except ValueError:
        return False


def release_only_recent(signals: List[dict], teams: List[dict], today: str, days: int = RELEASE_DAYS) -> List[str]:
    """발매 갈래 신호만 있고(남의 언급 없음) 첫 발매일이 없는 팀 중, 마지막 발매가 최근 days일 안인 팀 — 최근 발매 순."""
    no_release_date = {t["team_key"] for t in teams if not (t.get("first_release") or "").strip()}
    last: Dict[str, str] = {}
    other = set()
    for s in signals:
        k = s["team_key"]
        if s.get("branch") != "발매":
            other.add(k)
            continue
        last[k] = max(last.get(k, ""), s.get("signal_date") or "")
    since = (date.fromisoformat(today) - timedelta(days=days)).isoformat()
    keys = [k for k, d in last.items() if k not in other and k in no_release_date and since <= d <= today]
    return sorted(keys, key=lambda k: (last[k], k), reverse=True)


def build_names(snapshot: List[dict], teams: List[dict], outcomes: List[dict], signals: List[dict],
                matches: dict, today: str, attempts: Optional[dict] = None,
                snapshot_top: int = SNAPSHOT_TOP, limit: int = LIMIT,
                priority: Optional[List[str]] = None, profiled: Optional[set] = None) -> List[str]:
    info = {t["team_key"]: t for t in teams}
    attempts = attempts or {}
    priority = list(priority or [])
    profiled = {str(p) for p in (profiled or ())}

    def wanted(key: str, name: str) -> bool:
        if due_for_search(name, matches, attempts, today):
            return True
        m = matches.get(name)                # 0순위 팀: 번호는 있는데 프로필을 아직 못 받았으면 넣기
        return key in priority and isinstance(m, dict) and str(m.get("id", "")) not in profiled

    def ranked_snapshot() -> List[str]:
        rows = sorted(snapshot, key=lambda r: -float(r.get("score") or 0))[:snapshot_top]
        return [r["team_key"] for r in rows]

    winners = [o["team_key"] for o in outcomes if str(o.get("counted", "")).lower() == "true"]
    upcoming: Dict[str, str] = {}
    for s in signals:
        if s.get("branch") == "공연" and (s.get("signal_date") or "") >= today:
            k = s["team_key"]
            upcoming[k] = min(upcoming.get(k, s["signal_date"]), s["signal_date"])
    gigs = sorted(upcoming, key=lambda k: (upcoming[k], k))

    out: List[str] = []
    seen = set()
    for key in [*priority, *ranked_snapshot(), *release_only_recent(signals, teams, today), *winners, *gigs]:
        t = info.get(key)
        name = (t or {}).get("display_name", "").strip()
        if not t or t.get("profile_status") != "unknown" or not name or name in seen:
            continue
        seen.add(name)
        if wanted(key, name):
            out.append(name)
        if len(out) >= limit:
            break
    return out


def audit_priority(rows: List[dict]) -> List[str]:
    """후보 점검 결과에서 (b) 팀 키를 순위 순으로."""
    b = [r for r in rows if r.get("type") == "b" and str(r.get("rank", "")).isdigit()]
    return [r["team_key"] for r in sorted(b, key=lambda r: int(r["rank"]))]


def latest_audit(folder: Path = OUT_DIR) -> Optional[Path]:
    files = sorted(folder.glob("candidate_audit_????-??-??.csv")) if folder.is_dir() else []
    return files[-1] if files else None


def latest_snapshot(folder: Path = SNAPSHOT_DIR) -> Optional[Path]:
    files = sorted(p for p in folder.glob("????-??-??.csv")) if folder.is_dir() else []
    return files[-1] if files else None


def write_names(folder: Path, day: str, names: List[str]) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"melon_names_{day}.txt"
    path.write_text("".join(f"{n}\n" for n in names), encoding="utf-8")
    return path


def prune_old(folder: Path, keep: int = KEEP_FILES) -> List[Path]:
    files = sorted(folder.glob("melon_names_*.txt"))
    old = files[:-keep] if len(files) > keep else []
    for p in old:
        p.unlink()
    return old


def _csv(path: Optional[Path]) -> List[dict]:
    if not path or not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def main() -> int:
    today = date.today().isoformat()
    audit = latest_audit()
    priority = audit_priority(_csv(audit))
    try:
        profiled = set(json.loads(PROFILE_SEEN.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        profiled = set()
    names = build_names(_csv(latest_snapshot()), _csv(LAB / "teams.csv"), _csv(LAB / "outcomes.csv"),
                        _csv(LAB / "signals.csv"), _json(MATCHES), today, _json(ATTEMPTS),
                        priority=priority, profiled=profiled)
    path = write_names(OUT_DIR, today, names)
    removed = prune_old(OUT_DIR)
    print(f"✅ 멜론 보강 명단 {len(names)}팀 → {path.relative_to(ROOT)}"
          + (f" · 0순위(후보 점검 b) {len(priority)}팀 ← {audit.name}" if audit else "")
          + (f" (오래된 명단 {len(removed)}개 정리)" if removed else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
