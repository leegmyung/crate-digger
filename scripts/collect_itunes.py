"""iTunes 30초 미리듣기 찾기 → data/raw/state/itunes.json (비공개 상태)

    python3 scripts/collect_itunes.py                  # 바로 듣기 없는 대상 팀 순서대로, 한 번에 최대 300요청 (3.5초 간격, 약 18분)
    python3 scripts/collect_itunes.py --max-requests 50

- 왜: 후보 상위 500 중 바로 듣기 없는 팀이 많다. iTunes Search API 는 로그인·열쇠 없이 30초 미리듣기 주소를 준다.
  2026-11-28 시험(상위 500 미커버 50팀): 이름 유일 일치 15팀(30%), 전부 미리듣기 있음. 눈 확인 12팀 맞음·1팀 동명 의심.
- 한국 스토어(country=KR)는 음악 결과가 없다(한국 iTunes 스토어는 음악을 팔지 않음) → 미국 스토어(US)에서 한글 이름으로 찾는다.
  결과 이름은 영문 표기('Silica Gel')가 많아서 연결표의 별칭(영문 표기)까지 같은 이름으로 본다 (preview_match.itunes_pick).
- 확인 등급(confidence): titles = 곡·앨범 제목이 우리 발매 기록과 겹침 / year = iTunes 첫 발매 연도 = 팀 프로필 첫 발매 연도 /
  name = 이름만 같음. 앱(players.csv)에는 titles·year 만 내보낸다 (잘못 붙는 것이 놓치는 것보다 나쁨).
- 이용 조건(Apple Search API 'Promo Content'): 그 콘텐츠를 홍보하는 페이지에서만, 스트리밍만(내려받기·저장 금지),
  "provided courtesy of iTunes" 표기, iTunes/Apple Music 으로 가는 링크(배지) 옆에. → 우리는 주소만 저장하고 오디오는 저장 안 함,
  players.csv page_url 에 링크. 호출 한도 약 분당 20번 → 3.5초 간격.
- 대상: coverage_targets(후보 상위 500 → 정답 팀) 중 players.csv 에 없는 팀. 한 번 본 팀은 REFRESH_DAYS 뒤에 다시 본다.
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import coverage_targets  # noqa: E402
import preview_match as pm  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / "data" / "raw" / "state" / "itunes.json"
XREF_FILE = ROOT / "data" / "raw" / "state" / "artist_xref.json"
BLOCKLIST_FILE = ROOT / "config" / "link_blocklist.json"   # 사람이 틀렸다고 본 연결 (itunes 항목 = 아티스트 번호)
RAW_DIR = ROOT / "data" / "raw"
DATA_DIR = ROOT / "docs" / "lab" / "data"
API = "https://itunes.apple.com/search"
LOOKUP_API = "https://itunes.apple.com/lookup"
ARTIST_LIMIT = 10
MAX_LOOKUPS = 3       # 영문 이름의 동명 아티스트 중 곡을 조회해 볼 수
STORE = "US"
USER_AGENT = "indie-scene-research/0.1 (research script)"   # 개인 정보 없는 이름
MIN_INTERVAL_SEC = 3.5        # Apple: 약 분당 20번
HTTP_TIMEOUT_SEC = 20
DEFAULT_MAX_REQUESTS = 300
REFRESH_DAYS = 30
SEARCH_LIMIT = 50
EXPORT_CONFIDENCE = ("titles", "year")
LINK_HOSTS = ("music.apple.com", "itunes.apple.com")
ARTWORK_SUFFIX = ".mzstatic.com"


class ItunesUnavailable(RuntimeError):
    pass


def confidence(pick: dict, our_titles: Iterable[str], first_release: str) -> str:
    if pm.titles_overlap(our_titles, pick.get("titles") or ()):
        return "titles"
    year = (first_release or "")[:4]
    if year and year == pick.get("first_year"):
        return "year"
    return "name"


def _safe(url: str, hosts=(), suffix: str = "") -> str:
    return url if pm.safe_url(url or "", hosts, suffix) else ""


def entry_for(names: List[str], results: List[dict], our_titles: Iterable[str], first_release: str, today: date) -> dict:
    """검색 결과 → 상태 한 줄. 같은 팀을 못 고르면 {checked, artist_id: None}."""
    pick = pm.itunes_pick(names, results)
    if not pick:
        return {"checked": today.isoformat(), "artist_id": None}
    songs = [r for r in results if r.get("artistId") == pick["artist_id"]]
    years = sorted((r.get("releaseDate") or "")[:4] for r in songs if (r.get("releaseDate") or "")[:4].isdigit())
    pick = {**pick, "first_year": years[0] if years else ""}
    p = pick["preview"] or {}
    preview = {"track_id": p.get("trackId"), "track_name": p.get("trackName") or "",
               "collection_name": p.get("collectionName") or "", "release_date": (p.get("releaseDate") or "")[:10],
               "preview_url": _safe(p.get("previewUrl") or "", pm.ITUNES_AUDIO_HOSTS),
               "track_url": _safe(p.get("trackViewUrl") or "", LINK_HOSTS),
               "artwork_url": _safe(p.get("artworkUrl100") or "", (), ARTWORK_SUFFIX)} if p else None
    return {"checked": today.isoformat(), "artist_id": pick["artist_id"], "artist_name": pick["artist_name"],
            "artist_url": _safe(songs[0].get("artistViewUrl") or "", LINK_HOSTS),
            "first_year": pick["first_year"], "confidence": confidence(pick, our_titles, first_release), "preview": preview}


def _fresh(entry: Optional[dict], today: date) -> bool:
    try:
        return today - date.fromisoformat((entry or {}).get("checked") or "") < timedelta(days=REFRESH_DAYS)
    except ValueError:
        return False


CONFIDENCE_RANK = {"titles": 3, "year": 2, "name": 1}
MAX_EN_TERMS = 2      # 한글 이름으로 확인 못 하면 영문 활동명(en_names.py)으로 더 찾아볼 개수
MAX_TITLE_TERMS = 2   # 그래도 못 하면 우리 곡 제목(멜론 데뷔곡·발매 기록)으로 곡 검색해 볼 개수 — 이름(영문 후보 포함)이 맞아야 함
TITLE_PREFIX = "title:"


def _rank(entry: Optional[dict]) -> int:
    return CONFIDENCE_RANK.get((entry or {}).get("confidence"), 0) if (entry or {}).get("artist_id") else 0


def _todo_terms(prev: Optional[dict], terms: List[str], today: date) -> List[str]:
    """이번에 찾을 검색어: 오래됐으면 전부, 30일 안이면 확인 등급이 아닐 때 아직 안 써 본 검색어만."""
    if not _fresh(prev, today):
        return terms
    if prev.get("confidence") in EXPORT_CONFIDENCE and prev.get("artist_id"):
        return []
    tried = prev.get("terms") or terms[:1]
    return [t for t in terms if t not in tried]


def _confirmed_namesake(search, term: str, names: List[str], our_titles: List[str], first_release: str, today: date,
                        blocked_ids: Set[str], budget: int) -> Tuple[Optional[dict], int]:
    """아티스트 검색 → 이름이 같은 아티스트(최대 MAX_LOOKUPS)의 곡을 조회 → 확인 등급(titles·year)이 딱 하나면 그것.
    (찾은 항목 또는 None, 쓴 요청 수)."""
    if budget <= 0:
        return None, 0
    want = pm.name_keys(names)
    cands = [a for a in search.artists(term) if pm.artist_key(a.get("artistName") or "") in want
             and str(a.get("artistId")) not in blocked_ids]
    used, confirmed = 1, []
    for a in cands[:MAX_LOOKUPS]:
        if used >= budget:
            break
        songs = [r for r in search.songs_of(a["artistId"]) if r.get("artistId") == a["artistId"]]
        used += 1
        e = entry_for(names, songs, our_titles, first_release, today)
        if e.get("artist_id") and e.get("confidence") in EXPORT_CONFIDENCE:
            confirmed.append(e)
    return (confirmed[0] if len(confirmed) == 1 else None), used


def run(targets: List[dict], state: Dict[str, dict], search: Callable[[str], List[dict]], today: date,
        max_requests: int, skip: Set[str], aliases: Dict[str, List[str]], releases: Dict[str, List[str]],
        first_release: Dict[str, str], en_names: Optional[Dict[str, List[str]]] = None,
        blocked: Set[tuple] = frozenset(), titles: Optional[Dict[str, List[str]]] = None) -> Dict[str, dict]:
    """대상 순서대로: 팀 이름 → (확인 못 하면) 영문 활동명 순으로 찾아 가장 높은 확인 등급을 남긴다. 요청 max_requests 까지.
    blocked = {(팀, iTunes 아티스트 번호)} (config/link_blocklist.json) — 그 아티스트는 '못 찾음'으로 본다."""
    out, used, en_names, titles = dict(state), 0, en_names or {}, titles or {}
    for t in targets:
        key, name = t.get("team_key") or "", t.get("display_name") or ""
        if not key or not name or key in skip:
            continue
        en = [e for e in en_names.get(key, []) if e != name][:MAX_EN_TERMS]
        prev = out.get(key)
        if prev and (key, str(prev.get("artist_id"))) in blocked:
            prev = None                                   # 저장된 게 차단된 아티스트면 처음부터 다시
        by_title = [TITLE_PREFIX + x for x in titles.get(key, [])[:MAX_TITLE_TERMS]] if hasattr(search, "songs_by_title") else []
        todo = _todo_terms(prev, [name] + en + by_title, today)
        if not todo:
            continue
        fresh = _fresh(prev, today)
        best = prev if fresh else None
        tried = list((prev or {}).get("terms") or [name]) if fresh else []
        names = [name] + [a for a in aliases.get(key, []) if a != name] + en
        for term in todo:
            if used >= max_requests:
                break
            results = search.songs_by_title(term[len(TITLE_PREFIX):]) if term.startswith(TITLE_PREFIX) else search(term)
            used += 1
            tried.append(term)
            entry = entry_for(names, results, releases.get(key, []), first_release.get(key, ""), today)
            if (key, str(entry.get("artist_id"))) in blocked:
                entry = {"checked": today.isoformat(), "artist_id": None}
            if term != name and not term.startswith(TITLE_PREFIX) and _rank(entry) < CONFIDENCE_RANK["year"] \
                    and hasattr(search, "artists"):
                found, n = _confirmed_namesake(search, term, names, releases.get(key, []), first_release.get(key, ""),
                                               today, {a for (k, a) in blocked if k == key}, max_requests - used)
                used += n
                entry = found or entry
            if best is None or _rank(entry) > _rank(best):
                best = entry
            if best.get("confidence") in EXPORT_CONFIDENCE and best.get("artist_id"):
                break
        if best is not None:
            out[key] = {**best, "checked": today.isoformat(), "terms": tried}
        if used >= max_requests:
            break
    return out


def player_rows(state: Dict[str, dict], allowed: Iterable[str] = EXPORT_CONFIDENCE) -> List[dict]:
    """확인된(titles·year) 팀만 players.csv 줄로 (kind=itunes, id=미리듣기 주소, page_url=Apple Music 곡 페이지)."""
    rows = []
    for team, e in sorted(state.items()):
        p = (e or {}).get("preview") or {}
        if not e.get("artist_id") or e.get("confidence") not in tuple(allowed) or not p.get("preview_url"):
            continue
        rows.append({"team_key": team, "kind": "itunes", "id": p["preview_url"], "title": p.get("track_name") or "",
                     "channel_title": e.get("artist_name") or "", "source": "itunes",
                     "published_at": p.get("release_date") or "", "view_count": "",
                     "page_url": p.get("track_url") or e.get("artist_url") or ""})
    return rows


class ItunesSearch:
    """분당 약 20번 이하로 부르는 검색. 403·429(한도)·연결 오류가 이어지면 ItunesUnavailable."""

    def __init__(self, sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic):
        self._sleep, self._clock, self._last = sleep, clock, -MIN_INTERVAL_SEC

    def __call__(self, term: str) -> List[dict]:
        """곡 검색 (아티스트 이름으로)."""
        return self._get(API, {"term": term, "country": STORE, "media": "music", "entity": "song",
                               "attribute": "artistTerm", "limit": SEARCH_LIMIT})

    def artists(self, term: str) -> List[dict]:
        """아티스트 검색 — 동명 아티스트 목록 (영문 이름은 곡 검색 상위가 유명한 동명 가수로 채워져서)."""
        return self._get(API, {"term": term, "country": STORE, "media": "music", "entity": "musicArtist",
                               "attribute": "artistTerm", "limit": ARTIST_LIMIT})

    def songs_of(self, artist_id) -> List[dict]:
        """아티스트 한 명의 곡 목록."""
        return self._get(LOOKUP_API, {"id": artist_id, "country": STORE, "entity": "song", "limit": SEARCH_LIMIT})

    def songs_by_title(self, title: str) -> List[dict]:
        """곡 제목으로 곡 검색 (우리 발매 기록의 제목 — 영문으로만 올라 있는 팀을 찾을 때)."""
        return self._get(API, {"term": title, "country": STORE, "media": "music", "entity": "song", "limit": SEARCH_LIMIT})

    def _get(self, base: str, params: dict) -> List[dict]:
        gap = MIN_INTERVAL_SEC - (self._clock() - self._last)
        if gap > 0:
            self._sleep(gap)
        self._last = self._clock()
        req = urllib.request.Request(f"{base}?{urllib.parse.urlencode(params)}", headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SEC) as resp:
                return json.loads(resp.read().decode("utf-8")).get("results") or []
        except urllib.error.HTTPError as e:
            raise ItunesUnavailable(f"HTTP {e.code}") from e
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            raise ItunesUnavailable(type(e).__name__) from e


def _csv(path: Path) -> List[dict]:
    try:
        with open(path, encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except OSError:
        return []


def _releases() -> Dict[str, List[str]]:
    from artist_xref import canonical_key, load_xref
    from normalize import split_artist_cell
    index, out = load_xref(), {}
    for path in sorted(glob.glob(str(RAW_DIR / "raw_kr_release_*.csv"))):
        for r in _csv(Path(path)):
            for name in split_artist_cell(r.get("artist_text") or "") or [r.get("artist_text") or ""]:
                key = canonical_key(name, index)
                if key and r.get("title"):
                    out.setdefault(key, []).append(r["title"])
    return out


def _title_terms(releases: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """팀 → 곡 제목 검색어: 멜론 프로필 데뷔곡 → 발매 기록 제목 (같은 제목은 한 번)."""
    from artist_xref import canonical_key, load_xref
    index, out = load_xref(), {}
    for path in sorted(glob.glob(str(RAW_DIR / "raw_artist_profile_*melon*.csv"))):
        for r in _csv(Path(path)):
            key = canonical_key(r.get("artist_text") or "", index)
            if key and r.get("debut_title") and r["debut_title"] not in out.get(key, []):
                out.setdefault(key, []).append(r["debut_title"])
    for key, ts in releases.items():
        for t in ts:
            if t not in out.get(key, []):
                out.setdefault(key, []).append(t)
    return out


def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="iTunes 30초 미리듣기 찾기")
    ap.add_argument("--max-requests", type=int, default=DEFAULT_MAX_REQUESTS)
    args = ap.parse_args(argv)
    targets = coverage_targets.load_targets()
    if not targets:
        print("⏭ 대상 목록이 없어요 (먼저 .venv/bin/python scripts/coverage_targets.py)")
        return 0
    skip = {r["team_key"] for r in _csv(DATA_DIR / "players.csv") if r.get("kind") != "itunes"}
    teams = _csv(DATA_DIR / "teams.csv")
    aliases = {a["artist_key"]: list(a.get("aliases") or []) for a in _load_json(XREF_FILE, []) if isinstance(a, dict)}
    state = _load_json(STATE_FILE, {})
    stopped = ""
    batch = 25                                        # 25요청마다 저장
    remaining = args.max_requests
    search = ItunesSearch()
    releases = _releases()
    import en_names as en_mod                    # 영문 활동명 (검색 전용, scripts/en_names.py)
    en_state = en_mod.load()
    en = {k: en_mod.names_for(en_state, k) for k in en_state}
    blocked = {(e["team_key"], str(e["ref"])) for e in _load_json(BLOCKLIST_FILE, {}).get("blocked", [])
               if e.get("platform") == "itunes"}
    titles = _title_terms(releases)
    first = {r["team_key"]: r.get("first_release") or "" for r in teams}
    while remaining > 0:
        before = dict(state)
        try:
            state = run(targets, state, search, date.today(), min(batch, remaining), skip, aliases, releases, first, en,
                        blocked, titles)
        except ItunesUnavailable as e:
            stopped = str(e)
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=0), encoding="utf-8")
        if stopped or state == before:
            break
        remaining -= batch
    found = [v for v in state.values() if v.get("artist_id")]
    ok = sum(1 for v in found if v.get("confidence") in EXPORT_CONFIDENCE)
    print(f"✅ iTunes 미리듣기: 본 팀 누적 {len(state)} · 이름 일치 {len(found)} · 확인됨(앱에 나감) {ok}"
          + (f" — 멈춤: {stopped} (다음 실행에서 이어감)" if stopped else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
