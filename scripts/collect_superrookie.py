"""슈퍼루키챌린지(힙합·R&B 신인 서바이벌, 2013~) 참가자 수집기 → data/raw/raw_kr_selection_<날짜>_superrookie.csv

    .venv/bin/python scripts/collect_superrookie.py          # 처음엔 과거 전부, 이후엔 새 글만

- 시즌 15~17(2025~)과 보컬 시즌: 루트노트 한국 블로그·RADAR의 워드프레스 공개 API (robots.txt 없음 = 막지 않음, 2026-11-27 확인).
  글 본문에서 참가자 이름을 뽑는다 — 트랙 크레딧 '(feat. A, B)', '라인업 공개' 아래 'A @계정' 줄, 'TOP4·위너 발표' 아래
  'A (@계정)' 줄, 문장형 목록('features 6 artists — A, B, and C —', '“곡”에는 A, B — 10명', 'singers share the track: A and B').
- 시즌 14(2024): 포크라노스 앨범 페이지 크레딧 '(feat. …)' (워드프레스 공개 API, robots.txt 허용).
- 시즌 1~13(2013~2019)은 웹에 참가자 명단이 남아 있지 않아 받지 않는다 (docs/research_2026-11-27_hiphop_rnb_sources.md 4절).
- 단계: 사이퍼·라인업 = lineup(라운드 무대 진출, 2), TOP4·위너 = selected(3), 시즌 최종 우승 = final(4). 날짜는 글 게시일.
- 형식: raw_kr_selection (program='superrookie', source='routenote'|'poclanos', round='S15 R1'·'Vocal S1 R2').
- 이어받기: data/raw/state/superrookie_seen.json (본 글 주소). 스페셜 게스트·사회자·'Sounds Like' 비교 대상은 넣지 않는다.
"""
from __future__ import annotations

import csv
import html
import json
import re
import sys
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_webzines as cw  # noqa: E402
from csv_schema import TABLES  # noqa: E402
from normalize import artist_key  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
STATE_PATH = RAW_DIR / "state" / "superrookie_seen.json"
KST = cw.KST
COLUMNS = [f.name for f in TABLES["raw_kr_selection"]["fields"]]
PROGRAM = "superrookie"
ROUTENOTE_SITES = ("https://routenote.com/kr/blog", "https://routenote.com/radar")
ROUTENOTE_QUERIES = ("슈퍼루키", "Super Rookie", "슈루챌", "슈퍼 루키")
POCLANOS = "https://poclanos.com"
WP_FIELDS = "id,date,link,title,content"
MARK = re.compile(r"super\s*rookie|슈퍼\s*루키|슈루챌", re.I)
MAX_NAME_LEN = 40

ROUND_RE = re.compile(r"(?:Season|시즌)\s*(\d+)[^\d]{0,40}?(?:Round|라운드)\s*(\d+)", re.I | re.S)
VOCAL_RE = re.compile(r"Round\s*(\d+)\s+of\s+[^.]*?(first|\d+)(?:st|nd|rd|th)?\s+Vocal\s+Season|"
                      r"Vocal\s+Season\s*(\d+)\s*Round\s*(\d+)", re.I)
SELECTED_TITLE = re.compile(r"TOP\s*\d|위너|우승자|winner", re.I)
FINAL_TITLE = re.compile(r"최종\s*우승|챔피언|champion", re.I)
HANDLE_HEADER = re.compile(r"라인업\s*공개|Line-?up\s*:|위너\s*발표|TOP\s*\d", re.I)
HANDLE_LINE = re.compile(r"^(?P<name>[^@():✅]+?(?:\([^@)]*\))?)\s*(?:\(?@[\w.]+\)?\s*)+$")
SENTENCE_LISTS = (
    re.compile(r"(?:brings together|features|featuring)\s+\d+\s+(?:MCs|artists|rappers|singers|vocalists)\s*[—–-]\s*(.+?)\s*[—–]"),
    re.compile(r"(?:singers|rappers|MCs|artists|vocalists)\s+(?:share the track|take a part each)\s*:\s*(.+?)\.(?:\s|$)"),
    re.compile(r"에는\s+(.+?)\s*[—–-]\s*\d+\s*명"),
)


