"""장르별 편향 점검 → docs/genre_bias.md

점수 v2(lab_sql.DEFAULTS)가 특정 장르를 체계적으로 올리거나 내리는지 본다.
- 기준일 6개(score_tune.CUTOFFS)·같은 후보군·같은 지표(등급 가중 AUC)로, 장르(teams.primary_genre, 비면 '미분류')별
  후보 수·정답 수·기준율·장르 안 AUC(정답 5팀 미만은 '표본 부족')·상위 100 안 비율 vs 후보군 비율(쏠림 지수).
- 지금 날짜 후보 상위 100의 장르 구성, 장르별 출처 구성, 장르 안 순위.
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


def genre_label(value: Optional[str]) -> str:
    v = (value or "").strip()
    return v or UNCLASSIFIED


def bias_index(top_share: float, pool_share: float) -> Optional[float]:
    """쏠림 지수 = 상위 N 안 비율 ÷ 후보군 비율. 1이면 고르게, 1보다 크면 위로 쏠림, 작으면 아래로."""
    return top_share / pool_share if pool_share else None


def top_indices(scores: Sequence[float], keys: Sequence[str], n: int) -> List[int]:
    """점수 상위 n개 위치. 동점은 팀 키 순(score_tune.hits_at_k 와 같은 규칙)."""
    order = sorted(range(len(scores)), key=lambda i: (-scores[i], keys[i]))
    return sorted(order[:n])


def _wauc(rows: Sequence[dict]) -> Optional[float]:
    return st.weighted_auc([float(r["score"]) for r in rows], [float(r.get("hit_weight") or 0) for r in rows])


def _tops(by_cutoff: Dict[str, List[dict]], top_n: int) -> List[dict]:
    out = []
    for rows in by_cutoff.values():
        idx = top_indices([float(r["score"]) for r in rows], [r["team_key"] for r in rows], top_n)
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
    idx = set(top_indices([float(r["score"]) for r in rows], [r["team_key"] for r in rows], top_n))
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
    """팀 → (전체 순위, 장르 안 순위). 동점은 팀 키 순."""
    order = sorted(rows, key=lambda r: (-float(r["score"]), r["team_key"]))
    seen: Dict[str, int] = defaultdict(int)
    out = {}
    for i, r in enumerate(order, 1):
        seen[r["genre"]] += 1
        out[r["team_key"]] = (i, seen[r["genre"]])
    return out


# ---------- 데이터 ----------

def team_genres(con) -> Dict[str, str]:
    return {k: genre_label(g) for k, g in con.execute("SELECT team_key, primary_genre FROM teams").fetchall()}


def backtest_data(con, genres: Dict[str, str]) -> Dict[str, List[dict]]:
    w2 = {k: float(lab_sql.DEFAULTS[k]) for k, _ in st.V0_WEIGHTS}
    out = {}
    for c in st.CUTOFFS:
        rows = st.features(con, c)
        out[c] = [{**r, "genre": genres.get(r["team_key"], UNCLASSIFIED), "score": st.score(r, w2)} for r in rows]
    return out


def current_rows(con, day: str) -> List[dict]:
    rows = lab_sql.query(con, "candidates.sql", as_of=f"'{day}'", limit=str(CURRENT_LIMIT))
    return [{**r, "genre": genre_label(r.get("primary_genre")), "score": float(r["score"])} for r in rows]


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
    q = ("SELECT COALESCE(NULLIF(primary_genre,''),'') <> '' AS has_genre, profile_status <> 'unknown' AS has_profile, "
         "COUNT(*) FROM teams GROUP BY 1, 2")
    return {f"{'장르' if g else '미분류'}·{'프로필' if p else '프로필 없음'}": n for g, p, n in con.execute(q).fetchall()}


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
    lines = build_doc(day, table, overall, comp, rows, shares, note)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"✅ → {OUT.relative_to(lab_sql.ROOT)}")
    return 0


def build_doc(day: str, table: List[dict], overall: dict, comp: List[dict], rows: List[dict],
              shares: Dict[str, Dict[str, float]], note: Dict[str, int]) -> List[str]:
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
            "(리드머 소개·한국힙합어워즈 신인 → 힙합, 밴드 디스커버리 선정 → 록·밴드; `build_dashboard_data._infer_genres`).", "",
            "| 팀 표 | 팀 수 |", "|---|---|", *[f"| {k} | {v:,} |" for k, v in sorted(note.items())], "",
            *interpret(table, overall, comp, rows, shares)]


def _row(table: List[dict], genre: str) -> Optional[dict]:
    return next((t for t in table if t["genre"] == genre), None)


def interpret(table: List[dict], overall: dict, comp: List[dict], rows: List[dict],
              shares: Dict[str, Dict[str, float]]) -> List[str]:
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
             "장르는 멜론 프로필이나 수상·선정 출처가 있어야 붙는데, 멜론 프로필은 상위 후보와 정답 팀 위주로 모았고 "
             "보완 규칙 중 '한국힙합어워즈 신인 → 힙합'은 정답 프로그램 자체다. 그래서 장르별 숫자는 '장르 차이'보다 '프로필을 모은 순서'를 더 많이 반영한다. "
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
              "- **장르 붙이는 규칙 정리**: 정답 프로그램(한국힙합어워즈 신인)으로 장르를 붙이는 보완 규칙은 백테스트 해석을 흐린다. "
              "장르 분석용으로는 '기준일 전 정보로만 붙인 장르'를 따로 두는 것을 제안한다.",
              f"- **장르 정보 늘리기**: 지금 후보의 {_pct(cur[UNCLASSIFIED]['pool_share']) if UNCLASSIFIED in cur else '—'}가 미분류라 장르 비교는 방향으로만 읽어야 한다. "
              "스포티파이 장르·발매 장르 태그를 후보 전체로 넓히면 이 점검을 다시 돌린다.",
              "- **프로필 없는 기성 팀 거르기**: 매거진으로만 들어온 팀은 멜론 보강 명단 우선순위를 높여 유명 팀 제외가 작동하게 한다.",
              ""]
    return lines


if __name__ == "__main__":
    sys.exit(main())
