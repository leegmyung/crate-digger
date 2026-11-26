"""선정 명단 수집기 → data/raw/raw_kr_selection_<날짜>_<사이트>.csv (후보 신호)

    python3 scripts/collect_selection.py                  # 세 곳 모두, 새로 나온 팀만
    python3 scripts/collect_selection.py --site busan     # busan | sejong | gb | all
    python3 scripts/collect_selection.py --site busan --wayback   # 부산 지난 회차를 인터넷 보관소에서 채우기 (한 번만)

- busan  : 부산국제록페스티벌 루키즈 온 더 부락 페이지. 한 페이지를 해마다 덮어써서
           TOP15 → TOP10 → TOP3 단계가 바뀔 때마다 읽어야 한다. (robots.txt 허용)
- sejong : 세종음악창작소 뮤즈세종 '선정 뮤지션' 게시판 (robots.txt 허용)
- gb     : 경북음악창작소 054사운드빌 공개 API에서 음반 지원 결과 글만 (robots.txt 허용)
- 이미 저장한 팀은 data/raw/state/selection_seen.json 으로 걸러 새 행만 쓴다.
- 형식: docs/csv_spec.md 4장 / scripts/csv_schema.py
"""
import argparse
import csv
import html
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from csv_schema import TABLES

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
STATE = RAW_DIR / "state" / "selection_seen.json"
KST = timezone(timedelta(hours=9))
USER_AGENT = "crate-digger/0.1 (+https://github.com/leegmyung/crate-digger)"
COLUMNS = [f.name for f in TABLES["raw_kr_selection"]["fields"]]
KEY = TABLES["raw_kr_selection"]["key"]
REQUEST_DELAY_SEC = 2.0
TIMEOUT_SEC = 30

BUSAN_URL = "https://busanrockfestival.com/ROOKIES/"
WAYBACK_CDX = ("https://web.archive.org/cdx/search/cdx?url=busanrockfestival.com/ROOKIES/"
               "&output=json&fl=timestamp&filter=statuscode:200&collapse=digest")
SEJONG_LIST = "https://nurirock.or.kr/base/board/list?boardManagementNo=7&menuLevel=2&menuNo=29&page={page}"
SEJONG_READ = "https://nurirock.or.kr/base/board/read?boardManagementNo=7&boardNo={no}"
SEJONG_MAX_PAGES = 10
GB_API = "https://054soundville.or.kr/wp-json/wp/v2/project?per_page=100&_fields=date,link,title"

BUSAN_HEAD = re.compile(r"<\s*(\d{4})\s*루키즈 온 더 부락\s*>\s*TOP\s*(\d+)\s*발표")
BUSAN_RANKED = re.compile(r"TOP\s*(\d+)\s*:\s*(.+?)(?:\s+@([A-Za-z0-9._]+))?\s*$")
BUSAN_LISTED = re.compile(r"^[✶•·\-–]\s*(.+?)\s*$")
BUSAN_STOP = re.compile(r"Announcement|After the|순위와 무관|무대가|^\*")
SEJONG_ITEM = re.compile(
    r'href="[^"]*boardNo=(\d+)[^"]*".*?(?:/storage/board/artist/(\d{4})/(\d{2})/.*?)?'
    r'years-item">\s*(\d{4})\s*</span>\s*<span class="subject-item">(.*?)</span>', re.S)
GB_BRACKET = re.compile(r"^💿?\s*(.+?)\s*\[(.+)\]\s*$")
GB_DISC = re.compile(r"^(.+?)\s*💿\s*(.+?)\s*$")
GB_SKIP = re.compile(r"^\[|🎬|🤟|INTERVIEW|LIVE CLIP|클래스054", re.I)


