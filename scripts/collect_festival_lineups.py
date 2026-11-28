"""국내 큰 페스티벌 라인업(config/festival_lineups.json) → 공연 원본 data/raw/raw_kr_gig_<날짜>_festival.csv

    python3 scripts/collect_festival_lineups.py            # 새 행만 씀
    python3 scripts/collect_festival_lineups.py --dry-run  # 몇 행인지만

왜: 펜타포트 본무대·그랜드민트·뷰민라·부산록페 전체 라인업·DMZ 피스트레인은 인디스트릿·인디고에 거의 안 올라온다
(2026-11-28 세어 보니 펜타포트 2023~2025 본무대 국내 팀 0, 민트페이퍼 두 페스티벌 0). 공식 포스터·타임테이블을 옮긴
라인업 표를 공연 원본 행(공연 1건 × 팀 1팀)으로 바꾼다 — scripts/collect_regional_lineups.py 와 같은 방식.

규칙
- korean=false(해외 팀·확인 못 한 팀)는 쓰지 않는다 — 해외 팀이 새 팀으로 생겨 신인 후보에 끼지 않게(정답·점수 영향 없음).
- 같은 날 같은 팀(이름 키)이 이미 다른 공연 원본에 있으면 쓰지 않는다 — 같은 무대가 신호로 두 번 잡히지 않게.
- source = 'festival'(csv_schema.GIG_SOURCES), collector = 'manual', gig_url = 근거 문서 주소 + '#날짜'.
  큰 페스티벌 본무대는 '정답 성격'(크고 경쟁 센 무대)이라 후보 신호로 쓰지 않는다 — config/source_roles.json '공연:festival' = excluded
  (알림·사건 별점·점수 특징·같은 무대·공연장 사다리는 역할로 거르고, 공연장 프로필·예전 대시보드·페스티벌 '먼저 본 팀'은 따로 막음).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import normalize as nz  # noqa: E402
from csv_schema import TABLES  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "festival_lineups.json"
RAW_DIR = ROOT / "data" / "raw"
KST = timezone(timedelta(hours=9))
COLUMNS = [f.name for f in TABLES["raw_kr_gig"]["fields"]]
KEY = TABLES["raw_kr_gig"]["key"]
SOURCE = "festival"            # 큰 페스티벌 본무대 = 정답 성격 → 점수·검증에 안 씀(source_roles '공연:festival' excluded)
FILE_TAG = "festival"


XREF = RAW_DIR / "state" / "artist_xref.json"
_ALIAS: Dict[str, str] = {}


def _alias_map() -> Dict[str, str]:
    """이름 키 → 대표 팀 키 (artist_xref — 'NELL'·'넬' 같은 다른 표기를 같은 팀으로). 파일이 없으면 빈 표."""
    if not _ALIAS and XREF.exists():
        for e in json.loads(XREF.read_text(encoding="utf-8")):
            for k in [*e.get("keys", []), e["artist_key"]]:
                _ALIAS.setdefault(k, e["artist_key"])
    return _ALIAS


def name_key(name: str) -> str:
    k = nz.artist_key(name)
    return _alias_map().get(k, k)


def load_config(path: Path = CONFIG) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def rows_from_config(cfg: dict, collected_at: str, skip: Optional[Set[Tuple[str, str]]] = None) -> List[Dict[str, str]]:
    """라인업 표 → 공연 원본 행 (korean 팀만, skip 의 (날짜, 이름 키) 는 뺌)."""
    skip = skip or set()
    rows = []
    for fest, f in cfg["festivals"].items():
        for year, e in f["editions"].items():
            acts = [a for a in e["acts"] if a.get("korean") and not a.get("unlinked")]   # unlinked = 동명 위험, 팀에 안 붙임
            by_day: Dict[str, List[dict]] = {}
            for a in acts:
                by_day.setdefault(a["day"], []).append(a)
            for day, day_acts in sorted(by_day.items()):
                title = f"{year} {f['label']} ({day[5:].replace('-', '/')})"
                for i, a in enumerate(day_acts, 1):
                    if (day, name_key(a["name"])) in skip:
                        continue
                    row = {c: "" for c in COLUMNS}
                    row.update({"collected_at": collected_at, "source": SOURCE, "collector": "manual",
                                "source_id": f"festival:{fest}:{year}", "gig_date": day, "title": title,
                                "venue_text": e.get("venue_text") or f["venue_text"], "artist_text": a["name"],
                                "gig_url": f"{e['source_url'].split('#')[0]}#{day}",
                                "lineup_size": str(len(day_acts))})
                    rows.append(row)
    return rows


def existing_gig_keys(raw_dir: Path = RAW_DIR) -> Tuple[Set[Tuple[str, str]], Set[tuple]]:
    """이미 있는 모든 공연 원본의 (날짜, 이름 키)와, 이 수집기가 이미 쓴 행 키(source, gig_url, artist_text)."""
    day_names, mine = set(), set()
    for path in sorted(raw_dir.glob("raw_kr_gig_*.csv")):
        with open(path, encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                if f"_{FILE_TAG}" in path.name:
                    mine.add(tuple(r.get(c, "") for c in KEY))
                # 같은 날·같은 팀이 이미 어느 원본에든(이 수집기가 예전에 쓴 것 포함) 있으면 다시 쓰지 않음 — 근거 주소가 바뀌어도
                day_names.add(((r.get("gig_date") or "")[:10], name_key(r.get("artist_text") or "")))
    return day_names, mine


def write_csv(rows: Sequence[Dict[str, str]], out_dir: Path, day: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"raw_kr_gig_{day}_{FILE_TAG}.csv"
    if path.exists():  # 원본은 고치지 않는다
        path = out_dir / f"raw_kr_gig_{day}_{FILE_TAG}_{datetime.now(KST):%H%M%S}.csv"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="국내 큰 페스티벌 라인업 → 공연 원본")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    now = datetime.now(KST)
    day_names, mine = existing_gig_keys()
    rows = rows_from_config(load_config(), now.isoformat(timespec="seconds"), skip=day_names)
    fresh = [r for r in rows if tuple(r[c] for c in KEY) not in mine]
    print(f"페스티벌 라인업: {len(rows)}행 (다른 원본과 같은 날·같은 팀은 뺌) 중 새 행 {len(fresh)}행")
    if fresh and not args.dry_run:
        print(f"  → {write_csv(fresh, RAW_DIR, now.date().isoformat())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
