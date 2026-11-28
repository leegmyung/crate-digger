"""인스타 아티스트 프로필 수집기 → data/raw/raw_artist_profile_<날짜>_instagram.csv

    python3 scripts/collect_ig_artists.py              # 새로 태그된 아티스트 계정만 (최대 300개)
    python3 scripts/collect_ig_artists.py --limit 50

- 대상: 공연장 라인업·매거진 캡션에 태그된 @계정 (raw_press.artist_handle) +
  data/raw/review/instagram_candidates_snowball.json 의 artists_tag_counts. 매거진 계정 자체(config/insta_accounts.json)는 뺀다.
- aside 브라우저(aside repl)로 로그인 없이 프로필을 열어 meta 설명에서 팔로워 수·표시 이름·소개글을 읽는다.
  페이지가 뜰 때까지만(약 3초) 기다린다. 로그인 요구 화면이 3번 연달아 나오면 60초 쉬고 이어 간다.
- 소개글·링크에서 멜론/스포티파이/유튜브/밴드캠프/사운드클라우드/링크트리 주소를 찾아
  data/raw/state/ig_artist_links.json 에 남긴다 (유튜브 채널은 youtube_url 칸에도).
- 소개글·이름에 매거진·클럽·레이블·페스티벌 같은 말이 있으면 아티스트가 아닌 것으로 보고 CSV에서 빼고
  같은 파일의 "non_artists" 에 모아 2단계에서 검수한다.
- 이미 본 계정은 data/raw/state/ig_artists_seen.json (로그인 벽에 막힌 계정은 다음에 다시)
- --handles-file: 관찰 목록(scripts/followers_watch.py → data/raw/state/followers_watch_instagram.txt) 계정을 이미 봤어도
  마지막으로 받은 지 7일 지났으면 다시 열어 팔로워 수를 날짜별로 남긴다 (팔로워 30일 변화, docs/followers_plan.md).
- 형식: docs/csv_spec.md / scripts/csv_schema.py raw_artist_profile
"""
import argparse
import csv
import glob
import json
import re
import subprocess
import sys
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from collect_gigs import run_repl
from csv_schema import TABLES
from normalize import artist_key

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
STATE = RAW_DIR / "state" / "ig_artists_seen.json"
LINKS = RAW_DIR / "state" / "ig_artist_links.json"
SNOWBALL = RAW_DIR / "review" / "instagram_candidates_snowball.json"
OUTLETS = ROOT / "config" / "insta_accounts.json"
KST = timezone(timedelta(hours=9))
COLUMNS = [f.name for f in TABLES["raw_artist_profile"]["fields"]]
PROFILE_URL = "https://www.instagram.com/{handle}/"
DEFAULT_LIMIT = 300
BATCH = 5
PAGE_WAIT_MS = 3000
WALL_STREAK_LIMIT = 3
WALL_PAUSE_SEC = 60

UNITS = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000, "천": 1_000, "만": 10_000, "억": 100_000_000}
COUNT_RE = re.compile(r"^([\d.,]+)\s*([KMBkmb천만억]?)$")
FOLLOWERS_KO = re.compile(r"팔로워\s*([\d.,]+\s*[KMBkmb천만억]?)")
FOLLOWERS_EN = re.compile(r"([\d.,]+\s*[KMBkmb]?)\s+Followers")
BIO_KO = re.compile(r"님의 Instagram 계정\s*:\s*'(.*)'\s*$", re.S)
BIO_EN = re.compile(r"on Instagram\s*:\s*\"(.*)\"\s*$", re.S)
URL_TEXT = re.compile(r"(?:https?://)?(?:[\w-]+\.)+[a-z]{2,}(?:/[^\s'\"<>]*)?", re.I)
LINK_KINDS = [
    ("melon", re.compile(r"(?:^|\.|//)melon\.com/", re.I)),
    ("spotify", re.compile(r"(?:open\.spotify\.com|spotify\.link)/", re.I)),
    ("youtube", re.compile(r"(?:youtube\.com|youtu\.be)/", re.I)),
    ("bandcamp", re.compile(r"bandcamp\.com", re.I)),
    ("soundcloud", re.compile(r"soundcloud\.com/", re.I)),
    ("linktree", re.compile(r"linktr\.ee/", re.I)),
]
EMAIL_DOMAIN = re.compile(r"\.(?:com|net|kr|co|org|jp)$", re.I)   # 'abc@gmail.com'에서 잘못 잡힌 태그
YOUTUBE_CHANNEL = re.compile(r"youtube\.com/(?:@|channel/|c/|user/)[^\s/?#]+", re.I)
# 공연장·매거진·레이블 계정 판별. 영문은 낱말 단위로만 ('Olive'의 live는 무시)
NON_ARTIST_RE = re.compile(
    r"\b(?:magazine|club|live|hall|records|label|festival|promotion|venue)\b"
    r"|매거진|클럽|라이브|레이블|페스티벌|프로모션|공연장", re.I)


