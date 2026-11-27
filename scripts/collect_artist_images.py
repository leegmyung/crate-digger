"""아티스트 사진(썸네일) 주소 모으기 → data/raw/state/artist_images.json (팀 키 → 사진 주소)

- 대상: docs/lab/data/links.csv 의 스포티파이 아티스트 페이지가 있는 팀.
- 스포티파이 2026 개발자 모드에서 여러 명 한 번에 조회(/artists?ids=)는 403 → 한 명씩 /artists/{id}.
- 사진은 i.scdn.co 주소만 받는다(가로 TARGET_WIDTH 이상 중 가장 작은 것). 사진이 없는 팀도 '없음'으로 기억해 다시 묻지 않는다.
- 실행: python3 scripts/collect_artist_images.py   (export_lab_data.py가 이 파일로 docs/lab/data/images.csv를 만든다)
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_spotify as cs  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LINKS = ROOT / "docs" / "lab" / "data" / "links.csv"
CACHE = ROOT / "data" / "raw" / "state" / "artist_images.json"
TARGET_WIDTH = 200
BUDGET = 600                      # 한 번 실행의 최대 요청 수
SPOTIFY_ID = re.compile(r"open\.spotify\.com/artist/([A-Za-z0-9]{22})")
IMAGE_HOSTS = ("i.scdn.co",)


def pick_image(images: List[dict], target: int = TARGET_WIDTH) -> Optional[str]:
    ok = [i for i in images or [] if urlparse(i.get("url", "")).scheme == "https"
          and urlparse(i["url"]).netloc in IMAGE_HOSTS]
    if not ok:
        return None
    big_enough = sorted((i for i in ok if (i.get("width") or 0) >= target), key=lambda i: i.get("width") or 0)
    return (big_enough[0] if big_enough else max(ok, key=lambda i: i.get("width") or 0))["url"]


def targets(links: List[dict], cache: Dict[str, dict]) -> List[Tuple[str, str]]:
    out, seen = [], set()
    for r in links:
        m = SPOTIFY_ID.search(r.get("url", "")) if r.get("platform") == "spotify" else None
        if m and r["team_key"] not in cache and r["team_key"] not in seen:
            seen.add(r["team_key"])
            out.append((r["team_key"], m.group(1)))
    return out


def fetch_images(todo: List[Tuple[str, str]], get: Callable[[str, dict], dict], cache: Dict[str, dict],
                 budget: int = BUDGET) -> Dict[str, dict]:
    out = dict(cache)
    for team_key, sid in todo[:budget]:
        data = get(f"/artists/{sid}", {})
        out[team_key] = {"url": pick_image(data.get("images") or []), "source": "spotify", "spotify_id": sid}
    return out


def main() -> int:
    try:
        cache = json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    with open(LINKS, encoding="utf-8") as f:
        todo = targets(list(csv.DictReader(f)), cache)
    env = cs.load_env(cs.ENV_FILE)
    if not env.get("SPOTIFY_CLIENT_ID") or not env.get("SPOTIFY_CLIENT_SECRET"):
        print("❌ SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET 가 없어요 (.env)", file=sys.stderr)
        return 1
    import spotify_budget as sb                  # 하루 요청 예산 공유·429 뒤 그날 쉬기
    skip = sb.skip_message()
    if skip:
        print(skip)
        return 0
    client = cs.SpotifyClient(env["SPOTIFY_CLIENT_ID"], env["SPOTIFY_CLIENT_SECRET"], http=sb.BudgetedHttp(cs.urllib_http))
    try:
        cache = fetch_images(todo, client.get, cache)
    except (cs.RateLimited, cs.SpotifyError) as e:
        print(f"⚠️ 중간에 멈춤 (받은 것까지 저장): {e}", file=sys.stderr)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    have = sum(1 for v in cache.values() if v.get("url"))
    print(f"✅ 아티스트 사진: 대상 {len(todo)}팀 조회 → 사진 있는 팀 누적 {have}팀")
    return 0


if __name__ == "__main__":
    sys.exit(main())
