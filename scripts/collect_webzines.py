"""웹 음악 매거진(웹진) 수집기 → data/raw/raw_press_<날짜>_<매체>.csv

    python3 scripts/collect_webzines.py                       # 켜진 매체 전부 (처음이면 2023-01-01부터 되짚기)
    python3 scripts/collect_webzines.py --outlet izm --outlet weiv
    python3 scripts/collect_webzines.py --since 2025-01-01    # 시작일 직접 지정

- 매체 목록·주소·robots 확인 결과: config/webzines.json
  VISLA·weiv(워드프레스 공개 API), IZM(공개 API), 리드머·음악취향Y(목록 페이지), overtone(사이트맵 → 글 페이지).
  모두 robots.txt가 허용하는 주소만 쓰고, 요청 사이에 매체별로 쉰다.
- 글 1개 × 다룬 팀 1팀 = 1행. 팀 이름은 구조화된 칸(IZM artists, 리드머 Artist:, overtone JSON-LD)이나
  제목 형식('팀 – 앨범', '팀 인터뷰', 'Release Talk | …, 팀의 [앨범]')과 태그가 맞을 때만 쓴다(정밀도 우선).
  확실하지 않은 글은 data/raw/review/webzines_unparsed_<날짜>.json 에 모은다.
- 국내/해외 구분이 있는 매체(IZM·리드머·weiv 리뷰)는 국내 글만 받는다.
- 이미 본 글과 마지막 실행일: data/raw/state/webzines_seen.json (비공개). 다음 실행은 마지막 실행일 14일 전부터 새 글만.
"""
import argparse
import csv
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from csv_schema import TABLES

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "webzines.json"
RAW_DIR = ROOT / "data" / "raw"
STATE = RAW_DIR / "state" / "webzines_seen.json"
REVIEW_DIR = RAW_DIR / "review"
USER_AGENT = "crate-digger/0.1 (+https://github.com/leegmyung/crate-digger)"
KST = timezone(timedelta(hours=9))
COLUMNS = [f.name for f in TABLES["raw_press"]["fields"]]
TIMEOUT_SEC = 30
RETRY_WAIT_SEC = 30
MAX_PAGES = 400
SEEN_KEEP = 20000
MAX_ARTISTS_PER_ARTICLE = 6
MAX_SLOT_LEN = 40

TAG = re.compile(r"<[^>]+>")
SPONSORED_RE = re.compile(
    r"협찬|제작\s*지원|유료\s*광고|#광고|\[\s*AD\s*\]|\(\s*AD\s*\)|^\s*AD\s*[|:]|sponsored|paid partnership|브랜디드",
    re.I)


def clean(text):
    return re.sub(r"\s+", " ", html.unescape(TAG.sub(" ", text or ""))).strip()


def squeeze(text):
    """HTML 기호만 풀고 공백 정리 (<앨범> 같은 꺾쇠는 남김)."""
    return re.sub(r"\s+", " ", html.unescape(text or "")).strip()


def is_sponsored(text):
    return bool(SPONSORED_RE.search(text or ""))


