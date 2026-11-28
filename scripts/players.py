"""팀별 '바로 듣기' 재생 대상 고르기 → docs/lab/data/players.csv (export_lab_data 가 부른다)

한 팀에 최대 2줄: kind=spotify (아티스트 삽입 재생, links.csv 의 스포티파이 번호 → id 'artist:<22자>')
               kind=youtube (대표 영상 1개, id = 유튜브 영상 번호 11자).
유튜브 대표 영상 순서 — '바로 들었을 때 그 팀 음악이 나올 가능성'이 높은 것부터:
  1) 공식 채널 라이브 (official_live), 최신
  2) 공식 채널 음악 영상 (official 중 제목에 MV·Official Audio·Lyric·Live 등), 최신
  3) 무대 채널 영상 (stage), 조회수 많은 것 → 같으면 최신
  4) 공식 채널 그 밖의 영상 (브이로그 등), 최신
  5) 검색으로 찾은 영상 (search), 조회수 → 최신
영상은 export_lab_data 가 video_match·무대 아님 규칙으로 거른 뒤의 전체 목록을 받는다 (videos.csv 의 팀당 6개 자르기 전).
앱 쪽 읽기: docs/app/player_pick.js parsePlayersRows (team_key·kind·id·title·source, 나머지 칸은 덧붙임).
"""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Dict, List, Optional

PLAYER_FIELDS = ["team_key", "kind", "id", "title", "channel_title", "source", "published_at", "view_count"]
VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")
SPOTIFY_ARTIST = re.compile(r"^https://open\.spotify\.com/artist/([A-Za-z0-9]{22})$")
MUSIC_WORDS = re.compile(r"\bm/?v\b|music video|뮤직비디오|official (?:audio|video|visualizer)|visuali[sz]er|lyric|가사|"
                         r"\blive\b|라이브|session|세션|performance", re.I)
STATS_GLOB = "raw_video_stats_*.csv"
TIER_OFFICIAL_LIVE, TIER_OFFICIAL_MUSIC, TIER_STAGE, TIER_OFFICIAL_OTHER, TIER_SEARCH = range(5)
VIEW_RANKED_TIERS = (TIER_STAGE, TIER_SEARCH)


def _tier(v: dict) -> int:
    kind = v.get("kind")
    if kind == "official_live":
        return TIER_OFFICIAL_LIVE
    if kind == "official":
        return TIER_OFFICIAL_MUSIC if MUSIC_WORDS.search(v.get("title") or "") else TIER_OFFICIAL_OTHER
    if kind == "stage":
        return TIER_STAGE
    return TIER_SEARCH


def pick_youtube(videos: List[dict], views: Dict[str, int]) -> Optional[dict]:
    """한 팀의 영상들 중 대표 1개 (규칙은 모듈 설명). 없으면 None."""
    ok = [v for v in videos if VIDEO_ID.fullmatch(v.get("video_id") or "")]
    if not ok:
        return None
    best_tier = min(_tier(v) for v in ok)
    pool = [v for v in ok if _tier(v) == best_tier]
    if best_tier in VIEW_RANKED_TIERS:
        return max(pool, key=lambda v: (views.get(v["video_id"], -1), v.get("published_at") or ""))
    return max(pool, key=lambda v: v.get("published_at") or "")


def _source(v: dict) -> str:
    return "official" if v.get("kind") in ("official", "official_live") else (v.get("kind") or "")


def _spotify_ids(links: List[dict]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for r in links:
        m = SPOTIFY_ARTIST.match(r.get("url") or "") if r.get("platform") == "spotify" else None
        if m and r.get("team_key"):
            out.setdefault(r["team_key"], m.group(1))
    return out


def _youtube_row(team: str, best: dict, views: Dict[str, int]) -> dict:
    seen = views.get(best["video_id"])
    return {"team_key": team, "kind": "youtube", "id": best["video_id"], "title": best.get("title") or "",
            "channel_title": best.get("channel_title") or "", "source": _source(best),
            "published_at": (best.get("published_at") or "")[:10], "view_count": "" if seen is None else str(seen)}


def player_rows(links: List[dict], videos: List[dict], views: Dict[str, int]) -> List[dict]:
    """links.csv 줄 + 거른 영상 줄 + 조회수 → players.csv 줄 (팀 이름순, 팀마다 spotify 먼저)."""
    spotify = _spotify_ids(links)
    by_team: Dict[str, List[dict]] = {}
    for v in videos:
        if v.get("team_key"):
            by_team.setdefault(v["team_key"], []).append(v)
    out: List[dict] = []
    for team in sorted(set(spotify) | set(by_team)):
        if team in spotify:
            out.append({"team_key": team, "kind": "spotify", "id": f"artist:{spotify[team]}", "title": "",
                        "channel_title": "", "source": "spotify", "published_at": "", "view_count": ""})
        best = pick_youtube(by_team.get(team, []), views)
        if best:
            out.append(_youtube_row(team, best, views))
    return out


def latest_views(raw_dir: Path) -> Dict[str, int]:
    """raw_video_stats_<날짜>.csv 들에서 영상별 가장 최근 조회수."""
    out: Dict[str, int] = {}
    for path in sorted(Path(raw_dir).glob(STATS_GLOB)):    # 날짜순 → 뒤 파일이 덮어씀
        with open(path, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                count = (r.get("view_count") or "").strip()
                if VIDEO_ID.fullmatch(r.get("video_id") or "") and count.isdigit():
                    out[r["video_id"]] = int(count)
    return out
