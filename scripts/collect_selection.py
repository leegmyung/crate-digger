"""선정 명단 수집기 → data/raw/raw_kr_selection_<날짜>_<사이트>.csv (후보 신호)

    python3 scripts/collect_selection.py                  # 세 곳 모두, 새로 나온 팀만
    python3 scripts/collect_selection.py --site busan     # busan | sejong | gb | all
    python3 scripts/collect_selection.py --site busan --wayback   # 부산 지난 회차를 인터넷 보관소에서 채우기 (한 번만)

- busan  : 부산국제록페스티벌 루키즈 온 더 부락 페이지. 한 페이지를 해마다 덮어써서
           TOP15 → TOP10 → TOP3 단계가 바뀔 때마다 읽어야 한다. (robots.txt 허용)
- sejong : 세종음악창작소 뮤즈세종 '선정 뮤지션' 게시판 (robots.txt 허용)
- gb     : 경북음악창작소 054사운드빌 공개 API에서 음반 지원 결과 글만 (robots.txt 허용)
- yjh    : 유재하음악경연대회 역대 수상 페이지 — 본선 10팀 전원 (1989~, robots.txt 허용)
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
USER_AGENT = "gigle-research/0.1 (+https://github.com/leegmyung/gigle-research)"
COLUMNS = [f.name for f in TABLES["raw_kr_selection"]["fields"]]
KEY = TABLES["raw_kr_selection"]["key"]
REQUEST_DELAY_SEC = 0.3
TIMEOUT_SEC = 30

BUSAN_URL = "https://busanrockfestival.com/ROOKIES/"
WAYBACK_CDX = ("https://web.archive.org/cdx/search/cdx?url=busanrockfestival.com/ROOKIES/"
               "&output=json&fl=timestamp&filter=statuscode:200&collapse=digest")
SEJONG_LIST = "https://nurirock.or.kr/base/board/list?boardManagementNo=7&menuLevel=2&menuNo=29&page={page}"
SEJONG_READ = "https://nurirock.or.kr/base/board/read?boardManagementNo=7&boardNo={no}"
SEJONG_MAX_PAGES = 10
YJH_URL = "https://www.yjh.or.kr/History"
YJH_HEAD = re.compile(r"제\s*(\d+)\s*회\s*유재하\s*음악경연대회")
YJH_ROW = re.compile(r"<tr[^>]*>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>\s*</tr>", re.S)
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


def parse_busan(page, url, collected_at, seen_on=""):
    """seen_on: 이 페이지를 본 날짜(보관소 저장일·처음 읽은 날). 발표일을 모르므로 '늦어도 이날 발표됨'으로
    announced_at에 쓴다. 없으면 연도만 (백테스트에서는 scripts/timing.py가 보수적으로 해석)."""
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
            announced = seen_on if seen_on.startswith(year) else year
            rows.append(_row("busanrock", "burock_rookies", year, stage, announced, name, url, collected_at, note))
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


def yjh_year(round_no):
    """유재하음악경연대회 회차 → 연도. 1회 1989년, 2005년은 열리지 않아 17회(2006)부터 한 해 밀림."""
    return 1988 + round_no if round_no <= 16 else 1989 + round_no


def parse_yjh(page, collected_at):
    """역대 수상 페이지 → 본선 진출 팀(전원 수상). 같은 회차에 본상·특별상으로 두 번 나오면 1행으로 합치고
    상 이름은 note에 모은다. 발표일은 연도만 알 수 있어 연도로 적는다 (백테스트는 timing.py가 보수적으로 해석)."""
    rows, done = [], set()
    heads = list(YJH_HEAD.finditer(page or ""))
    for i, m in enumerate(heads):
        no = int(m.group(1))
        block = (page or "")[m.end():heads[i + 1].start() if i + 1 < len(heads) else len(page)]
        if no in done or "<table" not in block:   # 회차 제목만 있고 표가 없는 곳(목차 등)은 건너뜀
            continue
        done.add(no)
        teams = {}
        for label, cell in YJH_ROW.findall(block):
            award = clean_text(label)
            for part in re.split(r"<br\s*/?>|</p>", cell):
                name = clean_text(part).split("<")[0].strip()
                if name:
                    teams.setdefault(name, []).append(award)
        year = str(yjh_year(no))
        rows.extend(_row("yjh", "yoojaeha_finalist", f"{no}회", "selected", year, name, YJH_URL, collected_at,
                         ", ".join(dict.fromkeys(awards))) for name, awards in teams.items())
    return rows


def clean_text(fragment):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", fragment or ""))).strip()


def row_key(row):
    return "|".join(row[k] for k in KEY)


DAY_MARK = "@day"   # seen에 '<키>@day'가 있으면 그 팀의 발표일을 날짜까지 이미 저장했다는 뜻
FULL_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def drop_seen(rows, seen):
    """새 팀만 남긴다. 단, 예전에 연도·월까지만 저장한 팀에 날짜가 정확한 행이 오면 한 번은 다시 쓴다
    (적재 뷰 core.v_signal_base가 같은 키 중 가장 이른 발표일을 쓰므로 연말로 밀린 날짜가 바로잡힌다)."""
    out = []
    for r in rows:
        k = row_key(r)
        dated = bool(FULL_DATE.match(r.get("announced_at") or ""))
        if k in seen and not (dated and k + DAY_MARK not in seen):
            continue
        seen.add(k)
        if dated:
            seen.add(k + DAY_MARK)
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
    """보관소 사본(오래된 것부터)을 지금 페이지보다 먼저 읽는다 — drop_seen이 가장 이른 '늦어도 이날' 날짜를 남기게."""
    rows = []
    if wayback:
        stamps = [r[0] for r in json.loads(fetch(WAYBACK_CDX))[1:]]
        for ts in sorted(stamps):
            time.sleep(REQUEST_DELAY_SEC)
            snap = f"https://web.archive.org/web/{ts}/{BUSAN_URL}"
            seen_on = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"
            rows.extend(parse_busan(fetch(f"https://web.archive.org/web/{ts}id_/{BUSAN_URL}"), snap, collected_at, seen_on))
    return rows + parse_busan(fetch(BUSAN_URL), BUSAN_URL, collected_at, seen_on=collected_at[:10])


def collect_sejong(collected_at):
    rows = []
    for page in range(1, SEJONG_MAX_PAGES + 1):
        got = parse_sejong(fetch(SEJONG_LIST.format(page=page)), collected_at)
        if not got:
            break
        rows.extend(got)
        time.sleep(REQUEST_DELAY_SEC)
    return rows


def collect_yjh(collected_at):
    return parse_yjh(fetch(YJH_URL), collected_at)


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
            "gb": lambda: collect_gb(at), "yjh": lambda: collect_yjh(at)}
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
    ap.add_argument("--site", choices=["busan", "sejong", "gb", "yjh", "all"], default="all")
    ap.add_argument("--wayback", action="store_true", help="부산 지난 회차를 인터넷 보관소에서 채우기")
    args = ap.parse_args(argv)
    paths, report = collect(args.site, args.wayback)
    print("\n".join(report + [f"  → {p}" for p in paths]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
