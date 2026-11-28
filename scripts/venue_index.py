"""작은 공연장 색인 → docs/lab/data/venue_index.json (이름 → 도시·크기만).

    .venv/bin/python scripts/venue_index.py [--data-dir 폴더]   (scripts/build_app_extras.sh — venue_profiles 다음)

앱 팀 '공연' 탭(docs/app/db_team_extras.js loadVenueMeta)은 공연장마다 도시·크기만 쓰는데, 예전엔 venue_profiles.json
(약 600KB, 월별 공연·전후 흐름·좌표까지)을 통째로 받았다. 같은 두 칸만 뽑아 약 18KB 로 줄인다 (첫 진입 속도 점검 2026-11-28).
venue_profiles.json 이 없으면 아무것도 쓰지 않고 1 을 돌려준다(앱은 예전처럼 프로필을 읽음).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab_sql  # noqa: E402

VALID_TIERS = {"S", "M", "L", "XL"}


def build(profiles: dict) -> dict:
    """venue_profiles.json 내용 → {as_of, venues: {이름: {city?, tier?}}}. 도시·크기 둘 다 없으면 뺀다."""
    venues = profiles.get("venues") if isinstance(profiles, dict) else None
    out = {}
    if isinstance(venues, dict):
        for name, info in venues.items():
            if not isinstance(info, dict):
                continue
            entry = {}
            city = str(info.get("city") or "").strip()
            tier = str(info.get("tier") or "").strip().upper()
            if city:
                entry["city"] = city
            if tier in VALID_TIERS:
                entry["tier"] = tier
            if entry:
                out[str(name)] = entry
    as_of = profiles.get("as_of", "") if isinstance(profiles, dict) else ""
    return {"as_of": str(as_of or ""), "venues": out}


def write_atomic(path: Path, data: dict) -> None:
    """반쯤 쓴 파일을 앱이 읽지 않게 임시 파일에 쓰고 바꿔 끼운다."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".venue_index.", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="작은 공연장 색인(venue_index.json) 만들기")
    ap.add_argument("--data-dir", type=Path, default=lab_sql.DATA_DIR)
    args = ap.parse_args(argv)
    src = args.data_dir / "venue_profiles.json"
    if not src.is_file():
        print(f"❌ {src} 가 없어요 — venue_profiles.py 를 먼저 돌리세요", file=sys.stderr)
        return 1
    try:
        data = build(json.loads(src.read_text(encoding="utf-8")))
    except ValueError as err:
        print(f"❌ venue_profiles.json 을 읽지 못했어요: {err}", file=sys.stderr)
        return 1
    out = args.data_dir / "venue_index.json"
    write_atomic(out, data)
    print(f"✅ 공연장 {len(data['venues'])}곳 → {out} ({out.stat().st_size // 1024}KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
