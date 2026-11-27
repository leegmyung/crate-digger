"""장르별 편향 점검 → docs/genre_bias.md

점수 v2(lab_sql.DEFAULTS)가 특정 장르를 체계적으로 올리거나 내리는지 본다.
- 기준일 6개(score_tune.CUTOFFS)·같은 후보군·같은 지표(등급 가중 AUC)로, 장르(teams.primary_genre, 비면 '미분류')별
  후보 수·정답 수·기준율·장르 안 AUC(정답 5팀 미만은 '표본 부족')·상위 100 안 비율 vs 후보군 비율(쏠림 지수).
- 지금 날짜 후보 상위 100의 장르 구성, 장르별 출처 구성, 장르 안 순위.
- 장르별 출처 성적표: 멜론·발매 장르 태그가 있는 팀만(보완 규칙으로 붙은 장르는 빼고), 출처마다 수상 팀을
  정답 전에 잡은 수·가장 먼저 잡은 수·적중률, 힙합·R&B 수상 팀이 정답 전에 나온 출처 (PostgreSQL 이 있으면 원본 태그로).
바꾸지 않고 제안만 한다.

실행: .venv/bin/python scripts/genre_bias.py   → docs/genre_bias.md
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab_sql  # noqa: E402
import score_model  # noqa: E402
import score_tune as st  # noqa: E402

OUT = lab_sql.ROOT / "docs" / "genre_bias.md"
UNCLASSIFIED = "미분류"
TOP_N = 100
MIN_POS = 5              # 장르 안 AUC를 믿으려면 정답이 이만큼은 있어야
CURRENT_LIMIT = 100000   # 지금 후보 전체
SHOW_PER_GENRE = 3       # 장르 안 순위 예시 팀 수
# 사람 확인이 필요해 보이는 팀 (2026-11-27 생성 때 발견) — 지금 후보에 있으면 해석에 예로 적는다
SUSPECT_FAMOUS = frozenset({"사이먼도미닉"})      # 프로필이 없어 유명 팀 제외가 안 된 기성 래퍼로 보임
SUSPECT_GENRE = frozenset({"추다혜차지스"})        # 리드머 소개만으로 힙합이 붙은 것으로 보임
FOCUS_GENRES = ("힙합", "R&B·소울")               # 수상 팀 목록까지 자세히 볼 장르
# 생성 시점(2026-11-27) 힙합·R&B 태그 수상 팀 중 대형 기획사 아이돌 — 있으면 해석에 예로 적는다
IDOL_EXAMPLES = frozenset({"투어스", "올데이프로젝트", "키스오브라이프"})
SCORECARD_MIN_WINNERS = 5                         # 장르별 출처 성적표에 올릴 최소 수상 팀 수
SCORECARD_MIN_TEAMS = 10                          # 적중률을 적을 최소 후보 수(기준일 합산)


def genre_label(value: Optional[str]) -> str:
    v = (value or "").strip()
    return v or UNCLASSIFIED


def analysis_genre(value: Optional[str], confidence: Optional[str]) -> str:
    """비교·분석용 장르: 추정(inferred) 장르는 '미분류'로 — profile·press 장르만 쓴다 (2026-11-27 결정, docs/genre_fill.md)."""
    return UNCLASSIFIED if (confidence or "") == "inferred" else genre_label(value)


def bias_index(top_share: float, pool_share: float) -> Optional[float]:
    """쏠림 지수 = 상위 N 안 비율 ÷ 후보군 비율. 1이면 고르게, 1보다 크면 위로 쏠림, 작으면 아래로."""
    return top_share / pool_share if pool_share else None


def top_indices(scores: Sequence[float], keys: Sequence[str], n: int,
                last_seen: Optional[Sequence] = None) -> List[int]:
    """점수 상위 n개 위치. 순서는 앱과 같다(score_tune.app_order: 반올림 점수 → 마지막 신호 최근 순 → md5)."""
    return sorted(st.app_order(scores, keys, last_seen)[:n])


def _wauc(rows: Sequence[dict]) -> Optional[float]:
    return st.app_auc([float(r["score"]) for r in rows], [float(r.get("hit_weight") or 0) for r in rows],
                      [r["team_key"] for r in rows], [r.get("last_seen") for r in rows])


def _tops(by_cutoff: Dict[str, List[dict]], top_n: int) -> List[dict]:
    out = []
    for rows in by_cutoff.values():
        idx = top_indices([float(r["score"]) for r in rows], [r["team_key"] for r in rows], top_n,
                          [r.get("last_seen") for r in rows])
        out.extend(rows[i] for i in idx)
    return out


def genre_table(by_cutoff: Dict[str, List[dict]], top_n: int = TOP_N, min_pos: int = MIN_POS) -> List[dict]:
    """기준일을 합쳐 장르별 한 줄. AUC는 장르 안에서(기준일 합산) — 정답 min_pos 미만이면 None(표본 부족)."""
    rows = [r for rs in by_cutoff.values() for r in rs]
    tops = _tops(by_cutoff, top_n)
    total, total_top = len(rows), len(tops)
    total_pos = sum(int(r["is_hit"]) for r in rows)
    out = []
    for g in sorted({r["genre"] for r in rows}):
        gr = [r for r in rows if r["genre"] == g]
        gt = [r for r in tops if r["genre"] == g]
        pos = sum(int(r["is_hit"]) for r in gr)
        pool_share = len(gr) / total
        top_share = len(gt) / total_top if total_top else 0.0
        small = pos < min_pos
        out.append({"genre": g, "n": len(gr), "pos": pos, "base_rate": pos / len(gr),
                    "auc": None if small else _wauc(gr), "small": small,
                    "top_count": len(gt), "top_hits": sum(int(r["is_hit"]) for r in gt),
                    "pool_share": pool_share, "top_share": top_share, "bias": bias_index(top_share, pool_share),
                    "hit_share": pos / total_pos if total_pos else 0.0,
                    "top_recall": sum(int(r["is_hit"]) for r in gt) / pos if pos else None})
    return sorted(out, key=lambda t: (-t["n"], t["genre"]))


def overall_row(by_cutoff: Dict[str, List[dict]], top_n: int = TOP_N) -> dict:
    rows = [r for rs in by_cutoff.values() for r in rs]
    tops = _tops(by_cutoff, top_n)
    pos = sum(int(r["is_hit"]) for r in rows)
    return {"genre": "전체", "n": len(rows), "pos": pos, "base_rate": pos / len(rows) if rows else 0.0,
            "auc": _wauc(rows), "top_count": len(tops), "top_hits": sum(int(r["is_hit"]) for r in tops)}


def composition(rows: Sequence[dict], top_n: int = TOP_N) -> List[dict]:
    """한 날짜 후보의 장르 구성: 상위 top_n 안 vs 후보 전체."""
    idx = set(top_indices([float(r["score"]) for r in rows], [r["team_key"] for r in rows], top_n,
                          [r.get("last_seen") for r in rows]))
    n_top = len(idx)
    counts: Dict[str, List[int]] = defaultdict(lambda: [0, 0])
    for i, r in enumerate(rows):
        counts[r["genre"]][1] += 1
        if i in idx:
            counts[r["genre"]][0] += 1
    out = []
    for g, (t, a) in counts.items():
        top_share, pool_share = (t / n_top if n_top else 0.0), a / len(rows)
        out.append({"genre": g, "top_count": t, "all_count": a, "top_share": top_share, "pool_share": pool_share,
                    "bias": bias_index(top_share, pool_share)})
    return sorted(out, key=lambda c: (-c["top_count"], -c["all_count"], c["genre"]))


def source_shares(team_sources: Dict[str, Set[str]], team_genre: Dict[str, str]) -> Dict[str, Dict[str, float]]:
    """장르마다 '그 출처에 한 번이라도 나온 팀' 비율."""
    teams_by_genre: Dict[str, List[str]] = defaultdict(list)
    for k, g in team_genre.items():
        teams_by_genre[g].append(k)
    out: Dict[str, Dict[str, float]] = {}
    for g, keys in teams_by_genre.items():
        cnt: Dict[str, int] = defaultdict(int)
        for k in keys:
            for s in team_sources.get(k, ()):
                cnt[s] += 1
        out[g] = {s: c / len(keys) for s, c in cnt.items()}
    return out


def profile_missing_share(rows: Sequence[dict]) -> Dict[str, float]:
    """장르마다 멜론·스포티파이 프로필이 없는 팀 비율 (프로필이 없으면 첫 발매일·팬 수를 몰라 유명 팀 제외가 안 됨)."""
    tot: Dict[str, int] = defaultdict(int)
    miss: Dict[str, int] = defaultdict(int)
    for r in rows:
        tot[r["genre"]] += 1
        miss[r["genre"]] += int((r.get("profile_status") or "unknown") == "unknown")
    return {g: miss[g] / n for g, n in tot.items()}


def within_genre_ranks(rows: Sequence[dict]) -> Dict[str, Tuple[int, int]]:
    """팀 → (전체 순위, 장르 안 순위). 순서는 앱과 같다(score_tune.app_order)."""
    idx = st.app_order([float(r["score"]) for r in rows], [r["team_key"] for r in rows], [r.get("last_seen") for r in rows])
    order = [rows[i] for i in idx]
    seen: Dict[str, int] = defaultdict(int)
    out = {}
    for i, r in enumerate(order, 1):
        seen[r["genre"]] += 1
        out[r["team_key"]] = (i, seen[r["genre"]])
    return out


# ---------- 장르별 출처 성적표 ----------

def winner_sources(signals: Sequence[dict], outcomes: Sequence[dict], team_genre: Dict[str, str], genre: str) -> dict:
    """장르 수상 팀이 첫 정답 전에 나온 출처: 출처별 잡은 수(seen)·가장 먼저 잡은 수(first, 같은 날이면 모두)·
    그 출처에만 나온 수(only), 정답 전 신호가 하나도 없는 팀 수(unseen), 팀별 목록."""
    keys = {k for k, g in team_genre.items() if g == genre}
    outs = [o for o in outcomes if o["team_key"] in keys]
    winners = sorted({o["team_key"] for o in outs})
    leads = score_model.lead_times([s for s in signals if s["team_key"] in keys], outs)
    by_team: Dict[str, List[dict]] = defaultdict(list)
    for r in leads:
        by_team[r["team_key"]].append(r)
    stats: Dict[str, Dict[str, int]] = defaultdict(lambda: {"seen": 0, "first": 0, "only": 0})
    for k, rs in by_team.items():
        earliest = min(r["signal_date"] for r in rs)
        for r in rs:
            st_ = stats[r["source"]]
            st_["seen"] += 1
            st_["first"] += int(r["signal_date"] == earliest)
            st_["only"] += int(len(rs) == 1)
    first = first_outcomes(outs)
    teams = [{"team_key": k, "outcome_date": first[k]["date"], "grade": first[k]["grade"], "program": first[k]["program"],
              "sources": sorted(((r["signal_date"], r["source"]) for r in by_team.get(k, [])))}
             for k in winners]
    return {"winners": len(winners), "unseen": sum(1 for k in winners if k not in by_team),
            "sources": sorted(({"source": src, **v} for src, v in stats.items()), key=lambda r: (-r["seen"], r["source"])),
            "teams": teams}


def first_outcomes(outcomes: Sequence[dict]) -> Dict[str, dict]:
    """팀 → 첫 정답(날짜·등급·프로그램). 같은 날 여럿이면 등급이 높은 것."""
    out: Dict[str, dict] = {}
    for o in outcomes:
        d = str(o["announced_date"])[:10]
        g = o.get("grade") or ""
        cur = out.get(o["team_key"])
        if cur is None or (d, -score_model.GRADE_RANK.get(g, 0)) < (cur["date"], -score_model.GRADE_RANK.get(cur["grade"], 0)):
            out[o["team_key"]] = {"date": d, "grade": g, "program": o.get("program_label") or o.get("program") or ""}
    return out


def genre_source_hits(by_cutoff: Dict[str, List[dict]], team_src: Dict[str, Dict[str, Set[str]]],
                      team_genre: Dict[str, str]) -> Dict[Tuple[str, str], Tuple[int, int]]:
    """(장르, 출처) → (후보 수, 정답 수), 기준일 합산. 후보는 점수와 같은 후보군, 출처는 기준일 전 3년 안에 나온 것."""
    out: Dict[Tuple[str, str], List[int]] = defaultdict(lambda: [0, 0])
    for c, rows in by_cutoff.items():
        for r in rows:
            g = team_genre.get(r["team_key"])
            if not g:
                continue
            for src in team_src.get(c, {}).get(r["team_key"], ()):
                out[(g, src)][0] += 1
                out[(g, src)][1] += int(r["is_hit"])
    return {k: (v[0], v[1]) for k, v in out.items()}


# ---------- 데이터 ----------

def team_genres(con) -> Dict[str, str]:
    """팀 → 분석용 장르 (추정 장르는 미분류). teams 에 genre_confidence 칸이 있어야 한다(lab_sql.connect 가 없으면 만듦)."""
    q = "SELECT team_key, primary_genre, genre_confidence FROM teams"
    return {k: analysis_genre(g, c) for k, g, c in con.execute(q).fetchall()}


def backtest_data(con, genres: Dict[str, str]) -> Dict[str, List[dict]]:
    w2 = {k: float(lab_sql.DEFAULTS[k]) for k, _ in st.V0_WEIGHTS}
    out = {}
    for c in st.CUTOFFS:
        rows = st.features(con, c)
        out[c] = [{**r, "genre": genres.get(r["team_key"], UNCLASSIFIED), "score": st.score(r, w2)} for r in rows]
    return out


def current_rows(con, day: str) -> List[dict]:
    rows = lab_sql.query(con, "candidates.sql", as_of=f"'{day}'", limit=str(CURRENT_LIMIT))
    genres = team_genres(con)                       # 추정 장르는 미분류 (candidates.sql 의 primary_genre 대신)
    return [{**r, "genre": genres.get(r["team_key"], UNCLASSIFIED), "score": float(r["score"])} for r in rows]


def current_sources(con, day: str, keys: Set[str]) -> Dict[str, Set[str]]:
    """지금 후보 팀이 신호 기간(3년) 안에 나온 출처 (발굴·맥락 역할만 — 점수에 쓰는 것과 같은 범위)."""
    q = (f"SELECT team_key, branch || ':' || CASE WHEN branch = '선정·지원' THEN program ELSE source END "
         f"FROM signals WHERE role IN ('discovery','context') AND signal_date < DATE '{day}' "
         f"AND signal_date >= DATE '{day}' - INTERVAL 3 YEAR")
    out: Dict[str, Set[str]] = defaultdict(set)
    for k, s in con.execute(q).fetchall():
        if k in keys:
            out[k].add(s)
    return out


def genre_source_note(con) -> Dict[str, int]:
    """장르가 어떻게 붙었나: 멜론·발매 태그가 있는 팀 vs 보완 규칙(리드머·힙합어워즈 신인→힙합, 밴드 디스커버리→록)만."""
    q = ("SELECT COALESCE(NULLIF(primary_genre,''),'') <> '' AND COALESCE(genre_confidence,'') <> 'inferred' AS has_genre, "
         "profile_status <> 'unknown' AS has_profile, "
         "COUNT(*) FROM teams GROUP BY 1, 2")
    return {f"{'장르' if g else '미분류'}·{'프로필' if p else '프로필 없음'}": n for g, p, n in con.execute(q).fetchall()}


SCORECARD_SIGNAL_SQL = ("SELECT team_key, branch || ':' || CASE WHEN branch = '선정·지원' THEN program ELSE source END AS source, "
                        "role, CAST(signal_date AS VARCHAR) AS signal_date FROM signals")
SCORECARD_OUTCOME_SQL = ("SELECT team_key, program, program_label, CAST(announced_date AS VARCHAR) AS announced_date, grade "
                         "FROM outcomes WHERE counted")


def _dicts(con, sql: str) -> List[dict]:
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def platform_genres(con) -> Tuple[Dict[str, str], bool]:
    """멜론·발매 장르 태그로만 정한 장르(보완 규칙 제외). PostgreSQL 원본 태그를 읽고, 못 읽으면 랩 장르로 대신(False)."""
    try:
        import build_dashboard_data as bd
        import export_lab_data as ex
        rows = ex._records(bd.psql_csv(ex.queries(bd._has_xref_table(bd.psql_csv))["teams"]))
    except (ImportError, OSError, RuntimeError) as e:
        print(f"⚠️ PostgreSQL 장르 원본을 못 읽어 랩 장르로 대신함: {e}", file=sys.stderr)
        return {k: g for k, g in team_genres(con).items() if g != UNCLASSIFIED}, False
    out = {}
    for r in rows:
        labels = bd._infer_genres(r.get("raw_genres"), "", "")   # 출처 보완 없이 플랫폼 태그만
        if labels:
            out[r["team_key"]] = labels[0]
    return out, True


def cutoff_sources(con) -> Dict[str, Dict[str, Set[str]]]:
    """기준일마다 팀 → 기준일 전 3년 안에 나온 출처(모든 역할)."""
    out: Dict[str, Dict[str, Set[str]]] = {}
    for c in st.CUTOFFS:
        q = (SCORECARD_SIGNAL_SQL + f" WHERE signal_date < DATE '{c}' AND signal_date >= DATE '{c}' - INTERVAL 3 YEAR")
        m: Dict[str, Set[str]] = defaultdict(set)
        for r in _dicts(con, q):
            m[r["team_key"]].add(r["source"])
        out[c] = m
    return out


# ---------- 문서 ----------

def _pct(v: float) -> str:
    return f"{v * 100:.1f}%"


def _fb(v: Optional[float]) -> str:
    return "—" if v is None else f"{v:.2f}"


def section_backtest(table: List[dict], overall: dict) -> List[str]:
    lines = ["| 장르 | 후보(행) | 정답 | 기준율 | 장르 안 AUC | 정답 중 비율 | 상위 100 안 | 상위 100 안 정답 (포착률) | 후보군 비율 | 상위 100 비율 | 쏠림 지수 |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for t in table:
        auc = "표본 부족" if t["small"] else ("—" if t["auc"] is None else f"{t['auc']:.3f}")
        lines.append(f"| {t['genre']} | {t['n']:,} | {t['pos']} | {_pct(t['base_rate'])} | {auc} | {_pct(t['hit_share'])} | "
                     f"{t['top_count']} | {t['top_hits']} ({'—' if t['top_recall'] is None else _pct(t['top_recall'])}) | {_pct(t['pool_share'])} | {_pct(t['top_share'])} | {_fb(t['bias'])} |")
    lines.append(f"| **전체** | {overall['n']:,} | {overall['pos']} | {_pct(overall['base_rate'])} | {overall['auc']:.3f} | 100% | "
                 f"{overall['top_count']} | {overall['top_hits']} ({_pct(overall['top_hits'] / overall['pos'])}) | 100% | 100% | 1.00 |")
    return lines


def section_current(comp: List[dict], rows: List[dict], shares: Dict[str, Dict[str, float]]) -> List[str]:
    missing = profile_missing_share(rows)
    lines = ["| 장르 | 상위 100 안 | 상위 100 비율 | 후보 전체 | 후보 비율 | 쏠림 지수 | 프로필 없는 팀 |",
             "|---|---|---|---|---|---|---|"]
    for c in comp:
        lines.append(f"| {c['genre']} | {c['top_count']} | {_pct(c['top_share'])} | {c['all_count']:,} | "
                     f"{_pct(c['pool_share'])} | {_fb(c['bias'])} | {_pct(missing.get(c['genre'], 0))} |")
    sources = sorted({s for sh in shares.values() for s in sh}, key=lambda s: -sum(sh.get(s, 0) for sh in shares.values()))
    main_src = [s for s in sources if max(sh.get(s, 0) for sh in shares.values()) >= 0.05][:8]
    genres = [c["genre"] for c in comp if c["all_count"] >= 5]
    lines += ["", "**장르별 출처 구성** — 지금 후보 중 그 출처(신호 기간 3년, 발굴·맥락)에 한 번이라도 나온 팀 비율. 후보 5팀 이상 장르만.", "",
              "| 장르 | " + " | ".join(main_src) + " |", "|---|" + "---|" * len(main_src)]
    for g in genres:
        lines.append(f"| {g} | " + " | ".join(_pct(shares.get(g, {}).get(s, 0)) for s in main_src) + " |")
    ranks = within_genre_ranks(rows)
    names = {r["team_key"]: r.get("display_name") or r["team_key"] for r in rows}
    lines += ["", f"**장르 안 순위 예시** — 장르마다 장르 안 1~{SHOW_PER_GENRE}위 팀과 전체 순위 (미분류 제외).", "",
              "| 장르 | 장르 안 1위 (전체) | 2위 (전체) | 3위 (전체) |", "|---|---|---|---|"]
    by_genre: Dict[str, List[Tuple[int, str]]] = defaultdict(list)
    genre_of = {r["team_key"]: r["genre"] for r in rows}
    for k, (overall_rank, g_rank) in ranks.items():
        if g_rank <= SHOW_PER_GENRE and genre_of[k] != UNCLASSIFIED:
            by_genre[genre_of[k]].append((g_rank, f"{names[k]} ({overall_rank}위)"))
    best_rank = {g: min(ranks[k][0] for k in genre_of if genre_of[k] == g) for g in by_genre}
    for g in sorted(by_genre, key=best_rank.get):
        cells = [c for _, c in sorted(by_genre[g])] + ["—"] * (SHOW_PER_GENRE - len(by_genre[g]))
        lines.append(f"| {g} | " + " | ".join(cells) + " |")
    return lines


def main() -> int:
    con = lab_sql.connect()
    meta = json.loads((lab_sql.DATA_DIR / "meta.json").read_text(encoding="utf-8"))
    day = meta["data_end"]
    genres = team_genres(con)
    data = backtest_data(con, genres)
    table = genre_table(data)
    overall = overall_row(data)
    rows = current_rows(con, day)
    comp = composition(rows)
    shares = source_shares(current_sources(con, day, {r["team_key"] for r in rows}),
                           {r["team_key"]: r["genre"] for r in rows})
    note = genre_source_note(con)
    card_lines, cov = section_scorecard(con, data)
    lines = build_doc(day, table, overall, comp, rows, shares, note, cov) + card_lines
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"✅ → {OUT.relative_to(lab_sql.ROOT)}")
    return 0


def section_scorecard(con, data: Dict[str, List[dict]]) -> Tuple[List[str], dict]:
    """6절: 장르별 출처 성적표 (플랫폼 태그 장르만)."""
    tag_genre, from_db = platform_genres(con)
    signals = _dicts(con, SCORECARD_SIGNAL_SQL)
    outcomes = _dicts(con, SCORECARD_OUTCOME_SQL)
    role = {r["source"]: r["role"] for r in signals}
    names = dict(con.execute("SELECT team_key, display_name FROM teams").fetchall())
    winners = {o["team_key"] for o in outcomes}
    all_teams = set(names)
    cov = {"winner_tag": len(winners & set(tag_genre)) / max(len(winners), 1),
           "other_tag": len((all_teams - winners) & set(tag_genre)) / max(len(all_teams - winners), 1),
           "from_db": from_db}
    hits = genre_source_hits(data, cutoff_sources(con), tag_genre)
    genres = sorted(set(tag_genre.values()), key=lambda g: -sum(1 for k in winners if tag_genre.get(k) == g))
    ws = {g: winner_sources(signals, outcomes, tag_genre, g) for g in genres}
    lines = ["## 6. 장르별 출처 성적표 (멜론·발매 장르 태그가 있는 팀만)", "",
             ("장르는 PostgreSQL의 멜론·발매 장르 원본 태그로만 정했다(리드머 → 힙합 같은 보완 규칙으로 붙은 장르는 뺌 — 출처로 장르를 붙이고 "
              "그 출처의 성적을 재면 순환 논리라서)." if from_db else
              "⚠️ PostgreSQL을 못 읽어 랩 장르(보완 규칙 포함)로 대신했다 — 리드머·밴드 디스커버리 성적이 부풀 수 있다.")
             + f" 태그 장르가 있는 팀 {len(tag_genre):,}팀. 정답 팀(센 정답) {len(winners)}팀 중 {_pct(cov['winner_tag'])}가 태그를 가졌고, "
             f"나머지 팀은 {_pct(cov['other_tag'])}만 가졌다(프로필을 정답 팀 위주로 모았기 때문 — 4절 1번).", "",
             "**6-1. 장르별 수상 팀이 정답 전에 우리 데이터에 있었나** (정답 전 = 첫 정답보다 엄격하게 앞선 신호, 모든 역할)", "",
             "| 장르 | 수상 팀 | 정답 전 신호 있음 | 우리 데이터에 없음 | 가장 많이 잡은 출처 |", "|---|---|---|---|---|"]
    for g in genres:
        w = ws[g]
        if not w["winners"]:
            continue
        top = ", ".join(f"{r['source']} {r['seen']}" for r in w["sources"][:3]) or "—"
        lines.append(f"| {g} | {w['winners']} | {w['winners'] - w['unseen']} | {_pct(w['unseen'] / w['winners'])} | {top} |")
    lines += ["", f"**6-2. 장르 × 출처** (수상 팀 {SCORECARD_MIN_WINNERS}팀 이상 장르). '잡음'은 수상 팀을 정답 전에 잡은 수(가장 먼저 / 그 출처에만). "
              f"'적중률'은 기준일 6개 후보군(점수와 같은 후보, 그 출처에 3년 안에 나온 팀) 중 24개월 안 정답 비율 — 후보 {SCORECARD_MIN_TEAMS}행 미만은 표본 적음.", "",
              "| 장르 | 출처 | 역할 | 수상 팀 잡음 (가장 먼저 / 유일) | 적중률 (정답 / 후보) |", "|---|---|---|---|---|"]
    for g in genres:
        if ws[g]["winners"] < SCORECARD_MIN_WINNERS:
            continue
        srcs = {r["source"]: r for r in ws[g]["sources"]}
        for src in sorted(set(srcs) | {s_ for (gg, s_), (n, _) in hits.items() if gg == g and n >= SCORECARD_MIN_TEAMS},
                          key=lambda x: (-srcs.get(x, {}).get("seen", 0), x)):
            r = srcs.get(src, {"seen": 0, "first": 0, "only": 0})
            n, h = hits.get((g, src), (0, 0))
            rate = f"{_pct(h / n)} ({h} / {n})" if n >= SCORECARD_MIN_TEAMS else (f"표본 적음 ({h} / {n})" if n else "—")
            lines.append(f"| {g} | {src} | {role.get(src, '?')} | {r['seen']} ({r['first']} / {r['only']}) | {rate} |")
    sub = 3
    for g in FOCUS_GENRES:
        if g not in ws or not ws[g]["winners"]:
            continue
        lines += ["", f"**6-{sub}. {g} 수상 팀 — 정답 전에 어디 나왔나**", "",
                  "| 팀 | 첫 정답 (날짜 · 프로그램 · 등급) | 정답 전 출처 (처음 나온 날) |", "|---|---|---|"]
        for t in sorted(ws[g]["teams"], key=lambda t: t["outcome_date"]):
            srcs = ", ".join(f"{src} ({d[:7]})" for d, src in t["sources"]) or "**우리 데이터에 없음**"
            lines.append(f"| {names.get(t['team_key'], t['team_key'])} | {t['outcome_date']} · {t['program']} · {t['grade']} | {srcs} |")
        sub += 1
    idols = [names.get(k, k) for g in FOCUS_GENRES if g in ws for t in ws[g]["teams"] for k in [t["team_key"]] if k in IDOL_EXAMPLES]
    lines += [""] + interpret_scorecard(ws, sub, idols)
    return lines, cov


def interpret_scorecard(ws: Dict[str, dict], sub: int = 5, idols: Sequence[str] = ()) -> List[str]:
    tot_w = sum(w["winners"] for w in ws.values())
    tot_u = sum(w["unseen"] for w in ws.values())
    lines = [f"**6-{sub}. 읽는 법**", ""]
    if tot_w:
        lines.append(f"- 태그 장르가 있는 수상 팀 전체로 보면 {_pct(tot_u / tot_w)}가 정답 전에 우리 데이터에 없었다.")
    for g in FOCUS_GENRES:
        w = ws.get(g)
        if not w or not w["winners"]:
            continue
        top = w["sources"][0] if w["sources"] else None
        lines.append(f"- **{g}**: 수상 {w['winners']}팀 중 {_pct(w['unseen'] / w['winners'])}가 정답 전 우리 데이터에 없음"
                     + (f", 잡은 경우는 {top['source']}가 가장 많음({top['seen']}팀)" if top else "")
                     + ". 이 팀들이 정답 전에 먼저 나타나는 곳을 찾는 게 출처 보강의 목표다 → "
                     "[힙합·R&B 초기 신호 출처 조사](research_2026-11-27_hiphop_rnb_sources.md).")
    if idols:
        lines.append(f"- 힙합·R&B 태그 수상 팀에는 대형 기획사 아이돌({', '.join(idols)})도 섞여 있다(한대음·이즘 신인상). "
                     "인디 신호 출처(공연장·인디 매거진·선정 프로그램)로는 원래 잡기 어려운 팀이라, 힙합의 'IZM만 잡음'·'우리 데이터에 없음' 일부는 이 때문이다. "
                     "인디 신인 발굴이 목표라면 이 팀들은 정답에서 따로 표시하는 것을 제안한다.")
    lines += ["- 수상 팀 수가 장르마다 수십 팀 이하라 출처별 숫자는 방향으로만 읽는다. 큐레이션은 2023년, 인디스트릿 공연은 2024년부터만 기록이 있어 "
              "그 전 정답 팀은 '우리 데이터에 없음'으로 나오기 쉽다.", ""]
    return lines


def build_doc(day: str, table: List[dict], overall: dict, comp: List[dict], rows: List[dict],
              shares: Dict[str, Dict[str, float]], note: Dict[str, int], cov: Optional[dict] = None) -> List[str]:
    return ["# 장르별 편향 점검 (점수 v2)", "",
            "_자동 생성: `.venv/bin/python scripts/genre_bias.py`_", "",
            f"## 1. 과거 기준일 6개 합산 ({', '.join(st.CUTOFFS)}, 관찰 {st.HORIZON_MONTHS}개월)", "",
            "후보군·점수·정답은 [점수 교차 검증](score_tuning.md)·[학습 모델 비교](score_model.md)와 같다. 같은 팀이 여러 기준일에 다시 셀 수 있어 '행'으로 센다. "
            f"장르 안 AUC는 그 장르 후보끼리만 비교한 등급 가중 AUC(정답 {MIN_POS}행 미만은 '표본 부족'). "
            f"쏠림 지수 = 상위 {TOP_N} 안 비율 ÷ 후보군 비율(기준일마다 상위 {TOP_N}을 뽑아 합산). 1보다 크면 점수가 그 장르를 위로 몰고, 작으면 아래로 민다.", "",
            *section_backtest(table, overall), "",
            f"## 2. 지금({day}) 후보 상위 {TOP_N}의 장르 구성", "",
            f"앱 '후보 목록'과 같은 계산(candidates.sql, 이미 정답 받은 팀 제외). 후보 전체 {len(rows):,}팀.", "",
            *section_current(comp, rows, shares), "",
            "## 3. 장르는 어떻게 붙나 (해석 전에 꼭 볼 것)", "",
            "팀 표의 장르(`primary_genre`)는 멜론·발매 장르 태그로 정하고, 태그가 없을 때만 확실한 출처로 보완한다"
            "(리드머 소개 → 힙합, 밴드 디스커버리 선정 → 록·밴드; `build_dashboard_data._infer_genres`). "
            "정답 프로그램은 근거로 쓰지 않는다(2026-11-27 수정 — 그 전 규칙의 '한국힙합어워즈 신인 → 힙합'은 신호 데이터에 해당 프로그램이 없어 실제로 쓰인 적이 없다). "
            "빈칸을 같은 무대 다수결·공연장 성향·약한 출처 힌트로 채운 **추정 장르(genre_confidence = inferred)는 이 분석에서 '미분류'로 센다** "
            "— 비교·분석은 profile·press 장르만 쓴다(2026-11-27 결정, [장르 빈칸 채우기](genre_fill.md)). 아래 표의 '장르'도 추정을 뺀 수다.", "",
            "| 팀 표 | 팀 수 |", "|---|---|", *[f"| {k} | {v:,} |" for k, v in sorted(note.items())], "",
            *interpret(table, overall, comp, rows, shares, cov)]


def _row(table: List[dict], genre: str) -> Optional[dict]:
    return next((t for t in table if t["genre"] == genre), None)


def interpret(table: List[dict], overall: dict, comp: List[dict], rows: List[dict],
              shares: Dict[str, Dict[str, float]], cov: Optional[dict] = None) -> List[str]:
    """숫자를 보고 해석·제안 문단을 만든다 (다시 돌려도 숫자와 어긋나지 않게 조건으로)."""
    unc = _row(table, UNCLASSIFIED)
    classified = [t for t in table if t["genre"] != UNCLASSIFIED]
    cls_n = sum(t["n"] for t in classified)
    cls_pos = sum(t["pos"] for t in classified)
    up = [t for t in classified if (t["bias"] or 0) >= 2]
    missed = [t for t in classified if t["pos"] >= MIN_POS and t["top_recall"] is not None
              and t["top_recall"] < overall["top_hits"] / overall["pos"] / 2]
    cur = {c["genre"]: c for c in comp}
    cur_zero = [g for g, c in cur.items() if c["top_count"] == 0 and c["all_count"] >= 5]
    missing = profile_missing_share(rows)
    hip = shares.get("힙합", {})
    rock = shares.get("록·밴드", {})
    gig_key, rhy_key = "공연:indistreet", "큐레이션:rhythmer"
    lines = ["## 4. 해석", "",
             f"1. **장르 표시 자체가 '이미 주목받은 팀' 표시다.** 과거 후보 {overall['n']:,}행 중 장르가 붙은 것은 {cls_n:,}행"
             f"({_pct(cls_n / overall['n'])})뿐인데 정답의 {_pct(cls_pos / overall['pos'])}({cls_pos}행)가 여기에 있다. "
             f"장르가 붙은 후보의 기준율은 {_pct(cls_pos / cls_n)}, 미분류는 {_pct(unc['base_rate']) if unc else '—'}다. "
             "장르는 멜론·발매 장르 태그가 있어야 주로 붙는데, 멜론 프로필은 상위 후보와 정답 팀 위주로 모았다"
             + (f"(6절: 정답 팀은 {_pct(cov['winner_tag'])}가 플랫폼 장르 태그를 가졌고, 나머지 팀은 {_pct(cov['other_tag'])})" if cov else "")
             + ". 그래서 장르별 숫자는 '장르 차이'보다 '프로필을 모은 순서'를 더 많이 반영한다. "
             "→ **장르를 점수 특징으로 넣으면 안 된다**(정답 누수)."]
    if up:
        lines.append("2. **위로 몰리는 장르**: " + ", ".join(f"{t['genre']}(쏠림 {t['bias']:.1f})" for t in up)
                     + ". 다만 이 장르들은 기준율도 높아서(위 1번) 쏠림 자체가 잘못은 아니다. "
                     "상위 100 안 정답 포착률로 보면 " + ", ".join(f"{t['genre']} {_pct(t['top_recall'])}" for t in up if t["top_recall"] is not None)
                     + f"로 전체({_pct(overall['top_hits'] / overall['pos'])})와 비슷하거나 높다.")
    if missed:
        lines.append("3. **체계적으로 놓치는 장르**: " + ", ".join(
            f"{t['genre']}(정답 {t['pos']}행 중 상위 100 안 {t['top_hits']}, 장르 안 AUC {_fb(t['auc'])})"
            for t in missed) + ". 기준율은 전체보다 높은데 점수가 그 정답 팀을 위로 못 올린다.")
    if cur_zero:
        lines.append(f"4. **지금 상위 100에도 없음**: {', '.join(cur_zero)} 후보가 각각 5팀 이상인데 상위 100에 한 팀도 없다.")
    if hip and rock:
        lines.append(f"5. **원인 후보 — 출처 구성**: 점수 특징 중 공연장 다양성·수상 팀과 같은 무대는 공연 데이터(대부분 인디스트릿)에서 나온다. "
                     f"지금 후보 중 인디스트릿 공연에 나온 비율은 록·밴드 {_pct(rock.get(gig_key, 0))}, 힙합 {_pct(hip.get(gig_key, 0))}다. "
                     f"힙합 후보는 리드머({_pct(hip.get(rhy_key, 0))} — 리드머 소개로 힙합 장르를 붙이는 규칙 때문에 높게 나옴)·IZM 같은 매거진으로 들어오는데 리드머·IZM은 '맥락' 역할이라 가중치 0.5만 받는다. "
                     "선정 갈래도 밴드 디스커버리·유재하처럼 밴드·싱어송라이터 쪽 프로그램이 대부분이라 힙합·R&B·일렉트로닉 팀은 선정 단계 점수를 받을 길이 거의 없다.")
    if missing:
        hm = missing.get("힙합")
        lines.append("6. **원인 후보 — 유명 팀이 덜 걸러짐**: 매거진은 신인뿐 아니라 이미 알려진 팀도 소개한다. 프로필이 없으면 첫 발매일·팬 수를 몰라 "
                     "'우리 데이터에 처음 나온 날'로 신인을 판단하므로, 매거진으로만 들어온 기성 팀이 후보에 남는다"
                     + (f"(지금 힙합 후보 중 프로필 없는 팀 {_pct(hm)})" if hm is not None else "")
                     + ". 이런 팀이 섞이면 그 장르의 기준율과 장르 안 AUC가 함께 낮아진다.")
    flagged = [r.get("display_name") or r["team_key"] for r in rows
               if r["team_key"] in SUSPECT_FAMOUS or r["team_key"] in SUSPECT_GENRE]
    if flagged:
        lines.append(f"   - 생성 시점 예(사람 확인 요청): {', '.join(flagged)} — 이미 알려진 팀이거나, 리드머 소개 보완 규칙 때문에 힙합으로 붙었을 수 있다.")
    lines += ["", "## 5. 개선 제안 (바꾸지 않고 제안만)", "",
              "- **장르별 출처 보강**: 힙합·R&B 공연(클럽 공연 라인업, 힙합 공연 기획사 인스타), 힙합 신인 프로그램(선정형 경연·지원 사업)을 "
              "'후보 신호' 출처로 찾는다. 새 출처는 [출처 역할](source_roles.md) 규칙대로 성적표를 잰 뒤 역할을 정한다.",
              "- **장르 안 순위 병기**: 후보 목록에 '전체 순위'와 함께 '장르 안 순위'를 보여 주면, 공연 데이터가 얇은 장르의 1~3위도 담당자 눈에 띈다(위 표 예시). "
              "점수는 바꾸지 않고 보여 주는 방식만 바꾸는 것이라 위험이 적다.",
              "- **장르 분석은 플랫폼 태그 장르로**: 보완 규칙(리드머 → 힙합 등)으로 붙은 장르는 출처 성적을 잴 때 순환 논리가 된다(6절은 태그만 씀). "
              "또 프로필을 정답 팀 먼저 모으면 장르가 정답과 엮이므로, 장르 비교용 프로필은 후보 전체에서 정답과 상관없이(예: 무작위 표본) 모으는 것을 제안한다. "
              "(정답 프로그램으로 장르를 붙이던 규칙은 2026-11-27에 뺐다 — 신호 데이터에 해당 프로그램이 없어 실제 분포 변화는 0팀.)",
              f"- **장르 정보 늘리기**: 지금 후보의 {_pct(cur[UNCLASSIFIED]['pool_share']) if UNCLASSIFIED in cur else '—'}가 미분류라 장르 비교는 방향으로만 읽어야 한다. "
              "스포티파이 장르·발매 장르 태그를 후보 전체로 넓히면 이 점검을 다시 돌린다.",
              "- **프로필 없는 기성 팀 거르기**: 매거진으로만 들어온 팀은 멜론 보강 명단 우선순위를 높여 유명 팀 제외가 작동하게 한다.",
              ""]
    return lines


if __name__ == "__main__":
    sys.exit(main())
