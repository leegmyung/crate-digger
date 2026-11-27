"""멜론 트랙제로(인디 큐레이션) 수집기 → data/raw/raw_press_<날짜>_trackzero.csv

    .venv/bin/python scripts/collect_trackzero.py          # 처음엔 과거 전부(2022-04~), 이후엔 새 글만

- 대상: 멜론 뮤직스토리 '#트랙제로' 태그 글 (m.live.melon.com/musicstory/listByTagSeq.htm?tagSeq=84958).
  2026-11 기준 글 262개 — 이달의 아티스트(2023-02~, 월 1팀), 추천 신곡(전문위원이 최근 3~4개월 발매곡을 고른
  플레이리스트, 월 1회), 기획 플레이리스트(주제별), 공연 안내(라이브클럽데이 등).
- robots.txt: m.live.melon.com 은 빈 파일(= 막지 않음, 2026-11-27 확인)이라 스크립트로 읽는다. www.melon.com 은 막혀 있어 쓰지 않는다.
  목록은 50개씩(sIdx=1, 51, 101 …), 글 상세는 detail.htm?mstorySeq=<번호>. 요청 사이 1초씩 쉰다(일시 차단 방지).
- 팀: 글의 '연관 아티스트'(멜론 아티스트 번호 포함) → 곡 목록의 '아티스트명' 순서. 이달의 아티스트 글은 제목의 팀만 쓴다
  (본문 연관 아티스트에는 함께 작업한 사람이 섞임). 공연 안내·공연 후기 글은 공연 홍보라 넣지 않는다.
- 형식: raw_press (source='trackzero', outlet='멜론 트랙제로', collector='script', pick_label=글 종류,
  is_pick=1: 이달의 아티스트·추천 신곡 / 0: 기획 플레이리스트).
- 멜론 아티스트 번호는 raw_press 에 칸이 없어 data/raw/state/trackzero_seen.json 의 melon_ids {이름: 번호}에 남긴다
  (연결표에서 멜론 번호로 쓰는 것은 제안 단계).
"""
from __future__ import annotations

import csv
import html
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_webzines as cw  # noqa: E402
from csv_schema import TABLES  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
STATE_PATH = RAW_DIR / "state" / "trackzero_seen.json"
KST = cw.KST
COLUMNS = [f.name for f in TABLES["raw_press"]["fields"]]
BASE = "https://m.live.melon.com/musicstory"
TAG_SEQ = "84958"                 # '#트랙제로'
PAGE_SIZE = 50
MAX_PAGES = 40                    # 2,000글 — 안전 상한
MIN_MELON_ID = 1_000              # 이보다 작은 번호는 실제 아티스트 번호가 아님 (collect_artists 와 같은 기준)
SOURCE, OUTLET = "trackzero", "멜론 트랙제로"
PICK_KINDS = {"이달의 아티스트", "추천 신곡"}
REQUEST_GAP_SEC = 1.0             # 요청 사이 1초 — robots 제한은 없지만 멜론 일시 차단을 피하려고 (코디네이터 결정)

ITEM_RE = re.compile(r"goMstoryDetail\('(\d+)'\);\">\s*<p class=\"title[^>]*>(.*?)</p>.*?"
                     r"class=\"date\">(\d{4})\.(\d{2})\.(\d{2})<", re.S)
ARTIST_LINK_RE = re.compile(r"goDetail\('artist',\s*'(\d+)'\).*?<span class=\"txt-title\">(.*?)</span>", re.S)
ARTIST_NAME_RE = re.compile(r"아티스트명 : </span>\s*<span class=\"txt-description[^\"]*\">(.*?)</span>", re.S)
MONTH_ARTIST_RE = re.compile(r"^(?:\d{1,2}월의|이달의)\s*아티스트\s*:?\s*(.+)$")
GIG_RE = re.compile(r"공연 후기|라이브클럽데이|Alive|공연 안내")


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", s or ""))).strip()


def parse_list(page_html: str) -> List[dict]:
    return [{"seq": m.group(1), "title": _clean(m.group(2)), "date": f"{m.group(3)}-{m.group(4)}-{m.group(5)}"}
            for m in ITEM_RE.finditer(page_html)]


def post_kind(title: str) -> str:
    if GIG_RE.search(title):
        return "공연"
    if MONTH_ARTIST_RE.match(title.strip()):
        return "이달의 아티스트"
    if "추천 신곡" in title or "추천신곡" in title:
        return "추천 신곡"
    return "기획"


def month_artist(title: str) -> str:
    m = MONTH_ARTIST_RE.match(title.strip())
    return m.group(1).strip() if m else ""


def _valid_id(mid: str) -> bool:
    return mid.isdigit() and int(mid) >= MIN_MELON_ID


def _is_name(n: str) -> bool:
    return bool(re.search(r"\w", n))


