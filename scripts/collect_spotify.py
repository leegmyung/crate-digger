"""스포티파이 발매 이력 수집기 → data/raw/raw_artist_profile_<날짜>_spotify.csv

    python3 scripts/collect_spotify.py              # 후보·정답 팀 이름을 스포티파이에서 찾아 첫 발매일·발매 수 받기
    python3 scripts/collect_spotify.py --limit 100

- 왜: 멜론 데뷔일이 빈 팀이 많아서, 신인인지(첫 발매가 최근인지) 판단할 보조 자료가 필요하다.
- 대상 이름: 발매(raw_kr_release), 선정(raw_kr_selection, 2024년 이후 발표), 공연(raw_kr_gig, 2025-06-01 이후
  공연 2번 이상 나온 팀), 기사(raw_press), 정답(raw_outcome) 전부. normalize.artist_key로 같은 팀은 한 번만.
- 찾기: 이름 끝 '(별칭)'을 뺀 이름으로 먼저, 못 찾으면 별칭으로 검색. 스포티파이 이름의 키가 우리 이름 키나 별칭 키와
  같을 때만 받아들이고, 같은 키가 여럿이면 namesakes(동명 팀 수)를 남긴다 → data/raw/state/spotify_match.json
- 받는 것: 앨범+싱글 목록의 가장 이른 발매일(first_release_date, YYYY나 YYYY-MM일 수 있음)과 개수(album_count).
  2026년 개발자 모드 제한으로 인기도·팔로워·장르는 비어 오고, 비슷한 아티스트·추천은 막혀 있다. 검색·앨범 목록은 한 번에 10개까지.
- 인증: .env 또는 환경변수의 SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET (client credentials 방식). 값은 출력하지 않는다.
- 요청 사이 0.1초 쉬고, 429(너무 많은 요청)는 Retry-After만큼 기다린다 (너무 길면 멈추고 그때까지 결과를 저장).
- 형식: docs/csv_spec.md / scripts/csv_schema.py raw_artist_profile
"""
import argparse
import base64
import csv
import glob
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from csv_schema import TABLES
from normalize import artist_key

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
ENV_FILE = ROOT / ".env"
KST = timezone(timedelta(hours=9))
COLUMNS = [f.name for f in TABLES["raw_artist_profile"]["fields"]]

TOKEN_URL = "https://accounts.spotify.com/api/token"
API = "https://api.spotify.com/v1"
ARTIST_PAGE = "https://open.spotify.com/artist/{id}"
PAGE_LIMIT = 10              # 2026 개발자 모드: 검색·앨범 목록 최대 10개
MARKET = "KR"
LOCALE = "ko-KR,ko"          # 한국 팀은 한글 이름으로 받기 (없으면 영문 이름이 옴)
DELAY_SEC = 0.1
MAX_RETRY_AFTER_SEC = 120    # 이보다 오래 기다리라고 하면 멈춘다
MAX_RETRIES = 5
HTTP_TIMEOUT_SEC = 20
SAVE_EVERY = 50              # 이름 50개마다 짝 맞춤 결과 저장 (중간에 멈춰도 이어서)
GIG_SINCE = "2025-06-01"
GIG_MIN_COUNT = 2
SELECTION_SINCE_YEAR = "2024"
TRAILING_ALIAS = re.compile(r"\s*[\(\[]([^\)\]]+)[\)\]]\s*$")


class RateLimited(RuntimeError):
    pass


class SpotifyError(RuntimeError):
    pass


# ---------- 설정 ----------

def load_env(path, environ=None):
    """.env 의 KEY=VALUE 를 읽는다. 이미 환경변수에 있으면 그쪽이 우선."""
    environ = os.environ if environ is None else environ
    values = {}
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return {**values, **{k: v for k, v in environ.items() if k in values or k.startswith("SPOTIFY_")}}


# ---------- HTTP ----------

def urllib_http(method, url, headers=None, data=None):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SEC) as resp:
            return resp.status, dict(resp.headers), json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            parsed = json.loads(body or b"{}")
        except json.JSONDecodeError:
            parsed = {}
        return e.code, dict(e.headers or {}), parsed