def to_kst_date(stamp):
    """'2026-11-21T17:02:32.919Z' → 한국 날짜. 시간대 없는 값은 앞 10글자."""
    stamp = (stamp or "").strip()
    m = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?)(?:\.\d+)?Z$", stamp)
    if m:
        return datetime.fromisoformat(m.group(1)).replace(tzinfo=timezone.utc).astimezone(KST).date().isoformat()
    return stamp[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", stamp) else ""


def article(art_id, url, published_at, title, artists, is_pick, pick_label, release_title="", sponsored=False):
    return {"id": str(art_id), "url": url, "published_at": published_at, "title": title,
            "release_title": release_title, "is_pick": is_pick, "pick_label": pick_label,
            "is_sponsored": "1" if sponsored else "0", "artists": [{"artist": a} for a in artists if a]}


# ---------- 워드프레스 공통 ----------

def wp_terms(post, taxonomy):
    groups = post.get("_embedded", {}).get("wp:term", [])
    return [html.unescape(t.get("name", "")) for g in groups for t in g if t.get("taxonomy") == taxonomy]


# ---------- VISLA ----------

VISLA_PREFIX = re.compile(r"^\s*(Release Talk|Helicopter Talks|in their playlist|디거의 노래|地下의 소리(?:\s*#\d+)?|독자생존)\s*[|:]?\s*", re.I)
BRACKETED = re.compile(r"\[[^\]]*\]|“[^”]*”|\"[^\"]*\"|「[^」]*」|『[^』]*』|<[^>]*>|〈[^〉]*〉")
LABEL_LIKE = re.compile(r"레코드|records?\b|recordings|레이블|\blabel\b|뮤직비디오", re.I)
SLOT_LABELS = {"Interview", "in their playlist", "디거의 노래"}
ROLE_WORDS = (r"(?:밴드|래퍼|프로듀서|뮤지션|싱어송라이터|듀오|트리오|그룹|아티스트|디제이|DJ|피아니스트|기타리스트|베이시스트|"
              r"드러머|보컬|가수|전자음악가|작곡가|프론트맨|멤버|팀|걸그룹|보이그룹|크루|콜렉티브|레이블 대표)")
HANGUL_PRE = re.compile(r"(?:^|[,|:&×]|[와과]|" + ROLE_WORDS + r")\s*$")
HANGUL_POST = re.compile(r"^(?:\s*$|\s*[,&×|:]|의\s|의$|[와과가이는은를을]\s|\s+인터뷰|\s*\()")


def _hangul_position_ok(text, start, end):
    """한글 이름은 '이름 자리'(제목 맨 앞, 쉼표 뒤, '밴드 ○○', '○○의', '○○와')에 있을 때만 믿는다."""
    return bool(HANGUL_PRE.search(text[:start]) and HANGUL_POST.match(text[end:]))


def _tag_pattern(tag):
    parts = [re.escape(p) for p in tag.split()]
    body = r"\s*".join(parts)
    start = r"(?<![A-Za-z0-9가-힣])"
    end = r"(?![A-Za-z0-9])" if re.search(r"[A-Za-z0-9]$", tag) else ""
    return re.compile(start + body + end, re.I)


def _usable_tag(tag, stop):
    t = tag.strip()
    if len(re.sub(r"\W", "", t)) < 2 or t.lower() in stop or t.lstrip("#").lower() in stop:
        return False
    return not LABEL_LIKE.search(t)


def tags_in_text(text, tags, stop):
    """본문 글자 안에 나온 태그들(겹치면 긴 쪽만)을 나온 순서대로."""
    spans = []
    labels = [t.strip().lower() for t in tags if LABEL_LIKE.search(t)]
    for tag in dict.fromkeys(t.strip() for t in tags):
        if not _usable_tag(tag, stop) or any(lb.startswith(tag.lower() + " ") for lb in labels):
            continue
        m = _tag_pattern(tag).search(text)
        if m and (re.search(r"[A-Za-z0-9]", m.group(0)) or _hangul_position_ok(text, m.start(), m.end())):
            spans.append((m.start(), m.end(), m.group(0)))   # 제목에 쓰인 모양 그대로 (대소문자·띄어쓰기)
    keep = [s for s in spans if not any(o != s and o[0] <= s[0] and s[1] <= o[1] and (o[1] - o[0]) > (s[1] - s[0]) for o in spans)]
    return list(dict.fromkeys(name for _, _, name in sorted(keep)))


def parse_visla(post, stop):
    title = clean(post.get("title", {}).get("rendered", ""))
    cats = [c.upper() for c in wp_terms(post, "category")]
    tags = wp_terms(post, "post_tag")
    rest, label = title, ""
    m = VISLA_PREFIX.match(rest)
    if m:
        label = re.sub(r"\s*#\d+$", "", m.group(1))
        label = "Release Talk" if label.lower() == "release talk" else label
        rest = rest[m.end():]
    if re.search(r"\s인터뷰\s*$", rest):
        label = label or "Interview"
        rest = re.sub(r"\s인터뷰\s*$", "", rest)
    rel = re.search(r"\[([^\]]+)\]", rest)
    release = rel.group(1).strip() if rel else ""
    body = BRACKETED.sub(" ", rest)
    stop_all = set(stop) | ({release.lower()} if release else set())
    artists = tags_in_text(body, tags, stop_all)
    slot = body.split(",")[-1].strip()
    slot = re.sub(r"의\s*$", "", slot).strip()
    if artists and len(artists) > 1:
        in_slot = tags_in_text(slot, artists, stop_all)
        if in_slot and label in SLOT_LABELS | {"Release Talk"}:
            artists = in_slot
    if not artists and label in SLOT_LABELS and 0 < len(slot) <= MAX_SLOT_LEN and len(slot.split()) <= 5:
        artists = [slot]
    if len(artists) > MAX_ARTISTS_PER_ARTICLE:
        artists = []
    is_feature = "FEATURE" in cats or "INTERVIEW" in cats
    pick_label = label or ("Feature" if is_feature else "News")
    sponsored = "SPONSOR" in cats or is_sponsored(" ".join([title] + tags))
    return article(post.get("id"), post.get("link", ""), to_kst_date(post.get("date", "")) or post.get("date", "")[:10],
                   title, artists, "1" if is_feature or label else "0", pick_label, release, sponsored)


# ---------- weiv ----------

def split_outside_parens(text, sep=","):
    parts, depth, cur = [], 0, ""
    for ch in text:
        if ch in "([（":
            depth += 1
        elif ch in ")]）":
            depth -= 1
        if ch == sep and depth <= 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return [p.strip() for p in parts if p.strip()]


def _squash(text):
    return re.sub(r"\W", "", (text or "").lower())


def parse_weiv(post):
    cats = {c.lower() for c in wp_terms(post, "category")}
    if "interview" in cats:
        label, sep = "Interview", "|"
    elif "track" in cats:
        label, sep = "Track Review", "–"
    elif "local" in cats:
        label, sep = "Album Review", "–"
    else:
        return None   # 해외 리뷰·칼럼·믹스테잎은 받지 않음
    title = clean(post.get("title", {}).get("rendered", ""))
    if sep not in title:
        return article(post.get("id"), post.get("link", ""), post.get("date", "")[:10], title, [], "1", label)
    head, tail = [s.strip() for s in title.split(sep, 1)]
    release = re.sub(r"\s*\(\d{4}\)\s*$", "", tail) if sep == "–" else ""
    pieces = split_outside_parens(head)
    tags = wp_terms(post, "post_tag")
    matched = any(_squash(t) and _squash(t) in _squash(p) for p in pieces for t in tags)
    if not matched and len(tags) == 1:
        pieces = tags   # 번역본(일본어·중국어 제목)은 한국어 태그로
    return article(post.get("id"), post.get("link", ""), post.get("date", "")[:10], title, pieces, "1", label, release,
                   is_sponsored(title))


# ---------- IZM ----------

def parse_izm(item):
    main, sub, detail = item.get("main_category"), item.get("sub_category") or "", item.get("detail_category") or ""
    if main == "Review":
        if detail != "국내":
            return None
        is_pick, label = "1", f"{sub} 리뷰".strip()
    elif main == "Interview":
        is_pick, label = "1", "Interview"
    elif main == "Feature":
        is_pick, label = "0", f"Feature {sub}".strip()
    else:
        return None
    names = []
    for a in item.get("artists") or []:
        kr, en = (a.get("kr_name") or "").strip(), (a.get("en_name") or "").strip()
        names.append(f"{kr} ({en})" if kr and en and kr.lower() != en.lower() else (kr or en))
    if main == "Feature" and not names:
        return None
    title = clean(item.get("title", ""))
    return article(item.get("id"), f"https://izm.co.kr/posts?id={item.get('id')}", (item.get("created") or "")[:10],
                   title, names, is_pick, label, title if main == "Review" else "", is_sponsored(title))


# ---------- 리드머 ----------

RHYTHMER_ITEM = re.compile(
    r'<li class="tit"><a href="[^"]*?n=(\d+)[^"]*">(.*?)</a></li>\s*'
    r'<li class="txt"><a[^>]*>Artist:([^\r\n]*)\r?\nAlbum:([^\r\n]*).*?'
    r'<strong class="author">[^<]*</strong>\s*\S+\s*(\d{4}-\d{2}-\d{2})', re.S)


def parse_rhythmer_list(page_html, pick_label="국내 리뷰"):
    out = []
    for n, title, artist, album, posted in RHYTHMER_ITEM.findall(page_html or ""):
        out.append(article(n, f"http://board.rhythmer.net/src/go.php?n={n}&m=view&s=review", posted, clean(title),
                           [clean(artist)], "1", pick_label, clean(album), is_sponsored(title)))
    return out


# ---------- 음악취향Y ----------

MUSICY_ITEM = re.compile(
    r'<dd class="y_title"><a href="[^"]*?ix=(\d+)"><strong class="y_album">(.*?)</strong>'
    r'<span class="y_artist">(.*?)</span></a></dd>.*?<dd class="by">.*?<span>(\d{4})\.(\d{2})\.(\d{2})</span>', re.S)


def parse_musicy_list(page_html):
    out = []
    for ix, album, artist, y, mo, d in MUSICY_ITEM.findall(page_html or ""):
        album = clean(album)
        album = "" if re.fullmatch(r"[_\s]*", album) else album
        artist = clean(artist)
        names = [a.strip() for a in artist.split("×")] if "×" in artist else [artist]
        title = f"[Single-Out] {artist} 「{album}」" if album else f"[Single-Out] {artist}"
        out.append(article(ix, f"http://musicy.kr/?c=review&s=1&gbn=view&ix={ix}", f"{y}-{mo}-{d}", title, names,
                           "1", "Single-Out", album, is_sponsored(title)))
    return out


# ---------- overtone ----------

LD_JSON = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
OT_SECTION_LABEL = {"full-review": "Full Review", "interview": "Interview", "comment": "Comment"}


def _meta(page, prop):
    m = re.search(rf'<meta (?:property|name)="{re.escape(prop)}" content="([^"]*)"', page)
    return html.unescape(m.group(1)) if m else ""


def _ld_items(page):
    out = []
    for block in LD_JSON.findall(page):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        out.extend(data if isinstance(data, list) else [data])
    return out


def parse_overtone_page(url, page):
    section = urllib.parse.urlparse(url).path.strip("/").split("/")[0]
    label = OT_SECTION_LABEL.get(section, section)
    lds = [x for x in _ld_items(page) if isinstance(x, dict)]
    main = next((x for x in lds if x.get("@type") in ("CriticReview", "Article")), {})
    published = to_kst_date(main.get("datePublished") or _meta(page, "article:published_time") or _meta(page, "article:modified_time"))
    title = squeeze(main.get("headline") or re.sub(r"\s*-\s*overtone\s*$", "", _meta(page, "og:title")))
    artists, release = [], ""
    if section == "full-review":
        name = squeeze((main.get("itemReviewed") or {}).get("name", ""))
        m = re.match(r"^(.+?)\s*[<〈](.*?)[>〉]?\s*$", name)
        if m:
            artists, release = [m.group(1).strip()], m.group(2).strip()
    elif section == "interview":
        about = main.get("about")
        if isinstance(about, str) and about.strip() and about.strip() != title:
            artists = [squeeze(about)]
    elif section == "comment":
        m = re.search(r"<p>Artist</p><p>Release</p>.*?</div>\s*<div[^>]*>\s*<p[^>]*>(.*?)</p>", page, re.S)
        if m:
            artists = [clean(m.group(1))]
        r = re.search(r'<span class="comment-title-measure[^"]*"[^>]*>(.*?)</span>', page, re.S)
        release = clean(r.group(1)) if r else ""
    return article(url, url, published, title, artists, "1", label, release, is_sponsored(title))


def parse_overtone_sitemap(xml, sections, since):
    out = []
    for loc, lastmod in re.findall(r"<loc>([^<]+)</loc>\s*(?:<lastmod>([^<]*)</lastmod>)?", xml):
        path = urllib.parse.unquote(urllib.parse.urlparse(loc).path).strip("/")
        if path.split("/")[0] in sections and path.count("/") == 1 and (not lastmod or lastmod[:10] >= since):
            out.append(loc.strip())
    return out


# ---------- 행 만들기·저장 ----------

def to_rows(source, outlet, art, collected_at):
    sponsored = art.get("is_sponsored") == "1" or is_sponsored(art.get("title", ""))
    base = {"collected_at": collected_at, "source": source, "collector": "script", "outlet": outlet,
            "published_at": art["published_at"], "title": art["title"][:200], "url": art["url"],
            "release_title": art.get("release_title", ""), "is_pick": art["is_pick"], "pick_label": art.get("pick_label", ""),
            "artist_handle": "", "is_sponsored": "1" if sponsored else "0"}
    names = list(dict.fromkeys(a["artist"].strip() for a in art["artists"] if a.get("artist", "").strip()))
    return [dict(base, artist_text=n) for n in names]


def write_csv(rows, out_dir, day, outlet):
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"raw_press_{day}_{outlet}.csv"
    if path.exists():   # 원본은 고치지 않는다 → 같은 날 다시 받으면 시각을 붙인 새 파일
        path = out_dir / f"raw_press_{day}_{outlet}_{datetime.now(KST):%H%M%S}.csv"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def since_for(outlet_state, backfill_since, today, overlap_days=14):
    last = (outlet_state or {}).get("last_run")
    if not last:
        return backfill_since
    return (date.fromisoformat(last) - timedelta(days=overlap_days)).isoformat()


# ---------- 네트워크 ----------

def http_get(url, encoding="utf-8", timeout=TIMEOUT_SEC):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as res:
                return res.read().decode(encoding, "replace")
        except urllib.error.HTTPError as e:
            if e.code in (429, 502, 503, 504) and attempt == 0:
                time.sleep(RETRY_WAIT_SEC)
                continue
            raise
    raise RuntimeError(f"요청 실패: {url}")


def _wp_pages(api, since, delay, extra=None):
    """워드프레스 글 목록을 100개씩. since 이후 글만 (서버가 거름)."""
    for page in range(1, MAX_PAGES + 1):
        params = {"per_page": 100, "page": page, "after": f"{since}T00:00:00", "_embed": "wp:term",
                  "_fields": "id,date,link,title,_links,_embedded", **(extra or {})}
        try:
            posts = json.loads(http_get(f"{api}?{urllib.parse.urlencode(params)}"))
        except urllib.error.HTTPError as e:
            if e.code == 400:   # 마지막 페이지를 넘음
                return
            raise
        yield posts
        if len(posts) < 100:
            return
        time.sleep(delay)


def fetch_visla(cfg, since):
    stop = {s.lower() for s in cfg.get("stop_tags", [])}
    for posts in _wp_pages(cfg["api"], since, cfg["delay_sec"], {"categories": cfg["category_id"]}):
        yield [(str(p["id"]), p.get("date", "")[:10], parse_visla(p, stop)) for p in posts]


def fetch_weiv(cfg, since):
    for posts in _wp_pages(cfg["api"], since, cfg["delay_sec"]):
        yield [(str(p["id"]), p.get("date", "")[:10], parse_weiv(p)) for p in posts]


def _izm_page(api, page, size):
    return json.loads(http_get(f"{api}?page={page}&page_size={size}"))


def _izm_range(api, page, size, delay, small=10):
    """한 페이지가 서버 오류(500)면 작은 페이지로 쪼개 받고, 그래도 깨지는 글 1개만 건너뛴다."""
    try:
        return _izm_page(api, page, size)["results"], 0
    except urllib.error.HTTPError as e:
        if e.code != 500 or size <= 1:
            raise
    items, skipped, step = [], 0, small if size > small else 1
    first = (page - 1) * size // step + 1
    for sub in range(first, first + size // step):
        time.sleep(delay)
        try:
            got, bad = _izm_range(api, sub, step, delay, small=1)
        except urllib.error.HTTPError as e:
            if e.code == 404:   # 끝을 넘음
                break
            if e.code == 500 and step == 1:   # 깨진 글 1개
                skipped += 1
                continue
            raise
        items.extend(got)
        skipped += bad
    return items, skipped


def fetch_izm(cfg, since):
    for page in range(1, MAX_PAGES + 1):
        items, skipped = _izm_range(cfg["api"], page, cfg["page_size"], cfg["delay_sec"])
        if skipped:
            print(f"   ⚠️ IZM {page}쪽: 서버 오류로 글 {skipped}개 건너뜀", file=sys.stderr)
        yield [(str(i["id"]), (i.get("created") or "")[:10], parse_izm(i)) for i in items]
        if len(items) + skipped < cfg["page_size"] or not items or min((i.get("created") or "")[:10] for i in items) < since:
            return
        time.sleep(cfg["delay_sec"])


def _list_pages(cfg, since, parser):
    for page in range(1, MAX_PAGES + 1):
        arts = parser(http_get(cfg["list_url"].format(page=page)))
        yield [(a["id"], a["published_at"], a) for a in arts]
        if not arts or min(a["published_at"] for a in arts) < since:
            return
        time.sleep(cfg["delay_sec"])


def fetch_rhythmer(cfg, since):
    yield from _list_pages(cfg, since, lambda h: parse_rhythmer_list(h, cfg.get("pick_label", "국내 리뷰")))


def fetch_musicy(cfg, since):
    yield from _list_pages(cfg, since, parse_musicy_list)


def fetch_overtone(cfg, since, seen=()):
    # 사이트맵은 늘 되짚기 시작일부터 본다: 지난번 읽기 실패한 옛 글도 '본 글'이 아니면 다시 시도
    floor = min(since, cfg.get("backfill_since", since))
    local = cfg.get("sitemap_file")   # 사이트맵이 안 열릴 때 미리 받아 둔 사본 (--sitemap-file)
    xml = Path(local).read_text(encoding="utf-8") if local else http_get(cfg["sitemap"], timeout=cfg.get("sitemap_timeout_sec", 300))
    urls = [u for u in parse_overtone_sitemap(xml, cfg["sections"], floor) if u not in seen]
    batch = []
    for url in urls:
        time.sleep(cfg["delay_sec"])
        try:
            art = parse_overtone_page(url, http_get(url))
        except (urllib.error.URLError, OSError) as e:   # socket.timeout(3.9)도 OSError
            print(f"   ⚠️ overtone 글 읽기 실패 (다음에 다시): {url} ({e})", file=sys.stderr)
            continue
        batch.append((url, art["published_at"], art))
        if len(batch) >= 50:
            yield batch
            batch = []
    if batch:
        yield batch


FETCHERS = {"visla": fetch_visla, "weiv": fetch_weiv, "izm": fetch_izm, "rhythmer": fetch_rhythmer,
            "musicy": fetch_musicy, "overtone": fetch_overtone}


# ---------- 실행 ----------

class CsvAppender:
    """매체별 CSV를 묶음마다 이어 쓴다 (중간에 끊겨도 받은 데까지는 남게)."""

    def __init__(self, out_dir, day, outlet):
        self.out_dir, self.day, self.outlet, self.path = out_dir, day, outlet, None

    def add(self, rows):
        if not rows:
            return
        if self.path is None:
            self.path = write_csv(rows, self.out_dir, self.day, self.outlet)
            return
        with open(self.path, "a", encoding="utf-8", newline="") as fh:
            csv.DictWriter(fh, fieldnames=COLUMNS).writerows(rows)


def collect_outlet(code, cfg, since, seen, collected_at, on_batch=None):
    """→ (행 수, 검수 대기, 새로 본 글 id, 날짜 범위, 범위 안 글 수). 묶음마다 on_batch(행, 검수, id)를 부른다."""
    fetch = FETCHERS[code]
    pages = fetch(cfg, since, seen) if code == "overtone" else fetch(cfg, since)
    n_rows, review, new_ids, dates, in_scope = 0, [], [], [], 0
    if code == "overtone":   # 사이트맵 방식은 '본 글'로만 거른다 (실패했던 옛 글 재시도)
        since = min(since, cfg.get("backfill_since", since))
    for batch in pages:
        b_rows, b_review, b_ids = [], [], []
        for art_id, day, art in batch:
            if not day or day < since or art_id in seen:
                continue
            b_ids.append(art_id)
            if art is None:
                continue
            in_scope += 1
            dates.append(day)
            got = to_rows(code, cfg["name"], art, collected_at)
            if got:
                b_rows.extend(got)
            else:
                b_review.append({"outlet": code, "url": art["url"], "date": day, "title": art["title"],
                                 "pick_label": art.get("pick_label", "")})
        n_rows += len(b_rows)
        review.extend(b_review)
        new_ids.extend(b_ids)
        if on_batch:
            on_batch(b_rows, b_review, b_ids)
    return n_rows, review, new_ids, (min(dates), max(dates)) if dates else ("", ""), in_scope


def _load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _save_review(items, today):
    if not items:
        return None
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    rpath = REVIEW_DIR / f"webzines_unparsed_{today}.json"   # 같은 날 여러 번 돌면 이어 붙인다
    known = _load_json(rpath, [])
    have = {(r.get("outlet"), r.get("url")) for r in known}
    rpath.write_text(json.dumps(known + [r for r in items if (r["outlet"], r["url"]) not in have],
                                ensure_ascii=False, indent=1), encoding="utf-8")
    return rpath


def _save_state(state):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def collect(only=None, since_override=None, sitemap_file=None):
    """매체마다: 묶음(페이지)이 끝날 때마다 CSV·검수 목록·상태(본 글)를 저장 → 끊겨도 다시 돌리면 이어서.
    끝까지 마친 매체만 last_run을 오늘로 바꾼다."""
    now = datetime.now(KST).replace(microsecond=0)
    today = f"{now:%Y-%m-%d}"
    config = _load_json(CONFIG, {})
    state = _load_json(STATE, {})
    report = []
    for code, cfg in config.get("outlets", {}).items():
        if (only and code not in only) or (not only and not cfg.get("enabled")) or code not in FETCHERS:
            continue
        ostate = state.setdefault(code, {})
        since = since_override or since_for(ostate, config.get("backfill_since", "2023-01-01"), today,
                                            config.get("overlap_days", 14))
        seen = set(ostate.get("seen", []))
        cfg = dict(cfg, backfill_since=config.get("backfill_since", "2023-01-01"))
        if sitemap_file and code == "overtone":
            cfg["sitemap_file"] = sitemap_file
        out = CsvAppender(RAW_DIR, today, code)

        def on_batch(rows, review, ids, ostate=ostate, out=out):
            out.add(rows)
            _save_review(review, today)
            ostate["seen"] = (list(ostate.get("seen", [])) + ids)[-SEEN_KEEP:]
            _save_state(state)

        try:
            n_rows, review, _, (first, last), in_scope = collect_outlet(code, cfg, since, seen, now.isoformat(), on_batch)
        except (urllib.error.URLError, OSError, ValueError, KeyError) as e:   # 매체 하나 실패해도 계속
            report.append(f"⚠️ {cfg['name']}: 중간에 실패 ({e}) → 받은 데까지 저장, 다시 돌리면 이어서"
                          + (f" ({out.path.name})" if out.path else ""))
            continue
        parsed = in_scope - len(review)
        rate = f"{parsed / in_scope:.0%}" if in_scope else "-"
        report.append(f"✅ {cfg['name']}: {since}~ 글 {in_scope}개({first}~{last}) → {n_rows}행, 팀 찾음 {parsed}/{in_scope} ({rate})"
                      + (f" → {out.path.name}" if out.path else "") + (f", 검수 대기 {len(review)}" if review else ""))
        ostate["last_run"] = today
        _save_state(state)
    return report


def main(argv):
    ap = argparse.ArgumentParser(description="웹진 수집 (VISLA·weiv·IZM·리드머·음악취향Y·overtone)")
    ap.add_argument("--outlet", action="append", help="이 매체만 (여러 번 쓸 수 있음). 꺼진 매체도 지정하면 돈다")
    ap.add_argument("--since", help="이 날짜(YYYY-MM-DD) 이후 글만. 안 쓰면 상태 파일 기준")
    ap.add_argument("--sitemap-file", help="overtone 사이트맵이 안 열릴 때 쓸 로컬 사본 (sitemap.xml)")
    args = ap.parse_args(argv)
    print("\n".join(collect(set(args.outlet or []), args.since, args.sitemap_file)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
