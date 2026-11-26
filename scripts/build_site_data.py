"""data/raw/ 수집 파일 → 진행판 공개 데이터 docs/data/collect.json

    python3 scripts/build_site_data.py

공개 페이지에는 이름·제목·발매일·형태·소스·링크만 내보낸다 (레이블·소개문 등 제외).
검사기를 통과하지 못한 파일은 '수집 현황'에 실패로만 표시하고 내용은 내보내지 않는다.
"""
import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import validate_csv

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
OUT = ROOT / "docs" / "data" / "collect.json"
RECENT_LIMIT = 60
KST = timezone(timedelta(hours=9))


def _file_meta(path):
    table = validate_csv.table_for(path)
    rest = path.stem[len(table) + 1:]                      # 2026-11-26_poclanos(_153000)
    day, _, source = rest.partition("_")
    return table, day, source.split("_")[0]


def _read(path):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def build(raw_dir, recent_limit=RECENT_LIMIT):
    runs, releases = [], {}
    files = sorted(p for p in Path(raw_dir).glob("raw_*.csv") if validate_csv.table_for(p))
    for path in files:
        table, day, source = _file_meta(path)
        ok = not [i for i in validate_csv.validate_file(path) if i.level == "error"]
        rows = _read(path)
        runs.append({"date": day, "source": source, "table": table, "rows": len(rows), "file_ok": ok})
        if not ok or table != "raw_kr_release":
            continue
        for r in rows:
            key = (r["source"], r["release_url"], r["artist_text"])
            releases[key] = {
                "released_at": r["released_at"], "artist": r["artist_text"], "title": r["title"],
                "type": r.get("release_type", ""), "source": r["source"], "url": r["release_url"],
            }
    runs.sort(key=lambda x: (x["date"], x["source"]), reverse=True)
    recent = sorted(releases.values(), key=lambda x: x["released_at"], reverse=True)[:recent_limit]
    return {"generated": datetime.now(KST).replace(microsecond=0).isoformat(), "runs": runs, "recent_releases": recent}


def main():
    data = build(RAW_DIR)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    bad = [r for r in data["runs"] if not r["file_ok"]]
    print(f"✅ 수집 기록 {len(data['runs'])}개, 최근 발매 {len(data['recent_releases'])}건 → {OUT.relative_to(ROOT)}"
          + (f" (검사 실패 파일 {len(bad)}개는 내용 제외)" if bad else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