class SpotifyClient:
    def __init__(self, client_id, client_secret, http=urllib_http, sleep=time.sleep):
        if not client_id or not client_secret:
            raise SpotifyError("SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET 가 없습니다 (.env 확인)")
        self._basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        self._http = http
        self._sleep = sleep
        self._token = None

    def _refresh_token(self):
        status, _, body = self._http("POST", TOKEN_URL, {
            "Authorization": "Basic " + self._basic,
            "Content-Type": "application/x-www-form-urlencoded",
        }, b"grant_type=client_credentials")
        if status != 200 or not body.get("access_token"):
            raise SpotifyError(f"토큰 발급 실패 (HTTP {status})")
        self._token = body["access_token"]

    def get(self, path, params):
        url = f"{API}{path}?{urllib.parse.urlencode(params)}"
        if not self._token:
            self._refresh_token()
        refreshed = False
        for _ in range(MAX_RETRIES):
            status, headers, body = self._http("GET", url, {"Authorization": "Bearer " + self._token,
                                                            "Accept-Language": LOCALE})
            if status == 200:
                return body
            if status == 401 and not refreshed:
                self._refresh_token()
                refreshed = True
                continue
            if status == 429:
                wait = int(_header(headers, "Retry-After") or 1)
                if wait > MAX_RETRY_AFTER_SEC:
                    raise RateLimited(f"요청 한도 초과 — {wait}초 뒤에 다시 하라고 함")
                self._sleep(wait)
                continue
            if status >= 500:
                self._sleep(1)
                continue
            raise SpotifyError(f"HTTP {status}: {path}")
        raise SpotifyError(f"재시도 {MAX_RETRIES}번 실패: {path}")

    def search_artists(self, name):
        body = self.get("/search", {"q": name, "type": "artist", "market": MARKET, "limit": PAGE_LIMIT})
        return (body.get("artists") or {}).get("items") or []

    def _albums(self, artist_id, groups, offset=0):
        return self.get(f"/artists/{artist_id}/albums",
                        {"include_groups": groups, "market": MARKET, "limit": PAGE_LIMIT, "offset": offset})

    def release_summary(self, artist_id):
        """앨범+싱글의 가장 이른 발매일과 개수. 목록은 종류별(앨범→싱글) 최신순이라,
        10개를 넘으면 종류마다 마지막 페이지(가장 오래된 것)만 더 읽는다."""
        first = self._albums(artist_id, "album,single")
        total = first.get("total", 0)
        items = list(first.get("items") or [])
        if first.get("next"):
            for group in ("album", "single"):
                page = self._albums(artist_id, group)
                items += page.get("items") or []
                group_total = page.get("total", 0)
                if group_total > PAGE_LIMIT:
                    items += self._albums(artist_id, group, group_total - PAGE_LIMIT).get("items") or []
        return summarize(items, total)


def _header(headers, name):
    return next((v for k, v in (headers or {}).items() if k.lower() == name.lower()), None)


# ---------- 짝 맞추기·요약 ----------

def name_keys(name):
    keys = {artist_key(name)}
    m = TRAILING_ALIAS.search(name or "")
    if m:
        keys.add(artist_key(m.group(1)))
    return {k for k in keys if k}


def pick_match(query_name, items):
    """검색 결과 중 이름 키가 같은 첫 팀. 같은 키 팀 수(namesakes)를 같이 남긴다."""
    want = name_keys(query_name)
    hits = [a for a in items if artist_key(a.get("name", "")) in want]
    if not hits:
        return None
    return {"id": hits[0]["id"], "name": hits[0]["name"], "namesakes": len(hits)}


def summarize(items, total):
    dates = [d for d in (i.get("release_date") or "" for i in items) if d and not d.startswith("0000")]
    return {"first_release_date": min(dates, default=""), "album_count": str(total)}


def find_artist(client, name):
    base = TRAILING_ALIAS.sub("", name).strip() or name
    match = pick_match(name, client.search_artists(base))
    alias = TRAILING_ALIAS.search(name)
    if not match and alias:
        match = pick_match(name, client.search_artists(alias.group(1).strip()))
    return match


# ---------- 입력 이름 ----------

def _rows(raw_dir, pattern):
    for f in sorted(glob.glob(str(raw_dir / pattern))):
        with open(f, encoding="utf-8") as fh:
            yield from csv.DictReader(fh)


def _frequent_gig_artists(raw_dir):
    gigs = defaultdict(set)
    names = {}
    for r in _rows(raw_dir, "raw_kr_gig_*.csv"):
        if (r.get("gig_date") or "") < GIG_SINCE or not r.get("artist_text"):
            continue
        key = artist_key(r["artist_text"])
        gigs[key].add((r.get("source"), r.get("source_id"), r.get("gig_date")))
        names.setdefault(key, r["artist_text"])
    return [names[k] for k, g in gigs.items() if len(g) >= GIG_MIN_COUNT]


def input_names(raw_dir):
    """후보·정답 팀 이름 (같은 키는 처음 본 표기 하나만). 정답 이름을 먼저 둔다 — 별칭이 붙은 경우가 많아서."""
    groups = [
        [r.get("artist_text") for r in _rows(raw_dir, "raw_outcome_*.csv")],
        [r.get("artist_text") for r in _rows(raw_dir, "raw_kr_release_*.csv")],
        [r.get("artist_text") for r in _rows(raw_dir, "raw_kr_selection_*.csv")
         if (r.get("announced_at") or "")[:4] >= SELECTION_SINCE_YEAR],
        _frequent_gig_artists(raw_dir),
        [r.get("artist_text") for r in _rows(raw_dir, "raw_press_*.csv")],
    ]
    by_key = {}
    for name in (n.strip() for g in groups for n in g if n and n.strip()):
        by_key.setdefault(artist_key(name), name)
    return [n for k, n in by_key.items() if k]


