"""공연장 표기 묶기(venue_xref) — 같은 공연장의 여러 표기를 대표 이름 하나로.

    python3 scripts/venue_xref.py             # 공연 원본 → data/raw/state/venue_xref.json + venue_review.json
    python3 scripts/venue_xref.py --load-pg   # 위 + PostgreSQL ref.venue_xref (variant → venue)

왜: 'Club FF' / '클럽FF', '카페 언플러그드 홍대점' / '언플러그드 라운지' 처럼 같은 곳이 갈라지면
'같은 무대(같은 날·같은 공연장)' 점수, 선례, 공연장별 통계가 모두 흐려진다.

묶는 방법
1. 정규화 키(venue_key): 특수문자 풀기·대소문자·공백·기호 제거, 끝 괄호(영문 병기 등) 제거, '3F' → '3층',
   앞뒤 군더더기(KT&G·클럽/Club·카페/Cafe … / 라이브홀·홍대점·라이브하우스) 떼기. 떼면 빈 이름이 되는
   '라이브홀' 같은 이름은 지점을 알 수 없어(홍대·부산·춘천) 떼지 않고 검수 목록에 올린다.
2. 수동 확인 목록 config/venue_aliases.json: 규칙으로 못 잡는 확실한 쌍(한영 표기, 인스타 계정, 이름 변경)을
   이유와 함께 적는다. 키가 같은 묶음 전체가 대표 이름으로 간다.
3. 애매한 것(한 이름이 다른 이름을 포함하지만 키가 다름, 지점 없는 이름)은 묶지 않고 venue_review.json 으로.

PostgreSQL: ref.venue_xref(variant = 공연 원본의 공연장 칸 그대로, venue = 대표 이름).
sql/kr/00_core_views.sql 이 core.v_signal.venue 칸을 만든다 (표가 없으면 detail 그대로).
"""
from __future__ import annotations

import argparse
import csv
import glob
import html
import json
import os
import re
import subprocess
import tempfile
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
STATE_DIR = RAW_DIR / "state"
ALIASES_PATH = ROOT / "config" / "venue_aliases.json"
XREF_PATH = STATE_DIR / "venue_xref.json"
REVIEW_PATH = STATE_DIR / "venue_review.json"
PSQL = os.environ.get("PSQL", "/opt/homebrew/opt/postgresql@17/bin/psql")
DB = os.environ.get("PGDATABASE", "crate_digger")

NOT_WORD = re.compile(r"[^0-9a-z가-힣ㄱ-ㅎㅏ-ㅣ一-龥ぁ-んァ-ン]+")
TRAILING_PAREN = re.compile(r"\s*[\(\[][^\)\]]*[\)\]]\s*$")
FLOOR = re.compile(r"(\d+)\s*f\b")
PREFIXES = ("ktg", "liveclub", "라이브클럽", "club", "클럽", "cafe", "카페")      # 정규화(기호 제거) 뒤 모양
SUFFIXES = ("라이브홀", "livehall", "라이브하우스", "livehouse", "홍대점")
GENERIC = {"라이브홀", "사운드홀", "아트홀", "사운드홀로비", "야외공연장", "축제", "공식인스타그램live", "공식유튜브채널",
           "라이브스튜디오", "아트센터사운드홀"}
GENERIC_AFTER_STRIP = {"상상마당"}   # 지점 없이 체인 이름만 남는 경우 (홍대·부산·춘천 …)
FLOOR_ONLY = re.compile(r"^\d+층(?:라이브홀|루프탑)?$")
SKIP = {"", "공연장 미정"}
MIN_CONTAIN = 2
ROAD_NO = re.compile(r"([가-힣A-Za-z0-9]+(?:로|길))\s*(\d+(?:-\d+)?)")


def _unescape(text: str) -> str:
    prev, t = None, text or ""
    while t != prev:
        prev, t = t, html.unescape(t)
    return t


CHAIN_WORDS = re.compile(r"^\s*(?:KT\s*&\s*G\s*)?상상마당\s*")
BRANCH_PAREN = re.compile(r"^(?P<hall>.*?)\s*\((?P<building>\s*(?:KT\s*&\s*G\s*)?상상마당\s+(?P<branch>[^)]+?))\s*\)\s*$")


