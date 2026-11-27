"""힙합엘이 국내 뉴스 수집기 → data/raw/raw_press_<날짜>_hiphople.csv

    .venv/bin/python scripts/collect_hiphople.py                         # 매일: 1~2쪽, 새 글만
    .venv/bin/python scripts/collect_hiphople.py --backfill --max-pages 20 --since 2021-01-01   # 과거 기록 이어 받기

- 대상: https://hiphople.com/news_kr — "OO, 싱글 'XX' 공개" 형식의 국내 힙합·R&B 발매 소식 (쪽당 10건, 2026-11 기준 약 919쪽 ≈ 9천 건).
- robots.txt(2026-11-27 확인): `Disallow: /*?`·`Crawl-delay: 1` → 목록 쪽(`/news_kr?page=N`)은 봇 금지라
  CLAUDE.md 규칙대로 aside 브라우저(aside repl)로 읽는다. 사용자 지시대로 일부러 쉬지 않고 응답이 올 때까지만 기다린다.
  글 페이지(`/news_kr/<번호>`)는 허용되지만, 필요한 정보(팀·발매 제목·날짜)가 목록 제목에 다 있어 열지 않는다.
- 팀 이름: 제목이 '이름, (싱글|EP|정규 …) [제목] (공개|발매)' 형식일 때만 쉼표 앞을 팀으로 쓴다(정밀도 우선, 웹진 수집기와 같은 원칙).
  그 밖의 뉴스(예: '쇼미더머니12, 2차 예선 결과 공개')는 data/raw/review/hiphople_unparsed_<날짜>.json 에 모은다.
- 형식: raw_press (source='hiphople', outlet='HIPHOPLE', collector='aside', pick_label='국내 뉴스').
- 이어받기: data/raw/state/hiphople_seen.json — 본 글 번호, 과거 기록 다음 쪽(backfill_next_page), 마지막 실행일.
- 21:00~23:00(한국 시간)에는 매일 자동 수집과 브라우저가 겹치지 않게 실행하지 않는다(daily_run 안에서는 --no-time-guard).
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_webzines as cw  # noqa: E402
from collect_gigs import parse_repl_output  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
STATE_PATH = RAW_DIR / "state" / "hiphople_seen.json"
REVIEW_DIR = RAW_DIR / "review"
ITEMS_LOG = REVIEW_DIR / "hiphople_items.jsonl"     # 받은 글 전부 (다시 해석용, 비공개)
KST = cw.KST
COLUMNS = cw.COLUMNS
BASE = "https://hiphople.com"
SOURCE, OUTLET, LABEL = "hiphople", "HIPHOPLE", "국내 뉴스"
CRAWL_DELAY_MS = 0               # 사용자 지시(CLAUDE.md): aside로 읽을 땐 일부러 쉬지 않고 응답이 올 때까지만 기다림
PAGES_PER_CALL = 5
REPL_TIMEOUT_SEC = 180
RETRY_WAIT_SEC = 20
DAILY_PAGES = 2
DAILY_OVERLAP_DAYS = 14
FIRST_RUN_DAYS = 30
BACKFILL_SINCE = "2021-01-01"
SEEN_KEEP = 30000
MAX_NAME_SPACES = 3              # 이름 하나에 띄어쓰기가 이보다 많으면 문장으로 보고 버림
BLOCKED_HOURS = (21, 23)         # [21시, 23시) 실행 금지

ITEM_RE = re.compile(r'<a href="/news_kr/(\d+)(?:\?[^"]*)?"><span class="title">(.*?)</span></a>.*?'
                     r'<span class="date">(\d{4})\.(\d{2})\.(\d{2})</span>', re.S)
QUOTE_PAIRS = (("“", "”"), ('"', '"'), ("[", "]"), ("〈", "〉"), ("<", ">"), ("「", "」"), ("『", "』"), ("‘", "’"))
QUOTED_RE = re.compile("|".join(f"{re.escape(a)}([^{re.escape(b)}]*){re.escape(b)}" for a, b in QUOTE_PAIRS))
# 끝말: 발매 소식만 받는다 (뮤직비디오·트랙리스트 공개, 발매 예고 포함)
END_RE = re.compile(r"\s*(?:뮤직비디오|MV|M/V|트랙리스트)?\s*(?:선\s*)?(?:공개|발매|발표)(?:\s*예고)?\s*$")
# 종류를 나타내는 낱말 (이름 뒤나 쉼표 뒤에 붙음): '정규 2집 선공개 싱글', '새 싱글', '합작', '10월 6일 정규 앨범' 등
DESC_WORDS = frozenset({"싱글", "EP", "앨범", "정규", "미니", "디지털", "신보", "새", "선공개", "합작", "프로젝트", "컴필레이션",
                        "믹스테이프", "믹스테잎", "리믹스", "OST", "신곡", "더블", "첫", "리패키지", "스페셜", "곡", "타이틀",
                        "데뷔", "정규앨범", "미니앨범", "콜라보", "협업", "공동", "LP", "2nd", "1st", "3rd",
                        "정식", "컴백", "차기", "믹스테입", "디럭스", "버전", "트랙", "솔로", "단독"})
WITH_PARTNER = re.compile(r"^(?P<name>.+?)(?:과|와)\s*함께한$")   # '경제환과 함께한 싱글' → 경제환
# 함께한·피처링한 앞의 이름 = 함께한 팀: '로꼬와 문수진 등이 함께한' → 로꼬·문수진, '언텔 피처링한' → 언텔
PARTNER = re.compile(r"^(?P<names>.+?)\s*(?:과|와)?\s*(?:등이\s*)?함께\s?한$")
FEATURING = re.compile(r"^(?P<names>.+?)\s*피처링(?:한|의)$")
# 수식 문구 — 이름 자리에 있으면 그 조각만 버린다 (2026-11-27 점검: 'AOMG 합류 및'·'사운드클라우드를 통해' 등 46개가 팀 표에 섞였음)
CLAUSE = re.compile(r"합류|입단|영입|이적|개명|통해|만의|트리뷰트|깜짝|커버|일자|피처링|및|와의|과의|에서$|\s후$|함께$")
POSSESSIVE = re.compile(r"^(?P<name>.*[가-힣A-Za-z0-9)])의$")   # '최유정의 합작' → 최유정, 'EP의 선공개' → (종류 낱말이라 버림)
AND_SPLIT = re.compile(r"(?<=[가-힣A-Za-z0-9)])(?:과|와)\s+")    # '박찬과 24Oz' → 박찬, 24Oz (함께한·의 꼴에서만)
DESC_NUM = re.compile(r"^\d+(?:집|번째|월|일|th|st|nd|rd)?$")
# 이름 자리에 이런 낱말이 있으면 발매 소식이 아니거나 팀 이름이 아니라고 보고 버림 (정밀도 우선)
GENERIC = re.compile(r"음원|컨셉|포토|티저|무대|영상|채널|기념|본선|전곡|프로듀싱|작사|참여|주년|라이브|공연|콘서트|투어|유명|"
                     r"혐의|대표|신인|멤버|소속|계약|예선|결과|후보|결선|라인업|가요제")
# 레이블·회사 이름은 팀이 아님 (예: '저스트뮤직, 컴필레이션 앨범 … 공개')
LABEL_NAME = re.compile(r"(?:뮤직|엔터테인먼트|레코즈|레코드|레이블|records?|music|entertainment|label)$", re.I)
NAME_SPLIT = re.compile(r"\s+(?:&|＆|x|X|×)\s+|\s*[&＆]\s*|\s*×\s*")


# ---------- 변환 ----------

def parse_list_html(page_html: str) -> List[dict]:
    """목록 쪽 HTML → [{id, title, date, url}] (화면 순서 = 최신순)."""
    out = []
    for m in ITEM_RE.finditer(page_html or ""):
        art_id, title, y, mo, d = m.groups()
        out.append({"id": art_id, "title": cw.clean(title), "date": f"{y}-{mo}-{d}", "url": f"{BASE}/news_kr/{art_id}"})
    return out


def _is_desc(token: str) -> bool:
    return token in DESC_WORDS or bool(DESC_NUM.match(token))


def _strip_desc_suffix(piece: str) -> Tuple[str, bool]:
    """'판다곰 싱글' → ('판다곰', True). 끝의 종류 낱말을 떼고, 뗀 게 있었는지 함께 돌려준다."""
    tokens = piece.split()
    cut = len(tokens)
    while cut > 0 and _is_desc(tokens[cut - 1]):
        cut -= 1
    return " ".join(tokens[:cut]), cut < len(tokens)


def _ok_name(name: str) -> bool:
    return (bool(name) and len(name) <= cw.MAX_SLOT_LEN and name.count(" ") <= MAX_NAME_SPACES
            and not GENERIC.search(name) and not name.startswith(("<", "〈")))


def _expand_part(part: str) -> List[str]:
    """이름 자리 조각 하나 → 이름 조각들. 함께한·피처링한 꼴은 앞 이름을 살리고, 수식 문구면 버리고([]), '…의'는 '의'를 뗀다."""
    part = part.strip()
    m = PARTNER.match(part) or FEATURING.match(part)
    if m:
        return [n for n in AND_SPLIT.split(m.group("names")) if n.strip()]
    if CLAUSE.search(part):
        return []
    m = POSSESSIVE.match(part)
    if m:
        name, _ = _strip_desc_suffix(m.group("name"))
        return [n for n in AND_SPLIT.split(name) if n.strip()] if name else []
    return [part]


def parse_title(title: str) -> Optional[dict]:
    """발매 소식 제목 → {artists, release_title}. 형식이 아니면 None.
    예: '이름, 싱글 “제목” 공개' · '이름, [제목] 공개' · '이름, 새 싱글 "제목" 발표' · '이름, “제목” 뮤직비디오 공개' ·
        'A, B, C, EP [제목] 공개' · 'A & B 싱글 “제목” 공개'(쉼표 없음) · '이름, 판다곰 싱글 [제목] 공개'(이름이 쉼표로 이어짐).
    규칙: 끝말(공개·발매·발표[ 예고])이 있어야 하고, 따옴표 속 제목을 뺀 앞부분을 쉼표로 나눠
    첫 조각~가운데 조각은 이름, 마지막 조각은 '비었거나 / 종류 낱말만 / 이름+종류 낱말'이어야 한다."""
    m = END_RE.search(title or "")
    if not m:
        return None
    head = title[:m.start()]
    quoted = [g for mm in QUOTED_RE.finditer(head) for g in mm.groups() if g is not None]
    release = quoted[-1].strip() if quoted else ""
    pre = re.sub(r"\s+", " ", QUOTED_RE.sub(" ", head)).strip().rstrip(",").strip()
    pieces = cw.split_outside_parens(pre, ",") if pre else []
    if not pieces:
        return None
    first_q = QUOTED_RE.search(head)
    comma_before_quote = bool(first_q) and head[:first_q.start()].rstrip().endswith(",")   # '이름, [제목] 공개'
    last_name, had_desc = _strip_desc_suffix(pieces[-1])
    last = pieces[-1].strip()
    partner_form = bool(release and (PARTNER.match(last) or FEATURING.match(last)))   # '로꼬, 우원재와 함께한 "X" M/V 공개'
    if not had_desc and not (release and comma_before_quote) and not partner_form:
        return None             # 종류 낱말도, '이름, [제목]' 꼴도 아니면 발매 소식이 아님 (예: '…, 2차 예선 결과 공개')
    name_parts = pieces[:-1] + ([last_name] if last_name else [])
    # 'A X B X 벤 에서'처럼 이어 쓴 이름은 먼저 나눠서, 문구인 이름('벤 에서')만 버린다
    names = [n.strip() for part in name_parts for sub in NAME_SPLIT.split(part) if sub and sub.strip()
             for n in _expand_part(sub) if n.strip()]
    names = [n.strip().strip("'\"‘’“”").strip() for n in names]
    names = [n for n in names if n]
    if not names or not all(_ok_name(n) for n in names):
        return None
    names = [n for n in names if not LABEL_NAME.search(n)]
    if not names:
        return None
    return {"artists": names[:cw.MAX_ARTISTS_PER_ARTICLE], "release_title": release}


def items_to_rows(items: Sequence[dict], collected_at: str) -> Tuple[List[dict], List[dict]]:
    rows, unparsed = [], []
    for it in items:
        parsed = parse_title(it["title"])
        if parsed is None:
            unparsed.append(it)
            continue
        art = cw.article(it["id"], it["url"], it["date"], it["title"], parsed["artists"], "0", LABEL,
                         parsed["release_title"], cw.is_sponsored(it["title"]))
        rows += [dict(r, collector="aside") for r in cw.to_rows(SOURCE, OUTLET, art, collected_at)]
    return rows, unparsed


def write_rows(rows: List[dict], out_dir: Path, day: str) -> Path:
    return cw.write_csv(rows, out_dir, day, SOURCE)


def read_items(path: Path) -> List[dict]:
    """받은 글 기록(jsonl) 또는 목록(json)을 읽는다. 같은 글은 하나로(처음 나온 순서)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    if text.lstrip().startswith("["):
        items = json.loads(text)
    else:
        items = [json.loads(line) for line in text.splitlines() if line.strip()]
    seen, out = set(), []
    for it in items:
        if it["id"] not in seen:
            seen.add(it["id"])
            out.append(it)
    return out


