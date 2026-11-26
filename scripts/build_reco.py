"""좋아요 CSV + 외부 태그 + 팬 컬렉션 → 추천 계산 → out/reco/*.json

    python3 scripts/build_reco.py [bandcamp.db]

입력
  data/likes/<user_id>.csv     TuneMyMusic 파일 내보내기 (파일명 = user_id)
  data/ext_artist_tags.csv     artist_name, tag, weight
  data/fan_collections.csv     fan_id, item_url
플랫폼은 CSV의 'Playlist name'으로 추정하고, 모르면 파일명 뒤에 붙은 이름을 씁니다.
"""
import csv
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SQL = ROOT / "sql/reco"

# TuneMyMusic 컬럼명이 플랫폼/버전마다 조금씩 달라도 받아들이도록 별칭 처리
ALIASES = {
    "track_name": ["track name", "track", "title", "song", "name"],
    "artist_name": ["artist name", "artist", "artists"],
    "album": ["album", "album name"],
    "playlist_name": ["playlist name", "playlist"],
    "item_type": ["type"],
    "isrc": ["isrc"],
}
PLAYLIST_PLATFORM = {"liked songs": "Spotify", "favorite songs": "Apple Music", "liked music": "YouTube Music"}


def artist_key(name):
    """load_likes.sql 의 매칭 키와 같은 규칙."""
    n = name.strip()
    if n.lower().startswith("the "):
        n = n[4:]
    n = n.lower()
    for ch in [" ", ".", "-", "'", ","]:
        n = n.replace(ch, "")
    return n


def pick(row, field):
    low = {k.strip().lower(): v for k, v in row.items() if k}
    for a in ALIASES[field]:
        if a in low:
            return low[a]
    return None


def main(db_path):
    con = sqlite3.connect(db_path)
    con.executescript((SQL / "schema_reco.sql").read_text(encoding="utf-8"))

    # 1) 좋아요 CSV
    for f in sorted((ROOT / "data/likes").glob("*.csv")):
        uid = f.stem
        with open(f, newline="", encoding="utf-8-sig") as fh:
            rows = list(csv.DictReader(fh))
        for r in rows:
            pl = (pick(r, "playlist_name") or "").strip()
            platform = PLAYLIST_PLATFORM.get(pl.lower(), re.sub(r"^u_", "", uid))
            con.execute("INSERT INTO raw_tmm_export VALUES (?,?,?,?,?,?,?,?)",
                        (uid, platform, pick(r, "track_name"), pick(r, "artist_name"), pick(r, "album"),
                         pl, pick(r, "item_type"), pick(r, "isrc")))

    # 2) 외부 태그
    with open(ROOT / "data/ext_artist_tags.csv", newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            con.execute("INSERT OR REPLACE INTO ext_artist_tags VALUES (?,?,?,?)",
                        (artist_key(r["artist_name"]), r["artist_name"], r["tag"].lower(), float(r["weight"])))

    # 3) 팬 컬렉션
    with open(ROOT / "data/fan_collections.csv", newline="", encoding="utf-8") as fh:
        con.executemany("INSERT OR IGNORE INTO bc_fan_collection VALUES (?,?)",
                        [(r["fan_id"], r["item_url"]) for r in csv.DictReader(fh)])

    # 4) 앨범 상세 (있으면)
    details = ROOT / "data/album_details.csv"
    if details.exists():
        with open(details, newline="", encoding="utf-8") as fh:
            con.executemany("INSERT OR REPLACE INTO bc_album_detail VALUES (?,?,?,?,?,?,?,?,?)",
                            [(r["url"], r["art_id"] or None, r["art_url"] or None, r["release_date"] or None,
                              int(r["track_count"]) if r["track_count"] else None,
                              int(r["duration_sec"]) if r["duration_sec"] else None,
                              r["label"] or None, r["location"] or None, r["about"] or None)
                             for r in csv.DictReader(fh)])

    con.executescript((SQL / "load_likes.sql").read_text(encoding="utf-8"))
    pipeline = (SQL / "reco.sql").read_text(encoding="utf-8")
    con.executescript(pipeline)
    con.commit()

    for t in ["raw_tmm_export", "user_likes", "ext_artist_tags", "bc_fan_collection",
              "user_taste", "bc_artist_vec", "reco_score", "reco_final"]:
        print(f"{t:18s} {con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]:>8,}")

    out = ROOT / "out/reco"
    out.mkdir(parents=True, exist_ok=True)
    con.row_factory = sqlite3.Row
    for q in sorted((SQL / "queries").glob("*.sql")):
        sql = q.read_text(encoding="utf-8")
        rows = [dict(r) for r in con.execute(sql)]
        meta = [
            {"label": q.name, "value": sql, "type": "code", "lang": "sql"},
            {"label": "reco.sql (점수 계산 파이프라인)", "value": pipeline, "type": "code", "lang": "sql"},
            {"label": "Input", "value": "data/likes/*.csv (TuneMyMusic 형식 샘플), data/ext_artist_tags.csv, "
                                        "data/fan_collections.csv, bandcamp.db (가상 판매 샘플)"},
        ]
        (out / (q.stem + ".json")).write_text(json.dumps({"rows": rows, "meta": meta}, ensure_ascii=False, indent=1),
                                              encoding="utf-8")
        print(f"{q.name:24s} {len(rows):>4} rows")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "bandcamp.db"))
