"""음원 플랫폼 인디 신보 수집기 → data/raw/raw_kr_release_<날짜>_<플랫폼>.csv

    python3 scripts/collect_platforms.py                     # 멜론·지니·FLO·벅스, 최근 3일 발매
    python3 scripts/collect_platforms.py --site melon,flo    # 일부만
    python3 scripts/collect_platforms.py --days 7

- 네 곳 모두 robots.txt가 일반 수집을 막아서 aside 브라우저로 하루 한 번 읽는다 (일부러 쉬는 시간은 두지 않고,
  페이지가 뜰 때까지만 기다린다 — 2026-11-26 사용자 지시).
  원본(data/raw/)은 비공개로 둔다.
- 범위: 각 플랫폼의 '국내 인디 최신 앨범' 목록 + 멜론 랩/힙합·R&B 최신 앨범 (장르 확장, 유명 팀은 1.5단계에서 거름).
- 목록 → 처음 보는 앨범만 상세 페이지(발매일·유통사·기획사·장르) → 팀마다 1행.
  이미 본 앨범 번호는 data/raw/state/music_platforms_seen.json 으로 건너뛴다.
- 플랫폼 하나가 실패해도 나머지는 계속한다. 실패는 data/raw/state/platform_errors.log 에도 남긴다.
- 상세 읽기(fetch_details)는 앨범 번호만 있으면 되도록 분리해 두었다. 다른 갈래에서 찾은 팀의
  전체 발매를 나중에 거꾸로 찾아볼 때 그대로 쓴다.
- 형식: docs/csv_spec.md 1장 / scripts/csv_schema.py raw_kr_release
"""
import argparse
import csv
import html
import json
import re
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from collect_gigs import parse_repl_output
from csv_schema import TABLES
from normalize import artist_key, title_key

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
STATE = RAW_DIR / "state" / "music_platforms_seen.json"
ERROR_LOG = RAW_DIR / "state" / "platform_errors.log"
KST = timezone(timedelta(hours=9))
COLUMNS = [f.name for f in TABLES["raw_kr_release"]["fields"]]
PLATFORMS = ("melon", "genie", "flo", "bugs")
REPL_TIMEOUT_SEC = 240
MAX_DETAILS = 200         # 플랫폼마다 하루 상세 페이지 최대 수 (새 앨범은 사실상 다 읽음)
DETAIL_BATCH = 12         # aside 호출 1번에 여는 상세 페이지 수
SEEN_KEEP = 3000
PAGE_WAIT_MS = 3000
DETAIL_WAIT_MS = 2500

LIST_URLS = {
    "bugs": ["https://music.bugs.co.kr/newest/album/nindie?page=1"],
    "genie": ["https://www.genie.co.kr/genre/L0109?genreCode=L0109&pg=1",
              "https://www.genie.co.kr/genre/L0109?genreCode=L0109&pg=2"],
    # 멜론: 인디(GN0500) + 랩/힙합(GN0300) + R&B/Soul(GN0400) — 인디 목록만 보면 다른 장르 신인을 놓쳐서 (2026-11-27)
    "melon": ["https://www.melon.com/genre/album_list.htm?gnrCode=GN0500",
              "https://www.melon.com/genre/album_list.htm?gnrCode=GN0300",
              "https://www.melon.com/genre/album_list.htm?gnrCode=GN0400"],
    "flo": ["https://www.music-flo.com/browse/genre/newalbum/detail/9"],
}
LIST_SELECTOR = {"bugs": "ul.albumList > li", "genie": "tr.list", "melon": "li:has(a.album_name)"}
DETAIL_SELECTOR = {"bugs": "table.info", "genie": ".info-zone", "melon": ".section_info .wrap_info"}
ALBUM_URL = {
    "bugs": "https://music.bugs.co.kr/album/{id}",
    "genie": "https://www.genie.co.kr/detail/albumInfo?axnm={id}",
    "melon": "https://www.melon.com/album/detail.htm?albumId={id}",
    "flo": "https://www.music-flo.com/detail/album/{id}/albumtrack",
}
TYPE_MAP = {"정규": "LP", "싱글": "single", "ep": "EP", "미니": "EP", "ost": "OST", "컴필레이션": "compilation",
            "옴니버스": "compilation", "베스트": "compilation"}

TAG = re.compile(r"<[^>]+>")
DOT_DATE = re.compile(r"(\d{4})[.\-](\d{2})[.\-](\d{2})")


def clean(text):
    return re.sub(r"\s+", " ", html.unescape(TAG.sub(" ", text or ""))).strip()


