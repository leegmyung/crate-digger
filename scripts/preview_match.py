"""iTunes·Deezer 검색 결과에서 '우리 팀'을 보수적으로 고르는 규칙 (수집기·시험 스크립트가 같이 쓴다).

- 이름 키(normalize.artist_key)가 팀 이름이나 별칭(연결표의 영문 표기 등)과 같은 아티스트가 '딱 하나'일 때만 받는다.
  함께 부른 곡(A & B)은 안 셈. Deezer 의 앨범 0개짜리 빈 항목(같은 팀이 두 번 등록된 것)은 센 데서 뺀다.
- 검증: 그 아티스트의 곡·앨범 제목 중 하나라도 우리 발매 기록(raw_kr_release)의 제목과 같으면 '확인됨'.
  제목은 normalize.title_key 로 맞추고, iTunes 의 ' - Single'·' - EP' 꼬리와 끝 괄호(feat. 등)는 떼고 비교한다.
- 주소는 https + 알려진 도메인만 (미리듣기·사진).
"""
from __future__ import annotations

import re
from typing import Iterable, List, Optional, Set, Union
from urllib.parse import urlparse

from normalize import TRAILING_ALIAS, artist_key, title_key

ITUNES_AUDIO_HOSTS = ("audio-ssl.itunes.apple.com",)
ITUNES_IMAGE_SUFFIX = ".mzstatic.com"
DEEZER_AUDIO_SUFFIX = ".dzcdn.net"
RELEASE_SUFFIX = re.compile(r"\s*-\s*(?:single|ep)\s*$", re.I)
Names = Union[str, Iterable[str]]


def name_keys(names: Names) -> Set[str]:
    """팀 이름(+ 별칭: 영문 표기 등) → 이름 키 집합. 문자열 하나도 받는다."""
    items = [names] if isinstance(names, str) else list(names)
    return {k for k in (artist_key(n) for n in items) if k}


def safe_url(url: str, hosts: Iterable[str] = (), suffix: str = "") -> bool:
    p = urlparse(url or "")
    host = p.netloc.lower()
    return p.scheme == "https" and (host in tuple(hosts) or bool(suffix and host.endswith(suffix)))


def _title_keys(title: str) -> Set[str]:
    base = RELEASE_SUFFIX.sub("", title or "")
    keys = {title_key(base), title_key(TRAILING_ALIAS.sub("", base))}
    return {k for k in keys if k}


def titles_overlap(ours: Iterable[str], theirs: Iterable[str]) -> bool:
    mine: Set[str] = set()
    for t in ours:
        mine |= _title_keys(t)
    return any(_title_keys(t) & mine for t in theirs)


def itunes_pick(names: Names, results: List[dict]) -> Optional[dict]:
    """iTunes 곡 검색 결과 → {artist_id, artist_name, titles(곡·앨범 제목), preview(가장 최근 곡, 없으면 None)}.
    이름 키가 같은 아티스트가 둘 이상이거나 없으면 None."""
    want = name_keys(names)
    songs = [r for r in results if r.get("kind") == "song" and artist_key(r.get("artistName") or "") in want]
    ids = {r.get("artistId") for r in songs}
    if len(ids) != 1:
        return None
    titles = {t for r in songs for t in (r.get("trackName"), r.get("collectionName")) if t}
    playable = [r for r in songs if safe_url(r.get("previewUrl") or "", ITUNES_AUDIO_HOSTS)]
    preview = max(playable, key=lambda r: r.get("releaseDate") or "") if playable else None
    return {"artist_id": songs[0].get("artistId"), "artist_name": songs[0].get("artistName") or "",
            "titles": titles, "preview": preview}


def deezer_pick(names: Names, artists: List[dict]) -> Optional[dict]:
    """Deezer 아티스트 검색 결과 → 이름 키가 같은(앨범 0개 빈 항목 제외) 아티스트가 딱 하나면 그것."""
    want = name_keys(names)
    hits = [a for a in artists if artist_key(a.get("name") or "") in want and a.get("nb_album", 1) != 0]
    return hits[0] if len(hits) == 1 else None
