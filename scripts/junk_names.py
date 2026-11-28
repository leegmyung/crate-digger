"""팀이 아닌 이름 모양 규칙 — config/source_roles.json candidate_rules.name_patterns.

인스타 게시물 태그(@계정)를 팀 이름 대신 그대로 받은 줄('hivepark_kr', 'naiite.grind'), 웹 주소('https.jester.co.kr') 같은
쓰레기 이름이 떠오르는 차트·후보에 섞였다(docs/ui_review_2026-11-28.md 2-2). 원본 이름에 규칙을 대 보고 걸린 이름 키를
artist_xref.py 가 '팀 아님'(NON_ARTIST_KEY)으로 보내면 core.v_signal 이 그 줄을 신호에서 뺀다.

규칙마다 only_sources 가 있으면 그 이름(같은 이름 키)이 그 출처에서만 나왔을 때만 적용한다 —
인디스트릿·멜론·선정 명단 등 다른 출처에도 같은 이름이 있으면 실제 팀 이름으로 보고 남긴다('quinn_', 'mong_gle').
"""
from __future__ import annotations

import csv
import glob
import json
import re
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Set

ROOT = Path(__file__).resolve().parent.parent
ROLES = ROOT / "config" / "source_roles.json"
RAW_DIR = ROOT / "data" / "raw"
# 신호 원본 + 아티스트 프로필(멜론·스포티파이 프로필이 있으면 실제 팀 이름 — 'televisionoff'). 정답 표는 뺌(팀을 골라 받은 명단)
SIGNAL_PREFIXES = ("raw_kr_gig_", "raw_kr_selection_", "raw_kr_release_", "raw_press_", "raw_artist_profile_")


def load_name_rules(path: Path = ROLES) -> List[dict]:
    """[{name, regex, reason, only_sources(set|None)}] — 설정이 없거나 깨졌으면 []."""
    try:
        cfg = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    rules = (((cfg.get("candidate_rules") or {}).get("name_patterns") or {}).get("rules")) or []
    out = []
    for r in rules:
        try:
            out.append({"name": r.get("name", ""), "regex": re.compile(r["pattern"]), "reason": r.get("reason", ""),
                        "only_sources": set(r["only_sources"]) if r.get("only_sources") else None})
        except (KeyError, re.error, TypeError):
            continue
    return out


def junk_reason(name: str, sources: Set[str], rules: Iterable[dict]) -> str:
    """이름이 규칙에 걸리면 이유, 아니면 ''. sources = 그 이름 키가 나온 신호 출처들."""
    text = str(name or "").strip()
    if not text:
        return ""
    for r in rules:
        if r["only_sources"] is not None and not (sources and sources <= r["only_sources"]):
            continue
        if r["regex"].search(text):
            return r["reason"]
    return ""


def name_sources(raw_dir: Path = RAW_DIR, key_of: Optional[Callable[[str], str]] = None) -> Dict[str, dict]:
    """이름 키 → {sources: 나온 출처들, names: 원본 표기들}. 신호 원본(공연·선정·발매·기사)과 아티스트 프로필을 본다."""
    if key_of is None:
        import artist_xref
        key_of = artist_xref.name_key
    out: Dict[str, dict] = {}
    for path in sorted(glob.glob(str(Path(raw_dir) / "raw_*.csv"))):
        if not Path(path).name.startswith(SIGNAL_PREFIXES):
            continue
        with open(path, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                name = (r.get("artist_text") or "").strip()
                key = key_of(name) if name else ""
                if not key:
                    continue
                entry = out.setdefault(key, {"sources": set(), "names": set()})
                entry["sources"].add(r.get("source") or "")
                entry["names"].add(name)
    return out


def junk_keys(info: Mapping[str, dict], rules: Iterable[dict]) -> Dict[str, str]:
    """이름 키 → 이유. 원본 표기가 **모두** 규칙에 걸릴 때만 — 하나라도 정상 이름(인스타 프로필 이름 'Television off' 등)이면 남긴다."""
    rules = list(rules)
    out: Dict[str, str] = {}
    for key, v in info.items():
        names = sorted(v.get("names") or ())
        sources = set(v.get("sources") or ())
        reasons = [junk_reason(n, sources, rules) for n in names]
        if names and all(reasons):
            out[key] = reasons[0]
    return out
