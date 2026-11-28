"""포크라노스 신보 수집기 → data/raw/raw_kr_release_<날짜>_poclanos.csv

    python3 scripts/collect_poclanos.py              # 최근 3일 발매
    python3 scripts/collect_poclanos.py --days 7     # 최근 7일

- 목록: 공개 API /wp-json/wp/v2/download (robots.txt 허용)
- 상세: 앨범 페이지에서 레이블·형태·곡 수 (앨범마다 1번, 요청 사이 1초 쉼)
- 형식: docs/csv_spec.md / scripts/csv_schema.py
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
from datetime import datetime, timedelta, timezone
from pathlib import Path

from csv_schema import TABLES
from normalize import artist_key, title_key

ROOT = Path(__file__).resolve().parent.parent
API = "https://poclanos.com/wp-json/wp/v2/download"
USER_AGENT = "crate-digger/0.1 (+https://github.com/leegmyung/crate-digger)"
KST = timezone(timedelta(hours=9))
PER_PAGE = 100
MAX_PAGES = 10
REQUEST_DELAY_SEC = 0.3
COLUMNS = [f.name for f in TABLES["raw_kr_release"]["fields"]]
STATE = ROOT / "data" / "raw" / "state" / "poclanos_seen.json"   # 이미 받은 앨범 번호 (같은 날 재실행 중복 방지)
SEEN_KEEP = 3000

INFO_ROW = re.compile(r'<span class="title-left">\s*([^<]+?)\s*</span>(.*?)</li>', re.S)
TRACKLIST = re.compile(r'<ul class="album-tracklist">(.*?)</ul>', re.S)
TAG = re.compile(r"<[^>]+>")


def clean(text):
    return re.sub(r"\s+", " ", html.unescape(TAG.sub(" ", text or ""))).strip()


def map_format(text):
    t = (text or "").strip().lower().replace(".", "")
    if t == "single":
        return "single"
    if t in ("ep", "mini album", "mini"):
        return "EP"
    if t in ("album", "full album", "lp", "regular album", "정규"):
        return "LP"
    if t in ("ost", "soundtrack"):
        return "OST"
    if t in ("compilation", "va", "various artists"):
        return "compilation"
    return ""


def parse_detail(page_html):
    info = {k.strip().lower(): clean(v) for k, v in INFO_ROW.findall(page_html or "")}
    tracklist = TRACKLIST.search(page_html or "")
    tracks = tracklist.group(1).count('class="tno"') if tracklist else 0
    released = info.get("release", "")
    return {
        "released_at": released if re.match(r"^\d{4}(-\d{2}(-\d{2})?)?$", released) else "",
        "label_text": info.get("label", ""),
        "release_type": map_format(info.get("format", "")),
        "track_count": str(tracks) if tracks else "",
    }


def _terms(item, taxonomy):
    groups = item.get("_embedded", {}).get("wp:term", [])
    return [t for group in groups for t in group if t.get("taxonomy") == taxonomy]


def _release_date(page_date, post_date):
    """상세 페이지 발매일. 비었거나 '2026'·'2026-11'처럼 덜 자세한데 글 날짜와 같은 해·달이면 글 날짜를 쓴다
    (연도만 남기면 시점 규칙이 그해 12-31로 읽어 미래 신호가 된다). 더 옛 연도(재발매 원래 연도)는 그대로."""
    if not page_date:
        return post_date
    if len(page_date) < 10 and post_date.startswith(page_date):
        return post_date
    return page_date


def to_rows(item, detail, collected_at):
    base = {
        "collected_at": collected_at,
        "source": "poclanos",
        "collector": "script",
        "source_id": str(item["id"]),
        "released_at": _release_date(detail["released_at"], item.get("date", "")[:10]),
        "title": clean(item.get("title", {}).get("rendered", "")),
        "release_type": detail["release_type"],
        "genre": "|".join(clean(t["name"]) for t in _terms(item, "download_category")),
        "label_text": detail["label_text"],
        "track_count": detail["track_count"],
        "release_url": item.get("link", ""),
    }
    base["title_key"] = title_key(base["title"])
    if not base["title"]:   # 제목 없는 글은 필수 칸이 비어 파일 전체가 형식 검사에서 빠지므로 행을 만들지 않는다
        return []
    artists = [a for a in _terms(item, "download_artist") if clean(a.get("name", ""))]   # 팀 태그 없는 앨범도 같은 이유로 뺀다
    return [dict(base, artist_text=clean(a["name"]), artist_source_id=str(a["id"]), artist_key=artist_key(clean(a["name"])))
            for a in artists]


def new_items(items, seen):
    return [i for i in items if str(i.get("id")) not in seen]


def _load_seen():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def write_csv(rows, out_dir, day, tag="poclanos"):
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"raw_kr_release_{day}_{tag}.csv"
    if path.exists():  # 원본은 고치지 않는다 → 같은 날 다시 받으면 시각을 붙여 새 파일
        path = out_dir / f"raw_kr_release_{day}_{tag}_{datetime.now(KST):%H%M%S}.csv"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def http_get(url, retries=3):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt == retries:
                raise RuntimeError(f"{url} 요청 실패: {e}") from e
            time.sleep(REQUEST_DELAY_SEC * 3 * attempt)
    return ""


def list_items(since, until=None, max_pages=MAX_PAGES):
    """since 이후 글. until(YYYY-MM-DD)을 주면 그날까지, max_pages=None 이면 쪽 수 제한 없이(과거 되짚기)."""
    items = []
    page = 0
    while max_pages is None or page < max_pages:
        page += 1
        params = {
            "per_page": PER_PAGE, "page": page, "_embed": "wp:term",
            "after": since.strftime("%Y-%m-%dT00:00:00"), "orderby": "date", "order": "desc",
        }
        if until:
            nxt = datetime.strptime(until, "%Y-%m-%d") + timedelta(days=1)
            params["before"] = nxt.strftime("%Y-%m-%dT00:00:00")
        batch = json.loads(http_get(f"{API}?{urllib.parse.urlencode(params)}"))
        items.extend(batch)
        if len(batch) < PER_PAGE:
            break
        time.sleep(REQUEST_DELAY_SEC)
    return items


def collect(days, out_dir, since=None, until=None):
    """매일: 최근 days일. 과거 되짚기(since·until): 쪽 수 제한 없이, 파일 이름 ..._poclanos_backfill,
    매일 수집 상태(seen, 최근 SEEN_KEEP개)는 바꾸지 않는다 — 과거 번호 수천 개가 최근 번호를 밀어내지 않게."""
    now = datetime.now(KST).replace(microsecond=0)
    backfill = since is not None
    start = datetime.strptime(since, "%Y-%m-%d") if backfill else now - timedelta(days=days)
    seen = _load_seen()
    listed = list_items(start, until, None) if backfill else list_items(start)
    items = new_items(listed, set(seen))
    rows, failed = [], []
    for item in items:
        time.sleep(REQUEST_DELAY_SEC)
        try:
            detail = parse_detail(http_get(item["link"]))
        except RuntimeError as e:
            failed.append(item.get("link", ""))
            print(f"  ⚠️ 상세 페이지 실패, 목록 정보만 저장: {e}", file=sys.stderr)
            detail = parse_detail("")
        rows.extend(to_rows(item, detail, now.isoformat()))
    tag = "poclanos_backfill" if backfill else "poclanos"
    path = write_csv(rows, out_dir, f"{now:%Y-%m-%d}", tag) if rows else None
    if backfill:
        return path, len(items), len(rows), failed
    done = [str(i["id"]) for i in items if i.get("link", "") not in failed]   # 상세 실패분은 다음에 다시
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps((seen + done)[-SEEN_KEEP:]), encoding="utf-8")
    return path, len(items), len(rows), failed


def main(argv):
    ap = argparse.ArgumentParser(description="포크라노스 신보 수집")
    ap.add_argument("--days", type=int, default=3, help="최근 며칠 발매를 받을지 (기본 3)")
    ap.add_argument("--out", default=str(ROOT / "data" / "raw"), help="저장 폴더 (기본 data/raw)")
    ap.add_argument("--since", help="과거 되짚기: 이 날짜(YYYY-MM-DD)부터 (매일 상태는 안 바꿈)")
    ap.add_argument("--until", help="과거 되짚기: 이 날짜까지 (기본: 오늘)")
    args = ap.parse_args(argv)
    if args.days < 1 or args.days > 60:
        ap.error("--days 는 1~60 사이로 주세요")
    for v in (args.since, args.until):
        if v and not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            ap.error("날짜는 YYYY-MM-DD 로 주세요")
    if args.until and not args.since:
        ap.error("--until 은 --since 와 함께 주세요")
    try:
        path, n_items, n_rows, failed = collect(args.days, Path(args.out), args.since, args.until)
    except RuntimeError as e:
        print(f"❌ 수집 실패: {e}", file=sys.stderr)
        return 1
    print(f"✅ 새 앨범 {n_items}건 → {n_rows}행" + (f" 저장: {path}" if path else " (새 파일 없음)")
          + (f" (상세 실패 {len(failed)}건)" if failed else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
