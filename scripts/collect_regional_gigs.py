"""지역 공연장·페스티벌 공연 수집기 → data/raw/raw_kr_gig_<날짜>_regional.csv

    python3 scripts/collect_regional_gigs.py              # 누리락 공연 목록(스크립트) + 라인업 목록(사람이 옮긴 것)
    python3 scripts/collect_regional_gigs.py --no-fetch   # 인터넷 없이 라인업 목록만
    python3 scripts/collect_regional_gigs.py --dry-run    # 파일은 안 쓰고 몇 행인지만

왜: 인디스트릿·인디고에는 지방 공연이 드물게 올라온다 (세종 누리락: 23회째 '디깅라이브세종' 중 1회만 잡힘,
세종보헤미안뮤직페스티벌은 0건). 지역 공연장·지자체 문화재단 누리집이 직접 올리는 공연 일정을 읽어 채운다.

출처 (2026-11-28 확인)
1. 세종음악창작소 누리락 '프로그램 일정' (https://www.nurirock.or.kr/base/nrr/performance/list/?performanceManagementNo=1)
   — robots.txt 전체 허용. 한 쪽 9건, page=1,2,…. 제목·날짜·공연장소가 글자로 있다.
   1팀 공연(디깅라이브세종 [epN] 팀, 뮤즈세종 쇼케이스 팀 <앨범>, 월간 누리락 Vol.N '팀', 'X 단독…', 'X 전국투어…')만
   제목에서 팀을 뽑는다. 바이닐 스튜디오(음반 감상회)·아카데미·패키지 예매·합동공연·여러 팀 공연은 건너뛴다.
   (대관공연 일정 performanceManagementNo=4 는 클래식·국악·연극 대관이라 읽지 않는다.)
2. 라인업 목록 scripts/collect_regional_lineups.py — 페스티벌·교류공연처럼 출연진이 그림(포스터·타임테이블)에만 있는
   공연을 사람이 읽어 옮긴 것. 근거 URL 이 행의 gig_url 이 된다.

형식: scripts/csv_schema.py raw_kr_gig. source 는 'regional'(아래 SOURCE).
같은 (source, gig_url, artist_text) 는 한 번만 쓴다.
"""
from __future__ import annotations

import argparse
import csv
import html
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

import collect_regional_lineups as crl
from csv_schema import TABLES

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
KST = timezone(timedelta(hours=9))
USER_AGENT = "crate-digger/0.1 (+https://github.com/leegmyung/crate-digger)"
COLUMNS = [f.name for f in TABLES["raw_kr_gig"]["fields"]]
KEY = TABLES["raw_kr_gig"]["key"]
SOURCE = "regional"          # csv_schema.GIG_SOURCES
FILE_TAG = "regional"
TIMEOUT_SEC = 30
MAX_PAGES = 40

NURIROCK_LIST = "https://www.nurirock.or.kr/base/nrr/performance/list/?performanceManagementNo=1&page={page}"
NURIROCK_READ = "https://www.nurirock.or.kr/base/nrr/performance/read?performanceNo={no}"
NURIROCK_VENUE = crl.NURIROCK

ITEM = re.compile(
    r'cont__tit">(?P<title>.*?)</h3>\s*<p class="show-list__mid__item__cont__date">(?P<date>.*?)</p>'
    r'.*?<dt>공연장소</dt>\s*<dd>(?P<place>.*?)</dd>.*?performanceNo=(?P<no>\d+)', re.S)
DATE = re.compile(r"(\d{4})\.(\d{2})\.(\d{2})")
NURIROCK_PLACE = re.compile(r"누리락|세종\s*음악창작소|박연문화관")

SKIP_TITLE = re.compile(r"바이닐\s*스튜디오|아카데미|패키지|합동\s*공연|교류공연|페스티벌|스테이지|밤빛|"
                        r"우리음악인|개관기념|토크콘서트|서울라이브|선셋\s*라이브|팝업|콘서트$|^뮤즈세종\s*단독")
DIGGING = re.compile(r"^디깅\s*라이브\s*세종\s*[\[(]\s*ep\s*\d+\s*[\])]\s*(?P<name>.+)$", re.I)
SHOWCASE = re.compile(r"^\d{4}\s*뮤즈세종\s*쇼케이스\s+(?P<name>[^<]+?)\s*(?:<[^>]*>)?\s*$")
MONTHLY = re.compile(r"^월간\s*누리락\s*Vol\.?\s*\d+\s*['‘\"](?P<name>[^'’\"]+)['’\"]\s*$", re.I)
QUOTED_SOLO = re.compile(r"뮤지션\s*['‘\"](?P<name>[^'’\"]+)['’\"]\s*단독")
SOLO = re.compile(r"^(?P<name>[^:'‘\"<]+?)\s*(?:단독\s*(?:콘서트|공연)|전국\s*투어)")
COLLAB = re.compile(r"\s*[xX×]\s*")
PAREN = re.compile(r"\s*\(([^)]*)\)\s*$")


def clean(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment or ""))).strip()


def _iso(text: str) -> str:
    m = DATE.search(text or "")
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""


def parse_nurirock_list(page: str) -> List[dict]:
    """프로그램 일정 한 쪽 → [{no, title, start, end, place}] (날짜 없는 옛 글은 start='')."""
    out = []
    for m in ITEM.finditer(page or ""):
        dates = DATE.findall(m.group("date"))
        start = "-".join(dates[0]) if dates else ""
        out.append({"no": m.group("no"), "title": clean(m.group("title")), "start": start,
                    "end": "-".join(dates[-1]) if dates else "", "place": clean(m.group("place"))})
    return out


