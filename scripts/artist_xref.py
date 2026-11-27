"""아티스트 연결표(artist_xref) — 같은 팀의 여러 표기·플랫폼 번호·인스타 계정을 대표 이름 하나로 묶는다.

    python3 scripts/artist_xref.py             # data/raw 원본 → data/raw/state/artist_xref.json + docs/artist_xref.md
    python3 scripts/artist_xref.py --load-pg   # 위 + PostgreSQL ref.artist_xref 표로 넣기 (DB 없으면 건너뜀)

하는 일 (2단계 '아티스트 매칭·메타데이터 검수'). 문제 찾기는 검증 SQL(c02·c06·c08)이, 고친 표 만들기는 이 스크립트가 한다.
1. 선정 명단 칸 나누기 (split_cell): "박수정, 김민지" → 두 사람. '&'·영문 쉼표처럼 팀 이름 안에도
   나오는 기호는 나누지 않고 '애매함'으로 남겨 사람이 본다.
2. 같은 팀 다른 표기 묶기 (parse_name + 묶음): "피치 트럭 하이재커스(Peach Truck Hijackers)" 처럼 한 칸에
   한글·영문이 같이 적힌 것을 근거로 'Peach Truck Hijackers' 표기도 같은 팀으로 잇는다.
   같은 영문 별칭이 서로 다른 팀 둘 이상에 붙으면(동명 위험) 잇지 않고 검수 목록에 올린다.
3. 인스타 계정 → 팀: 프로필 표시 이름(ig_artist_links.json·instagram 프로필 CSV), 매거진 캡션에서
   '@계정' 바로 앞에 적힌 이름, 공연 라인업에 계정명이 그대로 적힌 경우를 근거로 잇고 확신도를 붙인다.
   - high: 다른 소스(공연·선정·발매 등)의 팀 이름과 맞고, 계정명도 그 이름과 닮았거나 근거가 2가지 이상
   - mid : 다른 소스의 팀 이름과 맞음 (근거 1가지)
   - low : 인스타에만 있는 이름 (다른 소스에서 아직 못 찾음)

다른 스크립트에서 쓰기 (score.py · build_dashboard_data.py):
    from artist_xref import canonical_key, load_xref
    index = load_xref()                              # 파일이 없어도 예외 없이 빈 색인
    canonical_key("Peach Truck Hijackers", index)    # → "피치트럭하이재커스"
    canonical_key("다브다 (Dabda)")                   # 색인 없이도 normalize.artist_key 와 같은 키
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
from datetime import datetime
from pathlib import Path

from normalize import _squash, artist_key

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
STATE_DIR = RAW_DIR / "state"
DEFAULT_XREF = STATE_DIR / "artist_xref.json"
REVIEW_PATH = STATE_DIR / "artist_xref_review.json"
SUMMARY_MD = ROOT / "docs" / "artist_xref.md"
MANUAL_ALIASES = ROOT / "config" / "artist_aliases.json"   # 사람이 확인한 별칭 (대표 이름 ↔ 별칭, 이유·근거·확인 날짜)
PSQL = os.environ.get("PSQL", "/opt/homebrew/opt/postgresql@17/bin/psql")
DB = os.environ.get("PGDATABASE", "crate_digger")

HANGUL = re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣ]")
LATIN = re.compile(r"[A-Za-z]")
KANA_KANJI = re.compile(r"[ぁ-んァ-ン一-龥]")
TRAILING_PAREN = re.compile(r"^(.*?)\s*[\(\[（【]([^\(\)\[\]（）【】]*)[\)\]）】]\s*$")
MEMBER_LIST = re.compile(r"^([^\(（]+?)\s*[\(（]([^\)）]*[,·、][^\)）]*)[\)）]\s*$")
OTHERS = re.compile(r"^(.+?)\s*외\s*\d+\s*(?:명|인|팀)$")
COLLAB_SEP = re.compile(r"\s+[xX×]\s+")
SLASH_SEP = re.compile(r"\s*/\s*")
JOINER = re.compile(r"&|\+|\band\b|w/", re.I)
FEAT_WORD = re.compile(r"^\s*(?:feat|ft|with)\b", re.I)
HANDLE_NOISE = {"official", "offcial", "band", "music", "the", "kr", "seoul", "korea", "musician", "artist", "sound"}
NAME_MAX_LEN = 40
MIN_HANDLE_CORE = 3
MIN_LATIN_ALIAS = 2
NOT_A_HANDLE = re.compile(r"\.(?:com|net|co|kr|org)$|@", re.I)   # 이메일 주소 조각 등
CONF_RANK = {"high": 3, "mid": 2, "low": 1}
SIGNAL_TABLES = {"gig", "selection", "release", "press"}

TABLE_OF = {
    "raw_kr_release": "release", "raw_kr_gig": "gig", "raw_kr_selection": "selection",
    "raw_press": "press", "raw_outcome": "outcome", "raw_artist_profile": "profile",
}


# ---------- 이름 다듬기 ----------

def clean(text: str) -> str:
    """HTML 특수문자 풀기(&amp;amp; 처럼 두 번 감싼 것까지), 전각 → 반각, 공백 정리."""
    prev, t = None, text or ""
    while t != prev:
        prev, t = t, html.unescape(t)
    t = unicodedata.normalize("NFKC", t)
    return re.sub(r"[ \t]+", " ", t).strip()


def script_of(text: str) -> str:
    """'hangul' | 'latin' | 'cjk' | 'mixed' | '' (글자 없음)."""
    kinds = {k for k, rx in (("hangul", HANGUL), ("latin", LATIN), ("cjk", KANA_KANJI)) if rx.search(text or "")}
    if not kinds:
        return ""
    return kinds.pop() if len(kinds) == 1 else "mixed"


def _is_alias_pair(main: str, alias: str) -> bool:
    """괄호·슬래시 속 말이 '다른 문자로 쓴 같은 이름'으로 볼 만한지."""
    if not main or not alias or FEAT_WORD.match(alias):
        return False
    a, b = script_of(main), script_of(alias)
    if not a or not b or "mixed" in (a, b) or a == b:
        return False
    latin = main if a == "latin" else alias if b == "latin" else ""
    return not latin or len(_squash(latin)) >= MIN_LATIN_ALIAS  # 'G(라이엇키즈)' 같은 멤버 표기는 제외


def parse_name(text: str) -> tuple[str, list[str]]:
    """(대표 표기, [다른 문자 별칭]). 같은 문자끼리의 괄호(소속·설명)나 숫자 괄호는 별칭으로 보지 않는다."""
    t = clean(text)
    parts = [p for p in SLASH_SEP.split(t) if p] if "/" in t else []
    if len(parts) == 2 and _is_alias_pair(parts[0], parts[1]):
        return parts[0], [parts[1]]
    m = TRAILING_PAREN.match(t)
    if m and m.group(1).strip():
        main, inner = m.group(1).strip(), m.group(2).strip()
        if not re.search(r"[,·、]", inner) and _is_alias_pair(main, inner):
            return main, [inner]
    return t, []


def name_key(text: str) -> str:
    """색인 없이 만드는 이름 키 (normalize.artist_key 규칙 + 특수문자 풀기·한영 슬래시 병기)."""
    return artist_key(parse_name(text)[0])


def canonical_key(name: str, index: dict | None = None) -> str:
    """팀 대표 키. index(load_xref 결과)를 주면 다른 표기도 대표 키로 바꿔 준다. 예외를 내지 않는다."""
    key = name_key(name)
    by_key = (index or {}).get("by_key") or {}
    if not by_key:
        return key
    if key in by_key:
        return by_key[key]
    for alias in parse_name(name)[1]:
        hit = by_key.get(_squash(alias))
        if hit:
            return hit
    return key


# ---------- 1. 한 칸에 여러 팀 나누기 ----------

def _split_outside_parens(text: str, sep: re.Pattern) -> list[str]:
    """괄호 밖에 있는 구분자로만 나눈다."""
    parts, buf, depth = [], [], 0
    for ch in text:
        depth += ch in "([（【"
        depth -= ch in ")]）】"
        if depth == 0 and sep.fullmatch(ch):
            parts.append("".join(buf))
            buf = []
            continue
        buf.append(ch)
    parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip()]


def _result(parts: list[str], status: str, reason: str = "", related: list[str] | None = None) -> dict:
    return {"parts": parts, "status": status, "reason": reason, "related": related or []}


def split_cell(text: str) -> dict:
    """선정 명단 한 칸 → {parts, status, reason, related}.

    status: single(한 팀) / split(나눔) / bilingual(한영 병기, 한 팀) / partial('외 N명', 앞 이름만) /
            team_with_members(팀(멤버…), 팀만 남김) / ambiguous(팀 이름일 수도 있어 그대로 둠) / empty
    """
    t = clean(text)
    if not t:
        return _result([], "empty")
    m = OTHERS.match(t)
    if m:
        return _result([m.group(1).strip()], "partial", "'외 N명' — 나머지 이름은 원문에 없음")
    m = MEMBER_LIST.match(t)
    if m:
        related = [p.strip() for p in re.split(r"[,·、]", m.group(2)) if p.strip()]
        return _result([m.group(1).strip()], "team_with_members", "괄호 속은 멤버·소속으로 보고 팀만 남김", related)
    if "/" in t and parse_name(t)[1]:
        return _result([t], "bilingual", "한글/영문 병기")
    for sep, label in ((re.compile(r"[,;\n]"), "쉼표"), (None, "x 협업"), (re.compile("/"), "슬래시")):
        parts = COLLAB_SEP.split(t) if sep is None else _split_outside_parens(t, sep)
        if len(parts) < 2:
            continue
        if all(HANGUL.search(p) for p in parts):
            return _result(parts, "split", f"{label}로 나눔")
        return _result([t], "ambiguous", f"{label}가 있지만 영문 팀 이름일 수 있어 그대로 둠")
    if JOINER.search(t):
        return _result([t], "ambiguous", "'&'·'+'·'and'는 팀 이름 안에도 나와 그대로 둠")
    return _result([t], "single")


# ---------- 3. 인스타 계정 ----------

def _token_kind(tok: str) -> str | None:
    if HANGUL.search(tok):
        return "hangul"
    if LATIN.search(tok):
        return "latin"
    if KANA_KANJI.search(tok):
        return "cjk"
    return None


def split_script_blocks(display: str) -> list[str]:
    """인스타 표시 이름을 문자 종류별 덩어리로. 'Confined White 컨파인드 화이트' → ['Confined White', '컨파인드 화이트']."""
    t = clean(display)
    bracketed = re.findall(r"[\[\(（【]([^\]\)）】]*)[\]\)）】]", t)
    outer = re.sub(r"[\[\(（【][^\]\)）】]*[\]\)）】]", " ", t)
    blocks: list[str] = []
    for seg in [*re.split(r"\s*[|/·•]\s*", outer), *bracketed]:
        groups: list[list[str]] = []
        last = None
        for tok in seg.split():
            kind = _token_kind(tok)
            if kind is None:  # 숫자만 있는 조각은 앞 덩어리에 붙이고, 이모지 등은 버림
                if groups and re.search(r"\w", tok):
                    groups[-1].append(tok)
                continue
            if kind != last:
                groups.append([])
            groups[-1].append(tok)
            last = kind
        blocks += [" ".join(g) for g in groups]
    return [b for b in blocks if _squash(b)]


def handle_core(handle: str) -> str:
    """계정명에서 official·band 같은 군더더기를 뺀 핵심. 'adoyband' → 'adoy'."""
    h = (handle or "").lstrip("@").lower()
    core = "".join(tok for tok in re.split(r"[._]+", h) if tok and tok not in HANDLE_NOISE)
    for noise in ("official", "band", "music"):
        if core.endswith(noise) and len(core) - len(noise) >= MIN_HANDLE_CORE:
            core = core[: -len(noise)]
    for noise in ("the", "band"):
        if core.startswith(noise) and len(core) - len(noise) >= MIN_HANDLE_CORE:
            core = core[len(noise):]
    return core if len(core) >= MIN_HANDLE_CORE else _squash(h)


def caption_name_for_handle(caption: str, handle: str, single_tag: bool = False) -> str:
    """캡션에서 그 계정을 가리키는 이름. '@계정' 바로 앞 이름, 또는 (태그가 하나뿐일 때) '이름 - 곡' 형식."""
    cap = clean(caption)
    idx = cap.lower().find("@" + handle.lower())
    if idx > 0:
        before = cap[:idx].rstrip(" .,")
        seg = re.split(r"[*\n|•\]】:]|\.\s", before)[-1].strip(" .,-")
        if seg and len(seg) <= NAME_MAX_LEN:
            return seg
        m = re.search(r"([^\s,(]+(?:\s[^\s,(]+){0,2}\s*\([^)]*\))$", before)
        if m:
            return m.group(1).strip()
    if single_tag:
        m = re.match(r"^\s*(?:\[[^\]]*\]\s*)?([^\n\-–—]{1,%d}?)\s+[-–—]\s+" % NAME_MAX_LEN, cap)
        if m:
            return m.group(1).strip()
    return ""


# ---------- 2. 묶기 (union-find) ----------

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


def _expand_names(names: list[dict], review: list[dict]) -> list[dict]:
    """선정 표는 칸을 나누고, 나머지 표는 그대로 → [{table, text, count}]."""
    out = []
    for row in names:
        text, table, count = row["name"], row["table"], int(row.get("count", 1))
        if table != "selection":
            out.append({"table": table, "text": text, "count": count})
            continue
        res = split_cell(text)
        if res["status"] in ("ambiguous", "partial", "team_with_members"):
            review.append({"kind": "cell_split", "detail": f"{clean(text)} → {' + '.join(res['parts'])}",
                           "reason": res["reason"], "weight": count})
        out += [{"table": table, "text": p, "count": count} for p in res["parts"]]
    return out


def _alias_edges(occurrences: list[dict]) -> list[tuple[str, str, str, str]]:
    """한 칸 안 한영 병기 → (대표 키, 별칭 키, 확신도, 근거)."""
    edges = []
    for occ in occurrences:
        main, aliases = parse_name(occ["text"])
        mk = artist_key(main)
        if not mk:
            continue
        legacy = artist_key(clean(occ["text"]))
        if legacy and legacy != mk:  # load_pg 의 예전 키('디아틱theatic')도 같은 팀으로
            edges.append((mk, legacy, "high", clean(occ["text"])))
        for a in aliases:
            ak = _squash(a)
            if ak and ak != mk:
                edges.append((mk, ak, occ.get("conf", "high"), clean(occ["text"])))
    return edges


AUTO_KINDS = {"alias_auto"}   # 확인 목록에 기록만 하고 사람 확인 건수에서는 빼는 종류
MIN_CONTAINED_KEY = 2   # 이보다 짧은 이름은 '품는다'고 보지 않음 (한 글자 이름이 아무 데나 들어가는 것 방지)


def _contained_owner(mains: set[str]) -> str | None:
    """충돌한 대표 키들 중 하나가 나머지 모두에 그대로 들어 있으면 그 키 ('해서웨이' ⊂ '보수동쿨러해서웨이').
    긴 쪽은 합동 표기('보수동쿨러 해서웨이 (hathaw9y)', '윤석철 세진(Sejin)')라서 별칭은 짧은 쪽(실제 팀)의 것."""
    short = min(mains, key=len)
    if len(short) < MIN_CONTAINED_KEY:
        return None
    return short if all(short in m for m in mains if m != short) else None


def _drop_conflicts(edges: list[tuple], review: list[dict]) -> list[tuple]:
    """같은 별칭 키를 서로 다른 대표 키 둘 이상이 가지면(동명 위험) 그 연결은 버린다.
    단 한 대표 키가 나머지를 그대로 품는 경우(합동 표기)는 별칭을 품긴 쪽(짧은 쪽)에만 남긴다."""
    claimed: dict[str, set[str]] = defaultdict(set)
    for mk, ak, *_ in edges:
        claimed[ak].add(mk)
    owner = {ak: _contained_owner(mains) for ak, mains in claimed.items() if len(mains) > 1}
    bad = {ak for ak, o in owner.items() if o is None}
    for ak in sorted(set(owner) - bad):
        others = ", ".join(sorted(claimed[ak] - {owner[ak]}))
        review.append({"kind": "alias_auto", "detail": f"{ak} → {owner[ak]} (뺌: {others})",
                       "reason": "자동 해결 — 긴 이름이 짧은 이름을 품음(합동 표기), 별칭은 짧은 쪽", "weight": 0})
    for ak in sorted(bad):
        review.append({"kind": "alias_conflict", "detail": f"{ak} ← {', '.join(sorted(claimed[ak]))}",
                       "reason": "같은 별칭이 여러 팀에 붙음 (동명 팀일 수 있음)", "weight": len(claimed[ak]),
                       "keys": sorted(claimed[ak])})
    return [e for e in edges if e[1] not in bad and (e[1] not in owner or e[0] == owner[e[1]])]


def _ig_candidates(ig_profiles: list[dict], ig_posts: list[dict]) -> dict[str, list[dict]]:
    """계정 → [{text, evidence, kind}] (프로필 이름 덩어리 + 캡션 이름)."""
    cands: dict[str, list[dict]] = defaultdict(list)
    ig_profiles = [p for p in ig_profiles if not NOT_A_HANDLE.search(p["handle"].lstrip("@"))]
    ig_posts = [p for p in ig_posts if not NOT_A_HANDLE.search(p["handle"].lstrip("@"))]
    for p in ig_profiles:
        h = p["handle"].lstrip("@").lower()
        for block in split_script_blocks(p.get("name", "")):
            cands[h].append({"text": block, "kind": "profile",
                             "evidence": f"인스타 프로필 이름 '{clean(p.get('name', ''))}' ({p.get('source', '')})"})
    for post in ig_posts:
        h = post["handle"].lstrip("@").lower()
        name = caption_name_for_handle(post.get("caption", ""), h, post.get("single_tag", False))
        if name:
            cands[h].append({"text": name, "kind": "caption",
                             "evidence": f"매거진 캡션 '{name} @{h}' {post.get('url', '')}".strip()})
    return cands


def _collect_occurrences(occ: list[dict]):
    spell: dict[str, Counter] = defaultdict(Counter)
    tables: dict[str, set[str]] = defaultdict(set)
    count: Counter = Counter()
    for o in occ:
        main, aliases = parse_name(o["text"])
        mk = artist_key(main)
        if not mk:
            continue
        spell[mk][clean(main) if aliases else clean(o["text"])] += o["count"]
        for a in aliases:
            spell[_squash(a)][a] += o["count"]
        tables[mk].add(o["table"])
        count[mk] += o["count"]
    return spell, tables, count


def _ig_edges(cands: dict, occ: list[dict], base: set[str], spell: dict) -> list[tuple]:
    """프로필 이름 덩어리끼리, 캡션의 한영 병기(팀이 이미 있을 때만), 라인업에 적힌 계정명 → 연결."""
    edges = []
    lower_names = {clean(o["text"]).lower().rstrip("."): artist_key(o["text"]) for o in occ}
    for h, items in cands.items():
        prof = [c for c in items if c["kind"] == "profile"]
        keys = [artist_key(parse_name(c["text"])[0]) for c in prof]
        edges += [(keys[0], k, "mid", prof[0]["evidence"]) for k in keys[1:] if k and keys[0] and k != keys[0]]
        for c in items:
            if c["kind"] == "caption" and artist_key(parse_name(c["text"])[0]) in base:
                edges += _alias_edges([{"text": c["text"], "conf": "mid"}])
                for a in parse_name(c["text"])[1]:  # 캡션의 영문 표기도 표기 목록에 (건수는 0)
                    spell[_squash(a)][a] += 0
        if h.rstrip(".") in lower_names:
            items.append({"text": h, "kind": "lineup", "key": lower_names[h.rstrip(".")],
                          "evidence": f"공연·명단에 계정명 '{h}'이 이름으로 적힘"})
    return edges


def load_manual_aliases(path: Path = MANUAL_ALIASES) -> list[dict]:
    """config/artist_aliases.json → 항목 목록. 파일이 없으면 빈 목록, 형식이 틀리면 어느 항목이 왜 틀렸는지 알리고 멈춘다."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    entries = data.get("aliases", []) if isinstance(data, dict) else None
    if not isinstance(entries, list):
        raise ValueError(f"{path}: 'aliases' 목록이 없어요")
    for i, e in enumerate(entries):
        problems = [why for ok, why in (
            (isinstance(e.get("main"), str) and e["main"].strip(), "main(대표 이름)이 비어 있음"),
            (isinstance(e.get("aliases"), list) and e["aliases"] and all(isinstance(a, str) and a.strip() for a in e["aliases"]),
             "aliases(별칭 목록)가 비어 있음"),
            (isinstance(e.get("reason"), str) and e["reason"].strip(), "reason(이유)이 비어 있음"),
            (isinstance(e.get("evidence"), list) and e["evidence"], "evidence(근거)가 비어 있음"),
            (isinstance(e.get("checked"), str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", e["checked"]), "checked(확인 날짜)가 YYYY-MM-DD가 아님"),
        ) if not ok]
        if problems:
            raise ValueError(f"{path} 항목 {i + 1} ({e.get('main', '?')}): {', '.join(problems)}")
    return entries


PLATFORMS = ("melon", "spotify")


def _common_problems(e: dict) -> list[str]:
    return [why for ok, why in (
        (isinstance(e.get("reason"), str) and e["reason"].strip(), "reason(이유)이 비어 있음"),
        (isinstance(e.get("evidence"), list) and e["evidence"], "evidence(근거)가 비어 있음"),
        (isinstance(e.get("checked"), str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", e["checked"]), "checked(확인 날짜)가 YYYY-MM-DD가 아님"),
    ) if not ok]


def _section(data: dict, key: str, check, path) -> list[dict]:
    entries = data.get(key, [])
    if not isinstance(entries, list):
        raise ValueError(f"{path}: '{key}'는 목록이어야 해요")
    for i, e in enumerate(entries):
        problems = check(e) + _common_problems(e)
        if problems:
            raise ValueError(f"{path} {key} 항목 {i + 1}: {', '.join(problems)}")
    return entries


def load_curation(path: Path | None = None) -> dict:
    """사람이 확인한 연결표 보정 전부 (config/artist_aliases.json):
    aliases(같은 팀 별칭) · distinct(다른 팀 — 묶지 말 것, 첫 이름은 따로 두고 겹치는 별칭은 나머지 이름 쪽에) ·
    platform_ids(플랫폼 번호 고정 — 맞는 번호와 다른 아티스트 번호 not) · non_artist_handles(팀이 아닌 인스타 계정)."""
    path = Path(path or MANUAL_ALIASES)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"aliases": [], "distinct": [], "platform_ids": [], "non_artist_handles": []}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: JSON 객체여야 해요")
    return {
        "aliases": load_manual_aliases(path),
        "distinct": _section(data, "distinct", lambda e: [] if isinstance(e.get("names"), list) and len(
            [n for n in e["names"] if isinstance(n, str) and n.strip()]) >= 2 else ["names(이름 2개 이상)가 없음"], path),
        "platform_ids": _section(data, "platform_ids", lambda e: [why for ok, why in (
            (isinstance(e.get("team"), str) and e["team"].strip(), "team(팀 이름)이 비어 있음"),
            (e.get("platform") in PLATFORMS, f"platform은 {'/'.join(PLATFORMS)} 중 하나"),
            (isinstance(e.get("id"), str) and e["id"].strip(), "id(맞는 번호)가 비어 있음"),
            (isinstance(e.get("not", []), list), "not(다른 아티스트 번호)은 목록"),
        ) if not ok], path),
        "non_artist_handles": _section(data, "non_artist_handles", lambda e: [] if isinstance(e.get("handle"), str)
                                       and e["handle"].strip() else ["handle(계정명)이 비어 있음"], path),
    }


def _apply_distinct(edges: list[tuple], distinct: list[dict]) -> list[tuple]:
    """'다른 팀' 쌍은 묶지 않는다: 두 이름 사이 직접 연결을 지우고, 첫 이름(멤버·개인)이 나머지 이름(그룹)과 같은 별칭을
    가지면('민기 (ATEEZ)' · '에이티즈 (ATEEZ)') 첫 이름 쪽 연결만 지운다 → 별칭은 그룹에 남는다."""
    groups = [[artist_key(n) for n in e["names"] if artist_key(n)] for e in distinct]
    claimed: dict[str, set[str]] = defaultdict(set)
    for mk, ak, *_ in edges:
        claimed[ak].add(mk)
    drop = set()
    for keys in groups:
        first, rest = keys[0], set(keys[1:])
        drop |= {(a, b) for a in keys for b in keys if a != b}
        drop |= {(first, ak) for ak, mains in claimed.items() if first in mains and mains & rest}
    return [e for e in edges if (e[0], e[1]) not in drop]


def _pin_platform_ids(platform_ids: list[dict], pins: list[dict]) -> list[dict]:
    """플랫폼 번호 고정: 다른 아티스트로 확인된 번호(not)는 어디서 왔든 버리고, 맞는 번호를 high 로 더한다."""
    blocked = {(p["platform"], str(x)) for p in pins for x in p.get("not", [])}
    kept = [r for r in platform_ids if (r["platform"], str(r["id"])) not in blocked]
    return kept + [{"name": p["team"], "platform": p["platform"], "id": str(p["id"]), "confidence": "high"} for p in pins]


def _manual_edges(entries: list[dict]) -> list[tuple]:
    """사람이 확인한 별칭 → (대표 키, 별칭 키, 'high', 근거) 간선. 충돌 검사는 자동 간선과 함께 받는다."""
    edges = []
    for e in entries:
        mk = artist_key(e["main"])
        for a in e["aliases"]:
            ak = artist_key(a)
            if mk and ak and ak != mk:
                edges.append((mk, ak, "high", f"사람 확인({e['checked']}): {e['reason']}"))
    return edges


def _settle_conflict(r: dict, g: "_Groups") -> dict:
    keys = r.get("keys") or []
    if r["kind"] != "alias_conflict" or len({g.find(k) for k in keys}) != 1:
        return {k: v for k, v in r.items() if k != "keys"}
    return {"kind": "alias_auto", "detail": r["detail"], "weight": 0,
            "reason": "자동 해결 — 충돌한 팀들이 다른 근거(사람 확인 별칭 등)로 한 팀이 됨"}


def build_xref(names: list[dict], ig_profiles: list[dict], ig_posts: list[dict],
               platform_ids: list[dict], manual_aliases: list[dict] | None = None,
               distinct: list[dict] | None = None, platform_pins: list[dict] | None = None) -> tuple[list[dict], list[dict]]:
    """원본 이름·인스타·플랫폼 번호 (+ 사람이 확인한 별칭) → (연결표 artists, 사람 확인 목록 review)."""
    review: list[dict] = []
    occ = _expand_names(names, review)
    spell, tables, count = _collect_occurrences(occ)
    base = set(count)
    cands = _ig_candidates(ig_profiles, ig_posts)
    edges = _apply_distinct(_alias_edges(occ) + _ig_edges(cands, occ, base, spell) + _manual_edges(manual_aliases or []),
                            distinct or [])
    edges = _drop_conflicts(edges, review)
    platform_ids = _pin_platform_ids(platform_ids, platform_pins or [])

    g = _Groups()
    for k in list(spell) + list(base):
        g.find(k)
    strong = _Groups()  # high 근거만으로 묶은 것 — 묶음 확신도 계산용
    evidence: dict[str, list[str]] = defaultdict(list)
    for a, b, conf, ev in edges:
        g.union(a, b)
        if conf == "high":
            strong.union(a, b)
        evidence[a].append(ev)

    review[:] = [_settle_conflict(r, g) for r in review]   # 다른 근거(사람 확인 별칭 등)로 결국 한 팀이 된 충돌은 해결로
    ig_links = _link_instagram(cands, g, base, count, spell, review)
    ctx = {"g": g, "spell": spell, "tables": tables, "count": count, "base": base,
           "strong": strong, "evidence": evidence, "ig_links": ig_links}
    return _assemble(ctx, platform_ids, review)


def _match_roots(items: list[dict], g: _Groups, base: set[str]) -> dict[str, list[dict]]:
    """후보 이름 중 다른 소스에 있는 팀(base)과 맞는 것 → {묶음 root: [후보]}."""
    by_root: dict[str, list[dict]] = defaultdict(list)
    for c in items:
        main, aliases = parse_name(c["text"])
        for k in [c.get("key") or artist_key(main), *(_squash(a) for a in aliases)]:
            if k and k in base:
                by_root[g.find(k)].append(c)
                break
    return by_root


def _link_instagram(cands, g, base, count, spell, review) -> dict[str, list[dict]]:
    """계정마다 팀(묶음 대표) 하나를 고르고 확신도를 붙인다 → {묶음 root: [instagram 항목]}."""
    links: dict[str, list[dict]] = defaultdict(list)
    root_count: Counter = Counter()
    for k in base:
        root_count[g.find(k)] += count[k]
    for h, items in sorted(cands.items()):
        by_root = _match_roots(items, g, base)
        if by_root:
            root = max(by_root, key=lambda r: (len({c["kind"] for c in by_root[r]}), root_count[r]))
            matched = by_root[root]
            if len(by_root) > 1:
                review.append({"kind": "ig_multiple_teams", "detail": f"@{h} → {', '.join(sorted(by_root))}",
                               "reason": "한 계정이 여러 팀 이름과 맞음", "weight": 2})
            core = handle_core(h)
            group_keys = [k for k in g.parent if g.find(k) == root]
            alike = any(core in k or (len(k) >= MIN_HANDLE_CORE and k in core) for k in group_keys)
            conf = "high" if alike or len({c["kind"] for c in matched}) >= 2 else "mid"
            links[root].append({"handle": h, "confidence": conf,
                                "evidence": sorted({c["evidence"] for c in matched})[:5]})
            continue
        first = next((c for c in items if c["kind"] == "profile"), items[0])
        k = artist_key(parse_name(first["text"])[0])
        if not k:
            continue
        spell[k][clean(first["text"])] += 0
        links[g.find(k)].append({"handle": h, "confidence": "low",
                                 "evidence": sorted({c["evidence"] for c in items})[:5]})
        review.append({"kind": "ig_unmatched", "detail": f"@{h} '{first['text']}'",
                       "reason": "인스타에만 있는 이름 — 다른 소스의 팀과 아직 못 이음", "weight": 1})
    return links


def _pick_id(records: list[dict], platform: str, label: str, review: list[dict]) -> str | None:
    ids: Counter = Counter()
    for r in records:
        ids[r["id"]] += CONF_RANK.get(r.get("confidence", "mid"), 2)
    if not ids:
        return None
    if len(ids) > 1:
        review.append({"kind": "multiple_platform_ids", "detail": f"{label} {platform} {', '.join(sorted(ids))}",
                       "reason": "한 팀에 플랫폼 번호가 여러 개 — 동명 팀이 섞였을 수 있음", "weight": 3})
    return ids.most_common(1)[0][0]


def _platform_by_root(g: _Groups, platform_ids: list[dict], review: list[dict]) -> dict:
    pid: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for r in platform_ids:
        main, aliases = parse_name(r["name"])
        for k in [artist_key(main), *(_squash(a) for a in aliases)]:
            if k in g.parent:
                pid[g.find(k)][r["platform"]].append(r)
                break
    return pid


def _record(root: str, keys: list[str], ctx: dict, pid: dict, review: list[dict]) -> dict | None:
    spell, count, base = ctx["spell"], ctx["count"], ctx["base"]
    in_base = [k for k in keys if k in base]
    if not in_base and root not in ctx["ig_links"]:
        return None  # 다른 표기로만 쓰이는 별칭 덩어리는 따로 팀이 아님
    key = max(in_base or keys, key=lambda k: (count[k], bool(HANGUL.search(k)), -len(k)))
    spellings: Counter = Counter()
    for k in keys:
        spellings.update(spell.get(k, {}))
    top = spell.get(key) or spellings
    display = max(top, key=lambda s: (top[s], -len(s))) if top else key
    srcs = set().union(*(ctx["tables"][k] for k in in_base)) if in_base else set()
    rec = {"artist_key": key, "display_name": display,
           "aliases": [s for s, _ in sorted(spellings.items(), key=lambda kv: (-kv[1], kv[0]))] or [display],
           "keys": sorted(keys), "instagram": ctx["ig_links"].get(root, [])}
    for platform in ("melon", "spotify"):
        chosen = _pick_id(pid[root][platform], platform, display, review)
        if chosen:
            rec[f"{platform}_id"] = chosen
            srcs.add(platform)
    if rec["instagram"]:
        srcs.add("instagram")
    if len(rec["instagram"]) > 1:
        review.append({"kind": "ig_multiple_handles",
                       "detail": f"{display} ← {', '.join('@' + i['handle'] for i in rec['instagram'])}",
                       "reason": "한 팀에 인스타 계정이 여러 개 — 동명 팀이거나 개인·팀 계정", "weight": 2})
    rec["sources"] = sorted(srcs)
    if "outcome" in srcs:  # 정답 팀이 신호와 이어졌나: 같은 키 하나로 / 다른 표기를 묶어서 / 안 이어짐
        same_key = any("outcome" in ctx["tables"][k] and SIGNAL_TABLES & ctx["tables"][k] for k in in_base)
        rec["outcome_link"] = "same_key" if same_key else "merged" if SIGNAL_TABLES & srcs else "none"
    one_strong = len({ctx["strong"].find(k) for k in keys}) == 1
    rec["confidence"] = ("high" if one_strong else "mid") if in_base else "low"
    if len(keys) > 1:
        rec["merge_evidence"] = sorted({e for k in keys for e in ctx["evidence"].get(k, [])})[:5]
    return rec


def _assemble(ctx: dict, platform_ids: list[dict], review: list[dict]) -> tuple[list[dict], list[dict]]:
    g = ctx["g"]
    members: dict[str, list[str]] = defaultdict(list)
    for k in list(g.parent):
        members[g.find(k)].append(k)
    pid = _platform_by_root(g, platform_ids, review)
    for r in platform_ids:
        if r.get("confidence") == "low":
            review.append({"kind": "platform_namesake", "detail": f"{clean(r['name'])} {r['platform']}:{r['id']}",
                           "reason": "검색 결과에 같은 이름이 여러 명", "weight": 1})
    artists = [rec for root, keys in members.items() if (rec := _record(root, keys, ctx, pid, review))]
    artists.sort(key=lambda a: a["artist_key"])
    review.sort(key=lambda r: (-r.get("weight", 0), r["kind"], r["detail"]))
    return artists, review


# ---------- 색인·통계 ----------

def _variant_keys(rec: dict) -> list[str]:
    """한 팀을 가리킬 수 있는 모든 키 (load_pg 의 artist_key·alias_key 규칙 포함)."""
    keys = [rec["artist_key"], *rec.get("keys", [])]
    for a in rec.get("aliases", []):
        main, aliases = parse_name(a)
        keys += [name_key(a), artist_key(clean(a)), _squash(clean(a)), artist_key(main), *(_squash(x) for x in aliases)]
    return list(dict.fromkeys(k for k in keys if k))


def index_from_artists(artists: list[dict]) -> dict:
    """연결표 행 목록 → {"artists", "by_key", "by_handle"} 색인."""
    index: dict = {"artists": {}, "by_key": {}, "by_handle": {}}
    for rec in artists:
        key = rec["artist_key"]
        index["artists"][key] = rec
        for k in _variant_keys(rec):
            index["by_key"].setdefault(k, key)
        for ig in rec.get("instagram", []):
            index["by_handle"].setdefault(ig["handle"].lower(), key)
    return index


def load_xref(path: Path | str = DEFAULT_XREF) -> dict:
    """연결표 파일 → 색인. 파일이 없거나 깨져 있으면 빈 색인 (canonical_key 는 정규화 키만 돌려줌)."""
    try:
        artists = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        artists = []
    return index_from_artists(artists if isinstance(artists, list) else [])


def outcome_signal_link(artists: list[dict]) -> dict:
    """정답 팀 중 신호(공연·선정·발매·기사)와 이어진 팀 수. 연결표 덕분에 새로 이어진 팀도 센다."""
    links = Counter(a.get("outcome_link", "none") for a in artists if "outcome" in a["sources"])
    return {"outcome_teams": sum(links.values()), "linked_teams": links["same_key"] + links["merged"],
            "linked_only_by_xref": links["merged"]}


NON_ARTIST_KEY = "__non_artist__"   # 팀이 아닌 계정(매거진·공연장·기관) — core.v_signal 이 이 키의 줄을 신호에서 뺀다
ORG_HANDLES = ("kocca_official", "_muse_on", "gmail.com", "naver.com")   # 캡션에 자주 태그되는 기관·프로그램 계정
# 팀처럼 잡히지만 지원·경연 프로그램 이름인 것 (연결표에 팀으로 있어도 덮어씀)
PROGRAM_NAME_KEYS = ("뮤즈온", "museon", "헬로루키", "hellorookie", "튠업", "인디스땅스", "뮤콘", "mucon")
INSTA_ACCOUNTS = ROOT / "config" / "insta_accounts.json"


def tracked_account_handles(path: Path = INSTA_ACCOUNTS) -> list[str]:
    """우리가 추적하는 매거진·공연장 계정 + 기관 계정 = 팀이 아닌 계정명. 파일이 없으면 기관 계정만."""
    try:
        accounts = json.loads(path.read_text(encoding="utf-8")).get("accounts", [])
    except (OSError, ValueError, AttributeError):
        accounts = []
    return [a.get("handle", "") for a in accounts if a.get("handle")] + list(ORG_HANDLES)


def xref_rows(artists: list[dict], non_artist_handles: list[str] | None = None) -> list[tuple[str, str, str, str]]:
    """DB ref.artist_xref 행: (variant_key, artist_key, display_name, confidence). variant_key 는 중복 없음."""
    rows: dict[str, tuple] = {}
    for rec in artists:
        for k in _variant_keys(rec):
            rows.setdefault(k, (k, rec["artist_key"], rec["display_name"], rec["confidence"]))
    # 연결된 인스타 계정명(확신 high·mid)도 그 팀의 표기로: 인스타 게시물에서 이름 대신 '@oysters.999'만 잡힌 줄을 잇는다.
    # 팀 이름 키를 다 넣은 뒤에 넣어서, 계정명 키가 다른 팀의 실제 이름 키를 덮어쓰지 않게 한다.
    for rec in artists:
        for ig in rec.get("instagram") or []:
            if ig.get("confidence") in ("high", "mid") and ig.get("handle"):
                k = artist_key(ig["handle"].lstrip("@"))
                if k:
                    rows.setdefault(k, (k, rec["artist_key"], rec["display_name"], ig["confidence"]))
    for k in PROGRAM_NAME_KEYS:                 # 프로그램 이름은 확실히 팀이 아니므로 덮어쓴다
        rows[k] = (k, NON_ARTIST_KEY, "팀 아님(지원·경연 프로그램 이름)", "high")
    for h in non_artist_handles or []:          # 마지막에: 실제 팀 키는 덮어쓰지 않음
        k = artist_key(h.lstrip("@"))
        if k:
            rows.setdefault(k, (k, NON_ARTIST_KEY, "팀 아님(매거진·공연장·기관 계정)", "high"))
    return list(rows.values())


def pg_load_script(csv_path: str) -> str:
    """ref.artist_xref 를 비우고 다시 채우는 psql 스크립트 (한 트랜잭션).
    core 뷰(sql/kr/00_core_views.sql)가 이 표를 참조하므로 DROP 하지 않는다."""
    return "\n".join([
        "BEGIN;",
        "CREATE SCHEMA IF NOT EXISTS ref;",
        "CREATE TABLE IF NOT EXISTS ref.artist_xref (variant_key text PRIMARY KEY, artist_key text NOT NULL, "
        "display_name text, confidence text);",
        "CREATE INDEX IF NOT EXISTS artist_xref_artist_key_idx ON ref.artist_xref (artist_key);",
        "TRUNCATE ref.artist_xref;",
        f"\\copy ref.artist_xref FROM '{csv_path}' WITH (FORMAT csv)",
        "COMMIT;",
    ]) + "\n"


def load_pg(artists: list[dict], psql_path: str = PSQL, db: str = DB) -> str:
    """ref.artist_xref 표로 넣기. psql·DB가 없으면 건너뛰고 메시지만 돌려준다.
    넣은 뒤 sql/kr/00_core_views.sql 을 다시 실행해야 뷰의 team_key 에 반영된다."""
    if not Path(psql_path).exists():
        return "PostgreSQL 적재 건너뜀: psql을 찾을 수 없음 (PSQL 환경변수로 위치 지정 가능)"
    rows = xref_rows(artists, tracked_account_handles())
    with tempfile.TemporaryDirectory() as d:
        csv_path, sql_path = Path(d) / "artist_xref.csv", Path(d) / "load.sql"
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerows(rows)
        sql_path.write_text(pg_load_script(str(csv_path)), encoding="utf-8")
        proc = subprocess.run([psql_path, "-v", "ON_ERROR_STOP=1", "-q", "-d", db, "-f", str(sql_path)],
                              capture_output=True, text=True)
    if proc.returncode != 0:
        return f"PostgreSQL 적재 건너뜀: {proc.stderr.strip()[:300]}"
    return f"PostgreSQL ref.artist_xref {len(rows):,}행 적재 (뷰 반영: psql -f sql/kr/00_core_views.sql)"


# ---------- 원본 읽기 ----------

def _read_csv(path: str) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _table_of(path: str) -> str:
    stem = Path(path).name
    return next((t for prefix, t in TABLE_OF.items() if stem.startswith(prefix + "_")), "")


def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _ig_posts(rows: list[dict], non_artists: set[str]) -> list[dict]:
    per_url = Counter(r["url"] for r in rows)
    return [{"handle": r["artist_handle"].lstrip("@"), "caption": r["title"], "url": r["url"],
             "single_tag": per_url[r["url"]] == 1}
            for r in rows if r.get("artist_handle") and r["artist_handle"].lstrip("@").lower() not in non_artists]


MIN_MELON_ID = 1_000   # 이보다 작은 멜론 번호는 버림 — 검색 결과에서 이름 속 숫자를 번호로 잘못 읽은 값 (12BH→12, D82→82)


def _usable_id(platform: str, pid) -> bool:
    s = str(pid or "")
    if platform != "melon":
        return bool(s)
    return s.isdigit() and int(s) >= MIN_MELON_ID


def collect_inputs(raw_dir: Path = RAW_DIR) -> tuple[list, list, list, list]:
    """data/raw 원본 → build_xref 입력 4가지 (names, ig_profiles, ig_posts, platform_ids)."""
    name_count: Counter = Counter()
    ig_profiles, ig_posts, platform_ids = [], [], []
    seen = _load_json(raw_dir / "state" / "ig_artists_seen.json", {})
    links = _load_json(raw_dir / "state" / "ig_artist_links.json", {})
    non_artists = {h.lower() for h in links.get("non_artists", {})} | {h.lower() for h, v in seen.items() if v == "non_artist"}
    non_artists |= {h.lstrip("@").lower() for h in tracked_account_handles(INSTA_ACCOUNTS)}   # 우리가 따라가는 매거진·공연장·기관 계정
    non_artists |= {e["handle"].lstrip("@").lower() for e in load_curation()["non_artist_handles"]}   # 사람이 확인한 팀 아닌 계정
    for path in sorted(glob.glob(str(raw_dir / "raw_*.csv"))):
        table = _table_of(path)
        rows = _read_csv(path) if table else []
        if table == "press" and rows and rows[0].get("source") == "instagram":
            ig_posts += _ig_posts(rows, non_artists)
            continue
        for r in rows:
            src = r.get("source", "")
            if table == "profile" and src == "instagram":
                if r["artist_source_id"].lower() not in non_artists:
                    ig_profiles.append({"handle": r["artist_source_id"], "name": r["artist_text"], "source": "instagram 프로필 CSV"})
                continue
            if r.get("artist_text"):
                name_count[(table, r["artist_text"])] += 1
            if table in ("profile", "release") and src in ("melon", "spotify") and _usable_id(src, r.get("artist_source_id")):
                platform_ids.append({"name": r["artist_text"], "platform": src, "id": r["artist_source_id"], "confidence": "high"})
    for h, v in links.items():
        if h != "non_artists" and h.lower() not in non_artists and isinstance(v, dict):
            ig_profiles.append({"handle": h, "name": v.get("name", ""), "source": "ig_artist_links"})
    for fname, platform in (("outcome_melon_match.json", "melon"), ("spotify_match.json", "spotify")):
        for name, m in _load_json(raw_dir / "state" / fname, {}).items():
            if isinstance(m, dict) and _usable_id(platform, m.get("id")):
                conf = "high" if int(m.get("namesakes") or 1) <= 1 else "mid"
                platform_ids.append({"name": name, "platform": platform, "id": str(m["id"]), "confidence": conf})
    names = [{"table": t, "name": n, "count": c} for (t, n), c in name_count.items()]
    return names, ig_profiles, ig_posts, platform_ids


# ---------- 요약 문서·실행 ----------

def _stats_lines(artists: list[dict], review: list[dict], names: list[dict], ig_handles: set[str],
                 manual: list[dict] | None = None, curation: dict | None = None) -> list[str]:
    cur = curation or {}
    multi_spell = [a for a in artists if len(a["aliases"]) >= 2]
    multi_key = [a for a in artists if len(a["keys"]) >= 2]
    conf_n = Counter(ig["confidence"] for a in artists for ig in a["instagram"])
    base_linked = conf_n["high"] + conf_n["mid"]
    split_n = sum(1 for r in names if r["table"] == "selection" and split_cell(r["name"])["status"] == "split")
    auto = [r for r in review if r["kind"] in AUTO_KINDS]
    review = [r for r in review if r["kind"] not in AUTO_KINDS]
    kinds = Counter(r["kind"] for r in review)
    oc = outcome_signal_link(artists)
    pct = lambda a, b: f"{100 * a / max(b, 1):.1f}%"  # noqa: E731
    return [
        "| 항목 | 값 |", "|---|---|",
        f"| 대표 팀 수 | {len(artists):,} |",
        f"| 표기 2개 이상으로 적힌 팀 | {len(multi_spell):,}팀 (표기 {sum(len(a['aliases']) for a in multi_spell):,}개) |",
        f"| 이름 키가 달라 갈라져 있던 팀 → 새로 묶음 (한영 병기·인스타 이름 근거) | {len(multi_key):,}팀 |",
        f"| 선정 명단에서 한 칸에 여러 명 → 팀 단위로 나눈 칸 | {split_n}칸 |",
        f"| 인스타 계정 (아티스트로 분류된 것) | {len(ig_handles):,}개 |",
        f"| └ 다른 소스의 팀과 연결 (high + mid) | {base_linked:,}개 ({pct(base_linked, len(ig_handles))}) — high {conf_n['high']}, mid {conf_n['mid']} |",
        f"| └ 인스타에만 있는 이름 (low) | {conf_n['low']:,}개 |",
        f"| 멜론 번호 / 스포티파이 번호 붙은 팀 | {sum('melon_id' in a for a in artists):,} / {sum('spotify_id' in a for a in artists):,} |",
        f"| **정답 팀 중 신호(공연·선정·발매·기사)와 이어진 팀** | {oc['linked_teams']:,} / {oc['outcome_teams']:,}팀 ({pct(oc['linked_teams'], oc['outcome_teams'])}) |",
        f"| └ 그중 연결표로 다른 표기를 묶어서 새로 이어진 팀 | {oc['linked_only_by_xref']:,}팀 |",
        f"| 사람이 확인한 별칭 (`config/artist_aliases.json`) | {len(manual or [])}팀 · 별칭 {sum(len(e['aliases']) for e in manual or [])}개 |",
        f"| 사람이 확인한 다른 팀 / 플랫폼 번호 고정 / 팀 아닌 인스타 계정 (같은 파일) | "
        f"{len(cur.get('distinct', []))}쌍 / {len(cur.get('platform_ids', []))}팀 / {len(cur.get('non_artist_handles', []))}개 |",
        f"| 별칭 충돌 자동 해결 (긴 이름이 짧은 이름을 품는 합동 표기 → 별칭은 짧은 쪽) | {len(auto):,}건 |",
        f"| 사람 확인 필요 | {len(review):,}건 ({', '.join(f'{k} {v}' for k, v in kinds.most_common())}) |",
    ]


def summarize(artists: list[dict], review: list[dict], names: list[dict], ig_handles: set[str],
              manual: list[dict] | None = None, curation: dict | None = None) -> str:
    """공개용 요약 (숫자·예시만, 개인 경로 없음)."""
    lines = [
        "# 아티스트 연결표 요약 (artist_xref)", "",
        f"_자동 생성: `python3 scripts/artist_xref.py` · {datetime.now():%Y-%m-%d %H:%M}_", "",
        "플랫폼·소스마다 다르게 적힌 팀 이름을 **대표 이름 1개 + 표기 목록**으로 묶고, 인스타 계정·멜론/스포티파이 번호를 붙인 표예요 "
        "(업계 말로 '아티스트 매칭·메타데이터 검수'). 문제 찾기는 검증 SQL(`docs/sql/README.md` c02·c06·c08), 고친 표 만들기는 이 스크립트, "
        "결과는 다시 PostgreSQL `ref.artist_xref`(표기 키 → 대표 키)로 넣어 SQL에서 씁니다.",
        "원본 연결표는 실제 수집 데이터라 저장소에 올리지 않고 여기엔 숫자와 예시만 둡니다.", "",
        "## 숫자", "", *_stats_lines(artists, review, names, ig_handles, manual, curation), "",
        "정답↔신호 연결률은 날짜를 따지지 않은 '이름이 이어지는가'만 본 숫자예요. 점수 백테스트의 정답 수는 여기에 "
        "'신호가 정답보다 먼저'·'정답 기간 2025년 이후'·'같은 프로그램 계열 제외' 조건이 더해져 줄어듭니다.", "",
        "확신도: **high** = 다른 소스의 팀 이름과 맞고 계정명도 닮았거나 근거가 2가지 이상 · **mid** = 근거 1가지 · **low** = 인스타에만 있음.", "",
        "자동 규칙으로 못 묶는 같은 팀의 다른 표기(철자·외래어 표기·숫자 읽기 차이)는 사람이 근거를 확인한 뒤 `config/artist_aliases.json`에 적는다. "
        "이유·근거 링크·확인 날짜가 있어야 하고, high 연결로 들어가되 자동 연결과 같이 충돌 검사(같은 별칭이 다른 팀에 붙으면 버림)를 받는다.", "",
        "## 묶인 예시 (표기가 많은 순 10개)", "",
        "| 대표 이름 | 표기 | 인스타 | 소스 |", "|---|---|---|---|",
    ]
    multi_key = [a for a in artists if len(a["keys"]) >= 2]
    for a in sorted(multi_key, key=lambda a: (-len(a["aliases"]), a["artist_key"]))[:10]:
        ig = ", ".join(f"@{i['handle']}({i['confidence']})" for i in a["instagram"]) or "-"
        lines.append(f"| {a['display_name']} | {' / '.join(a['aliases'][:5])} | {ig} | {', '.join(a['sources'])} |")
    lines += ["", "## 사람 확인이 필요한 애매한 목록 (상위 20)", "", "| 종류 | 내용 | 이유 |", "|---|---|---|"]
    lines += [f"| {r['kind']} | {r['detail'].replace('|', '/')} | {r['reason']} |" for r in [x for x in review if x['kind'] not in AUTO_KINDS][:20]]
    lines += ["", "종류: cell_split = 한 칸 여러 명 중 나누지 않고 둔 것 · alias_conflict = 같은 별칭이 여러 팀에 붙음 · "
              "multiple_platform_ids = 한 팀에 플랫폼 번호 여러 개 · ig_multiple_teams = 한 계정이 여러 팀과 맞음 · "
              "ig_unmatched = 인스타에만 있는 이름 · platform_namesake = 검색 동명이인. "
              "자동 해결(alias_auto)은 확인 목록 파일에만 기록하고 이 표·건수에서는 뺀다.", ""]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="아티스트 연결표 만들기")
    ap.add_argument("--load-pg", action="store_true", help="PostgreSQL ref.artist_xref 로도 넣기")
    args = ap.parse_args()
    names, ig_profiles, ig_posts, platform_ids = collect_inputs()
    cur = load_curation()
    manual = cur["aliases"]
    artists, review = build_xref(names, ig_profiles, ig_posts, platform_ids, manual_aliases=manual,
                                 distinct=cur["distinct"], platform_pins=cur["platform_ids"])
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    DEFAULT_XREF.write_text(json.dumps(artists, ensure_ascii=False, indent=1), encoding="utf-8")
    REVIEW_PATH.write_text(json.dumps(review, ensure_ascii=False, indent=1), encoding="utf-8")
    handles = {h for h in ({p["handle"].lstrip("@").lower() for p in ig_profiles} | {p["handle"].lower() for p in ig_posts})
               if not NOT_A_HANDLE.search(h)}
    SUMMARY_MD.write_text(summarize(artists, review, names, handles, manual, cur), encoding="utf-8")
    n_auto = sum(r["kind"] in AUTO_KINDS for r in review)
    print(f"대표 팀 {len(artists):,} · 확인 필요 {len(review) - n_auto:,} (자동 해결 {n_auto}) → {DEFAULT_XREF.relative_to(ROOT)}, {SUMMARY_MD.relative_to(ROOT)}")
    if args.load_pg:
        print(load_pg(artists))


if __name__ == "__main__":
    main()