def parse_count(text):
    m = COUNT_RE.match((text or "").strip())
    if not m:
        return None
    try:
        number = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    return int(round(number * UNITS.get(m.group(2).lower(), 1)))


def parse_meta(meta, handle):
    """프로필 meta 설명 → {followers, name, bio}. 팔로워 수를 못 읽으면 None."""
    meta = (meta or "").strip()
    m = FOLLOWERS_KO.search(meta) or FOLLOWERS_EN.search(meta)
    followers = parse_count(m.group(1)) if m else None
    if followers is None:
        return None
    name = re.search(rf"-\s+(?:See Instagram photos and videos from\s+)?(.*?)\s*\(@{re.escape(handle)}\)", meta, re.I)
    bio = BIO_KO.search(meta) or BIO_EN.search(meta)
    return {"followers": followers, "name": (name.group(1).strip() if name else "") or handle,
            "bio": bio.group(1).strip() if bio else ""}


def unwrap(url):
    """인스타 바깥 링크(l.instagram.com/?u=...)를 원래 주소로."""
    parsed = urllib.parse.urlparse(url or "")
    if parsed.netloc.endswith("l.instagram.com"):
        target = urllib.parse.parse_qs(parsed.query).get("u", [""])[0]
        return target or url
    return url or ""


def _with_scheme(url):
    return url if re.match(r"^https?://", url, re.I) else "https://" + url


def music_links(urls):
    """주소 목록 → [{kind, url}] (음악 플랫폼·링크트리만, 중복 없음)."""
    out, seen = [], set()
    for raw in urls:
        url = _with_scheme(unwrap(raw).strip().rstrip(".,)"))
        kind = next((k for k, pat in LINK_KINDS if pat.search(url)), None)
        if kind and url not in seen:
            seen.add(url)
            out.append({"kind": kind, "url": url})
    return out


def youtube_channel(links):
    for link in links:
        m = YOUTUBE_CHANNEL.search(link["url"]) if link["kind"] == "youtube" else None
        if m:
            return link["url"]
    return ""


def looks_non_artist(name, bio):
    return bool(NON_ARTIST_RE.search(f"{name or ''}\n{bio or ''}"))


def interpret(handle, page):
    """aside가 읽은 페이지 → {status: artist / non_artist / gone / login_wall / unparsed, ...}"""
    page = page or {}
    if page.get("login_wall"):
        return {"status": "login_wall"}
    if page.get("gone"):
        return {"status": "gone"}
    info = parse_meta(page.get("meta", ""), handle)
    if info is None:
        return {"status": "unparsed", "meta": (page.get("meta") or "")[:300]}
    texts = list(page.get("links") or [])
    texts += URL_TEXT.findall(f"{info['bio']}\n{page.get('header', '')}")
    links = music_links(texts)
    status = "non_artist" if looks_non_artist(info["name"], info["bio"]) else "artist"
    return dict(info, status=status, links=links)


