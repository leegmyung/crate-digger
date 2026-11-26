"""내 좋아요 CSV를 넣으면 Bandcamp 인디 뮤지션 큐레이션을 만들어 줍니다.

    python3 scripts/curate.py ~/Downloads/spotify_liked.csv --user me
    python3 scripts/curate.py spotify.csv apple.csv ytmusic.csv --user me   # 여러 플랫폼 합치기

순서
  1) CSV를 data/likes/<user>.csv 로 복사 (여러 개면 합침)
  2) LASTFM_API_KEY 가 있으면 Last.fm 태그 수집 (fetch_lastfm_tags.py), 없으면 기존 태그 파일 사용
  3) 추천 계산 (build_reco.py)
  4) 터미널에 큐레이션 출력 + out/curation_<user>.md 저장
"""
import argparse
import csv
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
FAM = {"rock": "록", "pop": "팝", "electronic": "일렉트로닉", "ambient": "앰비언트", "hip-hop": "힙합",
       "r&b/soul": "R&B·소울", "jazz": "재즈", "punk": "펑크", "metal": "메탈", "folk": "포크",
       "experimental": "실험음악", "soundtrack": "사운드트랙"}


def merge_csvs(paths, dest):
    header, rows = None, []
    for p in paths:
        with open(p, newline="", encoding="utf-8-sig") as f:
            r = csv.reader(f)
            h = next(r, None)
            if h is None:
                continue
            if header is None:
                header = h
            idx = [h.index(c) if c in h else None for c in header]
            rows += [[row[i] if i is not None and i < len(row) else "" for i in idx] for row in r]
    if header is None:
        sys.exit("CSV가 비어 있습니다.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    return len(rows)


def run(script, *args):
    res = subprocess.run([PY, str(ROOT / "scripts" / script), *args], cwd=ROOT)
    if res.returncode:
        sys.exit(f"{script} 실행 실패 (종료 코드 {res.returncode})")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", nargs="+", help="TuneMyMusic에서 내보낸 좋아요 CSV")
    ap.add_argument("--user", default="me", help="사용자 이름 (파일명으로 씀)")
    ap.add_argument("--db", default=str(ROOT / "bandcamp.db"))
    args = ap.parse_args()

    uid = "".join(ch for ch in args.user if ch.isalnum() or ch in "_-") or "me"
    n = merge_csvs(args.csv, ROOT / f"data/likes/{uid}.csv")
    print(f"① 좋아요 {n}곡 → data/likes/{uid}.csv")

    if os.environ.get("LASTFM_API_KEY"):
        print("② Last.fm 태그 수집")
        run("fetch_lastfm_tags.py")
    else:
        print("② LASTFM_API_KEY가 없어 기존 data/ext_artist_tags.csv를 사용합니다 (모르는 아티스트는 태그 없음)")

    print("③ 추천 계산")
    run("build_reco.py", args.db)

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    u = con.execute("SELECT * FROM user_likes WHERE user_id = ? LIMIT 1", (uid,)).fetchone()
    if not u:
        sys.exit("좋아요를 읽지 못했습니다. CSV에 'Track name', 'Artist name' 컬럼이 있는지 확인하세요.")
    seg = con.execute("SELECT family, share_pct FROM user_segment WHERE user_id = ? ORDER BY fam_rank", (uid,)).fetchall()
    tagged = con.execute("""SELECT COUNT(*) AS n, SUM(EXISTS(SELECT 1 FROM ext_artist_tags e WHERE e.artist_key = ua.artist_key)) AS t
                            FROM user_artist ua WHERE user_id = ?""", (uid,)).fetchone()
    recs = con.execute("SELECT * FROM reco_final WHERE user_id = ? ORDER BY rank", (uid,)).fetchall()

    lines = [f"# {uid}님을 위한 Bandcamp 큐레이션", ""]
    lines.append(f"좋아요 아티스트 {tagged['n']}팀 중 {tagged['t'] or 0}팀의 태그를 찾았습니다.")
    if seg:
        lines.append("취향 구성: " + " · ".join(f"{FAM.get(s['family'], s['family'])} {s['share_pct']:.0f}%" for s in seg if s["share_pct"] >= 5))
    lines.append("")
    if not recs:
        lines.append("추천을 만들 수 없었습니다. 태그를 찾은 아티스트가 너무 적습니다 (Last.fm 키를 설정하세요).")
    for r in recs:
        why = []
        if r["because_artist"]:
            why.append(f"좋아요한 {r['because_artist']}와 비슷")
        if r["because_tags"]:
            why.append(r["because_tags"])
        album = f" — 『{r['album_title']}』 ${r['album_price_usd']:.2f}" if r["album_title"] else ""
        lines.append(f"{r['rank']:>2}. {r['artist_name']} [{FAM.get(r['family'], r['family'])}]{album}")
        lines.append(f"    {' · '.join(why)}  (점수 {r['score']:.1f})")
    text = "\n".join(lines)
    out = ROOT / f"out/curation_{uid}.md"
    out.write_text(text + "\n", encoding="utf-8")
    print("\n" + text + f"\n\n④ 저장: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