def canonical_venue_text(venue_text: str) -> str:
    """괄호에 지점·건물명이 있는 표기를 '건물 + 홀'로 ('라이브홀 (KT&G 상상마당 홍대)' → 'KT&G 상상마당 홍대 라이브홀').
    괄호 앞만 공연장으로 쓰는 규칙(SQL split_part) 때문에 지점이 사라져 서로 다른 건물의 '라이브홀'이 한 이름이 되던 문제를 막는다.
    주소 괄호('Club FF (서울 마포구 …)')나 이미 고친 표기는 그대로 둔다."""
    t = _unescape(venue_text or "")
    m = BRANCH_PAREN.match(t)
    if not m:
        return t
    hall = CHAIN_WORDS.sub("", m.group("hall")).strip()
    return " ".join(p for p in ("KT&G 상상마당", m.group("branch").strip(), hall) if p)


def gig_detail(venue_text: str) -> str:
    """공연 원본 venue_text → SQL 의 TRIM(split_part(venue_text, ' (', 1)) 과 같은 값.
    특수문자를 풀고 지점 괄호를 앞으로 옮긴 뒤(canonical_venue_text) 자른다 — PostgreSQL 쪽도 같은 표기를 보도록
    load_pg 가 적재할 때 같은 변환을 해야 한다(그 전까지 SQL 은 옛 표기 '라이브홀'을 봄)."""
    return canonical_venue_text(venue_text).split(" (")[0].strip()


def gig_address(venue_text: str) -> str:
    """공연 원본 venue_text 의 괄호 속 주소 ('Club FF (서울 마포구 …)' → '서울 마포구 …'). 없으면 ''."""
    t = _unescape(venue_text)
    return t.split(" (", 1)[1].rstrip(") ").strip() if " (" in t else ""


def address_key(address: str) -> str:
    """주소 → '도로명+건물번호' ('서울 마포구 와우산로29길 12 지하1층' → '와우산로29길12'). 층·괄호 차이는 무시."""
    found = ROAD_NO.findall(_unescape(address or ""))
    return "".join(found[-1]) if found else ""


def _squash(text: str) -> str:
    t = unicodedata.normalize("NFKC", _unescape(text)).lower().strip()
    t = TRAILING_PAREN.sub("", t) or t
    t = FLOOR.sub(r"\1층", t)
    return NOT_WORD.sub("", t)


def is_generic(name: str) -> bool:
    """지점을 알 수 없는 일반 이름 ('라이브홀', '3층 라이브홀', 'KT&G 상상마당 라이브홀' …)."""
    s = _squash(name)
    return s in GENERIC or bool(FLOOR_ONLY.match(s)) or _strip(s) in GENERIC_AFTER_STRIP


def venue_key(name: str) -> str:
    """같은 공연장인지 비교하는 키. 일반 이름은 군더더기를 떼지 않는다."""
    s = _squash(name)
    if not s or is_generic(name):
        return s
    return _strip(s)


def _strip(s: str) -> str:
    """앞뒤 군더더기(KT&G·클럽·카페 / 라이브홀·홍대점 …)를 뗀다. 다 떼면 빈 이름이 되는 경우는 남긴다."""
    changed = True
    while changed:
        changed = False
        for p in PREFIXES:
            if s.startswith(p) and len(s) > len(p):
                s, changed = s[len(p):], True
        for suf in SUFFIXES:
            if s.endswith(suf) and len(s) > len(suf):
                s, changed = s[: -len(suf)], True
    return s


class _Groups:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        self.parent[self.find(a)] = self.find(b)


def _apply_aliases(g: _Groups, keys: set[str], aliases: list[dict], review: list[dict],
                   addr_by_key: dict[str, set[str]]) -> dict[str, str]:
    """수동 목록으로 키 묶음을 합치고 {묶음 root: 대표 이름} 을 돌려준다. 주소가 서로 다르면 묶지 않는다."""
    chosen: dict[str, str] = {}
    for rule in aliases:
        hit = [k for k in (venue_key(n) for n in [rule["venue"], *rule.get("variants", [])]) if k in keys]
        if not hit:
            continue
        addrs = set().union(*(addr_by_key.get(k, set()) for k in hit))
        if len(addrs) > 1:
            review.append({"kind": "address_conflict", "names": [rule["venue"], *rule.get("variants", [])],
                           "addresses": sorted(addrs), "rows": 0,
                           "reason": "수동 목록 규칙인데 주소가 서로 다름 — 다른 공연장으로 보고 묶지 않음"})
            continue
        for k in hit[1:]:
            g.union(k, hit[0])
        root = g.find(hit[0])
        old = next((v for r, v in chosen.items() if g.find(r) == root), None)
        if old and old != rule["venue"]:
            review.append({"kind": "alias_conflict", "names": [old, rule["venue"]],
                           "reason": "수동 목록 두 규칙이 같은 공연장 묶음을 가리킴 — 앞 규칙을 씀"})
            continue
        chosen[root] = rule["venue"]
    return {g.find(r): v for r, v in chosen.items()}


