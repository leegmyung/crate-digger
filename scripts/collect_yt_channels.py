"""팀 공식 유튜브 채널의 아바타(사진)·최신 영상 받기 → data/raw/state/yt_channels.json + data/raw/raw_video_<날짜>_channels.csv

    python3 scripts/collect_yt_channels.py               # 대상 팀 순서대로, 기본 예산 400단위
    python3 scripts/collect_yt_channels.py --budget 200

- 채널 주소를 '확인된 곳'에서만 모은다 (핸들 추측 안 함 — 2026-11-28 시험: 아는 59팀 중 4팀만 맞음):
  1) docs/lab/data/links.csv 의 youtube 줄  2) MusicBrainz 공식 링크(collect_musicbrainz)
  3) 팀 인스타 소개란의 유튜브 채널 링크(data/raw/state/ig_artist_links.json, 인스타 계정 → 팀은 links.csv·MusicBrainz).
  3') 인디스트릿·인디고 아티스트 페이지 구조화 데이터 sameAs 의 채널(data/raw/state/indistreet_sns.json·indiego_sns.json,
      채널 주소가 하나뿐일 때만 — MusicBrainz 다음 순위).
  4) 채널 검색(yt_channel_search, 하루 20번, 상위 300 중 링크 없는 팀)으로 찾은 채널.
- --teams-file: 한 줄에 팀 키 하나 — coverage_targets 밖 팀도 대상 뒤에 붙여 받는다.
- 비용(YouTube Data API v3): channels.list 1단위(snippet: 제목·아바타, contentDetails: 업로드 목록),
  links.csv 에 없는 채널만 playlistItems.list 1단위로 최신 영상 10개 (links.csv 채널은 collect_videos 가 매일 받는다).
  search.list(100단위)는 쓰지 않는다.
- 아바타: snippet.thumbnails (medium 240px 우선, yt3.ggpht.com·yt3.googleusercontent.com 의 https 주소만).
  YouTube API 정책: API로 받은 데이터는 30일 안에 새로 받거나 지운다 → REFRESH_DAYS(30) 지나면 다시 묻는다.
  앱은 사진 옆에 출처(유튜브)와 채널 링크를 건다 (images.csv page_url).
- 대상 순서: data/raw/state/coverage_targets.json (후보 상위 500 → 정답 팀).
- 영상 줄은 collect_videos 와 같은 칸(kind=official_live·official) → export_lab_data 가 videos.csv·players.csv 에 넣는다.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse, urlunparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_videos as cv  # noqa: E402
import coverage_targets  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / "data" / "raw" / "state" / "yt_channels.json"
LINKS_FILE = ROOT / "docs" / "lab" / "data" / "links.csv"
MUSICBRAINZ_FILE = ROOT / "data" / "raw" / "state" / "musicbrainz.json"
IG_LINKS_FILE = ROOT / "data" / "raw" / "state" / "ig_artist_links.json"
YT_SEARCH_FILE = ROOT / "data" / "raw" / "state" / "yt_search.json"   # yt_channel_search
SAMEAS_FILES = (("indistreet", ROOT / "data" / "raw" / "state" / "indistreet_sns.json"),   # collect_indistreet_sns
                ("indiego", ROOT / "data" / "raw" / "state" / "indiego_sns.json"))         # collect_indiego_sns

RAW_DIR = ROOT / "data" / "raw"
DEFAULT_BUDGET = 400
REFRESH_DAYS = 30
LATEST_N = 10
AVATAR_HOSTS = ("yt3.ggpht.com", "yt3.googleusercontent.com")
AVATAR_ORDER = ("medium", "high", "default")
INSTAGRAM_HOSTS = ("www.instagram.com", "instagram.com")


def _clean_channel_url(url: str) -> Optional[str]:
    """유튜브 '채널' 주소만 (영상·재생목록 주소는 None). 뒤 ?si= 같은 꼬리는 뗀다."""
    p = urlparse((url or "").strip())
    if p.scheme != "https":
        return None
    clean = urlunparse((p.scheme, p.netloc, p.path, "", "", ""))
    return clean if cv.parse_youtube_url(clean) else None


def _insta_handle(url: str) -> str:
    p = urlparse(url or "")
    parts = [x for x in p.path.split("/") if x]
    return parts[0].lower() if p.netloc in INSTAGRAM_HOSTS and len(parts) == 1 else ""


def sameas_channel(same_as: List[str]) -> Optional[str]:
    """sameAs 중 유튜브 '채널' 주소가 정확히 하나면 그 주소(꼬리 뗌), 없거나 둘 이상이면 None (어느 쪽이 팀 것인지 모름)."""
    found = list(dict.fromkeys(u for u in (_clean_channel_url(x) for x in same_as or [] if isinstance(x, str)) if u))
    return found[0] if len(found) == 1 else None


def candidate_channels(links: List[dict], musicbrainz: dict, ig_links: dict,
                       yt_search: Optional[dict] = None,
                       sameas: Optional[List[Tuple[str, dict]]] = None) -> Dict[str, Tuple[str, str]]:
    """팀 → (채널 주소, 출처). 출처 우선순위 links > musicbrainz > sameas(인디스트릿 → 인디고) > instagram > yt_search,
    같은 출처 안에서는 처음 것."""
    out: Dict[str, Tuple[str, str]] = {}
    for r in links:
        url = _clean_channel_url(r.get("url") or "") if r.get("platform") == "youtube" else None
        if url and r.get("team_key"):
            out.setdefault(r["team_key"], (url, "links"))
    insta_team: Dict[str, str] = {}
    for r in links:
        handle = _insta_handle(r.get("url") or "") if r.get("platform") == "instagram" else ""
        if handle and r.get("team_key"):
            insta_team.setdefault(handle, r["team_key"])
    for team, entry in sorted((musicbrainz or {}).items()):
        urls = (entry or {}).get("urls") or {} if (entry or {}).get("mbid") else {}
        for handle in urls.get("instagram") or []:
            insta_team.setdefault(handle.lower(), team)
        for raw in urls.get("youtube") or []:
            url = _clean_channel_url(raw)
            if url:
                out.setdefault(team, (url, "musicbrainz"))
    for source, state in sameas or []:                           # 팀이 페이지에 적은(또는 사이트가 붙인) 공식 채널
        for team, entry in sorted((state or {}).items()):
            url = sameas_channel((entry or {}).get("same_as") if isinstance(entry, dict) else None)
            if url:
                out.setdefault(team, (url, source))
    for handle, entry in (ig_links or {}).items():
        team = insta_team.get(handle.lower())
        if handle == "non_artists" or not team:
            continue
        for link in (entry or {}).get("links") or []:
            url = _clean_channel_url(link.get("url") or "") if link.get("kind") == "youtube" else None
            if url:
                out.setdefault(team, (url, "instagram"))
    for team, entry in sorted((yt_search or {}).items()):        # yt_channel_search: 채널 검색으로 찾은 것
        cid = (entry or {}).get("channel_id") or ""
        if re.fullmatch(r"UC[A-Za-z0-9_-]{22}", cid):
            out.setdefault(team, (f"https://www.youtube.com/channel/{cid}", "yt_search"))
    return out


def pick_avatar(thumbnails: dict) -> str:
    for size in AVATAR_ORDER:
        url = ((thumbnails or {}).get(size) or {}).get("url") or ""
        p = urlparse(url)
        if p.scheme == "https" and p.netloc in AVATAR_HOSTS:
            return url
    return ""


def _lookup_params(url: str) -> List[dict]:
    kind, value = cv.parse_youtube_url(url) or ("", "")
    if kind == "id":
        return [{"id": value}]
    if kind == "handle":
        return [{"forHandle": value}]
    if kind == "user":
        return [{"forUsername": value}]
    if kind == "custom":
        return [{"forHandle": "@" + value}, {"forUsername": value}]
    return []


def _fresh(entry: Optional[dict], today: date) -> bool:
    try:
        return today - date.fromisoformat((entry or {}).get("checked") or "") < timedelta(days=REFRESH_DAYS)
    except ValueError:
        return False


def fetch_channel(client, url: str) -> Optional[dict]:
    for params in _lookup_params(url):
        items = client.get("channels", {"part": "snippet,contentDetails", **params}, cv.COST_LIST).get("items") or []
        if items:
            it = items[0]
            sn = it.get("snippet") or {}
            return {"channel_id": it.get("id") or "", "title": sn.get("title") or "",
                    "avatar": pick_avatar(sn.get("thumbnails") or {}),
                    "uploads": ((it.get("contentDetails") or {}).get("relatedPlaylists") or {}).get("uploads") or ""}
    return None


def latest_videos(client, team_key: str, display_name: str, channel: dict, now: datetime) -> List[dict]:
    if not channel.get("uploads"):
        return []
    body = client.get("playlistItems", {"part": "snippet,contentDetails", "playlistId": channel["uploads"],
                                        "maxResults": LATEST_N}, cv.COST_LIST)
    rows = []
    for item in body.get("items") or []:
        vid, title, published, sn = cv._item_video(item)
        if not published or not cv.valid_video_id(vid):
            continue
        kind = "official_live" if cv.LIVE_WORDS.search(title) else "official"
        rows.append(cv.make_row(now, team_key, display_name, vid, title, sn.get("channelTitle"),
                                sn.get("channelId") or channel.get("channel_id"), published, kind, ""))
    return rows


def run(targets: List[dict], candidates: Dict[str, Tuple[str, str]], state: dict, client, now: datetime,
        linked: Set[str]) -> Tuple[dict, List[dict]]:
    """대상 순서대로 채널 정보(+ links.csv 밖 채널은 최신 영상). 예산이 끝나면 멈춘다. (새 상태, 영상 줄)."""
    teams, misses = dict(state.get("teams") or {}), dict(state.get("misses") or {})
    today, rows = now.date(), []
    for t in targets:
        key = t.get("team_key") or ""
        if key not in candidates or _fresh(teams.get(key), today) or _fresh(misses.get(key), today):
            continue
        url, source = candidates[key]
        try:
            channel = fetch_channel(client, url)
            if not channel or not channel["channel_id"]:
                misses[key] = {"url": url, "checked": today.isoformat()}
                continue
            if key not in linked:
                try:
                    rows += latest_videos(client, key, t.get("display_name") or key, channel, now)
                except cv.YouTubeError as e:
                    if e.status != 404:            # 404 = 업로드 목록 없는 채널 → 아바타만 저장
                        raise
        except cv.QuotaExceeded:
            break
        except cv.YouTubeError as e:
            print(f"⚠️ 채널 실패: {key} ({e})")
            continue
        teams[key] = {**channel, "url": url, "source": source, "checked": today.isoformat()}
        misses.pop(key, None)
    return {"teams": teams, "misses": misses}, rows


def with_extra_targets(targets: List[dict], keys: List[str], display: Dict[str, str]) -> List[dict]:
    """대상 뒤에 --teams-file 팀을 붙인다 (이미 있는 팀·빈 줄은 뺌)."""
    have = {t.get("team_key") for t in targets}
    extra = []
    for k in keys:
        k = (k or "").strip()
        if k and k not in have:
            have.add(k)
            extra.append({"team_key": k, "display_name": display.get(k, k)})
    return list(targets) + extra


def write_raw(raw_dir: Path, now: datetime, rows: List[dict]) -> Path:
    path = Path(raw_dir) / f"raw_video_{now:%Y-%m-%d}_channels.csv"
    cv.write_rows(path, rows)
    return path


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="팀 공식 유튜브 채널 아바타·최신 영상")
    ap.add_argument("--budget", type=int, default=DEFAULT_BUDGET, help="이번 실행에 쓸 최대 단위 (기본 400)")
    ap.add_argument("--teams-file", help="한 줄에 팀 키 하나 — coverage_targets 밖 팀도 대상 뒤에 붙여 받기")
    args = ap.parse_args(argv)
    targets = coverage_targets.load_targets()
    if args.teams_file:
        keys = Path(args.teams_file).read_text(encoding="utf-8").splitlines()
        with open(LINKS_FILE.parent / "teams.csv", encoding="utf-8") as f:
            display = {r["team_key"]: r.get("display_name") or r["team_key"] for r in csv.DictReader(f)}
        targets = with_extra_targets(targets, keys, display)
    if not targets:
        print("⏭ 대상 목록이 없어요 (먼저 .venv/bin/python scripts/coverage_targets.py)")
        return 0
    with open(LINKS_FILE, encoding="utf-8") as f:
        links = list(csv.DictReader(f))
    candidates = candidate_channels(links, _read_json(MUSICBRAINZ_FILE), _read_json(IG_LINKS_FILE), _read_json(YT_SEARCH_FILE),
                                    [(name, _read_json(path)) for name, path in SAMEAS_FILES])
    linked = {k for k, (_, src) in candidates.items() if src == "links"}
    env = cv.load_env(cv.ENV_FILE)
    try:
        client = cv.YouTubeClient(env.get("YOUTUBE_API_KEY"), quota=cv.Quota(args.budget))
    except cv.YouTubeError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1
    now = datetime.now(cv.KST).replace(microsecond=0)
    state, rows = run(targets, candidates, _read_json(STATE_FILE), client, now, linked)
    cv.save_state(STATE_FILE, state)
    path = write_raw(RAW_DIR, now, rows) if rows else None
    with_avatar = sum(1 for v in state["teams"].values() if v.get("avatar"))
    print(f"✅ 유튜브 공식 채널: 후보 주소 {len(candidates)}팀 · 채널 확인 누적 {len(state['teams'])}팀 (아바타 {with_avatar})"
          f" · 못 찾음 {len(state['misses'])} · 새 영상 {len(rows)}줄"
          + (f" → {path.relative_to(ROOT)}" if path else "") + f" · 사용 {client.quota.used}/{args.budget}단위")
    return 0


if __name__ == "__main__":
    sys.exit(main())