def to_row(handle, result, collected_at):
    return {
        "collected_at": collected_at, "source": "instagram", "collector": "aside",
        "artist_source_id": handle, "artist_text": result["name"],
        "debut_date": "", "debut_title": "", "activity_type": "", "agency_text": "", "genre": "", "nationality": "",
        "fan_count": str(result["followers"]), "album_count": "", "first_release_date": "",
        "youtube_url": youtube_channel(result.get("links", [])),
        "url": PROFILE_URL.format(handle=handle), "artist_key": artist_key(result["name"]),
    }


def targets(press_rows, tag_counts, seen, outlets):
    """태그된 계정 목록 (raw_press 순서 → 스노볼 태그 많은 순), 이미 본 계정·매거진 계정 제외."""
    handles = [r.get("artist_handle", "").lstrip("@").rstrip(".") for r in press_rows]
    handles += [h for h, _ in sorted((tag_counts or {}).items(), key=lambda kv: -kv[1])]
    skip = set(seen) | {o.lower() for o in outlets}
    return [h for h in dict.fromkeys(handles) if h and h.lower() not in skip and not EMAIL_DOMAIN.search(h)]


REVISIT_DAYS = 7


def last_fetched(profile_rows):
    """계정 → 마지막으로 프로필을 받은 날 (원본 인스타 프로필 파일의 수집일)."""
    out = {}
    for r in profile_rows:
        h, d = r.get("artist_source_id") or "", (r.get("collected_at") or "")[:10]
        if h and d and d > out.get(h, ""):
            out[h] = d
    return out


def revisit_targets(handles, last, today, outlets=(), days=REVISIT_DAYS):
    """다시 볼 계정: 처음 보는 계정 → 마지막으로 받은 지 days 일 이상 지난 계정(오래된 순). 매거진 계정·중복은 뺀다."""
    skip = {o.lower() for o in outlets}
    cut = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=days)).strftime("%Y-%m-%d")
    hs = [h for h in dict.fromkeys(handles) if h and h.lower() not in skip]
    new = [h for h in hs if h not in last]
    due = sorted((h for h in hs if h in last and last[h] <= cut), key=lambda h: last[h])
    return new + due


def wall_streak(statuses, streak):
    """로그인 벽이 연달아 나온 횟수 (다른 결과가 나오면 0부터)."""
    for s in statuses:
        streak = streak + 1 if s == "login_wall" else 0
    return streak


