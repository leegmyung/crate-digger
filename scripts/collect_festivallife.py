"""페스티벌라이프(https://www.festivallife.kr) '국내 페스티벌' 게시판 → 국내 페스티벌·회차 목록 (날짜·장소·근거 글)

    python3 scripts/collect_festivallife.py              # 목록·글을 읽어 data/raw/raw_festivallife_<날짜>.json + config/festival_catalog.json
    python3 scripts/collect_festivallife.py --pages 3    # 앞쪽 3쪽만 (주 1회 갱신용)
    python3 scripts/collect_festivallife.py --dry-run

왜: 나무위키 표가 없는 페스티벌·회차(잔다리·서울인디음악축제·렛츠락·사운드플래닛·지역 페스티벌 등)가 많다. 페스티벌라이프는
국내 페스티벌 소식(1차·2차·최종 라인업, 개최 일정)을 한 게시판에 모아 둔다.
무엇을: 글 제목(페스티벌 이름·연도·글 종류)과 본문 글자의 '일정'·'장소'만. 라인업은 포스터 그림이라 읽지 않는다
(그 회차는 목록·날짜·장소만 — lineup_text=false). 개인 정보(댓글·작성자)는 읽지 않는다.
예의: robots.txt — User-agent * 는 /site_join·/shop_cart·/?mode* 만 막음(파일 끝의 'User-agent: * Disallow: /' 그룹과
겹치지만 같은 길이 규칙은 허용 우선, 2026-11-28 확인). 한 번에 한 쪽, 쪽마다 1초 쉼, 일반 브라우저 User-Agent.
주 1회(월요일) 갱신 제안: scripts/daily_run.sh 에서 요일이 월요일일 때만 --pages 3.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
CATALOG = ROOT / "config" / "festival_catalog.json"
CACHE = RAW_DIR / "state" / "festivallife_posts.json"   # 읽은 글 캐시 (커밋 안 함, 끊겨도 이어 읽기)
BASE = "https://www.festivallife.kr"
LIST_URL = BASE + "/festival/?page={n}"
POST_URL = BASE + "/festival/?bmode=view&idx={idx}"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131 Safari/537.36"
KST = timezone(timedelta(hours=9))
PAUSE_SEC = 1.0
TIMEOUT_SEC = 30
YEARS = range(2021, 2027)

_LINK = re.compile(r'href="/festival/\?[^"]*bmode=view&idx=(\d+)[^"]*"(.*?)</a>', re.S)


def _text(fragment: str) -> str:
    t = html.unescape(re.sub(r"<[^>]+>", " ", fragment))
    return re.sub(r"\s+", " ", t.replace("-->", " ")).strip()


def parse_list(page: str) -> List[Tuple[str, str]]:
    """목록 쪽 → [(글 번호, 제목)] (앞의 '공지'·뒤의 새 글 표시 'N' 은 뗌, 같은 글은 1번)."""
    out, seen = [], set()
    for m in _LINK.finditer(page):
        idx, title = m.group(1), _text(m.group(2)).lstrip("> ").strip()
        title = re.sub(r"^공지\s*", "", title)
        title = re.sub(r"\s+N$", "", title).strip()
        if idx not in seen and title:
            seen.add(idx)
            out.append((idx, title))
    return out


def parse_title(title: str) -> Tuple[str, Optional[int], str]:
    """'이름 2026 - 최종 라인업' · '2025 이름 - 개최 일정' → (이름, 연도|None, 글 종류)."""
    title = title.replace("\ufeff", "").strip()
    title = re.sub(r"^\[[^\]]{1,6}\]\s*", "", title)                     # '[변경] …'
    head, kind = (title.split(" - ", 1) + [""])[:2] if " - " in title else (title, "")
    if not kind:                                                          # '… 개최 일정 공개' 처럼 구분선 없는 소식 글
        m = re.search(r"\s(개최|추가 일정|티켓|라인업|타임\s?테이블|일정|취소|연기|변경|온오프)(\s.*|!?)$", head)
        if m:
            head, kind = head[:m.start()], head[m.start():].strip()
    m = re.search(r"(?:^|\s)(20\d{2})(?:\s|$)", head)
    year = int(m.group(1)) if m else None
    name = re.sub(r"(?:^|\s)20\d{2}(?:\s|$)", " ", head) if m else head
    name = re.sub(r"\s\d{2}/\d{2}$", "", name)          # '카운트다운판타지 26/27'
    name = re.sub(r"\s20\d{2}\s*[-~]\s*20\d{2}$", "", name)   # '… 2026-2027'
    return re.sub(r"\s+", " ", name).strip(), year, kind.strip()


def _expand(y: int, m1: int, d1: int, m2: int, d2: int) -> List[str]:
    try:
        a, b = date(y, m1, d1), date(y, m2, d2)
    except ValueError:
        return []
    if b < a or (b - a).days > 14:
        return [a.isoformat()]
    return [(a + timedelta(days=i)).isoformat() for i in range((b - a).days + 1)]


def parse_dates(text: str) -> List[str]:
    """'2026년 10월 17~18일' · '2025년 9월 30일~10월 2일' · '2026년 10월 17일' → ISO 날짜들."""
    m = re.search(r"(20\d{2})년\s*(\d{1,2})월\s*(\d{1,2})일?\s*[~～\-]\s*(?:(\d{1,2})월\s*)?(\d{1,2})일", text)
    if m:
        y, m1, d1 = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return _expand(y, m1, d1, int(m.group(4) or m1), int(m.group(5)))
    m = re.search(r"(20\d{2})년\s*(\d{1,2})월\s*(\d{1,2})일", text)
    if m:
        try:
            return [date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()]
        except ValueError:
            return []
    return []


def parse_post(page: str) -> dict:
    """글 본문 → {'dates': [...], 'venue': '…', 'poster_images': n} (본문의 '일정'·'장소' 줄)."""
    body = re.sub(r"<script.*?</script>|<style.*?</style>", " ", page, flags=re.S)
    lines = [l.strip() for l in html.unescape(re.sub(r"<[^>]+>", "\n", body)).split("\n") if l.strip()]
    dates, venue = [], ""
    for l in lines:
        if not dates and re.match(r"^(공연\s*)?(일정|일시)\s*[:：]", l):
            dates = parse_dates(l)
        if not venue and re.match(r"^(공연\s*)?장소\s*[:：]", l):
            venue = re.split(r"[:：]", l, 1)[1].strip()
    posters = len(re.findall(r'<img[^>]+src="https://cdn\.imweb\.me/upload/', page))
    return {"dates": dates, "venue": venue, "poster_images": posters}


def festival_key(name: str) -> str:
    """같은 페스티벌의 띄어쓰기·대소문자·기호 차이를 하나로 (예: '인천 펜타포트 락 페스티벌' = '인천펜타포트락페스티벌')."""
    if re.search(r"[가-힣]", name) and re.search(r"[A-Za-z]{3,}", name):
        hangul = re.sub(r"[^가-힣0-9]", "", name)       # 한·영 같이 쓴 이름은 한글만 ('Madly Medley 매들리 메들리' = '매들리 메들리')
        if len(hangul) >= 3:
            name = hangul
    k = re.sub(r"[\s\-·_&'\"!?,.:()\[\]]", "", name).lower()
    return k.replace("록", "락").replace("페스타", "페스티벌").replace("festival", "페스티벌")


def build_catalog(posts: Iterable[dict], years: Sequence[int] = YEARS) -> Dict[str, dict]:
    """글 목록 → {페스티벌 키: {'name', 'editions': {연도: {dates, venue, posts, lineup_text}}}} (years 안의 회차만)."""
    cat: Dict[str, dict] = {}
    for p in posts:
        name, year, kind = parse_title(p["title"])
        if year is None and p.get("dates"):
            year = int(p["dates"][0][:4])
        if year is None or year not in years:
            continue
        f = cat.setdefault(festival_key(name), {"name": name, "editions": {}})
        e = f["editions"].setdefault(str(year), {"dates": [], "venue": "", "posts": [], "lineup_text": False})
        e["posts"].append({"title": p["title"], "kind": kind, "url": POST_URL.format(idx=p["idx"])})
        if p.get("dates") and (not e["dates"] or "최종" in kind):      # 최종 글의 날짜를 우선
            e["dates"] = list(p["dates"])
        if p.get("venue") and (not e["venue"] or "최종" in kind):
            e["venue"] = p["venue"]
    for f in cat.values():
        f["editions"] = dict(sorted(f["editions"].items()))
    return dict(sorted(cat.items()))


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ko"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as r:
        return r.read().decode("utf-8", "ignore")


def crawl(max_pages: int, report: List[str], fetch_fn=None, cache: Optional[Dict[str, dict]] = None,
          pause: float = PAUSE_SEC, save=None) -> List[dict]:
    """목록 1쪽부터 — 같은 쪽이 되풀이되면(마지막 쪽 뒤) 멈춤. 글마다 본문을 한 번씩 읽는다.
    cache(글 번호 → 읽은 결과)에 있는 글은 다시 읽지 않고, 새로 읽은 글은 cache 에 넣는다 — 인터넷이 끊겨도 이어서.
    save(cache) 를 주면 20편마다 부른다(중간 저장)."""
    fetch_fn = fetch_fn or fetch
    cache = cache if cache is not None else {}
    items, seen_idx, strikes, n = [], set(), 0, 0
    for n in range(1, max_pages + 1):
        try:
            page = parse_list(fetch_fn(LIST_URL.format(n=n)))
        except OSError as e:
            report.append(f"  목록 {n}쪽 읽기 실패: {e}")
            page = []
        time.sleep(pause)
        new = [(i, t) for i, t in page if i not in seen_idx]
        if not new:                       # 새 글 없는 쪽이 두 번 이어지면 끝(마지막 쪽 뒤는 마지막 쪽이 되풀이됨)
            strikes += 1
            if strikes >= 2:
                break
            continue
        strikes = 0
        seen_idx.update(i for i, _ in new)
        items.extend(new)
    report.append(f"  목록 {n}쪽 · 글 {len(items)}편")
    posts, seen, fresh = [], set(), 0
    for idx, title in items:
        if idx in seen:
            continue
        seen.add(idx)
        if idx not in cache:
            try:
                info = parse_post(fetch_fn(POST_URL.format(idx=idx)))
            except OSError as e:
                report.append(f"  글 {idx} 읽기 실패: {e}")
                continue
            cache[idx] = {"idx": idx, "title": title, **info}
            fresh += 1
            time.sleep(pause)
            if save and fresh % 20 == 0:
                save(cache)
        posts.append({**cache[idx], "title": title})
    report.append(f"  글 본문 새로 읽음 {fresh}편 · 캐시 {len(posts) - fresh}편")
    if save:
        save(cache)
    return posts


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="페스티벌라이프 국내 페스티벌 목록·회차 수집")
    ap.add_argument("--pages", type=int, default=60, help="읽을 목록 쪽 수 (주 1회 갱신은 3)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--offline", action="store_true", help="인터넷 없이 읽은 글 캐시만으로 목록을 다시 만듦")
    args = ap.parse_args(argv)
    now = datetime.now(KST)
    report = ["페스티벌라이프 수집"]
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}

    def save(c):
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")
    if args.offline:
        posts = sorted(cache.values(), key=lambda p: -int(p["idx"]))
        report.append(f"  캐시만 사용: 글 {len(posts)}편")
    else:
        posts = crawl(args.pages, report, cache=cache, save=None if args.dry_run else save)
    if CATALOG.exists() and args.pages < 60 and not args.offline:                       # 앞쪽만 읽었으면 예전 글과 합침
        old = json.loads(CATALOG.read_text(encoding="utf-8")).get("posts", [])
        keep = {p["idx"] for p in posts}
        posts += [p for p in old if p["idx"] not in keep]
    cat = build_catalog(posts)
    report.append(f"  페스티벌 {len(cat)}곳 · 회차 {sum(len(f['editions']) for f in cat.values())}개 ({YEARS.start}~{YEARS.stop - 1})")
    if not args.dry_run:
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        raw = RAW_DIR / f"raw_festivallife_{now.date().isoformat()}.json"
        if not args.offline:                                        # 캐시만 썼으면 원본은 그대로 둠
            raw.write_text(json.dumps(posts, ensure_ascii=False, indent=1), encoding="utf-8")
        CATALOG.write_text(json.dumps({
            "_설명": "페스티벌라이프 '국내 페스티벌' 게시판에서 모은 국내 페스티벌·회차 (scripts/collect_festivallife.py). "
                     "날짜·장소는 글 본문 글자, 라인업은 포스터 그림이라 없음(lineup_text=false) — 라인업 팀은 config/festival_lineups.json. "
                     "posts = 글 제목·번호·날짜·장소(다음 갱신 때 합치려고 보관).",
            "checked": now.date().isoformat(), "source": BASE + "/festival", "festivals": cat,
            "posts": [{k: p[k] for k in ("idx", "title", "dates", "venue")} for p in posts]},
            ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        report.append(f"  → {raw.name} · {CATALOG.relative_to(ROOT)}")
    print("\n".join(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
