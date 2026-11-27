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
KIND = (r"(?:디지털\s*)?(?:싱글|EP|정규\s*\d*\s*집?|정규\s*앨범|미니\s*\d*\s*집?|미니\s*앨범|앨범|믹스테이프|믹스테잎|"
        r"리믹스|프로젝트\s*앨범|컴필레이션\s*앨범|컴필레이션|OST|신곡|더블\s*싱글)")
QUOTE_PAIRS = (("“", "”"), ('"', '"'), ("[", "]"), ("〈", "〉"), ("<", ">"), ("「", "」"), ("『", "』"), ("‘", "’"))
QUOTED = "|".join(f"{re.escape(a)}(?P<q{i}>[^{re.escape(b)}]*){re.escape(b)}" for i, (a, b) in enumerate(QUOTE_PAIRS))
_REST = rf"{KIND}\s*(?:{QUOTED})?\s*(?:선\s*)?(?:공개|발매)\s*$"
REST_RE = re.compile(rf"^(?P<more>){_REST}")                          # '이름, 싱글 …'
REST_MORE_RE = re.compile(rf"^(?P<more>[^,]+?)\s+{_REST}")            # '이름, 이름2 싱글 …' (먼저 위를 시도)
# 레이블·회사 이름은 팀이 아님 (예: '저스트뮤직, 컴필레이션 앨범 … 공개')
LABEL_NAME = re.compile(r"(?:뮤직|엔터테인먼트|레코즈|레코드|레이블|records?|music|entertainment|label)$", re.I)
NAME_SPLIT = re.compile(r"\s+(?:&|x|X|×)\s+|\s*&\s*|\s*×\s*")


# ---------- 변환 ----------

def parse_list_html(page_html: str) -> List[dict]:
    """목록 쪽 HTML → [{id, title, date, url}] (화면 순서 = 최신순)."""
    out = []
    for m in ITEM_RE.finditer(page_html or ""):
        art_id, title, y, mo, d = m.groups()
        out.append({"id": art_id, "title": cw.clean(title), "date": f"{y}-{mo}-{d}", "url": f"{BASE}/news_kr/{art_id}"})
    return out


def parse_title(title: str) -> Optional[dict]:
    """'이름[ & 이름], 싱글 “제목” 공개' → {artists, release_title}. 발매 소식 형식이 아니면 None."""
    pieces = cw.split_outside_parens(title or "", ",")
    if len(pieces) < 2:
        return None
    names_part, rest = pieces[0], ", ".join(pieces[1:])
    m = REST_RE.match(rest.strip()) or REST_MORE_RE.match(rest.strip())
    if not m or len(names_part) > cw.MAX_SLOT_LEN:
        return None
    more = (m.group("more") or "").strip()            # '양홍원, 판다곰 싱글 …' 처럼 쉼표 뒤에 이어진 이름
    if len(more) > cw.MAX_SLOT_LEN:
        return None
    names = [n.strip() for n in NAME_SPLIT.split(names_part) + (NAME_SPLIT.split(more) if more else []) if n and n.strip()]
    if not names or any(n.count(" ") > MAX_NAME_SPACES for n in names):
        return None
    names = [n for n in names if not LABEL_NAME.search(n)]
    if not names:
        return None
    release = next((v for k, v in m.groupdict().items() if k.startswith("q") and v is not None), "")
    return {"artists": names[:cw.MAX_ARTISTS_PER_ARTICLE], "release_title": release.strip()}


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
            page = res["page"] + 1
            print(f"  {res['page']}쪽: 글 {len(items)}건, 새 글 {len(fresh)}건 (가장 오래된 {items[-1]['date']})",
                  file=sys.stderr)
            if too_old:
                stop = True
                break
        if stop:
            break
    return fresh_all, page


def main(argv: Sequence[str]) -> int:
    ap = argparse.ArgumentParser(description="힙합엘이 국내 뉴스 (aside 브라우저)")
    ap.add_argument("--backfill", action="store_true", help="과거 기록을 상태 파일의 다음 쪽부터 이어 받기")
    ap.add_argument("--max-pages", type=int, default=DAILY_PAGES)
    ap.add_argument("--since", default=None, help="이 날짜보다 오래된 글이 나오면 멈춤 (YYYY-MM-DD)")
    ap.add_argument("--no-time-guard", action="store_true", help="21~23시에도 실행 (daily_run 안에서만)")
    args = ap.parse_args(argv)
    now = datetime.now(KST)
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
    rows, unparsed = items_to_rows(fresh, now.replace(microsecond=0).isoformat())
    path = write_rows(rows, RAW_DIR, today) if rows else None
    if unparsed:
        REVIEW_DIR.mkdir(parents=True, exist_ok=True)
        (REVIEW_DIR / f"hiphople_unparsed_{today}.json").write_text(
            json.dumps(unparsed, ensure_ascii=False, indent=1), encoding="utf-8")
    state = mark_seen(state, [it["id"] for it in fresh],
                      backfill_next_page=next_page if args.backfill else None, today=today)
    save_state(STATE_PATH, state)
    print(f"✅ 새 글 {len(fresh)}건 → {len(rows)}행" + (f" → {path.relative_to(ROOT)}" if path else "")
          + f" · 발매 형식 아님 {len(unparsed)}건" + (f" · 다음 과거 쪽 {next_page}" if args.backfill else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