def map_type(text):
    t = clean(text).strip("[] ").lower()
    return next((v for k, v in TYPE_MAP.items() if k in t), "")


def dot_date(text):
    m = DOT_DATE.search(text or "")
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""


def _album(platform, album_id, title, artists, released_at="", release_type="", genre=""):
    """artists: [(이름, 플랫폼 아티스트 번호), ...]. 번호는 아티스트 메타데이터·동명 팀 구분에 쓴다."""
    pairs = [(clean(n), str(i or "")) for n, i in artists if clean(n)]
    return {"album_id": str(album_id), "title": clean(title), "artists": [n for n, _ in pairs],
            "artist_ids": [i for _, i in pairs],
            "released_at": released_at, "release_type": release_type, "genre": genre,
            "distributor": "", "label": "", "url": ALBUM_URL[platform].format(id=album_id)}


# ── 벅스 ──────────────────────────────────────────────
def parse_bugs_list(items):
    out = []
    for li in items:
        m = re.search(r'albumid="(\d+)"', li)
        title = re.search(r'class="albumTitle">\s*<a[^>]*title="([^"]*)"', li)
        if not m or not title:
            continue
        artists = [(n, i) for i, n in re.findall(
            r'href="[^"]*/artist/(\d+)[^"]*"[^>]*class="artistTitle"[^>]*title="([^"]*)"', li)]
        kind = re.search(r'class="albumType">([^<]*)<', li)
        out.append(_album("bugs", m.group(1), title.group(1), artists, dot_date(li),
                          map_type(kind.group(1)) if kind else ""))
    return out


def _table_pairs(page, row_re):
    return {clean(k): v for k, v in re.findall(row_re, page or "", re.S)}


def parse_bugs_detail(page):
    rows = _table_pairs(page, r'<th[^>]*>(.*?)</th>\s*<td[^>]*>(.*?)</td>')
    genre = "|".join(clean(g) for g in re.findall(r"<a[^>]*>(.*?)</a>", rows.get("장르", "")))
    return {"distributor": clean(rows.get("유통사", "")), "label": clean(rows.get("기획사", "")),
            "genre": genre, "released_at": dot_date(rows.get("발매일", ""))}


# ── 지니 (목록이 곡 단위라 앨범으로 묶음) ──────────────
def parse_genie_list(rows):
    out, seen = [], set()
    for tr in rows:
        m = re.search(r'class="albumtitle[^"]*"[^>]*fnViewAlbumLayer\((\d+)\)[^>]*>(.*?)</a>', tr, re.S)
        if not m or m.group(1) in seen:
            continue
        seen.add(m.group(1))
        artists = [(n, i) for i, n in re.findall(r'class="artist ellipsis"[^>]*fnViewArtist\((\d+)\)[^>]*>(.*?)</a>', tr, re.S)]
        out.append(_album("genie", m.group(1), m.group(2), artists))
    return out


def parse_genie_detail(page):
    rows = _table_pairs(page, r'<img[^>]*alt="([^"]*)"[^>]*>\s*</span>\s*<span class="value">(.*?)</span>\s*</li>')
    genre = "|".join(p.strip() for p in clean(rows.get("장르/스타일", "")).split("/") if p.strip())
    return {"distributor": clean(rows.get("발매사", "")), "label": clean(rows.get("기획사", "")),
            "genre": genre, "released_at": dot_date(rows.get("발매일", ""))}


# ── 멜론 ──────────────────────────────────────────────
def parse_melon_list(items):
    out = []
    for li in items:
        li = re.sub(r'<span class="checkEllipsis".*?</span>\s*</span>', "</span>", li, flags=re.S)
        m = re.search(r"goAlbumDetail\('(\d+)'\);\"[^>]*class=\"[^\"]*album_name[^\"]*\"[^>]*>(.*?)</a>", li, re.S)
        if not m:
            continue
        artists = [(n, i) for i, n in re.findall(
            r"goArtistDetail\('(\d+)'\);?\"[^>]*class=\"artist_name[^\"]*\"[^>]*>(.*?)</a>", li, re.S)]
        out.append(_album("melon", m.group(1), m.group(2), artists))
    return out


def parse_melon_detail(page):
    rows = _table_pairs(page, r"<dt>(.*?)</dt>\s*<dd>(.*?)</dd>")
    kind = re.search(r'class="gubun">(.*?)</span>', page or "", re.S)
    genre = "|".join(p.strip() for p in clean(rows.get("장르", "")).split(",") if p.strip())
    return {"distributor": clean(rows.get("발매사", "")), "label": clean(rows.get("기획사", "")), "genre": genre,
            "released_at": dot_date(rows.get("발매일", "")), "release_type": map_type(kind.group(1)) if kind else ""}