def _contains_review(reps: dict[str, str], counts_by_root: Counter, g: _Groups, review: list[dict],
                     generic_keys: set[str]) -> None:
    """키가 다른데 한쪽이 다른 쪽을 포함 → 같은 곳일 수 있으니 사람이 확인 (일반 이름은 제외 — 어디에나 포함됨)."""
    roots = sorted(r for r in reps if r not in {g.find(k) for k in generic_keys})
    keys_of: dict[str, set[str]] = defaultdict(set)
    for k in g.parent:
        keys_of[g.find(k)].add(k)
    for i, a in enumerate(roots):
        for b in roots[i + 1:]:
            pair = [(ka, kb) for ka in keys_of[a] for kb in keys_of[b]
                    if min(len(ka), len(kb)) >= MIN_CONTAIN and (ka in kb or kb in ka)]
            if pair:
                review.append({"kind": "contains", "names": [reps[a], reps[b]], "keys": list(pair[0]),
                               "rows": counts_by_root[a] + counts_by_root[b],
                               "reason": "한 이름이 다른 이름을 포함 — 같은 공연장이면 config/venue_aliases.json 에 추가"})


def _address_review(names: list[str], key_of: dict, addr_of: dict, g: _Groups, reps: dict,
                    rows_by_root: Counter, review: list[dict]) -> None:
    """한 묶음에 주소가 여럿(주소 충돌) / 다른 묶음인데 주소가 같음(같은 주소) → 사람이 확인."""
    addrs_by_root: dict[str, set[str]] = defaultdict(set)
    roots_by_addr: dict[str, set[str]] = defaultdict(set)
    for n in names:
        a, root = addr_of.get(n, ""), g.find(key_of[n])
        if a:
            addrs_by_root[root].add(a)
            roots_by_addr[a].add(root)
    for root, addrs in addrs_by_root.items():
        if len(addrs) > 1:
            review.append({"kind": "address_conflict", "names": sorted({n for n in names if g.find(key_of[n]) == root}),
                           "addresses": sorted(addrs), "rows": rows_by_root[root],
                           "reason": "같은 묶음인데 주소가 여러 개 — 다른 공연장이 섞였거나 이전한 곳"})
    for a, roots in roots_by_addr.items():
        if len(roots) > 1:
            review.append({"kind": "same_address", "names": sorted(reps[r] for r in roots), "addresses": [a],
                           "rows": sum(rows_by_root[r] for r in roots),
                           "reason": "주소가 같은데 이름이 다름 — 같은 공연장이면 config/venue_aliases.json 에 추가"})


def build_venue_xref(counts: dict[str, int], aliases: list[dict],
                     addresses: dict[str, str] | None = None) -> tuple[dict[str, str], list[dict]]:
    """{공연장 표기: 건수} + 수동 목록 (+ {표기: 주소}) → ({표기: 대표 이름}, 검수 목록)."""
    review: list[dict] = []
    names = [n for n in counts if n.strip() and n.strip() not in SKIP]
    key_of = {n: venue_key(n) for n in names}
    keys = set(key_of.values())
    addr_of = {n: address_key(a) for n, a in (addresses or {}).items()}
    addr_by_key: dict[str, set[str]] = defaultdict(set)
    for n in names:
        if addr_of.get(n):
            addr_by_key[key_of[n]].add(addr_of[n])
    g = _Groups()
    for k in keys:
        g.find(k)
    alias_rep = _apply_aliases(g, keys, aliases, review, addr_by_key)
    by_root: dict[str, Counter] = defaultdict(Counter)
    for n in names:
        by_root[g.find(key_of[n])][n] += counts[n]
    reps = {root: alias_rep.get(root) or max(c, key=lambda s: (c[s], -len(s))) for root, c in by_root.items()}
    for n in sorted(names, key=lambda n: -counts[n]):
        if is_generic(n):
            review.append({"kind": "generic", "name": n, "rows": counts[n],
                           "reason": "지점 없는 일반 이름 — 어느 지점인지 몰라 묶지 않음"})
    rows_by_root = Counter({r: sum(c.values()) for r, c in by_root.items()})
    _contains_review(reps, rows_by_root, g, review, {key_of[n] for n in names if is_generic(n)})
    _address_review(names, key_of, addr_of, g, reps, rows_by_root, review)
    review.sort(key=lambda r: -r.get("rows", 0))
    return {n: reps[g.find(key_of[n])] for n in names}, review