# ---------- 변환 ----------

def _text(post: dict, key: str) -> str:
    return html.unescape((post.get(key) or {}).get("rendered", ""))


def _lines(content_html: str) -> List[str]:
    text = html.unescape(re.sub(r"<[^>]+>", "\n", content_html or ""))
    return [re.sub(r"\s+", " ", ln).strip() for ln in text.split("\n") if ln.strip()]


def parse_round(text: str) -> Optional[str]:
    m = VOCAL_RE.search(text or "")
    if m:
        if m.group(1):
            season = "1" if m.group(2).lower() == "first" else m.group(2)
            return f"Vocal S{season} R{m.group(1)}"
        return f"Vocal S{m.group(3)} R{m.group(4)}"
    m = ROUND_RE.search(text or "")
    return f"S{m.group(1)} R{m.group(2)}" if m else None


def split_names(text: str) -> List[str]:
    out = []
    for piece in cw.split_outside_parens(text, ","):
        for name in re.split(r"\s+and\s+", re.sub(r"^and\s+", "", piece.strip())):
            name = re.sub(r"\s*@[\w.]+", "", name).strip(" .")
            if name and len(name) <= MAX_NAME_LEN:
                out.append(name)
    return out


def feat_lists(text: str) -> List[str]:
    """'(feat. A, B(별칭), C)' 안의 이름들. 괄호가 겹쳐도 짝을 맞춰 읽는다."""
    out = []
    for m in re.finditer(r"\(\s*feat\.?\s*", text, re.I):
        depth, i = 1, m.end()
        while i < len(text) and depth:
            depth += {"(": 1, ")": -1}.get(text[i], 0)
            i += 1
        out += split_names(text[m.end():i - 1])
    return out


def handle_block(lines: Sequence[str]) -> List[str]:
    """'라인업 공개'·'위너 발표' 줄 다음에 이어지는 'A @계정' / 'A (@계정)' 줄들. 첫 이름 전 2줄까지는 건너뜀."""
    for i, ln in enumerate(lines):
        if not HANDLE_HEADER.search(ln):
            continue
        names, skipped = [], 0
        for nxt in lines[i + 1:]:
            m = HANDLE_LINE.match(nxt)
            if m:
                names.append(m.group("name").strip())
            elif names or skipped >= 2:
                break
            else:
                skipped += 1
        if names:
            return names
    return []


def extract_names(content_html: str) -> List[str]:
    lines = _lines(content_html)
    joined = " ".join(lines)
    names = feat_lists(joined) or handle_block(lines)
    if not names:
        for rx in SENTENCE_LISTS:
            for m in rx.finditer(joined):
                names += split_names(m.group(1))
    return list(dict.fromkeys(names))


def stage_for(title: str) -> str:
    if FINAL_TITLE.search(title):
        return "final"
    return "selected" if SELECTED_TITLE.search(title) else "lineup"


def post_rows(post: dict, source: str, collected_at: str) -> List[dict]:
    title = re.sub(r"\s+", " ", _text(post, "title")).strip()
    content = (post.get("content") or {}).get("rendered", "")
    rnd = parse_round(title) or parse_round(" ".join(_lines(content)))
    if not rnd:
        return []
    names = extract_names(content)
    base = {"collected_at": collected_at, "source": source, "collector": "script", "program": PROGRAM,
            "round": rnd, "stage": stage_for(title), "announced_at": str(post.get("date", ""))[:10],
            "url": post.get("link", ""), "note": title[:80]}
    return [dict(base, artist_text=n) for n in names]


