"""팀별 영문 활동명 모으기 (검색 전용) → data/raw/state/en_names.json (비공개)

    python3 scripts/en_names.py

- 왜: '소여' 처럼 한글 이름 팀이 iTunes·유튜브에는 영문 이름('Sawyer')으로만 올라 있어 검색에 안 잡힌다.
- 연결표(config/artist_aliases.json·artist_xref)에 넣지 않는다 — 별칭은 팀 묶기에 쓰여서, 검색용 후보가 섞이면 다른 팀이 합쳐질 수 있다.
  이 파일은 collect_itunes·yt_channel_search 가 '검색어·이름 맞추기 후보'로만 쓴다. 맞는지 확인 규칙(발매곡·첫 발매 연도 겹침,
  Topic 은 발매곡 겹침)은 그대로라서 후보가 틀려도 앱에 나가지 않는다.
- 출처 (앞이 먼저): 원본 자료(공연·발매·기사·선정·정답·프로필)의 '한글 (English)' 표기 → 연결표 별칭 중 영문 →
  MusicBrainz 이름 → 스포티파이 매칭 이름 → (위가 하나도 없을 때만) 팀 인스타 계정에서 뽑은 이름(band_sawyer → sawyer).
- 한글 이름 팀만 (이미 영문 이름인 팀은 필요 없음).
"""
from __future__ import annotations

import csv
import glob
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from normalize import artist_key  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
STATE_DIR = RAW_DIR / "state"
STATE_FILE = STATE_DIR / "en_names.json"
DATA_DIR = ROOT / "docs" / "lab" / "data"
HANGUL = re.compile(r"[가-힣]")
KO = r"[가-힣][가-힣0-9 ]*?"
EN = r"[A-Za-z][A-Za-z0-9 .&'!-]*?"
PAIR = re.compile(rf"^\s*({KO})\s*[\(（]\s*({EN})\s*[\)）]\s*$|^\s*({EN})\s*[\(（]\s*({KO})\s*[\)）]\s*$")
NOT_NAME = re.compile(r"^(?:feat|ft|with|prod|live|remix|ver|version|inst)\b", re.I)
HANDLE_NOISE = {"band", "official", "offcl", "ofc", "music", "kr", "korea", "insta", "page"}
MIN_LETTERS = 3
SKIP_RAW = ("raw_video", "raw_collab")


def _letters(text: str) -> int:
    return sum(ch.isalpha() for ch in text)


def latin_pair(text: str) -> Optional[Tuple[str, str]]:
    """'한글 (English)' 또는 'English (한글)' → (한글, English). 아니면 None."""
    m = PAIR.match(text or "")
    if not m:
        return None
    ko, en = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
    ko, en = ko.strip(), en.strip()
    if NOT_NAME.match(en) or _letters(en) < MIN_LETTERS:
        return None
    return ko, en


def handle_name(handle: str) -> Optional[str]:
    """인스타 계정 → 이름 후보 (band·official 같은 낱말과 숫자 조각을 뗌). 너무 짧으면 None."""
    parts = [p for p in re.split(r"[._]+", (handle or "").lower()) if p and p not in HANDLE_NOISE and not p.isdigit()]
    name = " ".join(parts)
    return name if _letters(name) >= MIN_LETTERS else None


def build(display: Dict[str, str], xref_aliases: Dict[str, List[str]], raw_texts: Iterable[str],
          musicbrainz: dict, spotify: Dict[str, str], handles: Dict[str, List[str]],
          key_of: Callable[[str], str] = artist_key) -> Dict[str, List[dict]]:
    """팀 → [{name, source}] (한글 이름 팀만, 이름 키가 같은 것은 하나만)."""
    found: Dict[str, List[dict]] = {}

    def add(team: str, name: str, source: str) -> None:
        if team not in display or not HANGUL.search(display[team]) or not name:
            return
        k = artist_key(name)
        lst = found.setdefault(team, [])
        if k and k != artist_key(display[team]) and all(artist_key(x["name"]) != k for x in lst):
            lst.append({"name": name, "source": source})

    for text in raw_texts:
        pair = latin_pair(text)
        if pair:
            add(key_of(pair[0]), pair[1], "raw")
    for team, names in xref_aliases.items():
        for n in names:
            if not HANGUL.search(n) and _letters(n) >= MIN_LETTERS:
                add(team, n, "xref")
    for team, entry in musicbrainz.items():
        name = (entry or {}).get("name") or ""
        if (entry or {}).get("mbid") and not HANGUL.search(name):
            add(team, name, "musicbrainz")
    for team, name in spotify.items():
        if not HANGUL.search(name or ""):
            add(team, name, "spotify")
    for team, hs in handles.items():
        if found.get(team):
            continue                                   # 더 나은 출처가 있으면 계정 이름은 안 씀
        for h in hs:
            name = handle_name(h)
            if name:
                add(team, name, "instagram")
    return {k: v for k, v in found.items() if v}


def names_for(state: Dict[str, List[dict]], team: str) -> List[str]:
    out, seen = [], set()
    for x in state.get(team) or []:
        k = artist_key(x.get("name") or "")
        if k and k not in seen:
            seen.add(k)
            out.append(x["name"])
    return out


def load(path: Path = STATE_FILE) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _csv(path: Path) -> List[dict]:
    try:
        with open(path, encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except (OSError, csv.Error):
        return []


def _raw_texts() -> List[str]:
    out = []
    for path in sorted(glob.glob(str(RAW_DIR / "raw_*.csv"))):
        if not Path(path).name.startswith(SKIP_RAW):
            out += [r.get("artist_text") or "" for r in _csv(Path(path))]
    return out


def _xref_aliases() -> Dict[str, List[str]]:
    try:
        artists = json.loads((STATE_DIR / "artist_xref.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {a["artist_key"]: list(a.get("aliases") or []) for a in artists if isinstance(a, dict) and a.get("artist_key")}


def _handles() -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for r in _csv(DATA_DIR / "links.csv"):
        if r.get("platform") == "instagram":
            out.setdefault(r["team_key"], []).append(r["url"].rstrip("/").rsplit("/", 1)[-1])
    for name in ("indiego_sns.json", "indistreet_sns.json"):
        for team, e in load(STATE_DIR / name).items():
            if isinstance(e, dict) and e.get("instagram"):
                out.setdefault(team, []).append(e["instagram"])
    return out


def main() -> int:
    from artist_xref import canonical_key, load_xref
    index = load_xref()

    def key_of(name: str) -> str:
        return canonical_key(name, index)

    display = {r["team_key"]: r.get("display_name") or r["team_key"] for r in _csv(DATA_DIR / "teams.csv")}
    spotify = {key_of(n): m.get("name") or "" for n, m in load(STATE_DIR / "spotify_match.json").items()
               if isinstance(m, dict) and int(m.get("namesakes") or 1) <= 1}
    state = build(display, _xref_aliases(), _raw_texts(), load(STATE_DIR / "musicbrainz.json"), spotify, _handles(), key_of)
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=0), encoding="utf-8")
    first = Counter(v[0]["source"] for v in state.values())
    print(f"✅ 영문 활동명: {len(state)}팀 (첫 후보 출처 {dict(first)}) → {STATE_FILE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