def write_csv(rows, out_dir, day, path=None):
    """path가 있으면 이번 실행이 만든 그 파일을 다시 쓴다 (묶음마다 저장 — 중간에 끊겨도 행이 남게)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    if path is None:
        path = out_dir / f"raw_artist_profile_{day}_instagram.csv"
        if path.exists():  # 다른 실행이 만든 원본은 고치지 않는다
            path = out_dir / f"raw_artist_profile_{day}_instagram_{datetime.now(KST):%H%M%S}.csv"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _js(handles):
    return f"""await (async () => {{
  const out = {{}};
  for (const h of {json.dumps(handles)}) {{
    try {{
      const t = await openTab('https://www.instagram.com/' + h + '/'); await sleep({PAGE_WAIT_MS});
      out[h] = await t.evaluate(() => {{
        const meta = document.querySelector('meta[name="description"]')?.content || '';
        const body = document.body ? document.body.innerText : '';
        return {{
          meta,
          gone: /isn't available|페이지를 사용할 수 없습니다/.test(body),
          login_wall: location.pathname.startsWith('/accounts/login') || (!meta && !!document.querySelector('input[name="username"]')),
          header: (document.querySelector('header')?.innerText || '').slice(0, 1500),
          links: [...new Set([...document.querySelectorAll('header a[href], a[href*="l.instagram.com"]')]
            .map(a => a.href).filter(u => !/^https:\\/\\/www\\.instagram\\.com\\//.test(u)))].slice(0, 20)
        }};
      }});
      await closeTab(t);
    }} catch (e) {{ out[h] = {{ error: String(e) }}; }}
  }}
  console.log('RESULT ' + JSON.stringify(out));
}})();"""


def _load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _press_rows():
    rows = []
    for f in sorted(glob.glob(str(RAW_DIR / "raw_press_*.csv"))):
        with open(f, encoding="utf-8") as fh:
            rows.extend(r for r in csv.DictReader(fh) if r.get("artist_handle"))
    return rows


def _save(seen, links):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(seen, ensure_ascii=False, indent=1), encoding="utf-8")
    LINKS.write_text(json.dumps(links, ensure_ascii=False, indent=1), encoding="utf-8")


def _profile_rows():
    rows = []
    for f in sorted(glob.glob(str(RAW_DIR / "raw_artist_profile_*_instagram*.csv"))):
        with open(f, encoding="utf-8") as fh:
            rows += list(csv.DictReader(fh))
    return rows


def collect(limit, handles=None):
    seen = _load_json(STATE, {})                       # {handle: 결과 상태}
    links = _load_json(LINKS, {})
    links.setdefault("non_artists", {})
    outlets = [a["handle"] for a in _load_json(OUTLETS, {}).get("accounts", []) if a.get("role") != "artist"]   # 팀 본인 계정은 팀 후보로 둠
    tag_counts = _load_json(SNOWBALL, {}).get("artists_tag_counts", {})
    now = datetime.now(KST).replace(microsecond=0)
    if handles is not None:                           # 관찰 목록 다시 보기 (이미 본 계정도 7일마다)
        todo = revisit_targets(handles, last_fetched(_profile_rows()), f"{now:%Y-%m-%d}", outlets)[:limit]
    else:
        todo = targets(_press_rows(), tag_counts, seen, outlets)[:limit]
    rows, stats, streak, walls, pauses, path = [], {}, 0, 0, 0, None
    for i in range(0, len(todo), BATCH):
        batch = todo[i:i + BATCH]
        try:
            pages = run_repl(_js(batch))
        except (RuntimeError, subprocess.TimeoutExpired) as e:   # 한 묶음 실패해도 계속 (다음 실행에 다시)
            print(f"⚠️ {batch}: 읽기 실패 ({e})")
            continue
        for handle in batch:
            result = interpret(handle, pages.get(handle, {}))
            status = result["status"]
            stats[status] = stats.get(status, 0) + 1
            streak = wall_streak([status], streak)
            if status == "login_wall":
                walls += 1
                if streak >= WALL_STREAK_LIMIT:
                    pauses += 1
                    print(f"⏸ 로그인 벽 {streak}번 연속 → {WALL_PAUSE_SEC}초 쉼")
                    time.sleep(WALL_PAUSE_SEC)
                    streak = 0
                continue                                  # 다음 실행에 다시
            if status == "unparsed" or pages.get(handle, {}).get("error"):
                continue
            seen[handle] = status
            if status in ("artist", "non_artist"):
                entry = {"name": result["name"], "bio": result["bio"], "followers": result["followers"],
                         "links": result["links"]}
                if status == "artist":
                    links[handle] = entry
                    rows.append(to_row(handle, result, now.isoformat()))
                else:
                    links["non_artists"][handle] = entry
        if rows:                                          # 행을 먼저 쓰고 상태를 저장 (중간에 끊겨도 이어서)
            path = write_csv(rows, RAW_DIR, f"{now:%Y-%m-%d}", path)
        _save(seen, links)
    return path, todo, rows, stats, walls, pauses


def main(argv):
    ap = argparse.ArgumentParser(description="인스타 아티스트 프로필 수집 (aside 브라우저, 로그인 없이)")
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    ap.add_argument("--handles-file", help="한 줄에 인스타 계정 하나 — 이미 봤어도 7일 지났으면 다시 열어 팔로워 수 기록")
    args = ap.parse_args(argv)
    handles = None
    if args.handles_file:
        handles = [x.strip().lstrip("@") for x in Path(args.handles_file).read_text(encoding="utf-8").splitlines() if x.strip()]
    path, todo, rows, stats, walls, pauses = collect(args.limit, handles)
    print(f"결과별: {stats} · 로그인 벽 {walls}번 (60초 쉼 {pauses}번)")
    print(f"✅ 인스타 아티스트 프로필: 대상 {len(todo)}개 → {len(rows)}행" + (f" → {path}" if path else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