# ---------- 읽기·쓰기 ----------

def load_aliases(path: Path = ALIASES_PATH) -> list[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("aliases", [])
    except (OSError, ValueError):
        return []


def collect_counts(raw_dir: Path = RAW_DIR) -> Counter:
    """공연 원본의 공연장 칸 + 공연장 인스타 라인업 공지(기사 표의 outlet) → {표기: 건수} (core.v_signal 의 detail 과 같은 값)."""
    counts: Counter = Counter()
    for path in sorted(glob.glob(str(raw_dir / "raw_kr_gig_*.csv"))):
        with open(path, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                counts[gig_detail(r.get("venue_text", ""))] += 1
    for path in sorted(glob.glob(str(raw_dir / "raw_press_*.csv"))):
        with open(path, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                if r.get("pick_label") == "venue_lineup":
                    counts[_unescape(r.get("outlet", "")).strip()] += 1
    return counts


def collect_addresses(raw_dir: Path = RAW_DIR) -> dict[str, str]:
    """{공연장 표기: 가장 많이 적힌 주소} (공연 원본 venue_text 의 괄호 속)."""
    seen: dict[str, Counter] = defaultdict(Counter)
    for path in sorted(glob.glob(str(raw_dir / "raw_kr_gig_*.csv"))):
        with open(path, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                addr = gig_address(r.get("venue_text", ""))
                if addr:
                    seen[gig_detail(r.get("venue_text", ""))][addr] += 1
    return {n: c.most_common(1)[0][0] for n, c in seen.items()}


def xref_rows(mapping: dict[str, str]) -> list[tuple[str, str]]:
    return sorted(mapping.items())


def pg_load_script(csv_path: str) -> str:
    """ref.venue_xref 를 비우고 다시 채우는 psql 스크립트 (한 트랜잭션, core 뷰가 참조하므로 DROP 안 함)."""
    return "\n".join([
        "BEGIN;",
        "CREATE SCHEMA IF NOT EXISTS ref;",
        "CREATE TABLE IF NOT EXISTS ref.venue_xref (variant text PRIMARY KEY, venue text NOT NULL);",
        "TRUNCATE ref.venue_xref;",
        f"\\copy ref.venue_xref FROM '{csv_path}' WITH (FORMAT csv)",
        "COMMIT;",
    ]) + "\n"


def load_pg(mapping: dict[str, str], psql_path: str = PSQL, db: str = DB) -> str:
    """ref.venue_xref 적재. psql·DB가 없으면 건너뛰고 메시지만. 넣은 뒤 00_core_views.sql 을 다시 실행해야 반영."""
    if not Path(psql_path).exists():
        return "PostgreSQL 적재 건너뜀: psql을 찾을 수 없음 (PSQL 환경변수로 위치 지정 가능)"
    rows = xref_rows(mapping)
    with tempfile.TemporaryDirectory() as d:
        csv_path, sql_path = Path(d) / "venue_xref.csv", Path(d) / "load.sql"
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerows(rows)
        sql_path.write_text(pg_load_script(str(csv_path)), encoding="utf-8")
        proc = subprocess.run([psql_path, "-v", "ON_ERROR_STOP=1", "-q", "-d", db, "-f", str(sql_path)],
                              capture_output=True, text=True)
    if proc.returncode != 0:
        return f"PostgreSQL 적재 건너뜀: {proc.stderr.strip()[:300]}"
    return f"PostgreSQL ref.venue_xref {len(rows):,}행 적재 (뷰 반영: psql -f sql/kr/00_core_views.sql)"


def main() -> None:
    ap = argparse.ArgumentParser(description="공연장 표기 묶기")
    ap.add_argument("--load-pg", action="store_true", help="PostgreSQL ref.venue_xref 로도 넣기")
    args = ap.parse_args()
    counts = collect_counts()
    mapping, review = build_venue_xref(counts, load_aliases(), collect_addresses())
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    XREF_PATH.write_text(json.dumps(mapping, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    REVIEW_PATH.write_text(json.dumps(review, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"공연장 표기 {len(mapping):,}개 → 대표 {len(set(mapping.values())):,}곳 · 검수 {len(review)}건 "
          f"→ {XREF_PATH.relative_to(ROOT)}, {REVIEW_PATH.relative_to(ROOT)}")
    if args.load_pg:
        print(load_pg(mapping))


if __name__ == "__main__":
    main()