def html_to_lines(page):
    page = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", page or "", flags=re.S)
    page = re.sub(r"<br\s*/?>|</p>|</li>|</div>|</h\d>", "\n", page, flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", "", page))
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def _row(source, program, round_, stage, announced, artist, url, collected_at, note=""):
    return {"collected_at": collected_at, "source": source, "collector": "script", "program": program,
            "round": round_, "stage": stage, "announced_at": announced, "artist_text": artist,
            "url": url, "note": note}


def busan_stage(top_size):
    if top_size >= 15:
        return "document"   # 1차 서류 통과
    if top_size > 3:
        return "selected"   # 2차 실연 심사 통과 (본선)
    return "final"          # 최종 순위


def parse_busan(page, url, collected_at):
    lines = html_to_lines(page)
    head = next(((i, m) for i, ln in enumerate(lines) if (m := BUSAN_HEAD.search(ln))), None)
    if not head:
        return []
    start, m = head
    year, size = m.group(1), int(m.group(2))
    stage, rows, seen = busan_stage(size), [], set()
    for ln in lines[start + 1:]:
        if BUSAN_STOP.search(ln):
            if rows:
                break
            continue
        ranked, listed = BUSAN_RANKED.search(ln), BUSAN_LISTED.match(ln)
        if ranked:
            name = ranked.group(2).strip()
            note = f"TOP {ranked.group(1)}" + (f" @{ranked.group(3)}" if ranked.group(3) else "")
        elif listed and "TOP" not in ln:
            name, note = listed.group(1), f"TOP {size}"
        else:
            continue
        if name and name not in seen:
            seen.add(name)
            rows.append(_row("busanrock", "burock_rookies", year, stage, year, name, url, collected_at, note))
    return rows


def parse_sejong(page, collected_at):
    rows = []
    for no, img_y, img_m, year, name in SEJONG_ITEM.findall(page or ""):
        name = html.unescape(re.sub(r"<[^>]+>", "", name)).strip()
        announced = f"{img_y}-{img_m}" if img_y == year else year
        if name:
            rows.append(_row("sejong", "muse_sejong", year, "selected", announced, name,
                             SEJONG_READ.format(no=no), collected_at))
    return rows


def parse_gb(items, collected_at):
    rows = []
    for item in items or []:
        title = html.unescape(item.get("title", {}).get("rendered", "")).strip()
        if not title or GB_SKIP.search(title):
            continue
        m = GB_BRACKET.match(title) or (GB_DISC.match(title) if "💿" in title else None)
        if not m:
            continue
        name, album = m.group(1).replace("💿", "").strip(), m.group(2).strip()
        day = item.get("date", "")[:10]
        rows.append(_row("gbsound", "gb_creation", day[:4], "selected", day, name, item.get("link", ""),
                         collected_at, album))
    return rows


def row_key(row):
    return "|".join(row[k] for k in KEY)


def drop_seen(rows, seen):
    out = []
    for r in rows:
        k = row_key(r)
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def write_csv(rows, out_dir, day, site):
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"raw_kr_selection_{day}_{site}.csv"
    if path.exists():  # 원본은 고치지 않는다
        path = out_dir / f"raw_kr_selection_{day}_{site}_{datetime.now(KST):%H%M%S}.csv"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as res:
        return res.read().decode("utf-8", errors="replace")


def collect_busan(collected_at, wayback=False):
    rows = parse_busan(fetch(BUSAN_URL), BUSAN_URL, collected_at)
    if not wayback:
        return rows
    stamps = [r[0] for r in json.loads(fetch(WAYBACK_CDX))[1:]]
    for ts in stamps:
        time.sleep(REQUEST_DELAY_SEC)
        snap = f"https://web.archive.org/web/{ts}/{BUSAN_URL}"
        rows.extend(parse_busan(fetch(f"https://web.archive.org/web/{ts}id_/{BUSAN_URL}"), snap, collected_at))
    return rows


def collect_sejong(collected_at):
    rows = []
    for page in range(1, SEJONG_MAX_PAGES + 1):
        got = parse_sejong(fetch(SEJONG_LIST.format(page=page)), collected_at)
        if not got:
            break
        rows.extend(got)
        time.sleep(REQUEST_DELAY_SEC)
    return rows


def collect_gb(collected_at):
    return parse_gb(json.loads(fetch(GB_API)), collected_at)


def _load_seen():
    try:
        return set(json.loads(STATE.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return set()


def collect(site, wayback=False):
    now = datetime.now(KST).replace(microsecond=0)
    at, day = now.isoformat(), f"{now:%Y-%m-%d}"
    jobs = {"busan": lambda: collect_busan(at, wayback), "sejong": lambda: collect_sejong(at),
            "gb": lambda: collect_gb(at)}
    names = list(jobs) if site == "all" else [site]
    seen, report, paths = _load_seen(), [], []
    for name in names:
        try:
            rows = drop_seen(jobs[name](), seen)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as e:
            report.append(f"⚠️ {name}: 읽기 실패 ({e})")
            continue
        if rows:
            paths.append(write_csv(rows, RAW_DIR, day, name))
        report.append(f"✅ {name}: 새 행 {len(rows)}개")
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(sorted(seen), ensure_ascii=False, indent=0), encoding="utf-8")
    return paths, report


def main(argv):
    ap = argparse.ArgumentParser(description="선정 명단 수집 (부산 루키즈·세종·경북)")
    ap.add_argument("--site", choices=["busan", "sejong", "gb", "all"], default="all")
    ap.add_argument("--wayback", action="store_true", help="부산 지난 회차를 인터넷 보관소에서 채우기")
    args = ap.parse_args(argv)
    paths, report = collect(args.site, args.wayback)
    print("\n".join(report + [f"  → {p}" for p in paths]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
