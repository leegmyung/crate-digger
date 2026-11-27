"""큰 페스티벌 메인 무대 라인업을 '시험용 정답 B'로 더해 보면 점수 검증·출처 성적표가 어떻게 바뀌나 (메모리에서만).

    .venv/bin/python scripts/festival_outcome_test.py                       # 기본 + 엄격 두 변형, 결과 요약 출력
    .venv/bin/python scripts/festival_outcome_test.py --variants default --out /tmp/r.json

입력: data/raw/review/raw_outcome_2026-11-27_review_festival_main.csv (수동 정답 형식, 적재 폴더 밖 — 시험용)
      program = penta_main(펜타포트 본무대 전체 무대) · gmf_main · bml_main(그랜드민트·뷰민라 Mint Breeze 무대)
      note 칸 = 'tier=main; first=1; superrookie=0; idol=0; headliner=1; …'
규칙 (지금 정답과 같게):
  - 등급 B(가중치 1), 결과 selected. outcome_rules.excluded_teams(기획사 아이돌 10팀)는 뺌.
  - 5년 규칙: 정답 발표일에 첫 발매 후 5년 이내인 팀만 센 정답(counted). 첫 발매를 모르면 세지 않음
    (core.v_outcome 의 career_filtered 정답과 같은 계산).
  - 같은 집안: 우리 신호에 펜타포트·민트페이퍼 출처가 없어 '신호↔정답' 짝은 해당 없음. 대신
    ① 같은 해 펜타 슈퍼루키(정답 A) 무대 팀은 기본 변형에서 뺌(같은 행사 — 이미 정답),
    ② 펜타 슈퍼루키를 먼저 받은 팀의 본무대 / 뷰민라↔그랜드민트 메인을 먼저 선 팀의 다른 쪽 메인은
       same_house_sources='outcome:…'로 표시(정보용 — 이미 먼저 받은 정답이 있어 점수 적중엔 영향 없음).
변형: default = 슈퍼루키 무대 팀만 뺌 / strict = + 메인급 무대만(펜타 KB 무대·무대 모름 2026) + 아이돌·아이돌 출신 뺌.
비교: score_tune 교차 검증(기준일 6개, 등급 가중 AUC, 고른 가중치·v2·v0, 상위 20/50 적중)과
      출처 성적표(source_scorecard.sql, source_review 와 같은 기준일)를 '기존 정답만' vs '새 정답 포함'.
config·csv_schema·data/raw 적재 폴더는 건드리지 않는다 — DuckDB 메모리 표에만 넣는다.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab_sql  # noqa: E402

ROOT = lab_sql.ROOT
REVIEW = ROOT / "data" / "raw" / "review" / "raw_outcome_2026-11-27_review_festival_main.csv"
XREF = ROOT / "data" / "raw" / "state" / "artist_xref.json"
ROLES = ROOT / "config" / "source_roles.json"
CAREER_YEARS = 5                # ref.settings career_filter_years 와 같음
LABELS = {"penta_main": "펜타포트 본무대(시험)", "gmf_main": "그랜드민트 메인 무대(시험)",
          "bml_main": "뷰민라 메인 무대(시험)"}
MINT = ("gmf_main", "bml_main")
VARIANTS = {
    "default": {"superrookie": False, "idol": True, "main_only": False,
                "label": "기본 — 같은 해 펜타 슈퍼루키 무대 팀만 뺌"},
    "strict": {"superrookie": False, "idol": False, "main_only": True,
               "label": "엄격 — 메인급 무대만 + 아이돌·아이돌 출신 뺌"},
}
FLAG_BOOL = ("first", "superrookie", "idol", "headliner", "bml_N")


# ---------- 읽기·고르기 ----------

def parse_note(note: str) -> dict:
    out = {}
    for part in (note or "").split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            k, v = k.strip(), v.strip()
            out[k] = (v == "1") if k in FLAG_BOOL else v
    return out


def read_rows(rows: Iterable[dict]) -> List[dict]:
    return [{**r, "flags": parse_note(r.get("note", ""))} for r in rows]


def read_review(path: Path = REVIEW) -> List[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return read_rows(csv.DictReader(f))


def select(rows: Sequence[dict], variant: dict) -> List[dict]:
    out = []
    for r in rows:
        f = r["flags"]
        if f.get("superrookie") and not variant["superrookie"]:
            continue
        if f.get("idol") and not variant["idol"]:
            continue
        if variant["main_only"] and f.get("tier", "?") not in ("main", "?", ""):
            continue
        out.append(r)
    return out


# ---------- 정답 행 만들기 ----------

def _years_between(a: date, b: date) -> float:
    return (b - a).days / 365.25


def _date(s) -> Optional[date]:
    if isinstance(s, date):
        return s
    try:
        return date.fromisoformat(str(s or "")[:10])
    except ValueError:
        return None


def outcome_rows(rows: Sequence[dict], key_of: Callable[[str], str], teams: Dict[str, dict],
                 excluded: Iterable[str]) -> List[dict]:
    """검토 CSV 행 → 랩 정답 표 행 (등급 B·5년 규칙). 같은 팀·프로그램·연도는 가장 이른 발표일 하나."""
    ex = set(excluded)
    best: Dict[tuple, dict] = {}
    for r in rows:
        team = key_of(r["artist_text"])
        ann = _date(r["announced_at"])
        if not team or not ann or team in ex:
            continue
        fr = _date((teams.get(team) or {}).get("first_release"))
        counted = bool(fr and _years_between(fr, ann) <= CAREER_YEARS)
        row = {"team_key": team, "program": r["program"], "program_label": LABELS.get(r["program"], r["program"]),
               "tier": "mid", "result": r.get("result") or "selected", "announced_date": ann, "counted": counted,
               "grade": "B", "weight": 1, "same_house_sources": "", "same_house_scored": False}
        k = (team, r["program"], r.get("round") or ann.year)
        if k not in best or ann < best[k]["announced_date"]:
            best[k] = row
    return sorted(best.values(), key=lambda o: (o["announced_date"], o["program"], o["team_key"]))


def mark_same_house(new: Sequence[dict], existing: Sequence[dict]) -> List[dict]:
    """정보용 같은 집안 표시(새 사본): 펜타 슈퍼루키 뒤 본무대, 뷰민라↔그랜드민트 메인 중 뒤의 것."""
    sr: Dict[str, date] = {}
    for o in existing:
        if o["program"] == "penta_superrookie" and _date(o["announced_date"]):
            d = _date(o["announced_date"])
            sr[o["team_key"]] = min(sr.get(o["team_key"], d), d)
    mint_first: Dict[tuple, date] = {}
    for o in new:
        if o["program"] in MINT:
            k = (o["team_key"], o["program"])
            mint_first[k] = min(mint_first.get(k, o["announced_date"]), o["announced_date"])
    out = []
    for o in new:
        srcs = []
        if o["program"] == "penta_main" and o["team_key"] in sr and sr[o["team_key"]] < o["announced_date"]:
            srcs.append("outcome:penta_superrookie")
        if o["program"] in MINT:
            other = MINT[1 - MINT.index(o["program"])]
            d = mint_first.get((o["team_key"], other))
            if d and d < o["announced_date"]:
                srcs.append(f"outcome:{other}")
        out.append({**o, "same_house_sources": ";".join(srcs)})
    return out


def make_key_of(xref_path: Path = XREF) -> Callable[[str], str]:
    import normalize as nz
    key2team: Dict[str, str] = {}
    for e in json.loads(xref_path.read_text(encoding="utf-8")):
        for k in [*e.get("keys", []), e["artist_key"]]:
            key2team.setdefault(k, e["artist_key"])
    return lambda name: key2team.get(nz.artist_key(name), nz.artist_key(name))


# ---------- 실행·비교 ----------

def _connect_with(extra: Sequence[dict]):
    con = lab_sql.connect()
    if extra:
        cols = [r[0] for r in con.execute("DESCRIBE outcomes").fetchall()]
        con.executemany(f"INSERT INTO outcomes ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
                        [[o.get(c) for c in cols] for o in extra])
        pcols = [r[0] for r in con.execute("DESCRIBE programs").fetchall()]
        progs = sorted({o["program"] for o in extra})
        con.executemany(f"INSERT INTO programs ({', '.join(pcols)}) VALUES ({', '.join('?' for _ in pcols)})",
                        [[{"program": p, "label": LABELS.get(p, p), "kind": "outcome"}.get(c) for c in pcols]
                         for p in progs])
    return con


def summarize(con) -> dict:
    import score_tune as st
    import source_review as sr
    res = st.tune(con)
    data, evals, picks, ref = res["data"], res["evals"], res["picks"], res["ref_evals"]
    ties = st.data_ties(data)
    v2w = {k: float(lab_sql.DEFAULTS[k]) for k, _ in st.V0_WEIGHTS}
    v2 = st.evaluate(data, v2w, ties)
    per = {}
    for c in st.CUTOFFS:
        e = evals[int(picks[c])][c]
        per[c] = {"n": e["n"], "pos": e["pos"], "pick": e["auc"], "v2": v2[c]["auc"], "v0": ref["점수 v0"][c]["auc"],
                  "hits50_pick": e["hits50"], "hits50_v2": v2[c]["hits50"], "hits20_v2": v2[c]["hits20"],
                  "pick_weights": res["names"][int(picks[c])]}

    def mean(k: str) -> float:
        vals = [p[k] for p in per.values() if p[k] is not None]
        return sum(vals) / len(vals)

    meta = json.loads((lab_sql.DATA_DIR / "meta.json").read_text(encoding="utf-8"))
    cuts, since = sr.review_cutoffs(meta["data_end"])
    card = lab_sql.query(con, "source_scorecard.sql", cutoffs=sr.cutoffs_sql(cuts), since=f"'{since}'",
                         horizon_months=str(sr.HORIZON_MONTHS))
    return {"per_cutoff": per, "mean_pick": mean("pick"), "mean_v2": mean("v2"), "mean_v0": mean("v0"),
            "hits50_pick": sum(p["hits50_pick"] for p in per.values()),
            "hits50_v2": sum(p["hits50_v2"] for p in per.values()),
            "hits20_v2": sum(p["hits20_v2"] for p in per.values()),
            "pos": sum(p["pos"] for p in per.values()), "n": sum(p["n"] for p in per.values()),
            "scorecard_cutoffs": cuts,
            "scorecard": [{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in r.items()} for r in card]}


def diff(base: dict, new: dict) -> dict:
    keys = ("mean_pick", "mean_v2", "mean_v0", "hits50_pick", "hits50_v2", "hits20_v2", "pos", "n")
    return {k: (round(new[k] - base[k], 4) if isinstance(base[k], float) else new[k] - base[k])
            for k in keys if k in base and k in new}


def new_answer_stats(extra: Sequence[dict], existing: Sequence[dict]) -> dict:
    """새 정답 중 센 것, 그 팀의 '첫 센 정답'이 새 정답이 되는 팀(= 정답 팀이 새로 생기거나 더 일찍 생김)."""
    first_old: Dict[str, date] = {}
    for o in existing:
        if str(o.get("counted")).lower() == "true" and _date(o["announced_date"]):
            d = _date(o["announced_date"])
            first_old[o["team_key"]] = min(first_old.get(o["team_key"], d), d)
    counted = [o for o in extra if o["counted"]]
    first_new: Dict[str, date] = {}
    for o in counted:
        first_new[o["team_key"]] = min(first_new.get(o["team_key"], o["announced_date"]), o["announced_date"])
    brand_new = sorted(t for t in first_new if t not in first_old)
    earlier = sorted(t for t in first_new if t in first_old and first_new[t] < first_old[t])
    return {"rows": len(extra), "counted_rows": len(counted), "counted_teams": len(first_new),
            "new_answer_teams": len(brand_new), "earlier_answer_teams": len(earlier),
            "same_house_marked": sum(1 for o in extra if o.get("same_house_sources")),
            "new_answer_examples": brand_new, "earlier_examples": earlier,
            "by_program": {p: sum(1 for o in counted if o["program"] == p) for p in LABELS}}


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="큰 페스티벌 메인 무대 = 시험용 정답 B — 메모리에서만 비교")
    ap.add_argument("--review", type=Path, default=REVIEW)
    ap.add_argument("--variants", default="default,strict")
    ap.add_argument("--out", type=Path, help="결과 JSON (저장소 밖 권장)")
    args = ap.parse_args(argv)
    roles = json.loads(ROLES.read_text(encoding="utf-8"))
    excluded = set((roles.get("outcome_rules") or {}).get("excluded_teams") or {})
    with open(lab_sql.DATA_DIR / "teams.csv", encoding="utf-8") as f:
        teams = {r["team_key"]: r for r in csv.DictReader(f)}
    with open(lab_sql.DATA_DIR / "outcomes.csv", encoding="utf-8") as f:
        existing = list(csv.DictReader(f))
    rows = read_review(args.review)
    key_of = make_key_of()
    report = {"base": summarize(_connect_with([]))}
    b = report["base"]
    print(f"기존 정답만: 평균 AUC 고른 {b['mean_pick']:.3f} · v2 {b['mean_v2']:.3f} · v0 {b['mean_v0']:.3f} · "
          f"상위50(v2) {b['hits50_v2']} · 정답(기준일 합) {b['pos']}")
    for name in [v.strip() for v in args.variants.split(",") if v.strip()]:
        var = VARIANTS[name]
        extra = mark_same_house(outcome_rows(select(rows, var), key_of, teams, excluded), existing)
        stats = new_answer_stats(extra, existing)
        summ = summarize(_connect_with(extra))
        d = diff(b, summ)
        report[name] = {"variant": var["label"], "stats": stats, "summary": summ, "diff": d}
        print(f"[{name}] {var['label']}: 새 정답 행 {stats['rows']} (센 것 {stats['counted_rows']}, 팀 {stats['counted_teams']}, "
              f"새 정답 팀 {stats['new_answer_teams']}, 더 이른 정답 {stats['earlier_answer_teams']}) → 평균 AUC 고른 "
              f"{summ['mean_pick']:.3f}({d['mean_pick']:+.3f}) · v2 {summ['mean_v2']:.3f}({d['mean_v2']:+.3f}) · "
              f"v0 {summ['mean_v0']:.3f}({d['mean_v0']:+.3f}) · 상위50(v2) {summ['hits50_v2']}({d['hits50_v2']:+d}) · "
              f"정답 {summ['pos']}({d['pos']:+d})")
    if args.out:
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        print(f"✅ → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