def parse_detail(page_html: str) -> List[Tuple[str, str]]:
    """글 상세 → [(팀 이름, 멜론 번호 또는 '')] 처음 나온 순서, 이름 중복 없이."""
    out: Dict[str, str] = {}
    for mid, name in ARTIST_LINK_RE.findall(page_html):
        n = _clean(name)
        if _is_name(n) and n not in out:
            out[n] = mid if _valid_id(mid) else ""
    linked = list(out)
    for name in ARTIST_NAME_RE.findall(page_html):
        n = _clean(name)
        if any(k in n for k in linked):   # 공동 작업 곡은 이름을 이어 붙여 적음 → 연관 아티스트로 이미 받은 이름이 들어 있으면 버림
            continue
        if _is_name(n) and n not in out:
            out[n] = ""
    return list(out.items())


def post_rows(post: dict, artists: Sequence[Tuple[str, str]], collected_at: str) -> List[dict]:
    kind = post_kind(post["title"])
    if kind == "공연":
        return []
    names = [month_artist(post["title"])] if kind == "이달의 아티스트" else [n for n, _ in artists]
    base = {"collected_at": collected_at, "source": SOURCE, "collector": "script", "outlet": OUTLET,
            "published_at": post["date"], "title": post["title"],
            "url": f"{BASE}/detail.htm?mstorySeq={post['seq']}", "release_title": "",
            "is_pick": "1" if kind in PICK_KINDS else "0", "pick_label": kind, "artist_handle": "", "is_sponsored": "0"}
    return [{**base, "artist_text": n} for n in dict.fromkeys(names) if n]


# ---------- 상태 ----------

def load_state(path: Path = STATE_PATH) -> dict:
    try:
        st = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        st = {}
    return {"seen": list(st.get("seen", [])), "melon_ids": dict(st.get("melon_ids", {})), "last_run": st.get("last_run", "")}


def new_posts(posts: Sequence[dict], state: dict) -> List[dict]:
    seen = set(state["seen"])
    return [p for p in posts if p["seq"] not in seen]


def mark_seen(state: dict, seqs: Sequence[str], melon_ids: Dict[str, str], today: str) -> dict:
    return {"seen": list(dict.fromkeys([*state["seen"], *seqs])),
            "melon_ids": {**state.get("melon_ids", {}), **melon_ids}, "last_run": today}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def write_rows(rows: List[dict], out_dir: Path, day: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"raw_press_{day}_trackzero.csv"
    if path.exists():   # 원본은 고치지 않는다 → 같은 날 다시 받으면 시각을 붙인 새 파일
        path = out_dir / f"raw_press_{day}_trackzero_{datetime.now(KST):%H%M%S%f}.csv"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


# ---------- 네트워크 ----------

def polite_get(url: str) -> str:
    time.sleep(REQUEST_GAP_SEC)
    return cw.http_get(url)


def fetch_list(state: dict) -> List[dict]:
    """목록을 50개씩 — 이미 본 글이 나오는 쪽까지만 (처음엔 끝까지)."""
    posts: List[dict] = []
    seen = set(state["seen"])
    for page in range(MAX_PAGES):
        url = f"{BASE}/listByTagSeq.htm?tagSeq={TAG_SEQ}" + (f"&sIdx={page * PAGE_SIZE + 1}" if page else "")
        got = parse_list(polite_get(url))
        posts += got
        if not got or any(p["seq"] in seen for p in got):
            break
    return list({p["seq"]: p for p in posts}.values())


def main() -> int:
    now = datetime.now(KST)
    today, at = now.date().isoformat(), now.replace(microsecond=0).isoformat()
    state = load_state()
    try:
        posts = new_posts(fetch_list(state), state)
    except (OSError, ValueError, RuntimeError) as e:
        print(f"⚠️ 트랙제로 목록 읽기 실패: {e}", file=sys.stderr)
        return 1
    rows: List[dict] = []
    done: List[str] = []
    ids: Dict[str, str] = {}
    for p in sorted(posts, key=lambda p: p["date"]):
        if post_kind(p["title"]) == "공연":
            done.append(p["seq"])
            continue
        try:
            artists = parse_detail(polite_get(f"{BASE}/detail.htm?mstorySeq={p['seq']}"))
        except (OSError, ValueError, RuntimeError) as e:
            print(f"⚠️ 글 {p['seq']} 읽기 실패 (다음에 다시): {e}", file=sys.stderr)
            continue
        rows += post_rows(p, artists, at)
        ids.update({n: mid for n, mid in artists if mid})
        done.append(p["seq"])
    path = write_rows(rows, RAW_DIR, today) if rows else None
    save_state(STATE_PATH, mark_seen(state, done, ids, today))
    kinds: Dict[str, int] = {}
    for r in rows:
        kinds[r["pick_label"]] = kinds.get(r["pick_label"], 0) + 1
    print(f"✅ 트랙제로 새 글 {len(done)}건 → {len(rows)}행 ({len({r['artist_text'] for r in rows})}팀, {kinds})"
          + (f" → {path.relative_to(ROOT)}" if path else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
