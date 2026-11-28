"""천안 달빛산책(뮤직바·공연장) 블로그 'Live Stage' 글 → 공연 원본 data/raw/raw_kr_gig_<날짜>_regional_moonlight.csv

    python3 scripts/collect_moonlight_walk.py            # 되짚기: 지난 2년 (블로그 글 목록 전부 훑음)
    python3 scripts/collect_moonlight_walk.py --pages 2  # 월 1회 다시 보기: 최근 글 60개만
    python3 scripts/collect_moonlight_walk.py --dry-run  # 파일은 안 쓰고 몇 행인지만

왜: 달빛산책(충남 천안, 2025-11 개업)은 인디고·인디스트릿에 공연이 올라오지 않는다. 공식 블로그
(https://blog.naver.com/moonlight_walk_bar)에 공연마다 일정 글('🌙 YYYY.MM.DD (요일) 팀 – Live at 달빛산책', '소식 / 공연 일정')과
일부 공연의 후기 글('달빛산책 Live Stage YYYY. MM. DD. 팀', '대관 / 공연 사례')이 올라온다.
읽는 법: blog.naver.com 의 robots.txt 가 자동 수집을 막아(프로젝트 규칙) 스크립트로 받지 않고 aside 브라우저(aside repl)로
m.blog.naver.com 글 목록 화면을 연 뒤, 그 화면이 쓰는 글 목록(post-list)을 같은 사이트 안에서 읽는다. 일부러 쉬지 않는다.
쓰는 것은 공연 날짜·출연 팀 이름과 근거 글 주소뿐(글 본문·사진은 저장하지 않음).

형식: scripts/csv_schema.py raw_kr_gig, source = regional (collect_regional_gigs 와 같음).
- 공연 1건 × 출연 팀 1팀 = 1행. 한 공연을 (2)(3)으로 나눠 올린 글은 첫 글(글 번호가 가장 작은 것) 하나만 근거로 쓴다.
- gig_date = 제목의 공연 날짜(글 올린 날 아님), gig_time = 일정 글에 시각이 있으면. 'YYMMDD 팀 달빛산책 Live Stage',
  '1st Anniversary 팀'·'Special Live 팀'(날짜는 글 요약의 'YYYY년 M월 D일')도 읽는다. 날짜를 못 찾는 글(공지·대관 안내·
  술 소개)과 오픈 잼(Moonlight Playground)·드럼 솔로 영상 글은 건너뛴다.
- 팀 나누기: ', / & ·' 로 나누되, 끝이 Quartet·Quintet·Trio·Duo 인 한 팀 이름('홍태연 · 김의진 Quartet')과
  'X & Friends' 꼴은 나누지 않는다. 'Min Paul (민폴)'·'HSC (Highway Surf Club)' 처럼 괄호가 있으면 한글 이름, 없으면 긴 이름을 쓴다.
- 같은 날 같은 팀은 글이 여럿이어도 1행 — 일정 글이 먼저, 다음은 글 번호가 작은 글이 근거. 같은 팀 판단: 띄어쓰기·
  기호 무시·'밴드'='band', 같은 날 다른 이름의 한 조각('홍태연'·'김의진 Quartet' ⊂ '홍태연 · 김의진 Quartet')이거나
  거의 같은 철자(오타 'Highwway')면 같은 팀. 후기 글의 날짜가 일정 글과 1~3일 어긋난 같은 팀 행은 버린다(일정 글이 맞음).
- artist_url = 글 요약에서 팀 이름 바로 뒤에 붙은 인스타 @계정이 있을 때만.
- 다시 돌릴 때(월 1회): 이미 쓴 달빛산책 원본(raw_kr_gig_*_regional_moonlight*.csv)에 같은 날 같은 팀이 있으면 쓰지 않는다
  (근거 글이 일정 글 → 후기 글로 바뀌어 주소가 달라도). 후기 글 날짜가 저장된 공연과 1~3일 어긋나도 쓰지 않는다.
"""
from __future__ import annotations

