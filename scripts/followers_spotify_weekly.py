"""관찰 팀 스포티파이 팔로워 주 1회 → data/raw/state/followers_spotify.jsonl (팀·날짜·값 한 줄씩, 비공개)

    .venv/bin/python scripts/followers_spotify_weekly.py          # daily_run.sh 월요일 블록 (6일 안에 돌았으면 건너뜀)
    .venv/bin/python scripts/followers_spotify_weekly.py --force  # 주기 무시

- 대상: data/raw/state/followers_watch.json (scripts/followers_watch.py, 상위 300 + 관심 팀) 중 docs/lab/data/links.csv 에
  스포티파이 아티스트 주소가 있는 팀. /v1/artists?ids= 로 50팀씩 → 300팀이면 요청 6번/주.
- 하루 요청 예산·429 뒤 쉬기는 scripts/spotify_budget.py 를 공유한다. 한도·429 로 멈추면 이번 주는 거기까지(다음 주에 다시) —
  우회하지 않는다(약관).
- 2026 개발자 모드에서는 followers 가 비어 올 수 있다 → 그 팀은 기록하지 않고 '비어 옴' 수만 남긴다(상태 파일 empty_last).
- 같은 jsonl 을 collect_spotify(검색 응답에 팔로워가 있을 때)도 쓴다. 30일 변화는 scripts/followers.py (docs/followers_plan.md).
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_spotify as cs  # noqa: E402

STATE_DIR = cs.RAW_DIR / "state"
WATCH = STATE_DIR / "followers_watch.json"
LOG = STATE_DIR / cs.FOLLOWERS_LOG
STATE = STATE_DIR / "followers_spotify_weekly.json"
LINKS = cs.ROOT / "docs" / "lab" / "data" / "links.csv"
BATCH = 50
MIN_GAP_DAYS = 6
SPOTIFY_ARTIST = re.compile(r"^https://open\.spotify\.com/artist/([A-Za-z0-9]{22})")


def spotify_ids(teams: Sequence[Mapping], links: Mapping[str, Mapping[str, str]]) -> List[Tuple[str, str]]:
    """관찰 팀 → (팀 키, 스포티파이 번호). 주소가 아티스트 주소가 아니면 뺀다. 같은 번호는 한 번."""
    out, seen = [], set()
    for t in teams:
        m = SPOTIFY_ARTIST.match(links.get(t["team_key"], {}).get("spotify", ""))
        if m and m.group(1) not in seen:
            seen.add(m.group(1))
            out.append((t["team_key"], m.group(1)))
    return out


def batches(items: Sequence, n: int = BATCH) -> List[list]:
    return [list(items[i:i + n]) for i in range(0, len(items), n)]


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def run_weekly(client, pairs: Sequence[Tuple[str, str]], day: str, log_path: Path = LOG,
               state_path: Path = STATE, force: bool = False) -> dict:
    """50팀씩 받아 팔로워가 있는 팀만 jsonl 에 덧붙인다. 멈춰도(429·예산) 받은 데까지 남기고 이번 주는 끝으로 적는다."""
    state = _load(state_path)
    last = state.get("last_run")
    if not force and last and (date.fromisoformat(day) - date.fromisoformat(last)).days < MIN_GAP_DAYS:
        return {"skipped": True, "last_run": last, "recorded": 0, "empty": 0, "requests": 0, "stopped": "", "note": ""}
    key_of = dict((sid, team) for team, sid in pairs)
    recorded = empty = requests = 0
    stopped = ""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(log_path, "a", encoding="utf-8") as fh:
            for batch in batches([sid for _, sid in pairs]):
                requests += 1
                body = client.get("/artists", {"ids": ",".join(batch)})
                artists = body.get("artists") or []
                for sid, a in zip(batch, artists + [None] * (len(batch) - len(artists))):
                    total = ((a or {}).get("followers") or {}).get("total")
                    if not isinstance(total, int):
                        empty += 1
                        continue
                    fh.write(json.dumps({"team_key": key_of[sid], "spotify_id": sid, "date": day, "followers": total},
                                        ensure_ascii=False) + "\n")
                    recorded += 1
    except cs.RateLimited as e:              # spotify_budget 의 예산 소진·막힘도 이 예외 — 이번 주는 여기까지
        stopped = str(e)
    except cs.SpotifyError as e:
        stopped = f"오류: {e}"
    note = "팔로워가 모두 비어 옴 — 개발자 모드 제한으로 보임(기록 안 함)" if requests and not recorded and empty else ""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({"last_run": day, "requests": requests, "recorded": recorded, "empty_last": empty,
                                      "stopped": stopped}, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"skipped": False, "recorded": recorded, "empty": empty, "requests": requests, "stopped": stopped, "note": note}


def _links(path: Path) -> Dict[str, Dict[str, str]]:
    out: Dict[str, Dict[str, str]] = {}
    if path.exists():
        with open(path, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                out.setdefault(r["team_key"], {}).setdefault(r["platform"], r["url"])
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="관찰 팀 스포티파이 팔로워 주 1회")
    ap.add_argument("--force", action="store_true", help="6일 주기 무시")
    args = ap.parse_args(argv)
    import spotify_budget as sb
    skip = sb.skip_message()
    if skip:
        print(skip)
        return 0
    teams = _load(WATCH).get("teams", [])
    pairs = spotify_ids(teams, _links(LINKS))
    if not pairs:
        print("관찰 팀 중 스포티파이 주소가 있는 팀이 없음 — scripts/followers_watch.py 먼저")
        return 0
    env = cs.load_env(cs.ENV_FILE)
    try:
        client = cs.SpotifyClient(env.get("SPOTIFY_CLIENT_ID"), env.get("SPOTIFY_CLIENT_SECRET"), http=sb.BudgetedHttp(cs.urllib_http))
    except cs.SpotifyError as e:
        print(f"⚠️ {e}")
        return 1
    day = f"{datetime.now(cs.KST):%Y-%m-%d}"
    res = run_weekly(client, pairs, day, force=args.force)
    if res["skipped"]:
        print(f"이번 주 이미 함 ({res['last_run']}) — 건너뜀")
        return 0
    print(f"✅ 스포티파이 팔로워: 대상 {len(pairs)}팀 · 요청 {res['requests']}번 · 기록 {res['recorded']}팀 · 비어 옴 {res['empty']}팀")
    if res["note"]:
        print("⚠️", res["note"])
    if res["stopped"]:
        print("⚠️ 중간에 멈춤(다음 주에 다시):", res["stopped"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
