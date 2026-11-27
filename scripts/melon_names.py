"""멜론 프로필 보강 명단 만들기 → data/raw/review/melon_names_<오늘>.txt (한 줄에 팀 이름 하나, 최대 300줄)

    python3 scripts/melon_names.py

매일 21시 실행에서 collect_artists.py --names-file 이 이 명단을 하루 최대 100팀씩 받는다.
프로필(첫 발매일·팬 수)이 없는 팀(profile_status='unknown')을 '중요한 순서'로 줄 세운다:
  ① 최신 점수 스냅샷(docs/lab/data/snapshots/<날짜>.csv) 상위 300팀 — 점수 순
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
OUT_DIR = ROOT / "data" / "raw" / "review"
SNAPSHOT_TOP = 300     # 점수 상위 몇 팀까지 볼지
LIMIT = 300            # 명단 최대 줄 수 (하루 100팀씩 사흘치)
RETRY_DAYS = 30        # 못 찾았던 이름은 30일 뒤 다시 (멜론에 새로 등록됐을 수 있음)
KEEP_FILES = 7         # 명단 파일은 최근 7개만


def _ok_to_try(name: str, matches: dict, attempts: dict, today: str) -> bool:
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


def build_names(snapshot: List[dict], teams: List[dict], outcomes: List[dict], signals: List[dict],
                matches: dict, today: str, attempts: Optional[dict] = None,
                snapshot_top: int = SNAPSHOT_TOP, limit: int = LIMIT) -> List[str]:
    info = {t["team_key"]: t for t in teams}
    attempts = attempts or {}

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
    for key in [*ranked_snapshot(), *winners, *gigs]:
        t = info.get(key)
        name = (t or {}).get("display_name", "").strip()
        if not t or t.get("profile_status") != "unknown" or not name or name in seen:
            continue
        seen.add(name)
        if _ok_to_try(name, matches, attempts, today):
            out.append(name)
        if len(out) >= limit:
            break
    return out


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
    names = build_names(_csv(latest_snapshot()), _csv(LAB / "teams.csv"), _csv(LAB / "outcomes.csv"),
                        _csv(LAB / "signals.csv"), _json(MATCHES), today, _json(ATTEMPTS))
    path = write_names(OUT_DIR, today, names)
    removed = prune_old(OUT_DIR)
    print(f"✅ 멜론 보강 명단 {len(names)}팀 → {path.relative_to(ROOT)}"
          + (f" (오래된 명단 {len(removed)}개 정리)" if removed else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