import argparse
import csv
import difflib
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import collect_regional_gigs as crg
from collect_gigs import run_repl

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
KST = timezone(timedelta(hours=9))
BLOG_ID = "moonlight_walk_bar"
POST_URL = f"https://blog.naver.com/{BLOG_ID}/{{log_no}}"
VENUE_TEXT = "달빛산책 (충남 천안시 동남구 청수11로 26 205호)"
FILE_TAG = "regional_moonlight"
WINDOW_DAYS = 730          # 지난 2년
PAGE_SIZE = 30
MAX_PAGES = 20             # 30 × 20 = 600글 (2026-11 기준 약 360글)
BRIEF_KEEP = 600           # 요약은 인스타 @계정 찾기에만 쓴다

SCHEDULE = re.compile(r"(\d{4})\.(\d{1,2})\.(\d{1,2})\s*(?:(\d{1,2}:\d{2})\s*)?\([^)]*\)\s*(?P<acts>.+?)\s*[–-]\s*Live\s+at\s+달빛산책")
LIVE_STAGE = re.compile(r"Live\s*Stage\s*(\d{4})\s*\.\s*(\d{1,2})\s*\.\s*(\d{1,2})\s*\.?\s*(?P<acts>.+)$", re.I)
SHORT_DATE = re.compile(r"^(\d{2})(\d{2})(\d{2})\s+(?P<acts>.+?)\s+달빛산책\s*Live\s*Stage", re.I)
TEXT_TITLE = re.compile(r"(?:Special\s*Live|1st\s*Anniversary)\s+(?:첫|두|세|네)?(?:번째\s*뮤지션\s*)?(?P<acts>.+)$", re.I)
TEXT_DATE = re.compile(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일")
SKIP = re.compile(r"Moonlight\s*Playground|Open\s*Jam|Drum\s*Solo", re.I)
PART = re.compile(r"\s*(?:\(\d+\)|#\d+|\d+(?:st|nd|rd|th))\s*$", re.I)
SPLIT_HARD = re.compile(r"\s*[,/]\s*")
SPLIT_SOFT = re.compile(r"\s+[&·]\s+|(?<=[가-힣])\s*&\s*(?=[가-힣])")
ENSEMBLE = re.compile(r"\b(Quartet|Quintet|Trio|Duo|Sextet|Septet)$", re.I)
GENERIC = re.compile(r"^(friends|rising\s*stars|친구들)$", re.I)
BRACKET = re.compile(r"^(?P<out>.+?)\s*[(\[](?P<in>[^)\]]+)[)\]]$")
HANGUL = re.compile(r"[가-힣]")
HANDLE = r"@([A-Za-z0-9_.]+)"
SIMILAR = 0.88             # 같은 날 두 이름이 이만큼 비슷하면 같은 팀(오타)
NEAR_DAYS = 3              # 후기 글 날짜가 일정 글과 이만큼 안에서 어긋나면 후기 쪽을 버림


def _iso(y: int, m: int, d: int) -> Optional[str]:
    try:
        return date(y, m, d).isoformat()
    except ValueError:
        return None


def clean_name(name: str) -> str:
    """'Min Paul (민폴)' → 민폴, 'HSC (Highway Surf Club)' → Highway Surf Club (괄호 속이 한글이거나 더 길면 괄호 속)."""
    n = PART.sub("", name.strip()).strip()
    m = BRACKET.match(n)
    if not m:
        return n
    out, inner = m.group("out").strip(), m.group("in").strip()
    return inner if HANGUL.search(inner) or len(inner) > len(out) else out


def split_acts(text: str) -> List[str]:
    acts = []
    for part in SPLIT_HARD.split(PART.sub("", text).strip()):
        soft = SPLIT_SOFT.split(part)
        keep_whole = len(soft) > 1 and (ENSEMBLE.search(part.strip()) or any(GENERIC.match(x.strip()) for x in soft))
        acts.extend([part] if keep_whole else soft)
    return [c for c in (clean_name(a) for a in acts) if c]


def norm_key(name: str) -> str:
    """같은 팀 비교용: 소문자·'밴드'→band·글자와 숫자만."""
    return re.sub(r"[^0-9a-z가-힣]", "", name.lower().replace("밴드", "band"))


def parse_show(title: str, brief: str = "") -> Optional[Tuple[str, str, List[str]]]:
    """글 제목(+요약) → (공연 날짜, 시작 시각 또는 '', [팀]) 또는 공연 글이 아니면 None."""
    got = _parse(title, brief)
    return got[:3] if got else None


def _parse(title: str, brief: str = "") -> Optional[Tuple[str, str, List[str], bool]]:
    """parse_show + 일정 글('… – Live at 달빛산책')인지."""
    t = (title or "").strip()
    if SKIP.search(t):
        return None
    day, start, acts_text, schedule = None, "", None, False
    for pat, year_base in ((SCHEDULE, 0), (LIVE_STAGE, 0), (SHORT_DATE, 2000)):
        m = pat.search(t)
        if m:
            day = _iso(year_base + int(m.group(1)), int(m.group(2)), int(m.group(3)))
            schedule = pat is SCHEDULE
            start = (m.group(4) or "") if schedule else ""
            acts_text = m.group("acts")
            break
    else:
        m = TEXT_TITLE.search(t)
        d = TEXT_DATE.search(brief or "")
        if m and d:
            day = _iso(int(d.group(1)), int(d.group(2)), int(d.group(3)))
            acts_text = m.group("acts")
    if not day or not acts_text:
        return None
    if start and len(start) == 4:
        start = "0" + start
    acts = split_acts(acts_text)
    return (day, start, acts, schedule) if acts else None


def parse_title(title: str, brief: str = "") -> Optional[Tuple[str, List[str]]]:
    """parse_show 에서 시각을 뺀 것 (공연 날짜, [팀])."""
    got = parse_show(title, brief)
    return (got[0], got[2]) if got else None


def artist_url(name: str, brief: str) -> str:
    """요약에서 '팀이름 @계정' 꼴이면 그 인스타 주소."""
    m = re.search(re.escape(name) + r"\s*" + HANDLE, brief or "")
    return f"https://www.instagram.com/{m.group(1).rstrip('.')}/" if m else ""


def rows_from_posts(posts: Iterable[dict], collected_at: str, as_of: date) -> List[Dict[str, str]]:
    """블로그 글 목록 → 공연 원본 행 (지난 2년, 공연·팀마다 첫 글 하나, 날짜·팀 순)."""
    kept = _dedupe(_candidates(posts, (as_of - timedelta(days=WINDOW_DAYS)).isoformat(), as_of.isoformat()))
    rows = []
    for b in sorted(kept, key=lambda c: (c["day"], int(c["post"]["logNo"]), c["order"])):
        day = b["day"]
        p, multi = b["post"], b["size"] > 1
        row = crg._row(collected_at, "aside", f"moonlight_walk:{p['logNo']}", day, p["title"], VENUE_TEXT, b["name"],
                       POST_URL.format(log_no=p["logNo"]), str(b["order"]) if multi else "", "",
                       str(b["size"]) if multi else "")
        row["gig_time"] = b["start"]
        row["artist_url"] = artist_url(b["name"], p.get("brief", ""))
        rows.append(row)
    return rows


def _candidates(posts: Iterable[dict], first_day: str, last_day: str) -> List[dict]:
    """글마다 (날짜, 팀) 후보 — 일정 글 먼저, 다음 글 번호 순."""
    cands = []
    for p in posts:
        got = _parse(p.get("title", ""), p.get("brief", ""))
        if not got or not (first_day <= got[0] <= last_day):
            continue
        day, start, acts, schedule = got
        for i, name in enumerate(acts, 1):
            cands.append({"day": day, "key": norm_key(name), "name": name, "start": start, "post": p,
                          "order": i, "size": len(acts), "schedule": schedule})
    return sorted(cands, key=lambda c: (not c["schedule"], int(c["post"]["logNo"]), c["order"]))


def _same_act(a: str, b: str) -> bool:
    if a == b:
        return True
    short, long_ = sorted((a, b), key=len)
    if len(short) >= 2 and short in long_:
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= SIMILAR


def _days_apart(a: str, b: str) -> int:
    return abs((date.fromisoformat(a) - date.fromisoformat(b)).days)


def _dedupe(cands: Sequence[dict]) -> List[dict]:
    sched_days: Dict[str, List[str]] = {}
    for c in cands:
        if c["schedule"]:
            sched_days.setdefault(c["key"], []).append(c["day"])
    kept: List[dict] = []
    for c in cands:
        near = sched_days.get(c["key"], [])
        if not c["schedule"] and c["day"] not in near and any(0 < _days_apart(c["day"], d) <= NEAR_DAYS for d in near):
            continue   # 후기 글 날짜가 일정 글과 어긋남 → 일정 글을 믿는다
        if any(k["day"] == c["day"] and _same_act(k["key"], c["key"]) for k in kept):
            continue
        kept.append(c)
    return kept


def only_new_shows(rows: Sequence[Dict[str, str]], raw_dir: Path) -> List[Dict[str, str]]:
    """이미 쓴 달빛산책 원본과 같은 공연(같은 날 같은 팀, 또는 후기 글 날짜가 1~3일 어긋난 같은 팀)을 뺀 새 행."""
    saved = []
    for path in sorted(raw_dir.glob(f"raw_kr_gig_*_{FILE_TAG}*.csv")):
        with open(path, encoding="utf-8", newline="") as fh:
            saved.extend((r["gig_date"], norm_key(r["artist_text"])) for r in csv.DictReader(fh))
    out = []
    for r in rows:
        day, key = r["gig_date"], norm_key(r["artist_text"])
        recap = not SCHEDULE.search(r.get("title", ""))
        if any(d == day and _same_act(k, key) for d, k in saved):
            continue
        if recap and any(k == key and _days_apart(d, day) <= NEAR_DAYS for d, k in saved):
            continue
        out.append(r)
    return out


def write_rows(rows: Sequence[Dict[str, str]], out_dir: Path, day: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"raw_kr_gig_{day}_{FILE_TAG}.csv"
    if path.exists():  # 원본은 고치지 않는다
        path = out_dir / f"raw_kr_gig_{day}_{FILE_TAG}_{datetime.now(KST):%H%M%S}.csv"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=crg.COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def page_js(pages: int) -> str:
    """aside repl 코드: 블로그 첫 화면을 열고 글 목록(post-list)을 쪽마다 읽어 'RESULT {posts}' 한 줄로."""
    return f"""
await (async () => {{
  const t = await openTab('https://m.blog.naver.com/{BLOG_ID}');
  const posts = await t.evaluate(async (maxPages) => {{
    const out = [];
    for (let page = 1; page <= maxPages; page++) {{
      const r = await fetch('/api/blogs/{BLOG_ID}/post-list?categoryNo=0&itemCount={PAGE_SIZE}&page=' + page, {{ credentials: 'include' }});
      if (!r.ok) break;
      const items = ((await r.json()).result || {{}}).items || [];
      if (!items.length) break;
      for (const it of items) out.push({{ logNo: String(it.logNo), title: it.titleWithInspectMessage || '',
        brief: (it.briefContents || '').slice(0, {BRIEF_KEEP}), category: it.categoryName || '' }});
    }}
    return out;
  }}, {int(pages)});
  await closeTab(t);
  console.log('RESULT ' + JSON.stringify({{ posts }}));
}})();
"""


def main(argv: Sequence[str]) -> int:
    ap = argparse.ArgumentParser(description="달빛산책 블로그 Live Stage 글 → 공연 원본(regional)")
    ap.add_argument("--pages", type=int, default=MAX_PAGES, help=f"읽을 글 목록 쪽 수 (한 쪽 {PAGE_SIZE}글)")
    ap.add_argument("--out", type=Path, default=RAW_DIR)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    now = datetime.now(KST)
    result = run_repl(page_js(args.pages))
    posts = result.get("posts", [])
    rows = rows_from_posts(posts, now.isoformat(timespec="seconds"), now.date())
    new = only_new_shows(crg.only_new(rows, crg.existing_keys(args.out)), args.out)
    shows = len({r["gig_date"] for r in rows})
    print(f"블로그 글 {len(posts)}개 → 공연 {shows}회 · {len(rows)}행 (새 행 {len(new)})")
    if args.dry_run or not new:
        return 0
    path = write_rows(new, args.out, now.date().isoformat())
    print(f"✅ → {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
