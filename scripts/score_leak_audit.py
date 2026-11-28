"""점수 입력의 사후 수집 편향 점검 → docs/score_leak_audit_2026-11-28.md 의 숫자

'확인된 장르 = 사후 수집 편향'(docs/methods.md)과 같은 종류의 새는 곳이 점수 v2 입력(갈래 수·선정·발굴 매거진·
공연장 다양성·수상 팀과 같은 무대·맥락 매거진)에도 있는지 본다. 점수 신호 자체는 날짜·전체 목록으로 받지만
(수집기 대상 선정 점검은 문서 1절), 두 군데서 '정답·상위 팀 위주로 받은 자료'가 끼어든다.
  ① 이름 묶기 연결표(artist_xref): 멜론·스포티파이 프로필 이름, 정답 명단 이름, 정답 팀 멜론 번호 짝(outcome_melon_match),
     사람이 확인한 별칭 — 이것들로 묶인 다른 표기의 신호가 정답 팀 쪽에 더 잘 합쳐진다.
  ② 신인 판정: 첫 발매일을 멜론 프로필에서 먼저 쓴다(features.sql COALESCE(first_release, first_seen)).
판 3가지로 다시 잰다(점수 정의는 그대로):
  A. 연결표를 '팀을 고르지 않은 출처'(공연·선정·발매·기사 이름 + 발매 플랫폼 번호, 사람 별칭 없음)로만 다시 만들어,
     거기서 다른 팀으로 갈라지는 점수 신호를 옮긴 판
  B. 신인 판정에서 프로필 첫 발매일을 빼고 우리 데이터 첫 등장만 쓴 판
  C. A + B
  D. 신인 판정의 첫 발매일을 '팀 안 고른' 발매 원본(새 발매 목록·포크라노스 2020~ 날짜 되짚기)의 가장 이른 발매일로 —
     모든 팀에 같은 기준 (없으면 우리 데이터 첫 등장)
각 판에서 v2 기본 가중치 AUC(기준일 6개 평균)와 score_tune 방식 교차 검증 AUC(기준일 하나 빼고 고르기)를 낸다.

실행: .venv/bin/python scripts/score_leak_audit.py [--json 결과.json] [--no-cv]   (교차 검증은 판마다 몇 분)
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
UNTARGETED_TABLES = ("gig", "selection", "release", "press")   # 팀을 고르지 않고 날짜·목록으로 받은 원본 (artist_xref.SIGNAL_TABLES)
MIN_MELON_ID = 100                                            # artist_xref._usable_id 와 같은 하한 (공용 번호 0·1 제외)
RAW_SIGNAL_FILES = (("raw_kr_gig_*.csv", "공연", "gig_date"), ("raw_kr_selection_*.csv", "선정·지원", "announced_at"),
                    ("raw_press_*.csv", "큐레이션", "published_at"))
MapKey = Tuple[str, str, str, str]   # (팀 키, 갈래, 출처, 날짜 — 원본 그대로, 월·연도만 알 수도 있음)


# ---------- 순수 함수 (tests/test_score_leak_audit.py) ----------

def untargeted_names(names: Iterable[Mapping]) -> List[dict]:
    return [dict(n) for n in names if n.get("table") in UNTARGETED_TABLES]


def release_platform_ids(rows: Iterable[Mapping]) -> List[dict]:
    """발매 원본(새 발매 목록으로 받음)의 멜론·스포티파이 번호만 — 프로필·정답 짝 번호는 뺀다."""
    out = []
    for r in rows:
        src, pid, name = r.get("source", ""), str(r.get("artist_source_id") or ""), r.get("artist_text") or ""
        if not name or src not in ("melon", "spotify") or not pid:
            continue
        if src == "melon" and not (pid.isdigit() and int(pid) >= MIN_MELON_ID):
            continue
        out.append({"name": name, "platform": src, "id": pid, "confidence": "high"})
    return out


def key_map(raw: Iterable[Mapping], scored: Set[Tuple[str, str]], key_full: Callable[[str], str],
            key_unt: Callable[[str], str], split: Callable[[str], List[str]]) -> Dict[MapKey, Set[str]]:
    """점수에 쓰는 원본 신호 줄마다 (지금 연결표 팀 키, 갈래, 출처, 날짜) → '팀 안 고른 연결표'로 본 팀 키들."""
    out: Dict[MapKey, Set[str]] = defaultdict(set)
    for r in raw:
        if (r["branch"], r["source"]) not in scored or not r.get("date"):
            continue
        for part in split(r.get("artist_text") or ""):
            full, unt = key_full(part), key_unt(part)
            if full and unt:
                out[(full, r["branch"], r["source"], r["date"])].add(unt)
    return dict(out)


def _lookup(mapping: Mapping[MapKey, Set[str]], s: Mapping) -> Optional[Set[str]]:
    d = str(s.get("signal_date") or "")[:10]
    for k in (d, d[:7], d[:4]):
        hit = mapping.get((s["team_key"], s["branch"], s["source"], k))
        if hit is not None:
            return hit
    return None


def reassign(signals: Sequence[Mapping], mapping: Mapping[MapKey, Set[str]]) -> Tuple[List[dict], Dict[str, int]]:
    """신호 줄을 '팀 안 고른 연결표' 팀 키로 옮긴 새 목록. 원래 팀이 대응 목록에 있으면 남기고 나머지 팀에 복사,
    없으면 옮긴다(여러 팀이면 각자 하나씩). 대응을 못 찾은 줄은 그대로(unmatched)."""
    out: List[dict] = []
    stats = {"moved": 0, "copied": 0, "kept": 0, "unmatched": 0}
    for s in signals:
        targets = _lookup(mapping, s)
        if targets is None:
            stats["unmatched"] += 1
            out.append(dict(s))
            continue
        if s["team_key"] in targets:
            stats["kept"] += 1
            out.append(dict(s))
            others = sorted(targets - {s["team_key"]})
            stats["copied"] += len(others)
        else:
            stats["moved"] += 1
            others = sorted(targets)
        out.extend(dict(s, team_key=k) for k in others)
    return out, stats


def lost_teams(signals: Sequence[Mapping], mapping: Mapping[MapKey, Set[str]], cutoffs: Sequence[str]) -> Dict[str, Set[str]]:
    """기준일마다, 그 전 신호 중 하나라도 다른 팀으로 옮겨 가는(잃는) 팀."""
    lost_dates: Dict[str, List[str]] = defaultdict(list)
    for s in signals:
        targets = _lookup(mapping, s)
        if targets is not None and s["team_key"] not in targets:
            lost_dates[s["team_key"]].append(str(s["signal_date"])[:10])
    return {c: {k for k, ds in lost_dates.items() if any(d < c for d in ds)} for c in cutoffs}


def concentration(pool: Mapping[str, Sequence[Mapping]], flagged: Mapping[str, Set[str]]) -> dict:
    """표시된 팀 행이 정답 행에 얼마나 몰리나: 정답 중 비율(hit_share) 대 나머지 중 비율(other_share), 정답률 비교."""
    rows = hits = frows = fhits = 0
    for c, rs in pool.items():
        flag = flagged.get(c, set())
        for r in rs:
            y, f = int(r["is_hit"]), r["team_key"] in flag
            rows, hits, frows, fhits = rows + 1, hits + y, frows + f, fhits + (y and f)
    others = rows - hits
    return {"rows": rows, "hits": hits, "flag_rows": frows, "flag_hits": fhits,
            "hit_share": fhits / hits if hits else 0.0, "other_share": (frows - fhits) / others if others else 0.0,
            "rate_flag": fhits / frows if frows else 0.0,
            "rate_rest": (hits - fhits) / (rows - frows) if rows - frows else 0.0}


def untargeted_debut(rows: Iterable[Mapping], key_of: Callable[[str], str]) -> Dict[str, str]:
    """팀 → 발매 원본의 가장 이른 발매일 (월만 알면 그 달 1일 — 신인 쪽으로 너그럽지 않게 이른 날)."""
    out: Dict[str, str] = {}
    for r in rows:
        d, key = str(r.get("released_at") or "").strip(), key_of(r.get("artist_text") or "") if r.get("artist_text") else ""
        if not key or len(d) < 7:
            continue
        d = d[:10] if len(d) >= 10 else f"{d[:7]}-01"
        if key not in out or d < out[key]:
            out[key] = d
    return out


def mean_auc(per_cutoff: Mapping[str, Mapping]) -> Optional[float]:
    vals = [v["auc"] for v in per_cutoff.values() if v.get("auc") is not None]
    return sum(vals) / len(vals) if vals else None


# ---------- 데이터 ----------

def _read(pattern: str) -> List[dict]:
    rows: List[dict] = []
    for f in sorted(glob.glob(str(RAW_DIR / pattern))):
        with open(f, encoding="utf-8") as fh:
            rows.extend(csv.DictReader(fh))
    return rows


def raw_signal_rows() -> List[dict]:
    out = []
    for pattern, branch, date_col in RAW_SIGNAL_FILES:
        for r in _read(pattern):
            if r.get("source") == "instagram":
                continue
            out.append({"branch": branch, "source": r.get("source", ""), "date": (r.get(date_col) or "")[:10],
                        "artist_text": r.get("artist_text", "")})
    return out


def untargeted_index():
    import artist_xref as ax
    names, ig_profiles, ig_posts, _ = ax.collect_inputs()
    cur = ax.load_curation()
    artists, _ = ax.build_xref(untargeted_names(names), ig_profiles, ig_posts, release_platform_ids(_read("raw_kr_release_*.csv")),
                               manual_aliases=[], distinct=cur["distinct"], platform_pins=[])
    return ax.index_from_artists(artists), len(artists)


def scored_sources(signals: Iterable[Mapping]) -> Set[Tuple[str, str]]:
    return {(s["branch"], s["source"]) for s in signals if s.get("role") in ("discovery", "context")}


def _signals() -> List[dict]:
    import lab_sql
    with open(lab_sql.DATA_DIR / "signals.csv", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def replace_signals(con, rows: Sequence[Mapping], tmp_dir: Path) -> None:
    """랩 연결의 signals 표를 바꾸고, 새로 생긴 팀 키는 teams 에 빈 프로필로 넣는다(신인 판정은 첫 등장일)."""
    path = tmp_dir / "signals.csv"
    cols = list(rows[0].keys())
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    con.execute(f"CREATE OR REPLACE TABLE signals AS SELECT * FROM read_csv_auto('{path.as_posix()}', header=true)")
    con.execute("""INSERT INTO teams (team_key, display_name, first_seen, profile_status)
                   SELECT team_key, team_key, MIN(signal_date), 'unknown' FROM signals
                   WHERE team_key NOT IN (SELECT team_key FROM teams) GROUP BY team_key""")


def variant_result(con, cv: bool) -> dict:
    import lab_sql
    import score_tune as st
    data = {c: st.features(con, c) for c in st.CUTOFFS}
    w2 = {k: float(lab_sql.DEFAULTS[k]) for k, _ in st.V0_WEIGHTS}
    ev = st.evaluate(data, w2)
    out = {"rows": sum(len(v) for v in data.values()), "hits": sum(int(r["is_hit"]) for v in data.values() for r in v),
           "auc_v2": mean_auc(ev), "auc_v2_by_cutoff": {c: ev[c]["auc"] for c in ev},
           "hits50_v2": sum(ev[c]["hits50"] for c in ev)}
    if cv:
        res = st.tune(con)
        held = {c: res["evals"][int(res["picks"][c])][c] for c in st.CUTOFFS}
        out.update({"auc_cv": mean_auc(held), "auc_cv_by_cutoff": {c: held[c]["auc"] for c in held},
                    "hits50_cv": sum(held[c]["hits50"] for c in held),
                    "cv_picks": {c: res["names"][int(res["picks"][c])] for c in st.CUTOFFS}})
    return out, data


def main(argv: Optional[Sequence[str]] = None) -> int:
    import artist_xref as ax
    import lab_sql
    import score_tune as st
    ap = argparse.ArgumentParser(description="점수 입력 사후 수집 편향 점검")
    ap.add_argument("--json")
    ap.add_argument("--no-cv", action="store_true")
    args = ap.parse_args(argv)
    cv = not args.no_cv

    signals = _signals()
    full_idx = ax.load_xref()
    unt_idx, n_unt = untargeted_index()
    split = lambda t: [p for p in ax.split_cell(t)["parts"] if p]   # noqa: E731
    mapping = key_map(raw_signal_rows(), scored_sources(signals),
                      lambda t: ax.canonical_key(t, full_idx), lambda t: ax.canonical_key(t, unt_idx), split)
    scored = scored_sources(signals)
    scored_signals = [s for s in signals if (s["branch"], s["source"]) in scored]
    new_signals, stats = reassign(signals, mapping)
    scored_stats = reassign(scored_signals, mapping)[1]
    lost = lost_teams(scored_signals, mapping, st.CUTOFFS)

    result = {"xref_untargeted_teams": n_unt, "xref_full_teams": len(json.loads((RAW_DIR / "state" / "artist_xref.json").read_text())),
              "reassign_scored": scored_stats, "reassign_all": stats}
    con = lab_sql.connect()
    result["base"], base_data = variant_result(con, cv)
    result["lost_concentration"] = concentration(base_data, lost)
    prof = {k for (k,) in con.execute("SELECT team_key FROM teams WHERE first_release IS NOT NULL").fetchall()}
    result["profile_first_release_concentration"] = concentration(base_data, {c: prof for c in base_data})

    with tempfile.TemporaryDirectory() as tmp:
        con_a = lab_sql.connect()
        replace_signals(con_a, new_signals, Path(tmp))
        result["A_untargeted_xref"], _ = variant_result(con_a, cv)
        con_b = lab_sql.connect()
        con_b.execute("UPDATE teams SET first_release = NULL")
        result["B_no_profile_debut"], b_data = variant_result(con_b, cv)
        con_c = lab_sql.connect()
        replace_signals(con_c, new_signals, Path(tmp))
        con_c.execute("UPDATE teams SET first_release = NULL")
        result["C_both"], _ = variant_result(con_c, cv)
        debut = untargeted_debut(_read("raw_kr_release_*.csv"), lambda t: ax.canonical_key(t, full_idx))
        con_d = lab_sql.connect()
        con_d.execute("UPDATE teams SET first_release = NULL")
        con_d.execute("CREATE TEMP TABLE debut(team_key VARCHAR, d DATE)")
        con_d.executemany("INSERT INTO debut VALUES (?, ?)", sorted(debut.items()))
        con_d.execute("UPDATE teams SET first_release = debut.d FROM debut WHERE teams.team_key = debut.team_key")
        result["D_untargeted_debut"], d_data = variant_result(con_d, cv)
        result["D_debut_known_concentration"] = concentration(d_data, {c: set(debut) for c in d_data})
    base_keys = {c: {r["team_key"] for r in rows} for c, rows in base_data.items()}
    result["B_added_concentration"] = concentration(
        b_data, {c: {r["team_key"] for r in rows} - base_keys[c] for c, rows in b_data.items()})
    text = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    if args.json:
        Path(args.json).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
