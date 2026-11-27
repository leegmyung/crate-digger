"""라인업 역할 — 공연 원본에서 단독·헤드라이너·서포트를 가려 팀별로 센다 → docs/lab/data/lineup_roles.csv, docs/lineup_roles.md

Chartmetric 은 아티스트 공연 기록에 라인업 역할(헤드라이너/서포트)을 붙인다. 우리 공연 원본(data/raw/raw_kr_gig_*.csv)에는
역할·출연 순서 칸이 없고, 한 공연의 행 순서도 출연 순서로 믿기 어렵다(조사 결과는 문서 1절 — 매번 다시 잰다). 그래서:
- 단독 공연: 한 공연(같은 출처·같은 공연 주소)에 출연 팀이 1팀.
- 헤드라이너: 단독 공연, 또는 여러 팀 공연에서 제목에 이름이 걸린 팀이 정확히 1팀일 때 그 팀('○○ 단독 콘서트 with …').
- 서포트: 여러 팀 공연에서 제목에 이름이 없는 팀. 제목에 둘 이상이 걸리면(공동 주최) 헤드라이너도 서포트도 아님.
- 서포트 → 헤드라이너 전환: 첫 헤드라이너 공연보다 앞서 서포트 공연이 있음.
- 13팀 이상 공연(페스티벌)은 뺀다 (venue_ladder 와 같은 기준). 기준 날짜(meta.json data_end) 뒤 공연(예정)도 뺀다.
팀 키: 공연 원본 이름 → 정규화 키(normalize.artist_key) → 연결표(data/raw/state/artist_xref.json) 대표 키.

검증: 단독·헤드라이너·전환이 정답을 미리 알려 주는지 — 점수 v2에 특징으로 하나씩 더해 기준일 6개 교차 검증
(feature_lab 과 같은 방법·채택 기준, 특징은 기준일 전 3년 발굴 출처 공연만). 점수는 바꾸지 않음 — 효과 있으면 '요청'만.

실행: .venv/bin/python scripts/lineup_roles.py [--csv 경로] [--no-eval] [--data-only]   (21~23시엔 docs/lab/data 에 쓰지 말 것)
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import math
import re
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab_sql  # noqa: E402
from normalize import artist_key  # noqa: E402

RAW_DIR = lab_sql.ROOT / "data" / "raw"
XREF = RAW_DIR / "state" / "artist_xref.json"
ROLES = lab_sql.ROOT / "config" / "source_roles.json"
CSV_OUT = lab_sql.DATA_DIR / "lineup_roles.csv"
DOC = lab_sql.ROOT / "docs" / "lineup_roles.md"
MAX_EVENT_TEAMS = 12
MIN_NAME = 2          # 제목에서 찾을 이름의 최소 길이(정규화 후) — 'A'·'비' 같은 한 글자는 우연히 겹침
LOOKBACK_YEARS = 3
FIELDS = ("team_key", "gigs", "solo_gigs", "headline_gigs", "support_gigs", "headline_share", "avg_lineup",
          "first_headline_date", "support_to_headline")
FEATURES: Tuple[Tuple[str, str, str], ...] = (
    ("solo_count", "단독 공연 수", "기준일 전 3년 단독 공연(출연 1팀) 수, ln(1+수)"),
    ("headline_share", "헤드라이너 비율", "기준일 전 3년 공연 중 헤드라이너(단독 또는 제목에 이름이 걸린 단 한 팀) 비율"),
    ("avg_lineup", "평균 라인업 크기", "기준일 전 3년 공연의 평균 출연 팀 수 (페스티벌 제외)"),
    ("support_to_headline", "서포트 → 헤드라이너 전환", "기준일 전 3년 안에 서포트 공연 뒤 헤드라이너 공연이 있음 (1/0)"),
)
NAMES = {k: n for k, n, _ in FEATURES}


@dataclass(frozen=True)
class Gig:
    source: str
    url: str
    date: date
    title: str
    acts: Tuple[Tuple[str, str], ...]   # (팀 키, 원본 이름) — 원본 행 순서, 같은 팀 중복 제거


# ---------- 읽기 ----------

def load_xref(path: Path = XREF) -> Dict[str, str]:
    """연결표 → {표기 키: 대표 키}. 없으면 빈 표(정규화 키 그대로)."""
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: e["artist_key"] for e in entries for k in e.get("keys", [])}


def discovery_sources(path: Path = ROLES) -> Set[str]:
    """config/source_roles.json 에서 발굴 역할인 공연 출처 ('공연:indistreet' → 'indistreet')."""
    try:
        sig = json.loads(path.read_text(encoding="utf-8"))["signals"]
    except (OSError, ValueError, KeyError):
        return set()
    return {k.split(":", 1)[1] for k, v in sig.items() if k.startswith("공연:")
            and (v.get("role") if isinstance(v, dict) else v) == "discovery"}


def _day(s: str) -> Optional[date]:
    try:
        return date.fromisoformat((s or "")[:10])
    except ValueError:
        return None


def load_raw(raw_dir: Path = RAW_DIR, xref: Optional[Dict[str, str]] = None) -> List[Gig]:
    """공연 원본 → 공연 목록 (같은 출처·같은 공연 주소 = 한 공연, 다시 받은 파일의 같은 줄은 하나로)."""
    xref = xref if xref is not None else load_xref()
    acts: Dict[Tuple[str, str], List[Tuple[str, str]]] = defaultdict(list)
    info: Dict[Tuple[str, str], Tuple[date, str]] = {}
    for path in sorted(glob.glob(str(raw_dir / "raw_kr_gig_*.csv"))):
        with open(path, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                d, name = _day(r.get("gig_date", "")), (r.get("artist_text") or "").strip()
                if not d or not name or not r.get("gig_url"):
                    continue
                k = (r.get("source", ""), r["gig_url"])
                key = artist_key(name)
                team = xref.get(key, key)
                if team and team not in {t for t, _ in acts[k]}:
                    acts[k].append((team, name))
                info.setdefault(k, (d, r.get("title", "")))
    return [Gig(s, u, info[(s, u)][0], info[(s, u)][1], tuple(a)) for (s, u), a in acts.items() if a]


# ---------- 역할 ----------

def _norm(text: str) -> str:
    return re.sub(r"[\W_]+", "", (text or "").lower())


def _named(gig: Gig) -> List[str]:
    """제목에 이름이 들어 있는 출연 팀 (정규화 후 MIN_NAME 글자 이상만)."""
    title = _norm(gig.title)
    return [t for t, n in gig.acts if len(_norm(n)) >= MIN_NAME and _norm(n) in title]


def headliners(gig: Gig) -> Set[str]:
    if len(gig.acts) == 1:
        return {gig.acts[0][0]}
    named = set(_named(gig))
    return named if len(named) == 1 else set()


def _usable(gigs: Iterable[Gig], start: Optional[date], end: date, inclusive_end: bool,
            sources: Optional[Set[str]] = None) -> List[Gig]:
    out = []
    for gg in gigs:
        if sources is not None and gg.source not in sources:
            continue
        if len(gg.acts) > MAX_EVENT_TEAMS or (start and gg.date < start):
            continue
        if gg.date > end or (not inclusive_end and gg.date == end):
            continue
        out.append(gg)
    return out


def _aggregate(gigs: Sequence[Gig]) -> Dict[str, dict]:
    agg: Dict[str, dict] = defaultdict(lambda: {"gigs": 0, "solo": 0, "head": 0, "support": 0, "sizes": [],
                                                 "first_head": None, "first_support": None})
    for gg in sorted(gigs, key=lambda x: (x.date, x.url)):
        heads, named = headliners(gg), set(_named(gg))
        for team, _ in gg.acts:
            a = agg[team]
            a["gigs"] += 1
            a["sizes"].append(len(gg.acts))
            a["solo"] += len(gg.acts) == 1
            if team in heads:
                a["head"] += 1
                a["first_head"] = a["first_head"] or gg.date
            elif len(gg.acts) > 1 and team not in named:
                a["support"] += 1
                a["first_support"] = a["first_support"] or gg.date
    return agg


def _switched(a: dict) -> bool:
    return bool(a["first_head"] and a["first_support"] and a["first_support"] < a["first_head"])


def team_roles(gigs: Sequence[Gig], as_of: date, sources: Optional[Set[str]] = None) -> List[dict]:
    """팀마다 공연·단독·헤드라이너·서포트 수, 헤드라이너 비율, 평균 라인업 크기, 전환 여부 (기준 날짜까지)."""
    agg = _aggregate(_usable(gigs, None, as_of, True, sources))
    return [{"team_key": t, "gigs": a["gigs"], "solo_gigs": a["solo"], "headline_gigs": a["head"],
             "support_gigs": a["support"], "headline_share": round(a["head"] / a["gigs"], 4),
             "avg_lineup": round(statistics.mean(a["sizes"]), 3),
             "first_headline_date": a["first_head"].isoformat() if a["first_head"] else "",
             "support_to_headline": int(_switched(a))} for t, a in sorted(agg.items())]


def write_csv(rows: Sequence[dict], path: Path) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def role_features(gigs: Sequence[Gig], cutoff: date, sources: Set[str],
                  lookback_years: int = LOOKBACK_YEARS) -> Dict[str, Dict[str, float]]:
    """기준일 전(lookback 년 안) 발굴 출처 공연만으로 팀마다 특징."""
    start = date(cutoff.year - lookback_years, cutoff.month, cutoff.day)
    agg = _aggregate(_usable(gigs, start, cutoff, False, sources))
    return {t: {"solo_count": math.log(1 + a["solo"]), "headline_share": a["head"] / a["gigs"],
                "avg_lineup": float(statistics.mean(a["sizes"])), "support_to_headline": float(_switched(a))}
            for t, a in agg.items()}


# ---------- 조사 (출연 순서를 믿을 수 있나) ----------

def order_survey(gigs: Sequence[Gig]) -> dict:
    """여러 팀 공연에서 행 순서가 가나다/알파벳순인 비율, 제목에 이름이 걸린 단 한 팀이 행 순서의 어디(처음·중간·끝)에 있나."""
    multi = [gg for gg in gigs if 1 < len(gg.acts) <= MAX_EVENT_TEAMS]
    alpha = sum(1 for gg in multi if [n for _, n in gg.acts] == sorted(n for _, n in gg.acts))
    pos: Counter = Counter()
    for gg in multi:
        named = _named(gg)
        if len(set(named)) == 1:
            i = [t for t, _ in gg.acts].index(named[0])
            pos["first" if i == 0 else "last" if i == len(gg.acts) - 1 else "middle"] += 1
    return {"gigs": len(gigs), "multi_gigs": len(multi), "solo_gigs": sum(1 for gg in gigs if len(gg.acts) == 1),
            "alpha_sorted": alpha, "title_named_position": dict(pos),
            "by_source": dict(Counter(gg.source for gg in gigs))}


# ---------- 교차 검증 ----------

def evaluate(data_dir: Path, gigs: Sequence[Gig], sources: Set[str]) -> dict:
    import feature_lab as fl
    import score_tune as st

    con = lab_sql.connect(data_dir)
    data = {c: st.features(con, c) for c in st.CUTOFFS}
    zero = {f: 0.0 for f, _, _ in FEATURES}
    extra = {}
    for c in st.CUTOFFS:
        feats = role_features(gigs, date.fromisoformat(c), sources)
        extra[c] = {r["team_key"]: feats.get(r["team_key"], zero) for r in data[c]}
    res = {}
    for f, _, _ in FEATURES:
        r = fl.evaluate_feature(data, extra, f, fl.GRID_FINE)
        r["boot"] = fl.bootstrap_diff(data, r)
        r["desc"] = fl.describe(data, extra, f)
        res[f] = r
    return res


def verdict(r: dict) -> str:
    import venue_ladder as vl
    return vl.verdict(r)


# ---------- 문서 ----------

def _f(v: Optional[float]) -> str:
    return "—" if v is None else f"{v:.3f}"


def _pct(a: float, b: float) -> str:
    return f"{a / b:.0%}" if b else "—"


def render(survey: dict, rows: Sequence[dict], ev: Optional[dict], as_of: date, sources: Set[str]) -> str:
    pos = survey["title_named_position"]
    pos_n = sum(pos.values())
    with_head = [r for r in rows if r["headline_gigs"]]
    switched = [r for r in rows if r["support_to_headline"]]
    lines = ["# 라인업 역할 — 단독·헤드라이너·서포트", "",
             "_자동 생성: `.venv/bin/python scripts/lineup_roles.py` · 앱 데이터 `docs/lab/data/lineup_roles.csv`_", "",
             "Chartmetric은 아티스트 공연 기록에 라인업 역할(헤드라이너/서포트)을 붙입니다([경쟁 서비스 조사](research_2026-11-27_competitor_logic.md)). "
             "우리 공연 원본에서 같은 것을 만들 수 있는지 조사하고, 만들 수 있는 만큼 팀별로 셌습니다.", "",
             "## 1. 공연 원본에 무엇이 있나 (조사)", "",
             f"- 공연 원본 칸: 출처·공연 날짜·시각·제목·공연장·출연 팀 이름·공연 주소. **역할·출연 순서 칸은 없습니다.** "
             f"공연 {survey['gigs']:,}건(" + " · ".join(f"{s} {n:,}" for s, n in sorted(survey['by_source'].items(), key=lambda kv: -kv[1]))
             + f"), 그중 단독(출연 1팀) {survey['solo_gigs']:,}건, 2~12팀 공연 {survey['multi_gigs']:,}건.",
             f"- **행 순서를 출연 순서로 믿을 수 없습니다.** 여러 팀 공연에서 제목에 이름이 걸린 단 한 팀(사실상 주인공)이 행 순서의 "
             f"처음 {pos.get('first', 0)}번({_pct(pos.get('first', 0), pos_n)}) · 중간 {pos.get('middle', 0)}번 · "
             f"끝 {pos.get('last', 0)}번({_pct(pos.get('last', 0), pos_n)}) 나옵니다(총 {pos_n}건, 2팀 공연 포함). "
             "처음이 가장 많지만 끝도 적지 않아, 위치로 헤드라이너를 정하면 여러 공연에서 틀립니다. "
             f"가나다·알파벳순으로 정렬된 공연은 {_pct(survey['alpha_sorted'], survey['multi_gigs'])}입니다.",
             "- 그래서 **'마지막 순서 = 헤드라이너'는 쓰지 않고**, 확실한 두 가지만 씁니다: ① 단독 공연(출연 1팀) ② 여러 팀 공연에서 "
             "제목에 이름이 걸린 팀이 정확히 1팀이면 그 팀이 헤드라이너, 이름이 없는 팀은 서포트. 제목에 두 팀 이상이 걸리면 역할을 정하지 않습니다.",
             f"- 13팀 이상 공연(페스티벌)과 기준 날짜({as_of}) 뒤 예정 공연은 뺐습니다.", "",
             "## 2. 팀별 결과", "",
             f"- 공연한 팀 {len(rows):,}팀 중 헤드라이너(단독 포함) 공연이 있는 팀 {len(with_head):,}팀({_pct(len(with_head), len(rows))}), "
             f"단독 공연이 있는 팀 {sum(1 for r in rows if r['solo_gigs']):,}팀, "
             f"**서포트 → 헤드라이너 전환** {len(switched):,}팀.",
             f"- 평균 라인업 크기(팀별 평균의 중앙값) {statistics.median(r['avg_lineup'] for r in rows):.1f}팀." if rows else "", ""]
    lines += _eval_section(ev, sources) if ev else ["## 3. 교차 검증", "", "(`--no-eval` 로 건너뜀)", ""]
    lines += ["## 4. 한계", "",
              "- 제목에 이름이 걸리지 않은 헤드라이너(예: 기획 공연 제목만 있는 공연의 마지막 팀)는 서포트로 셉니다 — 헤드라이너가 적게 잡힙니다.",
              "- 상상마당 공연은 대부분 단독 공연이고 상상마당 출처는 이미 점수에 들어간 발굴 출처라, '단독 공연'과 출처 효과가 겹칩니다.",
              "- 출연 1팀으로 적힌 공연 중에는 원본이 출연 팀을 다 적지 않은 경우가 섞일 수 있습니다.",
              "- 출연 순서는 원본 페이지에 있을 수도 있으나 지금 수집기가 저장하지 않습니다. 저장하도록 바꾸면 '마지막 순서'를 다시 볼 수 있습니다(제안)."]
    return "\n".join(lines) + "\n"


def _eval_section(ev: dict, sources: Set[str]) -> List[str]:
    import feature_lab as fl
    import score_tune as st

    base = next(iter(ev.values()))
    bh = base["base_hits"]
    defs = {k: d for k, _, d in FEATURES}
    lines = ["## 3. 단독·헤드라이너·전환이 정답을 미리 알려 주나 — 점수 v2에 더해 교차 검증", "",
             f"[점수 새 특징 실험](feature_lab.md)과 같은 방법(기준일 6개 {', '.join(st.CUTOFFS)}, 관찰 {st.HORIZON_MONTHS}개월, "
             f"정답 등급 가중 AUC, 가중치 후보 0·{', '.join(f'{g:g}' for g in fl.GRID_FINE)}점을 기준일 하나 빼고 고름). "
             f"채택 기준: 평균 AUC +{fl.ADOPT_MIN_GAIN} 이상, 95% 구간 하한 > 0, 상위 50 적중 유지. "
             f"특징은 기준일 전 3년 발굴 출처({', '.join(sorted(sources))}) 공연만.", "",
             f"v2 그대로: 평균 AUC **{_f(base['base_mean'])}**, 상위 20 / 50 / 100 적중 {bh['hits20']} / {bh['hits50']} / {bh['hits100']}.", "",
             "| 특징 | 정의 | 평균 AUC (교차) | 차이 | 95% 구간 | 오른·내린 기준일 | 상위 20 / 50 / 100 | 고른 가중치 | 0 아닌 후보 | 평균: 정답 / 아닌 팀 | 판정 |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for f, r in ev.items():
        b, h = r["boot"], r["cv_hits"]
        picks = ", ".join(sorted({f"{w:g}" for w in r["picks"].values()}))
        lines.append(f"| {NAMES[f]} | {defs[f]} | {_f(r['cv_mean'])} | {r['cv_mean'] - r['base_mean']:+.3f} | "
                     f"{b[1]:+.3f} ~ {b[2]:+.3f} | {r['wins']} / {r['losses']} | {h['hits20']} / {h['hits50']} / {h['hits100']} | "
                     f"{picks} | {r['desc']['nonzero']:.1%} | {r['desc']['hit_mean']:.2f} / {r['desc']['non_mean']:.2f} | {verdict(r)} |")
    lines += ["", "(평균 정답 / 아닌 팀은 표준화 전 값, 기준일 6개 합침 — 라벨을 보는 참고용이고 가중치 고르기에는 안 썼습니다.)", "",
              _reading(ev), ""]
    adopt = [f for f, r in ev.items() if verdict(r) == "채택 후보"]
    if adopt:
        lines.append("**요청(코디네이터):** " + ", ".join(NAMES[f] for f in adopt) + " — 채택 기준을 넘었습니다. "
                     "`docs/lab/sql/features.sql`의 `lab_scored`에 기본 0인 인자로 넣고 라인업 표를 랩 데이터로 내보낸 뒤 "
                     "`score_tune.GRID`에 넣어 다시 고르는 것을 요청합니다(앱 기본값은 사용자 확인 뒤).")
    else:
        lines.append("**결론:** 채택 기준을 넘는 특징이 없습니다. 라인업 역할은 **점수에 넣지 않고 화면 정보로만** 씁니다"
                     "(팀 상세의 공연 기록에 '단독'·'헤드라이너' 표시, 전환 날짜).")
    return lines + [""]


def _reading(ev: dict) -> str:
    """가중치 방향과 크기를 숫자에 맞춰 풀어 쓴다."""
    parts = []
    for f, r in ev.items():
        gain = r["cv_mean"] - r["base_mean"]
        picks = list(r["picks"].values())
        sign = "음수" if all(w < 0 for w in picks) else "양수" if all(w > 0 for w in picks) else \
            "0" if all(w == 0 for w in picks) else "기준일마다 다름"
        worse = " — 95% 구간이 모두 0 아래: 더하면 나빠진다는 것이 분명" if r["boot"][2] < 0 else ""
        parts.append(f"'{NAMES[f]}' {gain:+.3f}(가중치 {sign}, 정답 팀 평균 {r['desc']['hit_mean']:.2f} vs 아닌 팀 "
                     f"{r['desc']['non_mean']:.2f}{worse})")
    return ("**읽는 법:** " + "; ".join(parts) + ". 정답 팀이 단독·헤드라이너 공연을 더 많이 했어도, 그 정보는 이미 v2에 들어 있는 "
            "상상마당 출처(대부분 단독 공연)·공연장 다양성과 겹쳐, 더하면 순위를 흔들기만 합니다. 0.002 안쪽 차이는 대부분 "
            "v2 점수가 같은 팀끼리의 순서를 바꾼 효과입니다.")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="라인업 역할 → docs/lab/data/lineup_roles.csv · docs/lineup_roles.md")
    ap.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    ap.add_argument("--data-dir", type=Path, default=lab_sql.DATA_DIR)
    ap.add_argument("--csv", type=Path, default=CSV_OUT, help="앱 데이터 경로 (21~23시엔 다른 곳으로)")
    ap.add_argument("--doc", type=Path, default=DOC)
    ap.add_argument("--no-eval", action="store_true")
    ap.add_argument("--data-only", action="store_true", help="앱 데이터(CSV)만 — 문서·교차 검증 없이 (매일 실행용)")
    args = ap.parse_args(argv)
    if args.data_only:
        args.no_eval, args.doc = True, None
    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    import venue_ladder as vl

    args = parse_args(argv)
    gigs = load_raw(args.raw_dir)
    as_of = vl.data_end(args.data_dir)
    sources = discovery_sources()
    rows = team_roles(gigs, as_of)
    write_csv(rows, args.csv)
    if args.doc:
        ev = None if args.no_eval else evaluate(args.data_dir, gigs, sources)
        args.doc.write_text(render(order_survey(_usable(gigs, None, as_of, True)), rows, ev, as_of, sources),
                            encoding="utf-8")
    print(f"공연 {len(gigs):,}건 · 팀 {len(rows):,} · 서포트→헤드라이너 전환 {sum(r['support_to_headline'] for r in rows):,}팀")
    print(f"✅ → {args.csv}" + (f", {args.doc}" if args.doc else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