# ---------- 저장 ----------

def _load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def to_row(match, summary, collected_at):
    return {"collected_at": collected_at, "source": "spotify", "collector": "script",
            "artist_source_id": match["id"], "artist_text": match["name"],
            "first_release_date": summary["first_release_date"], "album_count": summary["album_count"],
            "url": ARTIST_PAGE.format(id=match["id"]), "artist_key": artist_key(match["name"])}


def write_csv(rows, out_dir, day):
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"raw_artist_profile_{day}_spotify.csv"
    if path.exists():  # 원본은 고치지 않는다
        path = out_dir / f"raw_artist_profile_{day}_spotify_{datetime.now(KST):%H%M%S}.csv"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows([{c: r.get(c, "") for c in COLUMNS} for r in rows])
    return path


# ---------- 실행 ----------

def _profile(client, match, done, rows, collected_at, delay, failures):
    if not match or match["id"] in done:
        return
    try:
        rows.append(to_row(match, client.release_summary(match["id"]), collected_at))
        done.add(match["id"])
    except SpotifyError as e:
        failures.append(f"앨범 {match['name']}({match['id']}): {e}")
    time.sleep(delay)


def _collect(client, todo, matches, seen, rows, ctx):
    """먼저 지난번에 짝만 맞추고 앨범을 못 받은 팀, 그다음 새 이름을 하나씩 (검색 → 바로 앨범).
    한도에 걸려 멈춰도 그때까지 받은 행(rows)은 남는다."""
    collected_at, delay, failures, match_path = ctx
    done = set(seen)
    for m in list(matches.values()):
        _profile(client, m, done, rows, collected_at, delay, failures)
    for i, name in enumerate(todo, 1):
        try:
            matches[name] = find_artist(client, name)
        except SpotifyError as e:
            failures.append(f"검색 {name}: {e}")
            continue
        finally:
            if i % SAVE_EVERY == 0:
                _save_json(match_path, matches)
        time.sleep(delay)
        _profile(client, matches[name], done, rows, collected_at, delay, failures)


def run(client, names, raw_dir, day, collected_at, delay=DELAY_SEC, limit=None):
    match_path = raw_dir / "state" / "spotify_match.json"
    seen_path = raw_dir / "state" / "spotify_seen.json"
    matches = _load_json(match_path, {})
    seen = _load_json(seen_path, [])
    todo = [n for n in names if n not in matches][:limit]
    failures, rows, stopped = [], [], ""
    try:
        _collect(client, todo, matches, seen, rows, (collected_at, delay, failures, match_path))
    except RateLimited as e:
        stopped = str(e)
    finally:
        _save_json(match_path, matches)
        path = write_csv(rows, raw_dir, day) if rows else None
        _save_json(seen_path, sorted(set(seen) | {r["artist_source_id"] for r in rows}))
    queried = [n for n in todo if n in matches]
    return {"path": path, "queried": len(queried), "matched": sum(1 for n in queried if matches[n]),
            "rows": len(rows), "failures": failures, "stopped": stopped}


def main(argv):
    ap = argparse.ArgumentParser(description="스포티파이 발매 이력 수집 (첫 발매일·발매 수)")
    ap.add_argument("--limit", type=int, default=None, help="이번에 새로 검색할 이름 수 상한")
    args = ap.parse_args(argv)
    import spotify_budget as sb                  # 하루 요청 예산 공유·429 뒤 그날 쉬기 (세 스포티파이 단계 공통)
    skip = sb.skip_message()
    if skip:
        print(skip)
        return 0
    env = load_env(ENV_FILE)
    try:
        client = SpotifyClient(env.get("SPOTIFY_CLIENT_ID"), env.get("SPOTIFY_CLIENT_SECRET"), http=sb.BudgetedHttp(urllib_http))
        now = datetime.now(KST).replace(microsecond=0)
        res = run(client, input_names(RAW_DIR), RAW_DIR, f"{now:%Y-%m-%d}", now.isoformat(), limit=args.limit)
    except (SpotifyError, OSError) as e:
        print(f"⚠️ 스포티파이 수집 실패: {e}")
        return 1
    print(f"✅ 스포티파이: 검색 {res['queried']}명 → 짝 맞춤 {res['matched']}명 → {res['rows']}행"
          + (f" → {res['path']}" if res["path"] else ""))
    for f in res["failures"][:20]:
        print("  - 실패:", f)
    if res["stopped"]:
        print("⚠️ 중간에 멈춤:", res["stopped"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