def dedupe(rows: Sequence[dict]) -> List[dict]:
    """같은 라운드·단계에서 같은 사람(이름 키가 같음, 'X33D'와 'X33D(씨드)'도 같게)은 한 번만."""
    seen, out = set(), []
    for r in rows:
        key = (r["program"], r["round"], r["stage"], artist_key(r["artist_text"]))
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def rows_from_posts(posts: Sequence[dict], source: str, collected_at: str) -> List[dict]:
    """글마다 행을 만들되, 같은 라운드·단계를 한국어 블로그 글이 이미 다뤘으면 영어 글(RADAR)은 건너뛴다."""
    ordered = sorted(posts, key=lambda p: (0 if "/kr/" in p.get("link", "") else 1, str(p.get("date", ""))))
    done, out = set(), []
    for p in ordered:
        rows = post_rows(p, source, collected_at)
        keys = {(r["round"], r["stage"]) for r in rows}
        if not rows or ("/kr/" not in p.get("link", "") and keys & done):
            continue
        done |= keys
        out += rows
    return out


# ---------- 상태 ----------

def load_state(path: Path = STATE_PATH) -> dict:
    try:
        st = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        st = {}
    return {"seen": {"routenote": [], "poclanos": [], **st.get("seen", {})}, "last_run": st.get("last_run", "")}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def new_posts(posts: Sequence[dict], state: dict, source: str) -> List[dict]:
    seen = set(state["seen"].get(source, []))
    return [p for p in posts if p.get("link") not in seen]


def mark_seen(state: dict, source: str, links: Sequence[str], today: str) -> dict:
    seen = {**state["seen"], source: list(dict.fromkeys([*state["seen"].get(source, []), *links]))}
    return {"seen": seen, "last_run": today}


# ---------- 네트워크 ----------

def _get_json(url: str):
    return json.loads(cw.http_get(url))


def fetch_routenote() -> List[dict]:
    posts: Dict[str, dict] = {}
    for site in ROUTENOTE_SITES:
        for q in ROUTENOTE_QUERIES:
            url = f"{site}/wp-json/wp/v2/posts?search={urllib.parse.quote(q)}&per_page=100&_fields={WP_FIELDS}"
            for p in _get_json(url):
                if MARK.search(_text(p, "title")) or MARK.search(_text(p, "content")):
                    posts.setdefault(p["link"], p)
    return sorted(posts.values(), key=lambda p: p["date"])


def fetch_poclanos() -> List[dict]:
    hits = _get_json(f"{POCLANOS}/wp-json/wp/v2/search?search={urllib.parse.quote('Super Rookie Challenge')}&per_page=50")
    out = []
    for h in hits:
        if h.get("subtype") != "download":
            continue
        out.append(_get_json(f"{POCLANOS}/wp-json/wp/v2/download/{h['id']}?_fields={WP_FIELDS}"))
    return sorted(out, key=lambda p: p["date"])


def write_rows(rows: List[dict], out_dir: Path, day: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"raw_kr_selection_{day}_superrookie.csv"
    if path.exists():   # 원본은 고치지 않는다 → 같은 날 다시 받으면 시각을 붙인 새 파일
        path = out_dir / f"raw_kr_selection_{day}_superrookie_{datetime.now(KST):%H%M%S}.csv"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def main() -> int:
    now = datetime.now(KST)
    today, at = now.date().isoformat(), now.replace(microsecond=0).isoformat()
    state = load_state()
    rows: List[dict] = []
    for source, fetch in (("routenote", fetch_routenote), ("poclanos", fetch_poclanos)):
        try:
            posts = new_posts(fetch(), state, source)
        except (OSError, ValueError, RuntimeError) as e:
            print(f"⚠️ {source} 읽기 실패: {e}", file=sys.stderr)
            continue
        got = rows_from_posts(posts, source, at)
        print(f"  {source}: 새 글 {len(posts)}건 → {len(got)}행", file=sys.stderr)
        rows += got
        state = mark_seen(state, source, [p["link"] for p in posts], today)
    rows = dedupe(rows)
    path = write_rows(rows, RAW_DIR, today) if rows else None
    save_state(STATE_PATH, state)
    rounds = sorted({r["round"] for r in rows})
    print(f"✅ 슈퍼루키챌린지 {len(rows)}행 ({len({r['artist_text'] for r in rows})}명, 라운드 {', '.join(rounds) or '없음'})"
          + (f" → {path.relative_to(ROOT)}" if path else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