def append_items(path: Path, items: Sequence[dict]) -> None:
    """받은 글을 모두 남긴다 → 제목 해석 규칙을 고친 뒤 다시 받지 않고 --reparse 로 다시 해석할 수 있게."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        for it in items:
            fh.write(json.dumps(it, ensure_ascii=False) + "\n")


def merge_unparsed(path: Path, items: Sequence[dict]) -> None:
    """발매 형식이 아닌 글 목록: 같은 날 여러 번 돌려도 덮어쓰지 않고 합친다."""
    merged = read_items(path)
    ids = {it["id"] for it in merged}
    merged += [it for it in items if it["id"] not in ids]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------- 상태 ----------

def load_state(path: Path = STATE_PATH) -> dict:
    base = {"seen": [], "backfill_next_page": 1, "last_run": ""}
    try:
        return {**base, **json.loads(path.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return base


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def mark_seen(state: dict, ids: Sequence[str], backfill_next_page: Optional[int] = None,
              today: Optional[str] = None) -> dict:
    seen = list(dict.fromkeys([*state.get("seen", []), *ids]))[-SEEN_KEEP:]
    nxt = backfill_next_page if backfill_next_page is not None else state.get("backfill_next_page", 1)
    return {**state, "seen": seen, "backfill_next_page": nxt, "last_run": today or state.get("last_run", "")}


def select_new(items: Sequence[dict], state: dict, since: str) -> Tuple[List[dict], bool]:
    """안 본 글 중 since 이후만. since 보다 오래된 글이 하나라도 나오면 stop=True (더 뒤 쪽은 안 봐도 됨)."""
    seen = set(state.get("seen", []))
    fresh = [it for it in items if it["id"] not in seen and it["date"] >= since]
    return fresh, any(it["date"] < since for it in items)


def in_blocked_window(now: datetime) -> bool:
    return BLOCKED_HOURS[0] <= now.astimezone(KST).hour < BLOCKED_HOURS[1]


# ---------- aside ----------

def list_js(pages: Sequence[int]) -> str:
    """목록 쪽들을 한 탭 안에서 fetch로 읽는다 (쪽 사이 쉼은 CRAWL_DELAY_MS, 기본 0). 결과 HTML은 목록 부분만 잘라 보낸다."""
    return """
