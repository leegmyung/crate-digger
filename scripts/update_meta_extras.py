"""앱 보조 데이터 파일 목록을 docs/lab/data/meta.json 에 적는다 — 앱이 없는 파일을 받으려다 404 를 내지 않게.

    .venv/bin/python scripts/update_meta_extras.py [--data-dir 폴더]   (scripts/build_app_extras.sh 맨 끝 단계)

쓰는 칸 (다른 칸·순서는 그대로, generated_at 은 건드리지 않음 — 앱 캐시 무효화 키라서):
  extras        = 행이 있는 보조 파일의 이름(확장자 뺀 것) 배열 — 앱 docs/app/db.js labExtraListed 가 읽는 모양
                  (extras.includes(name) || extras.includes(`${name}.csv`))
  extras_rows   = {파일 이름: CSV 는 데이터 행 수, JSON 은 true} — 있는 파일 모두(0행 포함), 깨진 JSON·없는 파일은 뺌
  extras_updated_at = 이 단계를 돌린 시각 (보조 파일만 다시 만든 날을 알 수 있게 — generated_at 대신)
meta.json 은 export_lab_data.py 가 매번 새로 쓰므로, 매일 실행에서 이 단계는 build_app_extras.sh 끝에 다시 돈다.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Union

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab_sql  # noqa: E402

EXTRAS = ("team_cities.csv", "venue_tiers.csv", "venue_profiles.json", "city_profiles.json",
          "festival_profiles.json", "lineup_roles.csv", "event_stars.csv", "venue_ladder.json")

Count = Union[int, bool]


def _csv_rows(path: Path) -> int:
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        next(reader, None)                      # 머리말
        return sum(1 for row in reader if any(cell.strip() for cell in row))


def scan(data_dir: Path, names: Sequence[str] = EXTRAS) -> Dict[str, Count]:
    """있는 보조 파일 → {이름: 행 수 또는 true}. 없는 파일·깨진 JSON·읽기 오류는 뺀다(앱이 받지 않게)."""
    out: Dict[str, Count] = {}
    for name in names:
        path = data_dir / name
        if not path.is_file():
            continue
        try:
            if name.endswith(".csv"):
                out[name] = _csv_rows(path)
            else:
                json.loads(path.read_text(encoding="utf-8"))
                out[name] = True
        except (OSError, ValueError, csv.Error) as err:
            print(f"⚠️ {name}: 읽기 실패 — 목록에서 뺌 ({err})", file=sys.stderr)
    return out


def app_list(counts: Dict[str, Count]) -> List[str]:
    """앱이 받을 파일 이름(확장자 뺀 것): CSV 는 1행 이상, JSON 은 true."""
    return sorted(Path(n).stem for n, c in counts.items() if c is True or (not isinstance(c, bool) and c > 0))


def update(meta_path: Path, counts: Dict[str, Count], now: str) -> dict:
    """meta.json 의 extras·extras_rows·extras_updated_at 만 바꿔 다시 쓴다(원자적으로 — 앱이 반쯤 쓴 파일을 읽지 않게)."""
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    new = {k: v for k, v in meta.items() if k not in ("extras", "extras_rows", "extras_updated_at")}
    new.update({"extras": app_list(counts), "extras_rows": dict(sorted(counts.items())), "extras_updated_at": now})
    fd, tmp = tempfile.mkstemp(dir=meta_path.parent, prefix=".meta.", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(new, ensure_ascii=False, indent=2))   # export_lab_data 와 같은 모양(들여쓰기 2, 끝 줄바꿈 없음)
        os.replace(tmp, meta_path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return new


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="meta.json 에 앱 보조 데이터 파일 목록 적기")
    ap.add_argument("--data-dir", type=Path, default=lab_sql.DATA_DIR)
    args = ap.parse_args(argv)
    meta_path = args.data_dir / "meta.json"
    if not meta_path.is_file():
        print(f"❌ {meta_path} 가 없어요 — export_lab_data.py 를 먼저 돌리세요", file=sys.stderr)
        return 1
    counts = scan(args.data_dir)
    try:
        new = update(meta_path, counts, datetime.now().astimezone().isoformat(timespec="seconds"))
    except ValueError as err:
        print(f"❌ meta.json 을 읽지 못했어요: {err}", file=sys.stderr)
        return 1
    print(f"✅ extras {len(new['extras'])}개 ({', '.join(new['extras']) or '없음'}) → {meta_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
