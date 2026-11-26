"""Spotify Voyager로 Bandcamp 아티스트 벡터 검색 인덱스를 만들고, 취향 벡터로 후보를 찾습니다.

SQL의 reco_sim 은 모든 사용자 × 모든 아티스트를 내적합니다 (정확하지만 카탈로그가 커지면 느림).
Voyager는 근사 최근접 이웃(HNSW) 인덱스로 상위 K개만 빠르게 찾습니다. 수십만~수백만 앨범 규모에서
'후보 뽑기 → SQL로 정밀 점수' 2단계 구조의 1단계로 씁니다.

    pip install voyager
    python3 scripts/build_reco.py          # 먼저 벡터 테이블 생성
    python3 scripts/voyager_index.py [bandcamp.db] [--k 50]

결과
  data/bc_artist.voy      Voyager 인덱스 파일
  reco_ann (DB 테이블)    user_id, artist_id, ann_rank, ann_sim  — 근사 검색 후보
  bc_similar (DB 테이블)  artist_id, similar_artist_id, sim       — 'Bandcamp에서 비슷한 아티스트'
  콘솔: SQL 정확 결과와 비교한 recall@K
"""
import argparse
import sqlite3
import time
from pathlib import Path

import numpy as np
from voyager import Index, Space

ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("db", nargs="?", default=str(ROOT / "bandcamp.db"))
    ap.add_argument("--k", type=int, default=50, help="사용자별 후보 수")
    ap.add_argument("--similar", type=int, default=5, help="아티스트별 비슷한 아티스트 수")
    args = ap.parse_args()

    con = sqlite3.connect(args.db)
    # 공통 태그 어휘 = Bandcamp 태그 ∪ 사용자 취향 태그 (fam: 가상 태그 포함)
    vocab = [t for (t,) in con.execute("SELECT tag FROM bc_artist_vec UNION SELECT tag FROM user_taste ORDER BY 1")]
    col = {t: i for i, t in enumerate(vocab)}

    def dense(rows):
        out = {}
        for key, tag, w in rows:
            out.setdefault(key, np.zeros(len(vocab), dtype=np.float32))[col[tag]] = w
        return out

    artists = dense(con.execute("SELECT artist_id, tag, w FROM bc_artist_vec"))
    users = dense(con.execute("SELECT user_id, tag, w FROM user_taste"))
    ids = np.array(sorted(artists), dtype=np.int64)
    mat = np.stack([artists[i] for i in ids])

    t0 = time.perf_counter()
    index = Index(Space.Cosine, num_dimensions=len(vocab), M=16, ef_construction=200)
    index.add_items(mat, ids=ids)
    index.ef = max(100, args.k * 2)
    build_ms = (time.perf_counter() - t0) * 1000
    index.save(str(ROOT / "data/bc_artist.voy"))
    print(f"Voyager 인덱스: 아티스트 {len(ids):,}팀 × {len(vocab)}차원, 생성 {build_ms:.0f}ms → data/bc_artist.voy")

    # 1) 사용자 취향 → 후보 아티스트
    con.executescript("""
        DROP TABLE IF EXISTS reco_ann;
        CREATE TABLE reco_ann (user_id TEXT, artist_id INTEGER, ann_rank INTEGER, ann_sim REAL);
        DROP TABLE IF EXISTS bc_similar;
        CREATE TABLE bc_similar (artist_id INTEGER, similar_artist_id INTEGER, sim REAL);""")
    k = min(args.k, len(ids))
    for uid, vec in users.items():
        t0 = time.perf_counter()
        neigh, dist = index.query(vec, k=k)
        q_ms = (time.perf_counter() - t0) * 1000
        con.executemany("INSERT INTO reco_ann VALUES (?,?,?,?)",
                        [(uid, int(a), r + 1, float(1 - d)) for r, (a, d) in enumerate(zip(neigh, dist))])
        exact = {a for (a,) in con.execute(
            "SELECT artist_id FROM reco_sim WHERE user_id = ? ORDER BY sim DESC LIMIT ?", (uid, k))}
        final = {a for (a,) in con.execute(
            "SELECT a.artist_id FROM reco_final f JOIN dim_artist a ON a.artist_name = f.artist_name WHERE f.user_id = ?", (uid,))}
        got = {int(a) for a in neigh}
        print(f"  {uid:<10} 검색 {q_ms:5.2f}ms · SQL 정확 결과 대비 recall@{k} {len(got & exact) / len(exact):.0%}"
              f" · 최종 추천 {len(final)}팀 중 {len(got & final)}팀이 후보에 포함")

    # 2) 아티스트별 비슷한 Bandcamp 아티스트 (앨범 페이지 '이 아티스트를 좋아하면' 용)
    neigh, dist = index.query(mat, k=args.similar + 1)
    rows = [(int(a), int(n), float(1 - d)) for a, ns, ds in zip(ids, neigh, dist)
            for n, d in zip(ns, ds) if n != a][: len(ids) * args.similar]
    con.executemany("INSERT INTO bc_similar VALUES (?,?,?)", rows)
    con.commit()
    print(f"bc_similar: {len(rows):,}행 (아티스트당 {args.similar}팀)")


if __name__ == "__main__":
    main()
