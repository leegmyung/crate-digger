"""KT&G 상상마당 공연 목록 수집기 → data/raw/raw_kr_gig_<날짜>_sangsangmadang.csv

    python3 scripts/collect_ssm_shows.py                     # 전체 (지난 공연 포함), 새로 나온 행만
    python3 scripts/collect_ssm_shows.py --since 2024-01-01  # 이 날짜 이후 공연만

- 목록: https://www.sangsangmadang.com/show/list 화면이 부르는 JSON 주소
  (POST /show/selectShowList/ALL/all, page=1,2,… 한 쪽에 12건). robots.txt 전체 허용.
- 상세: GET /show/detail/<번호> HTML. 시간은 표의 '시간' 칸, 출연 팀은 본문의 '출연:' 줄에서 읽는다.
  본문이 포스터 그림뿐이면 공연명에서 조심스럽게 뽑는다 ('X 단독 콘서트', 'X 전국투어' 등).
  애매한 공연(페스티벌·학교 정기공연·클럽데이 등)은 건너뛴다.
- 뮤지컬·연극·영화·코미디 등 음악 공연이 아닌 것은 뺀다.
- 끝난 공연은 한 번 읽으면 data/raw/state/ssm_shows_seen.json 에 적어 다시 읽지 않는다.
  예정 공연은 출연진이 바뀔 수 있어 매번 다시 읽고 새 행만 쓴다.
- 형식: docs/csv_spec.md 2장 / scripts/csv_schema.py
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

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
STATE = RAW_DIR / "state" / "ssm_shows_seen.json"
KST = timezone(timedelta(hours=9))
USER_AGENT = "crate-digger/0.1 (+https://github.com/leegmyung/crate-digger)"
COLUMNS = [f.name for f in TABLES["raw_kr_gig"]["fields"]]
KEY = TABLES["raw_kr_gig"]["key"]
SOURCE = "sangsangmadang"
REQUEST_DELAY_SEC = 0.3
TIMEOUT_SEC = 30
MAX_LIST_PAGES = 500

BASE = "https://www.sangsangmadang.com"
LIST_URL = BASE + "/show/selectShowList/ALL/all"
DETAIL_URL = BASE + "/show/detail/{seq}"

BRANCHES = {"HD": "홍대", "CC": "춘천", "BS": "부산", "DS": "부산", "DC": "대치", "NS": "논산"}
BRANCH_WORDS = re.compile(r"홍대|춘천|부산|대치|논산|강남")

MUSIC_CATEGORIES = {"콘서트", "힙합", "기타"}
NON_MUSIC_GENRE = re.compile(
    r"영화|교육|코미디|애니|에니|강연|포럼|상영|무용|인형극|연극|뮤지컬|전시|네트워킹|오페라|클래식|"
    r"드라마|워크숍|클래스|캠프|댄스")

# ---- 본문 '출연:' 줄 ----
BODY_LABEL = re.compile(
    r"^[\s•·\-\*■□▶▷☆★◆◇●○※>]*"
    r"(?:(출연(?:\s*아티스트|진|자)?|아티스트|라인업|line\s*-?\s*up)\s*[:：]\s*|(출연)\s+)(.+)$", re.I)
SPLIT_NAMES = re.compile(r"\s*(?:,|/|·|、|\s[xX×]\s|\s&\s)\s*")
QUOTED = re.compile(r"^[^,'\"‘“]*['\"‘“]([^'\"’”]+)['\"’”]\s*$")
VAGUE = re.compile(r"초대손님|게스트|다수|재학생|전공|학생|대학|학교|정기공연|교수|출연진|소개|정보|미정|추후|공개|"
                   r"\d+\s*팀|등$|및|감독|진행|클래스|and more|special guest|신인 아티스트|학원|아카데미|실용음악|작가|예술원|"
                   r"상상파트너즈")
GUEST_PREFIX = re.compile(r"^(?:special\s+)?guests?\s*[:：]?\s*|^게스트\s*[:：]?\s*", re.I)
ROLE_IN_PAREN = re.compile(r"개그|MC|사회|진행|아나운서")
DAY_PREFIX = re.compile(r"^(?:\d+\s*월\s*)?\d+\s*일\s*[\)\-:：]?\s*")
ROLE_PREFIX = re.compile(r"^(?:싱어송라이터|밴드)\s+")
MAX_LINE = 120
MAX_NAME = 30

# ---- 공연명 ----
NAME_TOK = r"[^\s\[\]<>〈〉《》「」:：'\"‘’“”]+"
TITLE_MAIN = re.compile(
    rf"^(?P<name>{NAME_TOK}(?:\s+{NAME_TOK}){{0,2}}?)\s+"
    r"(?:(?:서울|부산|춘천|홍대|대치|논산)\s+)?(?:\d{4}\s+)?(?:\d+\s*주년\s+)?"
    r"(?:(?:정규|미니)\s*\d*\s*집?\s+|EP\s+|\d+\s*집\s+|\d+(?:st|nd|rd|th)\s+|첫\s*(?:번째\s+)?)?"
    r"(?:"
    r"(?:(?:여름|겨울|봄|가을|연말|송년|신년)\s*)?단독\s*(?:콘서트|공연)"
    r"|(?:\S+\s+)?발매\s*(?:기념\s*)?(?:단독\s*)?(?:공연|콘서트|쇼케이스)"
    r"|(?:(?:여름|겨울|봄|가을)\s*)?(?:클럽\s*|전국\s*)?투어"
    r"|(?:(?:소극장|라이브|어쿠스틱|팬|장기)\s*)?(?:(?:여름|겨울|봄|가을|썸머|윈터|연말|송년|신년|앵콜)\s*)?(?:콘서트|공연)"
    r"|쇼케이스"
    r")(?=$|[\s\[\(<〈《「\-:：'‘\"“])", re.I)
TITLE_SERIES = re.compile(r"^(?:상상스테이지\s*\d+|ZIPPER\s*\d+\.?|C-indie\s*play|WUNDERBUSK!)\s*[:：]?\s*(.+)$", re.I)
TITLE_PAIR = re.compile(r"^(\S+(?:\s\S+)?)\s+[xX×]\s+(\S+(?:\s\S+)?)$")
LEAD_TAG = re.compile(r"^\s*\[[^\]]*\]\s*")
LEAD_YEAR = re.compile(r"^\s*\d{4}\s+")
STRONG_KW = re.compile(r"단독|투어|발매")
BRACKET = re.compile(r"\[([^\]]+)\]")
BAD_NAME = re.compile(
    r"상상마당|KT&G|페스티벌|페스타|축제|대학|학과|학교|프로젝트|시즌|차세대|기념|합창|오케스트라|교향|"
    r"크리스마스|정규|미니|앨범|어린이날|상상파트너즈|[:：]|팬미팅|트리뷰트|song\s*book|러브레이크|\d+(?:st|nd|rd|th)\b|루프탑|상생|콜라보|레이블|디스커버리|지원|조인트|\d+년|festival|vol\.?|^the$|^\d+$|_", re.I)
PAREN = re.compile(r"\s*[\(（][^\)）]*[\)）]\s*")


def clean_text(fragment):
    """태그를 지우고 HTML 문자를 두 번 풀어(사이트가 &amp;nbsp; 처럼 두 번 감싼 곳이 있음) 공백을 정리."""
    text = re.sub(r"<[^>]+>", "", fragment or "")
    text = html.unescape(html.unescape(text)).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def _normalize_title(title):
    t = clean_text(title).replace("［", "[").replace("］", "]").replace("＆", "&")
    return t


def _clean_name(name):
    name = PAREN.sub(" ", name).strip(" -–·•'\"‘’“”")
    return re.sub(r"\s+", " ", name).strip()


def _ok_name(name):
    return bool(name) and len(name) <= MAX_NAME and not BAD_NAME.search(name)


def _title_main(text):
    text = LEAD_YEAR.sub("", LEAD_TAG.sub("", text)).strip()
    text = re.sub(r"^SSHOWBOX\s+", "", text, flags=re.I)   # 상상마당 기획 시리즈 머리말
    m = TITLE_MAIN.match(text)
    if not m:
        return []
    name = re.sub(r"\s*단독$", "", _clean_name(m.group("name")))
    return [name] if _ok_name(name) else []


def performers_from_title(title):
    """공연명에서 출연 팀을 조심스럽게 뽑는다. 확실한 꼴이 아니면 빈 목록."""
    t = _normalize_title(title)
    series = TITLE_SERIES.match(t)
    if series:
        rest = _clean_name(series.group(1))
        if rest and not re.search(r"[:：<〈《]", rest) and _ok_name(rest):
            return [rest]
        return []
    pair = TITLE_PAIR.match(t)
    if pair:
        names = [_clean_name(pair.group(1)), _clean_name(pair.group(2))]
        return names if all(_ok_name(n) for n in names) else []
    got = _title_main(t)
    if got:
        return got
    for inner in BRACKET.findall(t):   # '시리즈명 [X 단독 콘서트]' 꼴
        if STRONG_KW.search(inner):
            got = _title_main(inner)
            if got:
                return got
    return []


def _pieces(content):
    """'A (Guest B, C 외)' 처럼 괄호 안에 쉼표가 있으면 괄호를 풀어 각각 한 팀으로 본다."""
    for piece in SPLIT_NAMES.split(content):
        if piece.count("(") + piece.count("（") != piece.count(")") + piece.count("）"):
            yield from (x for x in re.split(r"[\(（\)）]", piece) if x.strip())
        else:
            yield piece


def _names_from_content(content):
    content = DAY_PREFIX.sub("", content.strip())
    quoted = QUOTED.match(content)
    if quoted:
        content = quoted.group(1)
    names = []
    for piece in _pieces(content):
        paren = " ".join(re.findall(r"[\(（]([^\)）]*)[\)）]", piece))
        if ROLE_IN_PAREN.search(paren):
            continue
        name = ROLE_PREFIX.sub("", GUEST_PREFIX.sub("", _clean_name(piece)))
        if re.fullmatch(r"\S(?: \S)+", name):   # '포 크 스 푼' 처럼 한 글자씩 띄운 이름
            name = name.replace(" ", "")
        name = re.sub(r"\s*외$|\s+with\s+special\s+guests?$", "", name, flags=re.I).strip()
        if not name or VAGUE.search(name) or len(name) > MAX_NAME or re.search(r"[<>:：]", name):
            continue
        names.append(name)
    return list(dict.fromkeys(names))


def performers_from_body(lines):
    """본문 줄 가운데 '출연: A, B' 꼴의 첫 줄에서 팀 이름을 뽑는다."""
    for line in lines or []:
        m = BODY_LABEL.match(line.strip())
        if not m:
            continue
        content = m.group(3).strip()
        if not content or len(content) > MAX_LINE:
            continue
        names = _names_from_content(content)
        if names:
            return names
    return []


def _hm(text):
    m = re.search(r"(\d{1,2}):(\d{2})", text or "")
    if m and int(m.group(1)) < 24 and int(m.group(2)) < 60:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    return ""


def parse_detail(page):
    """상세 HTML → {'time': 'HH:MM' 또는 '', 'lines': 본문 줄 목록}."""
    page = page or ""
    cell = re.search(r"<th[^>]*>\s*시간\s*</th>\s*<td[^>]*>(.*?)</td>", page, re.S)
    time_hm = _hm(clean_text(cell.group(1))) if cell else ""
    lines = []
    body = re.search(r"공유하기(.*?)>\s*목록\s*<", page, re.S)
    if body:
        # 본문 HTML이 한두 번 글자로 감싸여(&lt;br&gt;) 오는 공연이 있어 먼저 푼다
        chunk = html.unescape(html.unescape(body.group(1)))
        chunk = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", chunk, flags=re.S)
        chunk = re.sub(r"<br\s*/?>|</p>|</div>|</li>|</h\d>|</tr>", "\n", chunk, flags=re.I)
        lines = [ln for ln in (clean_text(x) for x in chunk.split("\n")) if ln]
    if not time_hm:   # 표에 시간이 없으면 본문 '일시: … 19:00' 줄에서
        when = next((ln for ln in lines if re.match(r"^[\s•·\-\*■]*일\s*시", ln)), "")
        time_hm = _hm(when)
    return {"time": time_hm, "lines": lines}


def is_music(item):
    category = item.get("cdVal") or ""
    if category in MUSIC_CATEGORIES:
        return True
    if category == "직접입력":
        return not NON_MUSIC_GENRE.search(item.get("genreTxt") or "")
    return False


CHAIN_PREFIX = re.compile(r"^\s*(?:KT\s*&\s*G\s*)?상상마당\s*")


def venue_text(item):
    """공연장 칸. 지점이 빠진 이름('라이브홀')은 '건물 + 홀'로 ('KT&G 상상마당 홍대 라이브홀').
    지점을 괄호에 두면 괄호 앞만 공연장으로 쓰는 규칙(SQL split_part) 때문에 지점이 사라진다 (2026-11-27 수정)."""
    loc = clean_text(item.get("performanceLocation"))
    branch = BRANCHES.get(item.get("spaceCd") or "", "")
    if not branch or BRANCH_WORDS.search(loc):
        return loc
    hall = CHAIN_PREFIX.sub("", loc).strip()
    return " ".join(p for p in (f"KT&G 상상마당 {branch}", hall) if p)


def gig_date(item):
    raw = item.get("startDt") or ""
    try:
        return datetime.strptime(raw, "%Y%m%d").strftime("%Y-%m-%d")
    except ValueError:
        return ""


def to_rows(item, detail, collected_at):
    day = gig_date(item)
    if not day:
        return []
    names = performers_from_body(detail.get("lines")) or performers_from_title(item.get("title"))
    seq = str(item.get("contentsSeq", ""))
    base = {"collected_at": collected_at, "source": SOURCE, "collector": "script", "source_id": seq,
            "gig_date": day, "gig_time": detail.get("time", ""), "title": _normalize_title(item.get("title")),
            "venue_text": venue_text(item), "artist_source_id": "",
            "gig_url": DETAIL_URL.format(seq=seq), "artist_url": ""}
    return [dict(base, artist_text=n) for n in dict.fromkeys(names)]


def select_items(items, since):
    if not since:
        return list(items)
    floor = since.replace("-", "")
    return [i for i in items if (i.get("startDt") or "") >= floor]


def row_key(row):
    return "|".join(row[k] for k in KEY)


def write_csv(rows, out_dir, day):
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"raw_kr_gig_{day}_{SOURCE}.csv"
    if path.exists():  # 원본은 고치지 않는다
        path = out_dir / f"raw_kr_gig_{day}_{SOURCE}_{datetime.now(KST):%H%M%S}.csv"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _open(req):
    with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as res:
        return res.read().decode("utf-8", errors="replace")


def fetch_list_page(page):
    data = urllib.parse.urlencode({"spaceCd": "ALL", "status": "all", "page": page}).encode()
    req = urllib.request.Request(LIST_URL, data=data, headers={"User-Agent": USER_AGENT, "AJAX": "true"})
    return json.loads(_open(req)).get("showListInfo", {}).get("showList") or []


def fetch_detail(seq):
    return _open(urllib.request.Request(DETAIL_URL.format(seq=seq), headers={"User-Agent": USER_AGENT}))


def fetch_all_items():
    items = []
    for page in range(1, MAX_LIST_PAGES + 1):
        got = fetch_list_page(page)
        if not got:
            break
        items.extend(got)
        time.sleep(REQUEST_DELAY_SEC)
    return items


def _load_state():
    try:
        data = json.loads(STATE.read_text(encoding="utf-8"))
        return set(data.get("done_shows", [])), set(data.get("rows", []))
    except (OSError, json.JSONDecodeError, AttributeError):
        return set(), set()


def _save_state(done, seen):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"done_shows": sorted(done, key=int), "rows": sorted(seen)},
                                ensure_ascii=False, indent=0), encoding="utf-8")


def collect(since=""):
    now = datetime.now(KST).replace(microsecond=0)
    at, day = now.isoformat(), f"{now:%Y-%m-%d}"
    done, seen = _load_state()
    items = select_items(fetch_all_items(), since)
    music = [i for i in items if is_music(i)]
    todo = [i for i in music if str(i.get("contentsSeq")) not in done]
    rows, failed, named = [], 0, 0
    for n, item in enumerate(todo, 1):
        seq = str(item.get("contentsSeq"))
        try:
            detail = parse_detail(fetch_detail(seq))
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            failed += 1
            print(f"⚠️ {seq}: 읽기 실패 ({e})", file=sys.stderr)
            continue
        got = to_rows(item, detail, at)
        named += bool(got)
        for r in got:
            if row_key(r) not in seen:
                seen.add(row_key(r))
                rows.append(r)
        if item.get("status") == "end":
            done.add(seq)
        if n % 100 == 0:
            print(f"  … {n}/{len(todo)}", file=sys.stderr)
            _save_state(done, seen)
        time.sleep(REQUEST_DELAY_SEC)
    path = write_csv(rows, RAW_DIR, day) if rows else None
    _save_state(done, seen)
    report = [f"목록 {len(items)}건 · 음악 공연 {len(music)}건 · 이번에 읽은 상세 {len(todo)}건 "
              f"(출연 팀 찾음 {named}건, 실패 {failed}건) · 새 행 {len(rows)}개"]
    return path, report


def main(argv):
    ap = argparse.ArgumentParser(description="KT&G 상상마당 공연 목록 수집 (지난 공연 포함)")
    ap.add_argument("--since", default="", help="이 날짜(YYYY-MM-DD) 이후 공연만")
    args = ap.parse_args(argv)
    if args.since and not re.match(r"^\d{4}-\d{2}-\d{2}$", args.since):
        ap.error("--since 는 YYYY-MM-DD 형식")
    path, report = collect(args.since)
    print("\n".join(report + ([f"  → {path}"] if path else [])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