def _split_names(text: str) -> List[str]:
    m = PAREN.search(text.strip())
    name = PAREN.sub("", text.strip())
    if m and len(name) < 2:          # 'ㅈ(지읒)' → 괄호 속 읽는 이름
        name = m.group(1).strip()
    parts = [p.strip() for p in COLLAB.split(name)] if re.search(r"[가-힣]\s*[xX×]\s*[가-힣]", name) else [name]
    return [p for p in parts if p]


def performers_from_title(title: str) -> List[str]:
    """1팀 공연 제목에서 출연 팀. 애매하면 [] (건너뜀)."""
    t = re.sub(r"\s+", " ", title or "").strip()
    if SKIP_TITLE.search(t):
        return []
    for pattern in (DIGGING, SHOWCASE, MONTHLY, QUOTED_SOLO, SOLO):
        m = pattern.search(t)
        if m:
            return _split_names(m.group("name"))
    return []


def nurirock_venue_text(place: str) -> str:
    """누리락 안 공간(공연장·스튜디오·옥상)은 한 공연장으로, 다른 곳은 이름 그대로."""
    p = clean(place)
    return NURIROCK_VENUE if NURIROCK_PLACE.search(p) else p


def _row(collected_at: str, collector: str, source_id: str, day: str, title: str, venue: str, artist: str,
         url: str, order: str = "", start: str = "", size: str = "") -> Dict[str, str]:
    row = {c: "" for c in COLUMNS}
    row.update({"collected_at": collected_at, "source": SOURCE, "collector": collector, "source_id": source_id,
                "gig_date": day, "title": title, "venue_text": venue, "artist_text": artist, "gig_url": url,
                "lineup_order": order, "lineup_time": start, "lineup_size": size})
    return row


def rows_from_nurirock(items: Iterable[dict], collected_at: str) -> List[Dict[str, str]]:
    rows = []
    for it in items:
        names = performers_from_title(it["title"])
        if not names or not it["start"] or it["start"] != it["end"]:
            continue
        url = NURIROCK_READ.format(no=it["no"])
        for name in names:
            rows.append(_row(collected_at, "script", f"nurirock:{it['no']}", it["start"], it["title"],
                             nurirock_venue_text(it["place"]), name, url))
    return rows


def rows_from_lineups(events: Sequence[crl.Event], collected_at: str) -> List[Dict[str, str]]:
    rows = []
    for e in events:
        size = str(len({n for n, _ in e.acts}))
        for i, (name, start) in enumerate(e.acts, 1):
            rows.append(_row(collected_at, "manual", f"lineup:{e.day}", e.day, e.title, e.venue_text, name,
                             f"{e.url}#{e.day}", str(i), start, size))
    return rows


def dedupe(rows: Iterable[Dict[str, str]]) -> List[Dict[str, str]]:
    seen, out = set(), []
    for r in rows:
        k = tuple(r[c] for c in KEY)
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def write_csv(rows: Sequence[Dict[str, str]], out_dir: Path, day: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"raw_kr_gig_{day}_{FILE_TAG}.csv"
    if path.exists():  # 원본은 고치지 않는다
        path = out_dir / f"raw_kr_gig_{day}_{FILE_TAG}_{datetime.now(KST):%H%M%S}.csv"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as res:
        return res.read().decode("utf-8", errors="replace")


def collect_nurirock(collected_at: str, report: List[str]) -> List[Dict[str, str]]:
    items: List[dict] = []
    for page in range(1, MAX_PAGES + 1):
        try:
            got = parse_nurirock_list(fetch(NURIROCK_LIST.format(page=page)))
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            report.append(f"  누리락 {page}쪽 읽기 실패: {e}")
            break
        if not got:
            break
        items.extend(got)
    rows = rows_from_nurirock(items, collected_at)
    used = {r["source_id"] for r in rows}
    skipped = [it["title"] for it in items if f"nurirock:{it['no']}" not in used]
    report.append(f"  누리락 프로그램 일정 {len(items)}건 → 1팀 공연 {len(used)}건 ({len(rows)}행), 건너뜀 {len(skipped)}건")
    return rows


def main(argv: Sequence[str]) -> int:
    ap = argparse.ArgumentParser(description="지역 공연장·페스티벌 공연 수집 (세종 누리락 + 라인업 목록)")
    ap.add_argument("--no-fetch", action="store_true", help="누리집은 읽지 않고 라인업 목록만")
    ap.add_argument("--dry-run", action="store_true", help="파일을 쓰지 않음")
    args = ap.parse_args(argv)
    now = datetime.now(KST)
    collected_at = now.isoformat(timespec="seconds")
    report: List[str] = ["지역 공연 수집"]
    rows = [] if args.no_fetch else collect_nurirock(collected_at, report)
    lineup_rows = rows_from_lineups(crl.EVENTS, collected_at)
    report.append(f"  라인업 목록 {len(crl.EVENTS)}건 → {len(lineup_rows)}행")
    rows = dedupe([*rows, *lineup_rows])
    report.append(f"  합계 {len(rows)}행")
    if rows and not args.dry_run:
        report.append(f"  → {write_csv(rows, RAW_DIR, now.date().isoformat())}")
    print("\n".join(report))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
