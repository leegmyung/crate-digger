"""data/raw/ 수집 파일 → 진행판 공개 데이터 docs/data/collect.json

    python3 scripts/build_site_data.py

공개 페이지에는 이름·제목·발매일·형태·소스·링크, 공연은 날짜·시간·공연장 이름·출연 팀·링크,
선정 명단은 프로그램·회차·단계·발표일·팀·링크, 갈래 겹침은 팀 이름·갈래만 내보낸다
(레이블·유통사·소개문·공연장 주소·인스타 계정 등 제외).
검사기를 통과하지 못한 파일은 '수집 현황'에 실패로만 표시하고 내용은 내보내지 않는다.
"""
import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import validate_csv
from normalize import artist_key

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
OUT = ROOT / "docs" / "data" / "collect.json"
RECENT_LIMIT = 60
GIG_LIMIT = 300
SELECTION_LIMIT = 200
CROSS_LIMIT = 100
BRANCH = {"raw_kr_release": "발매", "raw_kr_gig": "공연", "raw_kr_selection": "선정·지원", "raw_press": "큐레이션"}
NAME_PRIORITY = ["선정·지원", "큐레이션", "발매", "공연"]   # 겹침 표에 보일 이름: 공식 명단 표기 우선
KST = timezone(timedelta(hours=9))


def _file_meta(path):
    table = validate_csv.table_for(path)
    rest = path.stem[len(table) + 1:]                      # 2026-11-26_poclanos(_153000)
    day, _, source = rest.partition("_")
    return table, day, source.split("_")[0]


def _read(path):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _venue_name(venue_text):
    """'클럽 빵 (서울 마포구 …)' → '클럽 빵' (주소는 공개하지 않음)"""
    return (venue_text or "").split(" (")[0].strip()


def _add_gig_rows(gigs, rows):
    for r in rows:
        key = (r["source"], r["gig_url"])
        gig = gigs.setdefault(key, {
            "date": r["gig_date"], "time": r.get("gig_time", ""), "venue": _venue_name(r.get("venue_text")),
            "title": r.get("title", ""), "artists": [], "source": r["source"], "url": r["gig_url"],
        })
        if r["artist_text"] not in gig["artists"]:
            gig["artists"].append(r["artist_text"])


def _branch(table, row):
    """공연장·기획 계정의 인스타 라인업 글은 큐레이션이 아니라 공연 갈래로 센다 (이중 가점 방지)."""
    if table == "raw_press":
        if row.get("is_sponsored") == "1":
            return ""
        return "공연" if row.get("pick_label") == "venue_lineup" else "큐레이션"
    return BRANCH.get(table, "")


def _add_cross(cross, table, rows):
    for r in rows:
        branch, key = _branch(table, r), artist_key(r.get("artist_text", ""))
        if branch and key:
            cross.setdefault(key, {}).setdefault(branch, r["artist_text"].strip())


def _cross_summary(cross, limit):
    out = []
    for names in cross.values():
        if len(names) < 2:
            continue
        shown = next(names[b] for b in NAME_PRIORITY if b in names)
        out.append({"artist": shown, "branches": sorted(names)})
    out.sort(key=lambda x: (-len(x["branches"]), x["artist"]))
    return out[:limit]


def _merge_runs(runs):
    """같은 날 다시 돌려 생긴 파일(…_201156.csv)은 (날짜, 표, 소스) 하나로 합친다."""
    merged = {}
    for r in runs:
        key = (r["date"], r["table"], r["source"])
        m = merged.setdefault(key, dict(r, rows=0, file_ok=True))
        m["rows"] += r["rows"]
        m["file_ok"] = m["file_ok"] and r["file_ok"]
    last = {}                                    # (표, 소스) → 직전 실행 행 수 (수집량 급감 감지용)
    for key in sorted(merged):
        run = merged[key]
        run["prev_rows"] = last.get((run["table"], run["source"]))
        last[(run["table"], run["source"])] = run["rows"]
    return sorted(merged.values(), key=lambda x: (x["date"], x["source"]), reverse=True)


def build(raw_dir, recent_limit=RECENT_LIMIT, today=None, gig_limit=GIG_LIMIT):
    """today 를 주면 그날 이후 공연만 '다가오는 공연'에 넣는다."""
    runs, releases, gigs, selections, cross = [], {}, {}, {}, {}
    files = sorted(p for p in Path(raw_dir).glob("raw_*.csv") if validate_csv.table_for(p))
    for path in files:
        table, day, source = _file_meta(path)
        ok = not [i for i in validate_csv.validate_file(path) if i.level == "error"]
        rows = _read(path)
        runs.append({"date": day, "source": source, "table": table, "rows": len(rows), "file_ok": ok})
        if not ok:
            continue
        _add_cross(cross, table, rows)
        if table == "raw_kr_gig":
            _add_gig_rows(gigs, rows)
        elif table == "raw_kr_selection":
            for r in rows:
                selections[(r["program"], r["round"], r["stage"], r["artist_text"])] = {
                    "program": r["program"], "round": r["round"], "stage": r["stage"],
                    "announced_at": r["announced_at"], "artist": r["artist_text"], "url": r["url"]}
        elif table == "raw_kr_release":
            for r in rows:
                key = (r["source"], r["release_url"], r["artist_text"])
                releases[key] = {
                    "released_at": r["released_at"], "artist": r["artist_text"], "title": r["title"],
                    "type": r.get("release_type", ""), "source": r["source"], "url": r["release_url"],
                }
    recent = sorted(releases.values(), key=lambda x: x["released_at"], reverse=True)[:recent_limit]
    upcoming = sorted((g for g in gigs.values() if not today or g["date"] >= today),
                      key=lambda g: (g["date"], g["time"], g["venue"]))[:gig_limit]
    sel = sorted(selections.values(), key=lambda x: (x["round"], x["announced_at"]), reverse=True)[:SELECTION_LIMIT]
    return {"generated": datetime.now(KST).replace(microsecond=0).isoformat(), "runs": _merge_runs(runs),
            "recent_releases": recent, "upcoming_gigs": upcoming, "selections": sel,
            "cross_branch": _cross_summary(cross, CROSS_LIMIT)}


def main():
    data = build(RAW_DIR, today=f"{datetime.now(KST):%Y-%m-%d}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    bad = [r for r in data["runs"] if not r["file_ok"]]
    print(f"✅ 수집 기록 {len(data['runs'])}개, 최근 발매 {len(data['recent_releases'])}건, "
          f"다가오는 공연 {len(data['upcoming_gigs'])}건, 선정 명단 {len(data['selections'])}건, "
          f"갈래 겹침 {len(data['cross_branch'])}팀 → {OUT.relative_to(ROOT)}"
          + (f" (검사 실패 파일 {len(bad)}개는 내용 제외)" if bad else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
