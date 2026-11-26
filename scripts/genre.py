"""장르 큰 갈래(bucket) — 플랫폼마다 다른 장르 태그를 6~10개 큰 갈래로 묶는다.

- bucket_of("인디음악|록/메탈") → "rock"   (대표 갈래 하나, 모르면 "")
- buckets_of("인디음악|록/메탈|포크/블루스") → ["folk", "rock"]   (우선순위 순서)
- '인디음악'·'인디'·'가요' 같은 태그는 장르가 아니라 '어느 판에서 나왔나' 표시라서 갈래로 안 친다.
- 규칙은 config/genre_map.json 에 있다. 설명은 docs/genre_map.md.

실행: python3 scripts/genre.py [data/raw]  → 데이터 속 갈래 분포와 못 맞춘 태그를 보여준다.
"""
import csv
import json
import re
import sys
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "genre_map.json"
RAW_DIR = ROOT / "data" / "raw"
RERUN_SUFFIX = re.compile(r"_\d{4,6}$")
FILE_KINDS = {"raw_artist_profile_": "artist", "raw_kr_release_": "release"}


@lru_cache(maxsize=1)
def load_config(path: str = str(CONFIG_PATH)) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _norm(tag: str) -> str:
    return " ".join(tag.strip().lower().split())


@lru_cache(maxsize=1)
def _tables() -> tuple:
    cfg = load_config()
    exact = {}
    for key, bucket in cfg["buckets"].items():
        for tag in bucket["tags"]:
            exact[_norm(tag)] = key
    keywords = [(key, kw.lower()) for key in cfg["priority"] for kw in cfg["buckets"][key]["keywords"]]
    scene = {_norm(t) for t in cfg["scene_tags"]}
    rank = {key: i for i, key in enumerate(cfg["priority"])}
    return exact, keywords, scene, rank


def _split(field: Optional[str]) -> List[str]:
    return [_norm(t) for t in (field or "").split("|") if t.strip()]


def _tag_bucket(tag: str) -> str:
    exact, keywords, scene, _ = _tables()
    if tag in scene:
        return ""
    if tag in exact:
        return exact[tag]
    for key, kw in keywords:
        if kw in tag:
            return key
    return ""


def buckets_of(genre_field: Optional[str]) -> List[str]:
    """장르 칸('|'로 나뉜 태그들) → 해당하는 갈래 전부, 우선순위 순서, 중복 없음."""
    rank = _tables()[3]
    found = {_tag_bucket(t) for t in _split(genre_field)} - {""}
    return sorted(found, key=rank.__getitem__)


def bucket_of(genre_field: Optional[str]) -> str:
    """대표 갈래 하나. 장르 태그가 없거나 '인디' 같은 판 표시뿐이면 ''."""
    found = buckets_of(genre_field)
    return found[0] if found else ""


def unknown_tags(genre_field: Optional[str]) -> List[str]:
    """판 표시도 아니고 어느 갈래에도 안 맞는 태그 (규칙 보완용)."""
    scene = _tables()[2]
    return [t for t in _split(genre_field) if t not in scene and not _tag_bucket(t)]


def _kind(path: Path) -> str:
    for prefix, kind in FILE_KINDS.items():
        if path.name.startswith(prefix):
            return kind
    return ""


def _source_of(path: Path, row: dict) -> str:
    if row.get("source"):
        return row["source"]
    return RERUN_SUFFIX.sub("", path.stem).rsplit("_", 1)[-1]


def _row_id(row: dict) -> str:
    for col in ("source_id", "artist_source_id", "release_url", "url"):
        if row.get(col):
            return row[col]
    return f"{row.get('artist_text', '')}|{row.get('title', '')}"


def distribution(raw_dir=RAW_DIR) -> Dict[str, Dict[str, dict]]:
    """{'artist'|'release': {source: {rows, mapped, buckets{}, unknown{}}}}.
    같은 날 다시 돌린 파일(_213846 등)의 같은 행은 한 번만 센다."""
    seen = set()
    stats: Dict[str, Dict[str, dict]] = {}
    for path in sorted(Path(raw_dir).glob("raw_*.csv")):
        kind = _kind(path)
        if not kind:
            continue
        with open(path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if "genre" not in row:
                    break
                source = _source_of(path, row)
                key = (kind, source, _row_id(row))
                if key in seen:
                    continue
                seen.add(key)
                s = stats.setdefault(kind, {}).setdefault(
                    source, {"rows": 0, "mapped": 0, "buckets": Counter(), "unknown": Counter()})
                s["rows"] += 1
                bucket = bucket_of(row["genre"])
                if bucket:
                    s["mapped"] += 1
                    s["buckets"][bucket] += 1
                s["unknown"].update(unknown_tags(row["genre"]))
    for by_source in stats.values():
        for s in by_source.values():
            s["buckets"] = dict(s["buckets"])
            s["unknown"] = dict(s["unknown"])
    return stats


def _pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.0f}%" if whole else "-"


def main(argv: List[str]) -> int:
    raw_dir = Path(argv[1]) if len(argv) > 1 else RAW_DIR
    labels = {k: b["label"] for k, b in load_config()["buckets"].items()}
    stats = distribution(raw_dir)
    if not stats:
        print(f"장르 칸이 있는 파일이 없습니다: {raw_dir}")
        return 1
    for kind, by_source in stats.items():
        total, mapped, buckets = 0, 0, Counter()
        print(f"\n[{'아티스트 프로필' if kind == 'artist' else '발매'}]")
        for source, s in sorted(by_source.items()):
            total += s["rows"]
            mapped += s["mapped"]
            buckets.update(s["buckets"])
            dist = ", ".join(f"{labels[b]} {n}" for b, n in sorted(s["buckets"].items(), key=lambda x: -x[1]))
            print(f"  {source:9} {s['mapped']}/{s['rows']} ({_pct(s['mapped'], s['rows'])})  {dist}")
            if s["unknown"]:
                print(f"            못 맞춘 태그: {s['unknown']}")
        print(f"  합계      {mapped}/{total} ({_pct(mapped, total)})")
        for b, n in buckets.most_common():
            print(f"    {labels[b]:12} {n:3}  {_pct(n, mapped)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
