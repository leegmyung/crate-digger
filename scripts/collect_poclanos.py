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


def to_rows(item, detail, collected_at):
    base = {
        "collected_at": collected_at,
        "source": "poclanos",
        "collector": "script",
        "source_id": str(item["id"]),
        "released_at": detail["released_at"] or item.get("date", "")[:10],
        "title": clean(item.get("title", {}).get("rendered", "")),
        "release_type": detail["release_type"],
        "genre": "|".join(clean(t["name"]) for t in _terms(item, "download_category")),
        "label_text": detail["label_text"],
        "track_count": detail["track_count"],
        "release_url": item.get("link", ""),
    }
    base["title_key"] = title_key(base["title"])
    artists = _terms(item, "download_artist") or [{"id": "", "name": ""}]
    return [dict(base, artist_text=clean(a["name"]), artist_source_id=str(a["id"]), artist_key=artist_key(clean(a["name"])))
            for a in artists]


def new_items(items, seen):
    return [i for i in items if str(i.get("id")) not in seen]


def _load_seen():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def write_csv(rows, out_dir, day):
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"raw_kr_release_{day}_poclanos.csv"
    if path.exists():  # 원본은 고치지 않는다 → 같은 날 다시 받으면 시각을 붙여 새 파일
        path = out_dir / f"raw_kr_release_{day}_poclanos_{datetime.now(KST):%H%M%S}.csv"
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


def list_items(since):
    items = []
    for page in range(1, MAX_PAGES + 1):
        query = urllib.parse.urlencode({
            "per_page": PER_PAGE, "page": page, "_embed": "wp:term",
            "after": since.strftime("%Y-%m-%dT00:00:00"), "orderby": "date", "order": "desc",
        })
        batch = json.loads(http_get(f"{API}?{query}"))
        items.extend(batch)
        if len(batch) < PER_PAGE:
            break
        time.sleep(REQUEST_DELAY_SEC)
    return items


def collect(days, out_dir):
    now = datetime.now(KST).replace(microsecond=0)
    since = now - timedelta(days=days)
    seen = _load_seen()
    items = new_items(list_items(since), set(seen))
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
    path = write_csv(rows, out_dir, f"{now:%Y-%m-%d}") if rows else None
    done = [str(i["id"]) for i in items if i.get("link", "") not in failed]   # 상세 실패분은 다음에 다시
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps((seen + done)[-SEEN_KEEP:]), encoding="utf-8")
    return path, len(items), len(rows), failed


def main(argv):
    ap = argparse.ArgumentParser(description="포크라노스 신보 수집")
    ap.add_argument("--days", type=int, default=3, help="최근 며칠 발매를 받을지 (기본 3)")
    ap.add_argument("--out", default=str(ROOT / "data" / "raw"), help="저장 폴더 (기본 data/raw)")
    args = ap.parse_args(argv)
    if args.days < 1 or args.days > 60:
        ap.error("--days 는 1~60 사이로 주세요")
    try:
        path, n_items, n_rows, failed = collect(args.days, Path(args.out))
    except RuntimeError as e:
        print(f"❌ 수집 실패: {e}", file=sys.stderr)
        return 1
    print(f"✅ 새 앨범 {n_items}건 → {n_rows}행" + (f" 저장: {path}" if path else " (새 파일 없음)")
          + (f" (상세 실패 {len(failed)}건)" if failed else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