await (async () => {
  const t = await openTab('%(base)s/news_kr'); await sleep(2500);
  const out = await t.evaluate(async (pages) => {
    const res = [];
    for (const p of pages) {
      try {
        const r = await fetch('/news_kr?page=' + p);
        const html = await r.text();
        const a = html.indexOf('wz-item'), b = html.lastIndexOf('class="date"');
        res.push({ page: p, status: r.status, html: a >= 0 && b > a ? html.slice(a, b + 200) : '' });
      } catch (e) { res.push({ page: p, error: String(e) }); }
      await new Promise(ok => setTimeout(ok, %(delay)d));
    }
    return res;
  }, %(pages)s);
  await closeTab(t);
  console.log('RESULT ' + JSON.stringify(out));
})();
""" % {"base": BASE, "delay": CRAWL_DELAY_MS, "pages": json.dumps(list(pages))}


def read_pages(pages: Sequence[int]) -> Optional[List[dict]]:
    for attempt in (1, 2):
        try:
            proc = subprocess.run(["aside", "repl", "--json", list_js(pages)], capture_output=True, text=True,
                                  timeout=REPL_TIMEOUT_SEC)
            return parse_repl_output(proc.stdout)
        except (RuntimeError, subprocess.TimeoutExpired, OSError) as e:
            print(f"  ⚠️ 목록 {list(pages)} 읽기 실패 ({attempt}번째): {e}", file=sys.stderr)
            if attempt == 1:
                time.sleep(RETRY_WAIT_SEC)
    return None


# ---------- 실행 ----------

def collect(start_page: int, max_pages: int, since: str, state: dict, read=read_pages) -> Tuple[List[dict], int]:
    """start_page 부터 최대 max_pages 쪽 읽기. (새 글, 다음에 읽을 쪽)."""
    fresh_all: List[dict] = []
    page, end = start_page, start_page + max_pages
    while page < end:
        got = read(list(range(page, min(page + PAGES_PER_CALL, end))))
        if got is None:
            break
        stop = False
        for res in got:
            items = [] if res.get("error") or res.get("status", 200) != 200 else parse_list_html(res.get("html", ""))
            if not items:                       # 빈 쪽·오류 = 목록 끝이거나 실패 → 멈춤 (다음 실행이 이 쪽부터)
                stop = True
                break
            fresh, too_old = select_new(items, state, since)
            fresh_all += fresh
            page = res["page"] + (0 if too_old else 1)   # 기준일 경계 쪽은 다음에도 이 쪽부터 (계속 돌려도 쪽 번호가 밀리지 않게)
            print(f"  {res['page']}쪽: 글 {len(items)}건, 새 글 {len(fresh)}건 (가장 오래된 {items[-1]['date']})",
                  file=sys.stderr)
            if too_old:
                stop = True
                break
        if stop:
            break
    return fresh_all, page


def old_hiphople_rows(raw_dir: Path = RAW_DIR) -> List[dict]:
    """이미 적재 대상인 힙합엘이 원본 행들 (data/raw/raw_press_*_hiphople*.csv)."""
    rows: List[dict] = []
    for f in sorted(raw_dir.glob("raw_press_*_hiphople*.csv")):
        with open(f, encoding="utf-8", newline="") as fh:
            rows += list(csv.DictReader(fh))
    return rows


def reparse(path: Path, now: datetime, out: Optional[Path] = None, old_rows: Optional[Sequence[dict]] = None) -> dict:
    """받아 둔 글을 지금 규칙으로 다시 해석해 **새 파일**(기본: data/raw/review/hiphople_reparse_<날짜>.csv)로 쓴다.
    원본 raw 파일은 건드리지 않는다(적재 폴더 밖이라 바로 섞이지도 않음). 예전 원본 행과 팀 이름을 비교해 사라진·새로 생긴 이름을 돌려준다."""
    items = read_items(path)
    rows, unparsed = items_to_rows(items, now.replace(microsecond=0).isoformat())
    out = out or (REVIEW_DIR / f"hiphople_reparse_{now.date().isoformat()}.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    old = {r.get("artist_text", "") for r in (old_rows if old_rows is not None else old_hiphople_rows())} - {""}
    new = {r.get("artist_text", "") for r in rows} - {""}
    report = {"items": len(items), "rows": len(rows), "unparsed": len(unparsed), "out": str(out),
              "removed": sorted(old - new), "added": sorted(new - old)}
    print(f"✅ 다시 해석: 글 {len(items)}건 → {len(rows)}행 → {out}" + f" · 발매 형식 아님 {len(unparsed)}건"
          + f" · 예전 원본과 비교: 사라진 이름 {len(report['removed'])} · 새 이름 {len(report['added'])}")
    return report


def main(argv: Sequence[str]) -> int:
    ap = argparse.ArgumentParser(description="힙합엘이 국내 뉴스 (aside 브라우저)")
    ap.add_argument("--backfill", action="store_true", help="과거 기록을 상태 파일의 다음 쪽부터 이어 받기")
    ap.add_argument("--max-pages", type=int, default=DAILY_PAGES)
    ap.add_argument("--since", default=None, help="이 날짜보다 오래된 글이 나오면 멈춤 (YYYY-MM-DD)")
    ap.add_argument("--no-time-guard", action="store_true", help="21~23시에도 실행 (daily_run 안에서만)")
    ap.add_argument("--reparse", metavar="FILE", help="받아 둔 글(jsonl·json)을 지금 규칙으로 다시 해석만 (브라우저 안 씀, 새 파일로)")
    ap.add_argument("--out", type=Path, default=None, help="--reparse 결과 파일 (기본 data/raw/review/hiphople_reparse_<날짜>.csv)")
    args = ap.parse_args(argv)
    now = datetime.now(KST)
    if args.reparse:
        report = reparse(Path(args.reparse), now, out=args.out)
        report_path = Path(report["out"]).with_suffix(".json")
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        return 0
    if in_blocked_window(now) and not args.no_time_guard:
        print("⏸ 21:00~23:00에는 매일 자동 수집과 브라우저가 겹치지 않게 실행하지 않아요. 23시 이후에 다시 실행하세요.",
              file=sys.stderr)
        return 3
    today = now.date().isoformat()
    state = load_state()
    if args.backfill:
        since, start = args.since or BACKFILL_SINCE, int(state.get("backfill_next_page", 1))
    else:
        last = state.get("last_run")
        default = ((date.fromisoformat(last) - timedelta(days=DAILY_OVERLAP_DAYS)) if last
                   else (now.date() - timedelta(days=FIRST_RUN_DAYS))).isoformat()
        since, start = args.since or default, 1
    print(f"힙합엘이 국내 뉴스: {start}쪽부터 최대 {args.max_pages}쪽, {since} 이후", file=sys.stderr)
    fresh, next_page = collect(start, args.max_pages, since, state)
    append_items(ITEMS_LOG, fresh)
    rows, unparsed = items_to_rows(fresh, now.replace(microsecond=0).isoformat())
    path = write_rows(rows, RAW_DIR, today) if rows else None
    if unparsed:
        merge_unparsed(REVIEW_DIR / f"hiphople_unparsed_{today}.json", unparsed)
    state = mark_seen(state, [it["id"] for it in fresh],
                      backfill_next_page=next_page if args.backfill else None, today=today)
    save_state(STATE_PATH, state)
    print(f"✅ 새 글 {len(fresh)}건 → {len(rows)}행" + (f" → {path.relative_to(ROOT)}" if path else "")
          + f" · 발매 형식 아님 {len(unparsed)}건" + (f" · 다음 과거 쪽 {next_page}" if args.backfill else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