# ── FLO (공개 JSON) ───────────────────────────────────
def parse_flo_list(payload):
    albums = ((payload or {}).get("data") or {}).get("albumList") or []
    out = []
    for a in albums:
        ymd = str(a.get("releaseYmd", ""))
        day = f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:8]}" if re.fullmatch(r"\d{8}", ymd) else ""
        genre = "|".join(g.strip() for g in str(a.get("genreStyle", "")).split(",") if g.strip())
        out.append(_album("flo", a.get("id"), a.get("title", ""),
                          [(x.get("name", ""), x.get("id", "")) for x in a.get("artistList") or []],
                          day, map_type(a.get("albumTypeStr", "")), genre))
    return out


def parse_flo_detail(payload):
    d = (payload or {}).get("data") or {}
    labels = [x.get("labelNm", "") for x in d.get("albumLabelList") or [] if x.get("labelNm")]
    return {"distributor": d.get("agencyNm", "") or "", "label": "|".join(labels)}


# ── 공통 ──────────────────────────────────────────────
def merge_detail(album, detail):
    """상세 정보를 합친 새 앨범을 돌려준다. 발매일·형태는 비어 있을 때만 채운다."""
    merged = dict(album)
    for k in ("distributor", "label", "genre"):
        if detail.get(k):
            merged[k] = detail[k]
    for k in ("released_at", "release_type"):
        if not merged.get(k) and detail.get(k):
            merged[k] = detail[k]
    return merged


def unique_albums(albums):
    """같은 앨범 번호가 목록에 여러 번 나오면 처음 것만 (멜론 목록은 같은 앨범을 두 군데 보여줌)."""
    out, seen = [], set()
    for a in albums:
        if a["album_id"] not in seen:
            seen.add(a["album_id"])
            out.append(a)
    return out


def in_window(day, today, days):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day or ""):
        return False
    first = (date.fromisoformat(today) - timedelta(days=days - 1)).isoformat()
    return first <= day <= today


def to_rows(source, album, collected_at):
    if not album.get("released_at"):
        return []
    base = {"collected_at": collected_at, "source": source, "collector": "aside", "source_id": album["album_id"],
            "released_at": album["released_at"], "artist_source_id": "", "title": album["title"],
            "release_type": album.get("release_type", ""), "genre": album.get("genre", ""),
            "label_text": album.get("label", ""), "track_count": "", "release_url": album["url"],
            "distributor_text": album.get("distributor", ""), "title_key": title_key(album["title"])}
    ids = dict(zip(album["artists"], album.get("artist_ids") or []))
    return [dict(base, artist_text=a, artist_key=artist_key(a), artist_source_id=ids.get(a, ""))
            for a in dict.fromkeys(album["artists"])]


def write_csv(rows, out_dir, day, name):
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"raw_kr_release_{day}_{name}.csv"
    if path.exists():  # 원본은 고치지 않는다
        path = out_dir / f"raw_kr_release_{day}_{name}_{datetime.now(KST):%H%M%S}.csv"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


# ── aside 브라우저 ────────────────────────────────────
def run_repl(code):
    proc = subprocess.run(["aside", "repl", "--json", code], capture_output=True, text=True, timeout=REPL_TIMEOUT_SEC)
    return parse_repl_output(proc.stdout)


def _list_js(platform):
    urls = json.dumps(LIST_URLS[platform])
    if platform == "flo":
        grab = "items.push(await t.evaluate(async () => (await fetch('/api/display/v1/browser/genre/newalbum/9')).json()));"
    else:
        sel = json.dumps(LIST_SELECTOR[platform])
        grab = f"items.push(...await t.evaluate(s => [...document.querySelectorAll(s)].map(e => e.outerHTML), {sel}));"
    # 탭을 비워 두고 이동(goto)하면 멜론에서 이동 시간 초과가 나서, 페이지마다 탭을 새로 열고 닫는다.
    return f"""await (async () => {{
  const items = [];
  for (const u of {urls}) {{ const t = await openTab(u); await sleep({PAGE_WAIT_MS}); {grab} await closeTab(t); }}
  console.log('RESULT ' + JSON.stringify(items));
}})();"""


