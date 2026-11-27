"""공연장 종류 정하기 — config/venues_kr.json 의 type 칸을 **공개 근거**로 다시 정하고 근거를 type_basis 에 적는다.

예전 type 은 이름만 보고 짐작해서(guess_type) 이름에 단서가 없으면 모두 '라이브클럽'이 됐다. 이 스크립트는 근거가 있을 때만 종류를 붙이고,
없으면 빈칸('미정')으로 둔다. 근거 순서:
  1. 공식 이름(별칭 포함)의 낱말 — 창작소 · 야외/페스티벌 · 소극장/씨어터 · 카페/커피/살롱/바 · 홀/아트센터/돔 · 클럽/재즈클럽/스테이지
  2. 확인된 수용 인원(config/venue_capacity.json — 출처 링크 있음, 또는 마스터 capacity) — 401명 이상 = 홀, 400명 이하 스탠딩 = 라이브클럽
     (좌석 수만 알면 클럽·카페·소극장을 가를 수 없어 정하지 않음)
  3. 근거 링크 메모·상태 메모의 낱말(라이브클럽·재즈클럽·카페·소극장)
type_basis 가 '수동:'으로 시작하면 사람이 정한 것이라 건드리지 않는다. 새 근거가 없어도 예전 값이 이름 짐작(guess_type)으로는
나올 수 없는 값이면 앞선 조사에서 정한 것으로 보고 유지한다('이전 조사' 표시).

실행: .venv/bin/python scripts/venue_types.py            # 바뀔 목록만 보여 줌
     .venv/bin/python scripts/venue_types.py --write    # config/venues_kr.json 에 씀 (그다음 scripts/venues_kr.py 로 문서 갱신)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

import venues_kr as vk  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "venues_kr.json"
CAPACITY = ROOT / "config" / "venue_capacity.json"
MANUAL_PREFIX = "수동:"
RESEARCHED = "이전 조사"
RESEARCHED_BASIS = "이전 조사에서 정한 값(이름 짐작과 다름) — 근거 링크(sources) 참고"
HALL_MIN = 401                  # venue_capacity.json 체급 L 시작 = 홀

# (종류, 낱말 정규식) — 위가 먼저. 대표 이름을 먼저 다 보고, 단서가 없을 때만 별칭을 본다.
NAME_RULES: List[Tuple[str, str]] = [
    ("creation_center", r"창작소|창작지원|진흥센터|뮤지스탕스|문화재단"),
    ("festival", r"야외|페스티벌|축제|공원|광장"),
    ("hall", r"라이브\s?홀"),                # '드림씨어터 라이브홀'처럼 라이브홀이 더 구체적
    ("theater", r"소극장|씨어터|시어터|theat(?:er|re)"),
    ("cafe", r"카페|cafe|커피|coffee|다방|라운지|살롱|펍|pub|책방|바$|bar$"),
    ("hall", r"라이브홀|아트홀|아트센터|예술의전당|문화회관|회관|돔|dome|아레나|arena|KINTEX|킨텍스|체육관|홀$|홀\s|hall"),
    ("live_club", r"재즈클럽|클럽|club|스테이지|stage"),
]
NOTE_RULES: List[Tuple[str, str]] = [
    ("live_club", r"라이브\s?클럽|재즈\s?클럽|live\s?(?:music\s?)?club"),
    ("theater", r"소극장"),
    ("cafe", r"카페|cafe"),
]


def _names(e: dict) -> List[str]:
    return [n for n in [e.get("name"), *(e.get("aliases") or [])] if n]


def _capacity(e: dict, capacity_cfg: Optional[dict]) -> Tuple[Optional[int], Optional[bool], str]:
    """(수용 인원, 스탠딩 값인가, 어디서) — venue_capacity.json 이 먼저(스탠딩/좌석 구분이 있음), 없으면 마스터 capacity."""
    venues = (capacity_cfg or {}).get("venues") or {}
    for n in [e.get("our_venue"), *(e.get("our_names") or []), *_names(e)]:
        info = venues.get(n) if n else None
        if isinstance(info, dict) and info.get("capacity"):
            return int(info["capacity"]), bool(info.get("standing")), "venue_capacity 확인값"
    if e.get("capacity"):
        return int(e["capacity"]), True, "마스터 목록, 스탠딩 기준 값"
    return None, None, ""


def classify(e: dict, capacity_cfg: Optional[dict] = None) -> Tuple[str, str]:
    """(종류 또는 '', 근거 문장 또는 '')."""
    for n in _names(e):
        for kind, pat in NAME_RULES:
            m = re.search(pat, n.replace(" ", "") if kind != "hall" else n, re.I)
            if m:
                return kind, f"이름 '{n}'에 '{m.group(0)}' → {vk.TYPES[kind]}"
    cap, standing, where = _capacity(e, capacity_cfg)
    if cap is not None and cap >= HALL_MIN:
        return "hall", f"수용 인원 {cap}명({where}) — {HALL_MIN}명 이상은 홀"
    if cap is not None and standing:
        return "live_club", f"스탠딩 수용 {cap}명({where}) — 400명 이하 스탠딩 공연장은 라이브클럽"
    notes = [e.get("status_note") or "", *[(s or {}).get("note") or "" for s in e.get("sources") or []]]
    for kind, pat in NOTE_RULES:
        for t in notes:
            m = re.search(pat, t, re.I)
            if m:
                return kind, f"근거 메모 '{t[:40]}'에 '{m.group(0)}' → {vk.TYPES[kind]}"
    return "", ""


def apply(cfg: dict, capacity_cfg: Optional[dict] = None) -> Tuple[dict, List[Tuple[str, str, str, str]]]:
    """새 설정과 바뀐 목록 [(이름, 예전 종류, 새 종류, 근거)]. 원본은 바꾸지 않는다."""
    venues, changes = [], []
    for e in cfg.get("venues", []):
        if str(e.get("type_basis") or "").startswith(MANUAL_PREFIX):
            venues.append(dict(e))
            continue
        kind, basis = classify(e, capacity_cfg)
        old = e.get("type") or ""
        prev_basis = str(e.get("type_basis") or "")
        researched = (not prev_basis and old != vk.guess_type(str(e.get("name") or ""))) or prev_basis.startswith(RESEARCHED)
        if not kind and old and researched:
            kind, basis = old, RESEARCHED_BASIS
        if kind != e.get("type") or basis != e.get("type_basis"):
            changes.append((str(e.get("name")), str(e.get("type") or ""), kind, basis))
        venues.append({**e, "type": kind, "type_basis": basis})
    return {**cfg, "types": dict(vk.TYPES), "venues": venues}, changes


def _load(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="공연장 종류를 공개 근거로 정하기 → config/venues_kr.json type·type_basis")
    ap.add_argument("--write", action="store_true", help="config/venues_kr.json 에 씀")
    args = ap.parse_args(argv)
    cfg = _load(CONFIG)
    if not cfg:
        print(f"{CONFIG} 를 읽을 수 없음", file=sys.stderr)
        return 1
    new, changes = apply(cfg, _load(CAPACITY))
    count = Counter(vk.TYPES.get(e["type"], vk.TYPE_UNKNOWN) for e in new["venues"])
    print("종류별: " + " · ".join(f"{k} {v}" for k, v in count.most_common()))
    print(f"바뀌는 곳 {len(changes)}곳")
    for name, old, kind, basis in changes:
        print(f"  {name}: {vk.TYPES.get(old, old or vk.TYPE_UNKNOWN)} → {vk.TYPES.get(kind, vk.TYPE_UNKNOWN)}  ({basis or '근거 없음'})")
    if args.write:
        CONFIG.write_text(json.dumps(new, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"→ {CONFIG.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
