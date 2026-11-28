"""부산음악창작소 '공연지원' 게시판 → 공연 목록 (scripts/collect_regional_gigs.py 가 공연 원본 행으로 바꾼다).

출처: https://www.musiclabbusan.com/board/photo?page=1,2,… (robots.txt: /Administrator 만 금지)
- 카드 하나 = 공연 1건: 종류(쇼케이스·기획공연·브랜드공연·협력사업)·제목·날짜(여러 개 가능)·장소(쉼표로 여러 곳)·출연.
- 날짜 수 = 장소 수이면 순서대로 짝 (예: 2025-10-24 상상마당부산, 2025-11-01 롤링홀 홍대).
  장소가 1곳이면 모든 날짜가 그곳, 날짜가 1개인데 장소가 여러 곳(여러 공연장 축제)이면 첫 장소에 모두 넣는다.
  그 밖(날짜 2개·장소 5곳 등)은 어느 날 어디인지 몰라 건너뛴다.
- 장소 끝 괄호(부산)·(서울)은 주소 자리로 옮긴다('노드(부산)' → '노드 (부산)'). 마지막 장소에만 붙어 있으면
  앞 장소들에도 같은 괄호를 붙인다 ('바이닐언더그라운드, 오방가르드, 노드(부산)').
- 출연: 쉼표로 나누되 괄호 안 쉼표는 팀 구성원이라 나누지 않는다('해서웨이(강키위, 최세요)' → 해서웨이).
  (멘토)·(멘티)·(MC) 같은 괄호, '외 7명'·'등 총24팀' 꼬리, '대표 ○○' 같은 사람 소개는 뺀다.
  '제이통X로다운30' 협업은 팀마다 한 행.
- 카드에 상세 주소가 없어 gig_url 은 게시판 주소 + '#' + 제목·날짜로 만든 짧은 해시.
"""
from __future__ import annotations

import hashlib
import html
import re
from typing import Dict, List

LIST_URL = "https://www.musiclabbusan.com/board/photo?page={page}"
BOARD_URL = "https://www.musiclabbusan.com/board/photo"
SOURCE_PREFIX = "musiclabbusan"

CARD = re.compile(
    r'board-type"><span>(?P<kind>.*?)</span>.*?board-subject">(?P<title>.*?)</div>.*?'
    r'board-date">(?P<date>.*?)</div>.*?board-place">(?P<place>.*?)</div>.*?board-cast">(?P<cast>.*?)</div>', re.S)
DATE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")
TAIL_PAREN = re.compile(r"\s*\(([^()]*)\)\s*$")
DROP_TAIL = re.compile(r"\s*(?:외\s*\d+\s*명|등\s*(?:총\s*)?\d+\s*팀)\s*$")
STAFF = re.compile(r"대표|^MC\b|^DJ\s", re.I)
COLLAB = re.compile(r"(?<=[가-힣0-9])\s*[xX×]\s*(?=[가-힣])")


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment or ""))).strip()


def split_top(text: str, sep: str = ",") -> List[str]:
    """괄호 밖의 쉼표로만 나눈다."""
    out, depth, cur = [], 0, []
    for ch in text:
        depth += ch == "("
        depth -= ch == ")" and depth > 0
        if ch == sep and depth == 0:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur))
    return [p.strip() for p in out if p.strip()]


def parse_list(page: str) -> List[dict]:
    items = []
    for m in CARD.finditer(page or ""):
        dates = [f"{y}-{int(mo):02d}-{int(d):02d}" for y, mo, d in DATE.findall(m.group("date"))]
        items.append({"kind": _text(m.group("kind")), "title": _text(m.group("title")), "dates": dates,
                      "places": split_top(_text(m.group("place"))), "cast": _text(m.group("cast"))})
    return items


def split_cast(text: str) -> List[str]:
    names: List[str] = []
    for part in split_top(text):
        part = DROP_TAIL.sub("", TAIL_PAREN.sub("", part)).strip()
        if not part or STAFF.search(part):
            continue
        names.extend(p.strip() for p in COLLAB.split(part) if p.strip())
    return names


# 같은 이름의 다른 도시 공연장과 헷갈리는 표기 → 마스터 이름 ((이름, 괄호 속 힌트) → 이름)
PLACE_FIX = {("인터플레이", "금정구"): "인터플레이 부산"}


def _place_texts(places: List[str]) -> List[str]:
    hints = [TAIL_PAREN.search(p) for p in places]
    shared = hints[-1].group(1) if hints and hints[-1] and not any(hints[:-1]) else ""
    out = []
    for p, h in zip(places, hints):
        name = TAIL_PAREN.sub("", p).strip()
        hint = h.group(1).strip() if h else shared
        name = PLACE_FIX.get((name, hint), name)
        out.append(f"{name} ({hint})" if hint else name)
    return out


def _pairs(dates: List[str], places: List[str]) -> List[tuple]:
    if not dates or not places:
        return []
    if len(dates) == len(places):
        return list(zip(dates, places))
    if len(places) == 1 or len(dates) == 1:
        return [(d, places[0]) for d in dates]
    return []


def _key(item: dict) -> str:
    raw = f"{item['title']}|{','.join(item['dates'])}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]


def gigs_from_items(items: List[dict]) -> List[Dict[str, str]]:
    """카드 → [{day, title, venue_text, artist, url, source_id, lineup_order, lineup_size}]."""
    gigs = []
    for it in items:
        names = split_cast(it["cast"])
        pairs = _pairs(it["dates"], _place_texts(it["places"]))
        if not names or not pairs:
            continue
        key = _key(it)
        for day, venue in pairs:
            for name in names:
                gigs.append({"day": day, "title": it["title"], "venue_text": venue, "artist": name,
                             "url": f"{BOARD_URL}#{key}-{day}", "source_id": f"{SOURCE_PREFIX}:{key}",
                             "lineup_order": "", "lineup_size": str(len(names))})
    return gigs