def _detail_js(platform, album_ids):
    ids = json.dumps(album_ids)
    if platform == "flo":
        return f"""await (async () => {{
  const out = {{}}; const t = await openTab('https://www.music-flo.com/browse/genre/newalbum/detail/9'); await sleep({PAGE_WAIT_MS});
  for (const id of {ids}) {{ out[id] = await t.evaluate(async i => (await fetch('/api/meta/v1/album/' + i)).json(), id); }}
  await closeTab(t); console.log('RESULT ' + JSON.stringify(out));
}})();"""
    tmpl, sel = json.dumps(ALBUM_URL[platform]), json.dumps(DETAIL_SELECTOR[platform])
    return f"""await (async () => {{
  const out = {{}};
  for (const id of {ids}) {{
    try {{
      const t = await openTab({tmpl}.replace('{{id}}', id)); await sleep({DETAIL_WAIT_MS});
      out[id] = await t.evaluate(s => document.querySelector(s)?.outerHTML || '', {sel}); await closeTab(t);
    }} catch (e) {{ out[id] = ''; }}
  }}
  console.log('RESULT ' + JSON.stringify(out));
}})();"""


LIST_PARSERS = {"bugs": parse_bugs_list, "genie": parse_genie_list, "melon": parse_melon_list,
                "flo": lambda items: [a for p in items for a in parse_flo_list(p)]}
DETAIL_PARSERS = {"bugs": parse_bugs_detail, "genie": parse_genie_detail, "melon": parse_melon_detail,
                  "flo": parse_flo_detail}


def fetch_list(platform):
    return LIST_PARSERS[platform](run_repl(_list_js(platform)))


def fetch_details(platform, album_ids):
    """앨범 번호 목록 → {번호: 상세 정보}. 다른 갈래에서 찾은 팀을 거꾸로 찾을 때도 쓴다."""
    out = {}
    for i in range(0, len(album_ids), DETAIL_BATCH):
        raw = run_repl(_detail_js(platform, album_ids[i:i + DETAIL_BATCH]))
        out.update({k: DETAIL_PARSERS[platform](v) for k, v in raw.items()})
    return out


def collect_platform(platform, seen, today, days):
    """한 플랫폼 → (행 목록, 새로 본 앨범 번호). 목록에 날짜가 있으면 기간 밖 앨범은 상세를 열지 않는다."""
    albums = [a for a in unique_albums(fetch_list(platform)) if a["album_id"] not in seen]
    skipped = [a["album_id"] for a in albums if a["released_at"] and not in_window(a["released_at"], today, days)]
    todo = [a for a in albums if a["album_id"] not in skipped][:MAX_DETAILS]
    details = fetch_details(platform, [a["album_id"] for a in todo]) if todo else {}
    at = datetime.now(KST).replace(microsecond=0).isoformat()
    rows = []
    for a in todo:
        merged = merge_detail(a, details.get(a["album_id"], {}))
        if in_window(merged["released_at"], today, days):
            rows.extend(to_rows(platform, merged, at))
    read_ok = [a["album_id"] for a in todo if any(details.get(a["album_id"], {}).values())]   # 못 읽은 앨범은 다음에 다시
    return rows, skipped + read_ok


def _load_seen():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _log_error(platform, err):
    ERROR_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(ERROR_LOG, "a", encoding="utf-8") as fh:
        fh.write(f"{datetime.now(KST):%Y-%m-%dT%H:%M:%S%z} {platform} {type(err).__name__}: {err}\n")


def collect(platforms, days):
    today = f"{datetime.now(KST):%Y-%m-%d}"
    state, paths, report, failed = _load_seen(), [], [], []
    for p in platforms:
        seen = state.get(p, [])
        try:
            rows, new_ids = collect_platform(p, set(seen), today, days)
        except (RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            failed.append(p)
            _log_error(p, e)
            report.append(f"⚠️ {p}: 읽기 실패 ({type(e).__name__}: {str(e)[:120]}) — 나머지 플랫폼은 계속")
            continue
        state[p] = (seen + new_ids)[-SEEN_KEEP:]
        if rows:
            paths.append(write_csv(rows, RAW_DIR, today, p))
        report.append(f"✅ {p}: 새 앨범 {len(new_ids)}개 확인 → 최근 {days}일 발매 {len(rows)}행")
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    return paths, report, failed


def main(argv):
    ap = argparse.ArgumentParser(description="음원 플랫폼 인디 신보 수집 (aside 브라우저, 하루 1번)")
    ap.add_argument("--site", default=",".join(PLATFORMS), help="melon,genie,flo,bugs 중 쉼표로")
    ap.add_argument("--days", type=int, default=3)
    args = ap.parse_args(argv)
    platforms = [p for p in args.site.split(",") if p in PLATFORMS]
    paths, report, failed = collect(platforms, args.days)
    print("\n".join(report + [f"  → {p}" for p in paths]))
    return 1 if platforms and len(failed) == len(platforms) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
