"""MusicBrainz(공개 음악 DB)에서 팀 공식 링크 찾기 → data/raw/state/musicbrainz.json (비공개 상태 파일)

    python3 scripts/collect_musicbrainz.py                    # 대상 팀 순서대로, 한 번에 최대 600요청 (2초 간격, 약 20~30분)
    python3 scripts/collect_musicbrainz.py --max-requests 100

- 왜: 유튜브 공식 채널·스포티파이 번호·인스타 계정을 '사람이 확인해 올린 링크'로 얻는다 (핸들 추측은 2026-11-28 시험에서
  이미 아는 59팀 중 4팀만 맞고 55팀이 같은 이름의 남의 채널 → 안 씀). MusicBrainz 핵심 데이터는 CC0(자유 이용).
- API: https://musicbrainz.org/ws/2/ — robots.txt 가 /ws/ 를 막지 않고, 공식 규칙대로 초당 1번 이하·이름 있는 User-Agent.
  503(속도 제한)이면 쉬었다가 다시, 계속되면 멈추고 받은 데까지 저장.
- 대상: data/raw/state/coverage_targets.json (scripts/coverage_targets.py: 후보 상위 500 → 정답 팀) 순서.
- 맞추기(보수적): 검색 artist:"이름" AND country:KR → 이름 키(normalize.artist_key)가 같은 아티스트가 '딱 하나'일 때만.
  짧은 이름·흔한 낱말(video_match.name_rule 이 'ok' 아님)은 동명 위험이 커서 묻지 않는다.
- 받는 것: 그 아티스트의 url-rels 중 유튜브 '채널' 주소(영상 하나짜리 주소는 뺌)·스포티파이 아티스트 번호·인스타 계정.
  export_lab_data 가 links.csv 에 붙이고, collect_yt_channels·collect_videos 가 그 채널을 쓴다.
- 상태: 팀마다 {checked, mbid, name, urls}. 못 찾은 팀도 적어 두고 REFRESH_DAYS 뒤에 다시 본다.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Optional
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import coverage_targets  # noqa: E402
import video_match  # noqa: E402
from normalize import artist_key  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / "data" / "raw" / "state" / "musicbrainz.json"
API = "https://musicbrainz.org/ws/2/"
USER_AGENT = "indie-scene-research/0.1 (research script)"   # 개인 정보 없는 이름
MIN_INTERVAL_SEC = 2.0        # MusicBrainz 규칙은 초당 1번 이하 — 503이 잦아 2초 (2026-11-28)
RETRY_WAIT_SEC = 10
MAX_RETRIES = 4
HTTP_TIMEOUT_SEC = 20
DEFAULT_MAX_REQUESTS = 600
REFRESH_DAYS = 30
SEARCH_LIMIT = 5
SAVE_EVERY_REQUESTS = 50     # 이만큼 요청마다 저장 (중간에 멈춰도 이어서)
TRAILING_ALIAS = re.compile(r"\s*[\(\[]([^\)\]]+)[\)\]]\s*$")
YT_CHANNEL_PATH = re.compile(r"^/(?:@[^/]+|channel/UC[A-Za-z0-9_-]{22}|c/[^/]+|user/[^/]+)/?$")
SPOTIFY_ARTIST_PATH = re.compile(r"^/artist/([A-Za-z0-9]{22})/?$")
INSTAGRAM_PATH = re.compile(r"^/([A-Za-z0-9._]{1,30})/?$")
INSTAGRAM_NOT_PROFILE = {"p", "reel", "reels", "explore", "stories", "tv"}


class MusicBrainzUnavailable(RuntimeError):
    pass


def searchable(name: str) -> bool:
    base = TRAILING_ALIAS.sub("", name or "").strip()
    common, _ = video_match.load_common()
    return video_match.name_rule(video_match.tokens(base), common) == "ok"


def pick_artist(name: str, artists: List[dict]) -> Optional[dict]:
    """검색 결과 중 이름 키가 같은 아티스트가 딱 하나면 그것, 아니면 None(없음·동명)."""
    want = artist_key(name)
    hits = [a for a in artists if want and artist_key(a.get("name") or "") == want]
    return hits[0] if len(hits) == 1 else None


def _host(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.").removeprefix("m.")


def classify_urls(relations: List[dict]) -> Dict[str, List[str]]:
    """url-rels → {youtube: [채널 주소], spotify: [아티스트 번호], instagram: [계정]} (https 만, 빈 갈래는 뺌)."""
    out: Dict[str, List[str]] = {}

    def add(kind: str, value: str) -> None:
        if value not in out.setdefault(kind, []):
            out[kind].append(value)

    for rel in relations or []:
        url = ((rel or {}).get("url") or {}).get("resource") or ""
        p = urlparse(url)
        if p.scheme != "https":
            continue
        host = _host(url)
        if host == "youtube.com" and YT_CHANNEL_PATH.match(p.path):
            add("youtube", url)
        elif host == "open.spotify.com" and SPOTIFY_ARTIST_PATH.match(p.path):
            add("spotify", SPOTIFY_ARTIST_PATH.match(p.path).group(1))
        elif host == "instagram.com" and INSTAGRAM_PATH.match(p.path):
            handle = INSTAGRAM_PATH.match(p.path).group(1)
            if handle.lower() not in INSTAGRAM_NOT_PROFILE:
                add("instagram", handle)
    return out


def _fresh(entry: dict, today: str) -> bool:
    checked = (entry or {}).get("checked") or ""
    try:
        return date.fromisoformat(today) - date.fromisoformat(checked) < timedelta(days=REFRESH_DAYS)
    except ValueError:
        return False


def _search_query(name: str) -> str:
    base = TRAILING_ALIAS.sub("", name).strip().replace('"', "")
    return f'artist:"{base}" AND country:KR'


def run(targets: List[dict], state: Dict[str, dict], api: Callable[[str, dict], dict], today: str,
        max_requests: int = DEFAULT_MAX_REQUESTS) -> Dict[str, dict]:
    """대상 순서대로 검색 → 맞으면 url-rels 조회. 요청 수가 max_requests 에 닿으면 멈춘다. 새 상태 dict 를 돌려준다."""
    out = dict(state)
    used = 0
    for t in targets:
        key, name = t.get("team_key") or "", t.get("display_name") or ""
        if not key or _fresh(out.get(key), today) or not searchable(name):
            continue
        if used >= max_requests:
            break
        found = pick_artist(name, api("artist", {"query": _search_query(name), "limit": SEARCH_LIMIT}).get("artists") or [])
        used += 1
        if not found:
            out[key] = {"checked": today, "mbid": None}
            continue
        if used >= max_requests:
            break                                   # 조회할 예산이 없으면 이 팀은 다음 실행에
        rels = api(f"artist/{found['id']}", {"inc": "url-rels"}).get("relations") or []
        used += 1
        out[key] = {"checked": today, "mbid": found["id"], "name": found.get("name") or "", "urls": classify_urls(rels)}
    return out


class MusicBrainzApi:
    """초당 1번 이하로 부르는 작은 클라이언트. 503·연결 오류는 쉬었다가 다시, 계속되면 MusicBrainzUnavailable."""

    def __init__(self, sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic):
        self._sleep, self._clock, self._last = sleep, clock, 0.0

    def _wait_turn(self) -> None:
        gap = MIN_INTERVAL_SEC - (self._clock() - self._last)
        if gap > 0:
            self._sleep(gap)
        self._last = self._clock()

    def __call__(self, path: str, params: dict) -> dict:
        url = API + path + "?" + urllib.parse.urlencode({**params, "fmt": "json"})
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        for _ in range(MAX_RETRIES):
            self._wait_turn()
            try:
                with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SEC) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return {}
                if e.code not in (429, 503):
                    raise MusicBrainzUnavailable(f"HTTP {e.code} ({path})") from e
            except (urllib.error.URLError, TimeoutError, ValueError):
                pass
            self._sleep(RETRY_WAIT_SEC)
        raise MusicBrainzUnavailable(f"{MAX_RETRIES}번 실패 ({path})")


def load_state(path: Path = STATE_FILE) -> Dict[str, dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_state(path: Path, state: Dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=0), encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="MusicBrainz 공식 링크(유튜브 채널·스포티파이·인스타) 찾기")
    ap.add_argument("--max-requests", type=int, default=DEFAULT_MAX_REQUESTS)
    args = ap.parse_args(argv)
    targets = coverage_targets.load_targets()
    if not targets:
        print("⏭ 대상 목록이 없어요 (먼저 .venv/bin/python scripts/coverage_targets.py)")
        return 0
    state = load_state()
    today = date.today().isoformat()
    stopped = ""
    batch = SAVE_EVERY_REQUESTS
    remaining = args.max_requests
    api = MusicBrainzApi()
    while remaining > 0:
        before = dict(state)
        try:
            state = run(targets, state, api, today, max_requests=min(batch, remaining))
        except MusicBrainzUnavailable as e:
            stopped = str(e)
        save_state(STATE_FILE, state)
        print(f"  … 본 팀 {len(state)} (이번 묶음 +{len(state) - len(before)})", flush=True)
        if stopped or state == before:
            break
        remaining -= batch
    hits = [v for v in state.values() if v.get("mbid")]
    yt = sum(1 for v in hits if (v.get("urls") or {}).get("youtube"))
    sp = sum(1 for v in hits if (v.get("urls") or {}).get("spotify"))
    ig = sum(1 for v in hits if (v.get("urls") or {}).get("instagram"))
    print(f"✅ MusicBrainz: 본 팀 누적 {len(state)} · 찾은 팀 {len(hits)} (유튜브 채널 {yt} · 스포티파이 {sp} · 인스타 {ig})"
          + (f" — 멈춤: {stopped} (다음 실행에서 이어감)" if stopped else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
