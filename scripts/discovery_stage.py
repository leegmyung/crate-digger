"""발굴 단계·단계 안 모멘텀 성적표 → docs/discovery_stage.md

경쟁 서비스(Chartmetric)의 '경력 단계'와 '같은 단계 안 모멘텀'을 우리 데이터로 옮겨서,
과거 기준일 6개에서 각 단계 팀이 이후 정답을 받은 비율(단계가 '다음 정답'을 얼마나 가르나)과
단계 안 모멘텀 상위가 정답률이 높은지를 잰다. 점수는 바꾸지 않는다(화면 칸·필터용 제안).
계산은 docs/lab/sql/discovery_stage.sql 한 곳에만 있다.

실행: .venv/bin/python scripts/discovery_stage.py [--data-dir 폴더] [--as-of YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab_sql  # noqa: E402
import score_tune as st  # noqa: E402

OUT = lab_sql.ROOT / "docs" / "discovery_stage.md"
SQL = "discovery_stage.sql"
STAGES: Tuple[Tuple[int, str, str], ...] = (
    (0, "백지", "첫 발매(자기 발매)만, 남의 언급 없음"),
    (1, "첫 신호", "남의 언급 1갈래 (공연·큐레이션·선정·지원 중)"),
    (2, "여러 갈래", "남의 언급 2갈래 이상"),
    (3, "선정·중간 정답", "선정 단계 3(선정) 이상(DMZ 제외) 또는 B등급 정답"),
    (4, "졸업", "S·A등급 정답 또는 유명 팀(유명 판정은 2026-11-26 이후 기준일만)"),
)
LABELS = {s: name for s, name, _ in STAGES}
MOMENTUM_STAGES = (1, 2, 3)      # 백지는 언급이 없고, 졸업은 후보가 아니라 모멘텀 비교에서 뺀다
TOP_SHARE = 0.2                  # 단계 안 모멘텀 상위 20%
Z = 1.96                         # 95% 구간
MIN_TEAMS = 20                   # 이보다 적으면 '표본 부족'
EXAMPLES = 5                     # 오늘 기준 예시 팀 수


# ---------- 계산 ----------

def stage_rows(con, as_of: str, horizon: int = st.HORIZON_MONTHS) -> List[dict]:
    return lab_sql.query(con, SQL, as_of=f"'{as_of}'", horizon_months=str(horizon))


def wilson(k: int, n: int) -> Tuple[Optional[float], Optional[float]]:
    """정답 비율 k/n 의 95% 윌슨 구간(%). 표본이 작아도 0 아래·100 위로 안 나간다."""
    if n == 0:
        return None, None
    p = k / n
    den = 1 + Z * Z / n
    mid = (p + Z * Z / (2 * n)) / den
    half = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / den
    return 100 * max(0.0, mid - half), 100 * min(1.0, mid + half)


def _group(rows: Sequence[dict]) -> dict:
    n = len(rows)
    hits = sum(int(r["is_hit"]) for r in rows)
    hits_sa = sum(int(r["hit_sa"]) for r in rows)
    lo, hi = wilson(hits, n)
    return {"teams": n, "hits": hits, "hits_sa": hits_sa,
            "rate": 100 * hits / n if n else None, "rate_sa": 100 * hits_sa / n if n else None, "lo": lo, "hi": hi}


def stage_summary(rows: Sequence[dict]) -> List[dict]:
    """단계 0~4마다 팀 수·정답·S·A 정답·정답률(빈 단계도 줄을 남긴다)."""
    return [{"stage": s, **_group([r for r in rows if r["stage"] == s])} for s, _, _ in STAGES]


def momentum_split(rows: Sequence[dict], top_share: float = TOP_SHARE) -> Tuple[dict, dict]:
    """단계 안 모멘텀 백분위 상위(1 − top_share 이상) 대 나머지."""
    scored = [r for r in rows if r.get("momentum_pct") is not None]
    top = [r for r in scored if float(r["momentum_pct"]) >= 1 - top_share]
    rest = [r for r in scored if float(r["momentum_pct"]) < 1 - top_share]
    return _group(top), _group(rest)


def direction_split(rows: Sequence[dict]) -> Dict[str, dict]:
    """모멘텀 방향(최근 90일 언급이 그 전 90일보다 많음·같음·적음)별."""
    def direction(m: float) -> str:
        return "상승" if m > 0 else ("하락" if m < 0 else "보합")
    scored = [r for r in rows if r.get("momentum") is not None]
    return {d: _group([r for r in scored if direction(float(r["momentum"])) == d]) for d in ("상승", "보합", "하락")}


def stage_auc(rows: Sequence[dict]) -> Optional[float]:
    """단계 숫자만으로 줄 세웠을 때 정답 팀이 더 위에 있을 확률(동점은 절반)."""
    return st.auc([float(r["stage"]) for r in rows], [int(r["is_hit"]) for r in rows])


def momentum_auc(rows: Sequence[dict]) -> Optional[float]:
    scored = [r for r in rows if r.get("momentum") is not None]
    return st.auc([float(r["momentum"]) for r in scored], [int(r["is_hit"]) for r in scored])


# ---------- 문서 ----------

def _pct(v: Optional[float], digits: int = 1) -> str:
    return "—" if v is None else f"{v:.{digits}f}%"


def _ci(g: dict) -> str:
    if g["lo"] is None:
        return "—"
    note = " (표본 부족)" if g["teams"] < MIN_TEAMS else ""
    return f"{g['lo']:.1f}~{g['hi']:.1f}%{note}"


def _f(v: Optional[float]) -> str:
    return "—" if v is None else f"{v:.3f}"


def summary_table(rows: Sequence[dict]) -> List[str]:
    out = ["| 단계 | 팀 (기준일 6개 합) | 이후 정답 | 정답률 | 95% 구간 | 이후 S·A 정답 | S·A 정답률 |",
           "|---|---|---|---|---|---|---|"]
    for g in stage_summary(rows):
        out.append(f"| {g['stage']} {LABELS[g['stage']]} | {g['teams']:,} | {g['hits']} | {_pct(g['rate'])} | {_ci(g)} | "
                   f"{g['hits_sa']} | {_pct(g['rate_sa'])} |")
    return out


def per_cut_table(per_cut: Dict[str, List[dict]]) -> List[str]:
    out = ["| 기준일 | " + " | ".join(f"{s} {LABELS[s]}" for s, _, _ in STAGES) + " |",
           "|---" * (len(STAGES) + 1) + "|"]
    for c, rows in per_cut.items():
        cells = [f"{g['teams']:,} / {g['hits']}" for g in stage_summary(rows)]
        out.append(f"| {c} | " + " | ".join(cells) + " |")
    return out


def momentum_table(rows: Sequence[dict]) -> List[str]:
    out = ["| 단계 | 모멘텀 상위 20% (팀 / 정답 / 정답률) | 나머지 | 상승 | 보합 | 하락 | 단계 안 모멘텀 AUC |",
           "|---|---|---|---|---|---|---|"]

    def cell(g: dict) -> str:
        return f"{g['teams']:,} / {g['hits']} / {_pct(g['rate'])}"
    for s in MOMENTUM_STAGES:
        sub = [r for r in rows if r["stage"] == s]
        top, rest = momentum_split(sub)
        d = direction_split(sub)
        out.append(f"| {s} {LABELS[s]} | {cell(top)} | {cell(rest)} | {cell(d['상승'])} | {cell(d['보합'])} | "
                   f"{cell(d['하락'])} | {_f(momentum_auc(sub))} |")
    return out


def profile_only(rows: Sequence[dict]) -> List[dict]:
    return [r for r in rows if r.get("first_release") is not None]


def today_section(rows: Sequence[dict], today: str) -> List[str]:
    out = [f"## 5. 오늘({today}) 기준 단계 분포", "",
           "| 단계 | 팀 | 모멘텀 상승 | 보합 | 하락 |", "|---|---|---|---|---|"]
    for s, name, _ in STAGES:
        sub = [r for r in rows if r["stage"] == s]
        if s == 0 or s == 4:
            out.append(f"| {s} {name} | {len(sub):,} | — | — | — |")
            continue
        d = direction_split(sub)
        out.append(f"| {s} {name} | {len(sub):,} | {d['상승']['teams']:,} | {d['보합']['teams']:,} | {d['하락']['teams']:,} |")
    out += ["", f"**단계 안 모멘텀 상위 예시** (최근 90일 남의 언급이 많이 는 팀, 단계마다 {EXAMPLES}팀):", ""]
    for s in (3, 2, 1):
        sub = sorted([r for r in rows if r["stage"] == s and r.get("momentum") is not None],
                     key=lambda r: (-float(r["momentum"]), -int(r["recent_n"]), r["team_key"]))[:EXAMPLES]
        names = ", ".join(f"{r['display_name']}({r['prev_n']}→{r['recent_n']})" for r in sub) or "—"
        out.append(f"- {s} {LABELS[s]}: {names}")
    return out + [""]


def _ratio(a: Optional[float], b: Optional[float]) -> str:
    return "—" if not a or not b else f"{a / b:.1f}배"


def _rising(vals: Sequence[Optional[float]]) -> bool:
    """값이 모두 있고 앞에서 뒤로 커지면(같아도 됨) 참."""
    return all(v is not None for v in vals) and all(a <= b for a, b in zip(vals, vals[1:]))


def _overlap(a: dict, b: dict) -> bool:
    return a["lo"] is not None and b["lo"] is not None and a["lo"] <= b["hi"] and b["lo"] <= a["hi"]


def key_findings(pooled: Sequence[dict]) -> List[str]:
    """맨 위 요약: 숫자는 모두 이번 계산에서 나온 값, 문장도 숫자에 따라 바뀐다(데이터가 바뀌면 다시 생성)."""
    by = {g["stage"]: g for g in stage_summary(pooled)}
    multi = _group([r for r in pooled if r["stage"] in (2, 3)])
    prof = {g["stage"]: g for g in stage_summary(profile_only(pooled))}
    rates = [by[s]["rate"] for s in (1, 2, 3)]
    head = "**단계는 다음 정답을 가릅니다.**" if _rising(rates) else "**단계 순서와 정답률이 딱 맞지는 않습니다.**"
    prates = [prof[s]["rate"] for s in (0, 1, 2, 3)]
    same = "봐도 순서가 같습니다" if _rising(prates) else "보면 순서가 일부 뒤집힙니다"
    lines = ["## 요약", "",
             f"- {head} 이후 정답률: 첫 신호 {_pct(by[1]['rate'])} → 여러 갈래 {_pct(by[2]['rate'])} → "
             f"선정·중간 정답 {_pct(by[3]['rate'])}. 2단계 이상은 첫 신호의 {_ratio(multi['rate'], by[1]['rate'])}입니다.",
             f"- 같은 치우침끼리(첫 발매일이 있는 팀만) {same}: 백지 {_pct(prof[0]['rate'])} → 첫 신호 {_pct(prof[1]['rate'])} → "
             f"여러 갈래 {_pct(prof[2]['rate'])} → 선정·중간 정답 {_pct(prof[3]['rate'])}."]
    if _overlap(by[2], by[3]):
        lines.append(f"- 다만 **여러 갈래와 선정·중간 정답은 구별되지 않습니다**({_pct(by[2]['rate'])} 대 {_pct(by[3]['rate'])}, "
                     "95% 구간이 겹침). 큰 차이는 '1갈래 → 2갈래 이상'에서 납니다.")
    for s in (1, 2):
        sub = [r for r in pooled if r["stage"] == s]
        top, rest = momentum_split(sub)
        d = direction_split(sub)
        active = _group([r for r in sub if r.get("momentum") is not None and float(r["momentum"]) != 0])
        line = (f"- {LABELS[s]} 단계 안 모멘텀 상위 20%: 정답률 {_pct(top['rate'])} 대 나머지 {_pct(rest['rate'])}"
                f" ({_ratio(top['rate'], rest['rate'])}, 단계 안 AUC {_f(momentum_auc(sub))}). "
                f"보합(대부분 최근 반년 언급 없음) {_pct(d['보합']['rate'])} 대 상승·하락(최근 반년 언급 있음) {_pct(active['rate'])}")
        down, flat = d["하락"]["rate"], d["보합"]["rate"]
        if down is not None and flat is not None and down > flat:
            line += " — 줄어드는 팀(하락)도 보합보다 높아서, **방향보다 '최근 반년 안에 누가 다뤘나'가 더 가릅니다.**"
        lines.append(line)
    lines += ["- 결론: 단계·모멘텀은 **점수에 넣지 않고**(점수 v2가 이미 갈래 수·선정 단계를 씀) 후보 목록의 **칩 필터·정렬·배지**로 씁니다.", ""]
    return lines


def render(per_cut: Dict[str, List[dict]], today_rows: Sequence[dict], today: str) -> List[str]:
    pooled = [r for rows in per_cut.values() for r in rows]
    cand = [r for r in pooled if r["stage"] in MOMENTUM_STAGES]
    base = _group(pooled)
    cuts = list(per_cut)
    lines = [
        "# 발굴 단계와 단계 안 모멘텀 — 단계가 '다음 정답'을 얼마나 가르나", "",
        "_자동 생성: `.venv/bin/python scripts/discovery_stage.py` · 계산식: [`discovery_stage.sql`](lab/sql/discovery_stage.sql)_", "",
        "**왜 만들었나**: Chartmetric은 아티스트를 '경력 단계'(지난 1년 점수 중앙값으로 나눈 순위 구간)로 나누고, "
        "'성장'은 **같은 단계 안에서만** 비교합니다([경쟁 서비스 조사](research_2026-11-27_competitor_logic.md) B1·D3). "
        "예측 모델이 아니라 **사람이 고르기 쉽게 나누는 화면 장치**입니다. 우리 [점수 새 특징 실험](feature_lab.md)에서도 "
        "'신호 가속도'·'선정 단계 상승'은 점수를 올리지 못했으므로, 이것도 **점수에 넣지 않고 화면 칸·필터로** 쓰는 안입니다.", "",
        *key_findings(pooled),
        "## 1. 정의 (기준일 '전' 정보만 — 미래 정보 누수 없음)", "",
        "| 단계 | 이름 | 조건 (위 단계가 우선) |", "|---|---|---|",
        *[f"| {s} | {name} | {rule} |" for s, name, rule in reversed(STAGES)], "",
        "- **남의 언급** = 자기 발매(발매 갈래)가 아닌 신호. 제외 출처·DMZ 라인업은 빼고, 맥락·검증 대기 출처는 셉니다"
        "(점수와 달리 '누가 다뤘나'라는 사실만 봄). [데뷔 코호트](debut_cohort.md)의 '언급'과 같은 정의입니다.",
        "- **후보 범위**: 신인(프로필 첫 발매일 우선, 없으면 우리 데이터 첫 등장이 기준일 전 3년 안)이고 기준일에 이미 알려진 팀.",
        "- **단계는 '최고 도달'** 이라 한 번 오르면 내려가지 않습니다 — Chartmetric이 1년 중앙값으로 하루하루 튀는 값을 누른 것과 같은 효과.",
        "- **단계 안 모멘텀** = ln(1+최근 90일 남의 언급 수) − ln(1+그 전 90일). 같은 단계 팀끼리만 백분위(0~1)를 매깁니다. "
        "방향: 상승(최근이 더 많음)·보합·하락. 백지는 언급이 없어 모멘텀이 없습니다.",
        f"- **채점**: 기준일 뒤 {st.HORIZON_MONTHS}개월 안 센 정답(같은 집안 정답 제외, [methods](methods.md)와 같음). "
        f"기준일 {len(cuts)}개({', '.join(cuts)}) — 점수 검증과 같은 기준일. 한 팀이 여러 기준일에 들어갈 수 있어 합계는 '팀×기준일' 수입니다.", "",
        "## 2. 단계별 팀 수와 이후 정답률 (기준일 6개 합)", "",
        *summary_table(pooled), "",
        f"- 전체 {base['teams']:,}팀×기준일 중 이후 정답 {base['hits']} (기준율 {_pct(base['rate'], 2)}).",
        f"- 단계 숫자만으로 줄 세운 AUC(정답 팀이 더 높은 단계일 확률): 전체 {_f(stage_auc(pooled))}, "
        f"후보 단계(1~3)만 {_f(stage_auc(cand))}. 참고로 점수 v2의 교차 검증 AUC는 약 0.78입니다([methods](methods.md)).",
        "- **0 백지의 정답률은 그대로 믿으면 안 됩니다.** 백지는 '첫 발매일'이 있어야 판정되는데, 첫 발매일(멜론·스포티파이 프로필)은 "
        "정답 팀과 상위 후보 위주로 모았습니다. 그래서 백지 칸에는 '나중에 정답 받은 팀'이 몰려 있습니다(아래 3절 참고).",
        "- **4 졸업**은 이미 S·A 정답을 받은 팀이라 후보가 아닙니다. 이후 정답률은 '한 번 받은 팀이 또 받는 비율'입니다.", "",
        "**기준일별 (팀 / 이후 정답)**", "", *per_cut_table(per_cut), "",
        "## 3. 같은 조건끼리 비교 — 프로필(첫 발매일)이 있는 팀만", "",
        "첫 발매일이 있는 팀만 남기면 모든 단계가 같은 '정답 팀 위주로 모은' 치우침을 갖게 되어, 단계끼리는 공정하게 견줄 수 있습니다(절대 비율은 높게 나옴).", "",
        *summary_table(profile_only(pooled)), "",
        "## 4. 단계 안 모멘텀 상위가 정답률이 높은가 (기준일 6개 합)", "",
        *momentum_table(pooled), "",
        "- '상위 20%'는 같은 단계 안 백분위 0.8 이상. 언급이 없는 팀(보합 0→0)이 많아 동점이 많고, 그래서 상위 20%에 든 팀 수가 정확히 20%는 아닙니다.",
        "- 단계 안 모멘텀 AUC가 0.5 근처면 '같은 단계 안에서 최근 언급이 는 팀이 더 잘 되지는 않는다'는 뜻입니다.", "",
        *today_section(today_rows, today),
        "## 6. 읽는 법과 앱 반영 제안", "",
        "- 단계는 **'지금 어디쯤인가'** 를 한 단어로 보여 주는 칸입니다. 정답률 차이가 있어도 점수(v2)가 이미 갈래 수·선정 단계를 쓰고 있어, "
        "단계를 점수에 또 더하면 같은 정보를 두 번 세는 것이 됩니다 → **점수에는 넣지 않습니다.**",
        "- 모멘텀은 같은 단계 안에서 '요즘 움직이는 팀'을 먼저 보게 하는 정렬·배지입니다. 정답을 더 잘 맞힌다는 근거가 약하면(4절) "
        "'예측'이 아니라 '최근 활동'이라고 이름 붙여야 정직합니다.",
        "- 앱 제안(안티그래비티 담당, 요청으로 전달): ① 후보 목록 위 **단계 칩 필터**(백지·첫 신호·여러 갈래·선정·중간 정답, 졸업은 기본 숨김) "
        "② 팀 상세 머리에 **단계 배지 + 다음 단계 조건**(예: '여러 갈래 — 선정 단계 3 이상이면 다음 단계') "
        "③ 후보 표에 **'단계 안 모멘텀' 칸**(백분위 + 상승/보합/하락 화살표, 최근 90일 대 그 전 90일 언급 수를 말풍선으로). "
        "계산은 이 SQL을 그대로 쓰면 앱과 문서의 정의가 같아집니다.", "",
        "## 7. 한계", "",
        "- 정답 표본이 작습니다(기준일마다 수십 팀). 95% 구간이 넓은 칸은 방향만 읽습니다.",
        "- 공연 기록은 2024년부터 두꺼워져서, 이른 기준일일수록 '여러 갈래' 팀이 적습니다.",
        "- 발매·인스타 출처는 2026-11부터만 있어 과거 기준일의 백지·모멘텀에는 거의 영향이 없고, 오늘 기준에는 영향이 큽니다"
        "(오늘의 모멘텀은 수집 시작 효과로 '상승'이 부풀 수 있음).",
        "- 단계는 우리 데이터가 본 것만 셉니다. 우리가 모으지 않는 곳(방송·스트리밍 차트)에서 이미 큰 팀은 낮은 단계로 보일 수 있습니다.",
        "- '첫 신호'가 후보의 90% 이상(대부분 공연 1갈래)이라 칩 하나로는 잘 안 좁혀집니다. 이 칸 안에서는 모멘텀(최근 언급) 정렬이 사실상 주 도구입니다.", "",
    ]
    return lines


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data-dir", type=Path, default=lab_sql.DATA_DIR)
    ap.add_argument("--as-of", default=None, help="오늘 기준일 (기본: 데이터 meta.json 의 data_end)")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    today = args.as_of
    if today is None:
        meta = args.data_dir / "meta.json"
        today = json.loads(meta.read_text(encoding="utf-8")).get("data_end") if meta.exists() else None
    if not today:
        print("❌ 오늘 기준일을 알 수 없음: --as-of 를 주세요", file=sys.stderr)
        return 1
    con = lab_sql.connect(args.data_dir)
    per_cut = {c: stage_rows(con, c) for c in st.CUTOFFS}
    lines = render(per_cut, stage_rows(con, today), today)
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"✅ → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
