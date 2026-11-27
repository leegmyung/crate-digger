"""무대·라이브 세션 채널 출연 평가 → docs/live_sessions.md (계산만 — config·features.sql·랩 데이터는 바꾸지 않음)

config/video_channels.json 채널(EBS 스페이스 공감·딩고·it's Live·KBS Kpop·목캔디·난장·온스테이지·Tiny Desk Korea)의 무대 영상은
지금 signals 에 들어가지 않는다. 그래서 '출연'을 임시 '큐레이션' 신호(출처 video_<채널>)로 만들어 메모리 안의 DuckDB 에만 더한 뒤
출처 성적표(source_scorecard.sql)·데뷔 코호트(source_scorecard_debut.sql)·점수 교차 검증(score_tune·feature_lab)을 같은 계산식으로 잰다.

- 영상: 원본 data/raw/raw_video_*.csv 전체 (2021-01 까지 백필, 2026-11-28). 앱용 videos.csv 는 팀당 6개(최신순)라 옛 출연이 잘려서
  평가에는 쓰지 않고, 같은 거르기 규칙(export_lab_data.video_rows + video_match)을 팀당 개수 제한 없이 적용한다.
- 날짜 = 영상 업로드일(실제 출연·녹화일보다 늦을 수 있음 → '먼저 짚었다'를 덜 세는 쪽).
- 같은 집안: EBS 스페이스 공감 ↔ EBS 헬로루키(월간·올해의) — 정답 발표 전에 그 채널에 나온 팀의 헬로루키 정답은 적중으로 세지 않음.
- 점수 교차 검증 두 가지: (가) 신호로 넣기 — 발굴(discovery)·맥락(context) 역할로 signals 에 더하고 점수 v2 를 6개 기준일에 채점,
  (나) 특징으로 넣기 — 후보군·정답은 그대로 두고 '기준일 전 3년 안에 나온 영상 채널 수'를 feature_lab 규칙(기준일 하나 빼고 가중치 고르기,
  짝 부트스트랩, 채택 기준 +0.005·구간 하한 > 0·상위 50 적중 안 줄기)으로.

실행: .venv/bin/python scripts/live_sessions.py [--data-dir 폴더] [--raw-dir 폴더] [--out 문서]
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab_sql  # noqa: E402
import score_tune as st  # noqa: E402

OUT = lab_sql.ROOT / "docs" / "live_sessions.md"
CHANNELS = {   # videos.csv channel_title → 임시 출처 키
    "스페이스 공감": "video_ebs_space", "it's Live": "video_its_live", "딩고 뮤직 / dingo music": "video_dingo",
    "목캔디의 인디밴드 라이브": "video_mokcandy", "KBS Kpop": "video_kbs_kpop", "문화콘서트난장 Real K-Music": "video_nanjang",
    "ONSTAGE 온스테이지": "video_onstage", "온스테이지 ONSTAGE": "video_onstage", "Tiny Desk Korea": "video_tinydesk_kr",
}
LABELS = {"video_ebs_space": "EBS 스페이스 공감", "video_its_live": "it's Live", "video_dingo": "딩고 뮤직",
          "video_mokcandy": "목캔디의 인디밴드 라이브", "video_kbs_kpop": "KBS Kpop (스케치북·더 시즌즈)",
          "video_nanjang": "문화콘서트 난장", "video_onstage": "온스테이지", "video_tinydesk_kr": "Tiny Desk Korea"}
SAME_HOUSE = {"video_ebs_space": {"hello_rookie", "hello_rookie_year"}}   # 같은 방송사(EBS) — 스페이스 공감 ↔ 헬로루키
RAW_DIR = lab_sql.ROOT / "data" / "raw"
CV_CUTOFFS = st.CUTOFFS                 # 점수 검증 기준일 6개 (2023-01-01 ~ 2025-07-01)
CV_SINCE = "2022-07-01"                 # 수상 팀(먼저 잡았나)은 첫 기준일 반년 전부터 (source_review 와 같은 규칙)
HORIZON = st.HORIZON_MONTHS             # 기준일 뒤 24개월 안 정답 = 적중
LOOKBACK_YEARS = 3
IDOL_HEAVY = {"video_kbs_kpop", "video_its_live"}   # 아이돌·기성 가수 무대가 대부분인 채널
MIN_TEAMS = 20                          # source_review 와 같은 기준: 후보 20팀 미만이면 표본 부족
PROMOTE_LIFT = 2.0                      # 기준선의 2배 이상 맞히거나 …
PROMOTE_MIN_ONLY = 3                    # … 이 채널만 잡은 수상 팀 3팀 이상(정확도 기준선 이상)이면 발굴 후보
ADOPT_MIN_GAIN = 0.005                  # feature_lab 채택 기준
REFERENCE_SOURCES = ("공연:indistreet", "공연:sangsangmadang", "큐레이션:musicy", "큐레이션:izm", "큐레이션:visla")


KEYWORDS = (("온스테이지", "video_onstage"), ("onstage", "video_onstage"), ("스페이스 공감", "video_ebs_space"),
            ("dingo", "video_dingo"), ("딩고", "video_dingo"), ("it's live", "video_its_live"), ("목캔디", "video_mokcandy"),
            ("난장", "video_nanjang"), ("tiny desk", "video_tinydesk_kr"), ("kbs kpop", "video_kbs_kpop"))


def channel_source(title: str) -> Optional[str]:
    """채널 이름 → 임시 출처 키. 정확히 같은 이름이 없으면 낱말로(백필로 들어올 채널의 API 이름을 미리 모름)."""
    if title in CHANNELS:
        return CHANNELS[title]
    low = (title or "").lower()
    return next((src for kw, src in KEYWORDS if kw in low), None)


def src_key(source: str) -> str:
    return f"큐레이션:{source}"


def video_signal_rows(videos: Iterable[dict], role: str = "discovery") -> List[dict]:
    """무대 영상(kind=stage, 알려진 채널) → 임시 신호 (같은 팀·채널·날짜는 한 줄)."""
    seen, out = set(), []
    for v in videos:
        src = channel_source(v.get("channel_title", ""))
        if v.get("kind") != "stage" or not src or not v.get("published_at"):
            continue
        key = (v["team_key"], src, v["published_at"][:10])
        if key in seen:
            continue
        seen.add(key)
        out.append({"team_key": key[0], "branch": "큐레이션", "source": src, "program": src, "stage_rank": None,
                    "signal_date": key[2], "venue": "", "role": role})
    return out


def same_house_tags(outcomes: Iterable[dict], signals: Sequence[dict]) -> Set[Tuple[str, str, date]]:
    """같은 집안 짝 채널에 정답 발표 '전에' 나온 팀의 짝 정답 → (팀, 프로그램, 발표일)."""
    first: Dict[Tuple[str, str], date] = {}
    for s in signals:
        if s["source"] in SAME_HOUSE:
            d = date.fromisoformat(s["signal_date"])
            k = (s["team_key"], s["source"])
            first[k] = min(first.get(k, d), d)
    tags = set()
    for o in outcomes:
        for src, programs in SAME_HOUSE.items():
            d0 = first.get((o["team_key"], src))
            if o["program"] in programs and d0 and d0 < o["announced_date"]:
                tags.add((o["team_key"], o["program"], o["announced_date"]))
    return tags


def channel_coverage(videos: Iterable[dict]) -> List[dict]:
    agg: Dict[str, dict] = defaultdict(lambda: {"videos": 0, "teams": set(), "dates": []})
    for v in videos:
        src = channel_source(v.get("channel_title", ""))
        if v.get("kind") == "stage" and src:
            a = agg[src]
            a["videos"] += 1
            a["teams"].add(v["team_key"])
            a["dates"].append(v["published_at"][:10])
    return [{"source": s, "videos": a["videos"], "teams": len(a["teams"]), "first": min(a["dates"]), "last": max(a["dates"])}
            for s, a in sorted(agg.items(), key=lambda kv: -kv[1]["videos"])]


# ---------- 영상 → 신호·특징 ----------

def stage_videos(raw: Sequence[dict]) -> List[dict]:
    """원본 영상 줄 → 내보내기와 같은 거르기(흔한 낱말·짧은 이름·인터뷰·쇼츠·KBS 비무대)를 팀당 개수 제한 없이."""
    import export_lab_data as ex
    return ex.video_rows(list(raw), per_team=10 ** 9)


def load_stage_videos(raw_dir: Path = RAW_DIR) -> List[dict]:
    import export_lab_data as ex
    return stage_videos(ex._raw_videos(raw_dir))


def video_feature(signals: Iterable[dict], cutoff: str, sources: Optional[Set[str]] = None,
                  years: int = LOOKBACK_YEARS) -> Dict[str, float]:
    """팀별 '기준일 전 years 년 안에 나온 영상 채널 수' (기준일 뒤 영상은 안 봄)."""
    c = date.fromisoformat(cutoff)
    lo = c.replace(year=c.year - years)
    seen: Dict[str, Set[str]] = defaultdict(set)
    for s in signals:
        d = date.fromisoformat(s["signal_date"][:10])
        if lo <= d < c and (sources is None or s["source"] in sources):
            seen[s["team_key"]].add(s["source"])
    return {t: float(len(v)) for t, v in seen.items()}


def judge_channel(r: Optional[dict]) -> Tuple[str, str]:
    """6개 기준일 성적표 한 줄 → (역할 제안, 근거). source_review 의 승격·강등 기준을 채널에 그대로."""
    r = r or {}
    teams, only = int(r.get("teams") or 0), int(r.get("only_source") or 0)
    lift = r.get("lift")
    lift = None if lift in (None, "") else float(lift)
    nums = f"후보 {teams}팀·적중 {r.get('hits') or 0}·배수 {'—' if lift is None else f'{lift:g}'}·유일 기여 {only}팀"
    if teams < MIN_TEAMS or lift is None:
        return "pending", f"표본 부족 ({nums})"
    if lift >= PROMOTE_LIFT or (only >= PROMOTE_MIN_ONLY and lift >= 1.0):
        return "discovery", f"기준선보다 잘 맞히거나 이 채널만 짚은 수상 팀이 있음 ({nums})"
    if lift >= 1.0:
        return "context", f"기준선 이상이지만 발굴 근거(배수 {PROMOTE_LIFT:g}·유일 {PROMOTE_MIN_ONLY}팀)는 못 미침 ({nums})"
    if only == 0:
        return "excluded", f"기준선보다 못 맞히고 이 채널만 짚은 수상 팀도 없음 ({nums})"
    return "context", f"기준선보다 못 맞히지만 이 채널만 짚은 수상 팀이 있음 ({nums})"


# ---------- DuckDB (메모리 안에서만) ----------

def insert_signals(con, rows: Sequence[dict]) -> int:
    con.executemany("INSERT INTO signals (team_key, branch, source, program, stage_rank, signal_date, venue, role) "
                    "VALUES (?, ?, ?, ?, ?, CAST(? AS DATE), ?, ?)",
                    [(r["team_key"], r["branch"], r["source"], r["program"], r["stage_rank"], r["signal_date"], r["venue"],
                      r["role"]) for r in rows])
    return len(rows)


def mark_same_house(con, rows: Sequence[dict]) -> int:
    """같은 집안 정답(스페이스 공감 출연 뒤 헬로루키)에 표시 — 출처 성적표와 점수 적중 둘 다에서 빠진다."""
    outs = [{"team_key": t, "program": p, "announced_date": d} for t, p, d in
            con.execute("SELECT team_key, program, CAST(announced_date AS DATE) FROM outcomes WHERE announced_date IS NOT NULL").fetchall()]
    tags = same_house_tags(outs, rows)
    for t, p, d in tags:
        src = next(s for s, ps in SAME_HOUSE.items() if p in ps)
        con.execute("UPDATE outcomes SET same_house_sources = CASE WHEN COALESCE(same_house_sources, '') = '' THEN ? "
                    "ELSE same_house_sources || ';' || ? END, same_house_scored = true "
                    "WHERE team_key = ? AND program = ? AND CAST(announced_date AS DATE) = ?",
                    [src_key(src), src_key(src), t, p, d])
    return len(tags)


def add_video_signals(con, rows: Sequence[dict]) -> int:
    """메모리 DuckDB 의 signals 에 임시 행을 더하고, 같은 집안 정답에 표시한다 (파일은 안 건드림)."""
    n = insert_signals(con, rows)
    mark_same_house(con, rows)
    return n


def cutoffs_sql(cuts: Sequence[str]) -> str:
    return ",".join(f"(DATE '{c}')" for c in cuts)


def scorecard(con, cuts: Sequence[str], since: str) -> List[dict]:
    return lab_sql.query(con, "source_scorecard.sql", cutoffs=cutoffs_sql(cuts), horizon_months=str(HORIZON), since=f"'{since}'")


def debut(con, cuts: Sequence[str]) -> List[dict]:
    return lab_sql.query(con, "source_scorecard_debut.sql", cutoffs=cutoffs_sql(cuts), mention_months="6",
                         horizon_months=str(HORIZON))


def v2_eval(con) -> Dict[str, dict]:
    w2 = {k: float(lab_sql.DEFAULTS[k]) for k, _ in st.V0_WEIGHTS}
    return st.evaluate({c: st.features(con, c) for c in CV_CUTOFFS}, w2)


def feature_cv(con, signals: Sequence[dict], feats: Dict[str, Optional[Set[str]]]) -> Dict[str, dict]:
    """특징으로 넣기 — feature_lab 과 같은 교차 검증·부트스트랩·채택 기준. 후보군·정답은 con 그대로."""
    import feature_lab as fl
    data = {c: st.features(con, c) for c in CV_CUTOFFS}
    out = {}
    for name, sources in feats.items():
        extra = {c: {t: {name: v} for t, v in video_feature(signals, c, sources).items()} for c in CV_CUTOFFS}
        best = None
        for grid in (fl.GRID, fl.GRID_FINE):
            res = fl.evaluate_feature(data, extra, name, grid)
            if best is None or res["cv_mean"] > best["cv_mean"]:
                best = {**res, "grid": grid}
        diff, lo, hi = fl.bootstrap_diff(data, best)
        gain = best["cv_mean"] - best["base_mean"]
        adopt = gain >= ADOPT_MIN_GAIN and lo > 0 and best["cv_hits"]["hits50"] >= best["base_hits"]["hits50"]
        out[name] = {"res": best, "diff": diff, "lo": lo, "hi": hi, "gain": gain, "adopt": adopt,
                     "desc": fl.describe(data, extra, name)}
    return out


def signals_before(rows: Sequence[dict], cutoff: str) -> int:
    return sum(1 for r in rows if r["signal_date"] < cutoff)


# ---------- 문서 ----------

def _f(v, nd=3) -> str:
    return "—" if v is None else (f"{v:.{nd}f}" if isinstance(v, float) else str(v))


def _mean(vals) -> Optional[float]:
    v = [x for x in vals if x is not None]
    return sum(v) / len(v) if v else None


def coverage_note(cov: dict) -> str:
    notes = []
    if cov["source"] == "video_kbs_kpop":
        notes.append("YouTube 업로드 목록이 최근 2만 개까지만 보여 줘서 2024-08 이후만 있음")
    if cov["first"] > "2022-01-01" and cov["source"] != "video_kbs_kpop":
        notes.append(f"채널 기록이 {cov['first'][:7]}부터라 앞쪽 기준일엔 신호 없음")
    if cov["last"] < "2025-01-01":
        notes.append(f"{cov['last'][:7]} 뒤로 업로드 없음(멈춘 채널)")
    return "; ".join(notes)


def _card_table(sc: List[dict], keys: Sequence[str]) -> List[str]:
    by = {r["src"]: r for r in sc}
    lines = ["| 출처 | 후보 팀 | 적중 | 적중률 | 배수 | 먼저 잡은 수상 팀 (가장 먼저 / 유일) | 선행 개월 |", "|---|---|---|---|---|---|---|"]
    for k in keys:
        r = by.get(k, {})
        name = LABELS.get(k.split(":", 1)[1], k)
        lines.append(f"| {name} | {r.get('teams', 0)} | {r.get('hits', 0)} | {_f(r.get('rate'), 2)} | {_f(r.get('lift'), 1)} | "
                     f"{r.get('winners_seen', 0)} ({r.get('first_to_see', 0)} / {r.get('only_source', 0)}) | {_f(r.get('median_lead_months'), 1)} |")
    return lines


def _base_rate(sc: List[dict]) -> Optional[float]:
    return next((r["base_rate"] for r in sc if r.get("base_rate") is not None), None)


def render(ctx: dict) -> str:
    cov, rows = ctx["cov"], ctx["rows"]
    chan_keys = [src_key(c["source"]) for c in cov]
    sc6, sc_recent = ctx["sc6"], ctx["sc_recent"]
    by6 = {r["src"]: r for r in sc6}
    base, disc, ctxt = ctx["v2_base"], ctx["v2_disc"], ctx["v2_ctx"]
    m = lambda e, k: _mean(e[c][k] for c in CV_CUTOFFS)
    s = lambda e, k: sum(e[c][k] for c in CV_CUTOFFS)
    fc = ctx["feature_cv"]
    roles = {c["source"]: judge_channel(by6.get(src_key(c["source"]))) for c in cov}
    counts = defaultdict(list)
    for c in cov:
        counts[roles[c["source"]][0]].append(LABELS.get(c["source"], c["source"]))
    adopt_any = any(v["adopt"] for v in fc.values())
    lines = ["# 무대·라이브 세션 채널 출연 — 나중 정답을 미리 알려 주나", "",
             "_자동 생성: `.venv/bin/python scripts/live_sessions.py` (계산만 — config·계산식·랩 데이터는 바꾸지 않음). "
             f"영상: 과거 업로드 백필(2021-01까지) 포함 원본 전체, 랩 데이터 {ctx['data_end']}_", "",
             "## 1. 결론", "",
             f"- **6개 기준일 출처 성적표 기준 역할 제안:** " + " · ".join(f"{k} {len(v)}개({', '.join(v)})" for k, v in sorted(counts.items())) + ".",
             f"- **점수에 넣으면 (신호로):** 발굴 역할이면 6개 기준일 평균 등급 가중 AUC {_f(m(base, 'auc'))} → {_f(m(disc, 'auc'))}, "
             f"맥락 역할이면 → {_f(m(ctxt, 'auc'))} (상위 50 적중 합 {s(base, 'hits50')} → {s(disc, 'hits50')} / {s(ctxt, 'hits50')}).",
             "- **점수에 넣으면 (특징으로, feature_lab 채택 기준):** " + " · ".join(
                 f"{k} {v['gain']:+.4f} (95% 구간 {v['lo']:+.4f} ~ {v['hi']:+.4f}) → {'채택 기준 통과' if v['adopt'] else '채택 안 함'}"
                 for k, v in fc.items()) + ".",
             f"- 그래서 **점수에는 {'넣을 만한 근거가 있습니다' if adopt_any else '넣지 않는 것'}**을 권합니다. 역할(source_roles 등록)·같은 집안 짝·export 여부는 코디네이터가 정합니다.", "",
             "## 2. 데이터", "",
             f"- 무대 영상(kind=stage, 알려진 8개 채널)을 임시 큐레이션 신호로 만든 것이 **{len(rows):,}행**(같은 팀·채널·날짜는 한 줄)입니다. "
             "앱용 `videos.csv`는 팀당 6개라 옛 출연이 잘려서, 평가는 원본 전체에 내보내기와 같은 거르기(흔한 낱말·짧은 이름·인터뷰·쇼츠·KBS 비무대)를 적용했습니다.",
             f"- 6개 기준일 각각에서 기준일 전 영상 신호: " + " · ".join(f"{c[:7]} {signals_before(rows, c):,}" for c in CV_CUTOFFS) + ".",
             f"- 같은 집안: 스페이스 공감 출연 뒤 받은 헬로루키 정답 **{ctx['same_house']}건**을 스페이스 공감의 적중에서 뺐습니다(신호로 넣는 점수 검증에서도 적중에서 뺌 — 규칙 그대로).",
             "- 날짜는 업로드일이라 실제 출연보다 늦을 수 있습니다 → '먼저 짚었다'를 덜 세는 보수적인 쪽.", "",
             "| 채널 | 무대 영상 | 팀 | 첫 업로드 | 마지막 업로드 | 참고 |", "|---|---|---|---|---|---|"]
    for c in cov:
        lines.append(f"| {LABELS.get(c['source'], c['source'])} | {c['videos']:,} | {c['teams']:,} | {c['first']} | {c['last']} | {coverage_note(c) or ''} |")
    lines += ["", f"## 3. 출처 성적표 — 6개 기준일 ({CV_CUTOFFS[0]} ~ {CV_CUTOFFS[-1]}, 관찰 {HORIZON}개월)", "",
              f"[출처 성적표](source_roles.md)와 같은 계산식(`source_scorecard.sql`). 수상 팀은 {CV_SINCE} 이후 첫 정답 팀. "
              f"기준선(후보 전체 적중률) {_f(_base_rate(sc6), 2)}%. 비교용으로 기존 주요 출처도 함께 적습니다.", ""]
    lines += _card_table(sc6, chan_keys + list(REFERENCE_SOURCES))
    lines += ["", f"## 4. 출처 성적표 — 최근 기준일 ({', '.join(ctx['recent_cuts'])}, source_review 기준)", "",
              f"역할 판정(`source_review`)이 쓰는 기준일입니다. 수상 팀은 {ctx['recent_since']} 이후. 기준선 {_f(_base_rate(sc_recent), 2)}%. "
              "마지막 기준일은 관찰 기간이 아직 짧습니다.", ""]
    lines += _card_table(sc_recent, chan_keys + list(REFERENCE_SOURCES))
    deb = {r.get("src"): r for r in ctx["debut"]}
    any_deb = next(iter(deb.values()), {})
    lines += ["", "## 5. 데뷔 코호트 — 첫 발매 6개월 안에 다뤘나 (6개 기준일)", "",
              f"과거 이력 없는 신인이 첫 발매를 낸 뒤 6개월 안에 다룬 출처(`source_scorecard_debut.sql`). 코호트는 6개 기준일 합쳐 "
              f"{any_deb.get('cohort_teams', 0)}팀(정답 {any_deb.get('cohort_hits', 0)}팀, 기준율 {_f(any_deb.get('base_rate'), 1)}%) — 첫 발매일을 아는 팀만이라 작습니다.", "",
              "| 출처 | 다룬 코호트 팀 | 적중 | 첫 발매 → 첫 언급 (일, 중앙값) | 가장 먼저 언급 |", "|---|---|---|---|---|"]
    for k in chan_keys + list(REFERENCE_SOURCES):
        d = deb.get(k, {})
        lines.append(f"| {LABELS.get(k.split(':', 1)[1], k)} | {d.get('teams', 0)} | {d.get('hits', 0)} | "
                     f"{_f(d.get('median_days'), 0)} | {d.get('first_mention', 0)} |")
    lines += ["", "- 무대 영상은 갓 데뷔한 팀을 거의 다루지 않습니다 — 어느 정도 알려진 뒤 섭외되는 경우가 많다는 뜻입니다."]
    lines += ["", "## 6. 점수에 넣었을 때 — 6개 기준일 교차 검증", "",
              "### (가) 신호로 넣기 — 점수 v2 가중치 그대로", "",
              "영상 출연을 `큐레이션:video_<채널>` 신호로 더하면 후보군(신호가 있는 팀)과 특징(매체 수·갈래 수 등)이 함께 바뀝니다. "
              "그래서 후보 수가 달라져 짝 비교는 아니고, 실제로 내보냈을 때의 모습입니다.", "",
              "| 기준일 | 지금 AUC | 발굴로 넣으면 | 맥락으로 넣으면 | 상위 50 적중 (지금 / 발굴 / 맥락) | 후보 팀 (지금 / 발굴) | 정답 팀 (지금 / 발굴) |",
              "|---|---|---|---|---|---|---|"]
    for c in CV_CUTOFFS:
        lines.append(f"| {c} | {_f(base[c]['auc'])} | {_f(disc[c]['auc'])} | {_f(ctxt[c]['auc'])} | "
                     f"{base[c]['hits50']} / {disc[c]['hits50']} / {ctxt[c]['hits50']} | {base[c]['n']:,} / {disc[c]['n']:,} | {base[c]['pos']} / {disc[c]['pos']} |")
    lines += [f"| **평균·합** | **{_f(m(base, 'auc'))}** | **{_f(m(disc, 'auc'))}** | **{_f(m(ctxt, 'auc'))}** | "
              f"**{s(base, 'hits50')} / {s(disc, 'hits50')} / {s(ctxt, 'hits50')}** | | |", "",
              "### (나) 특징으로 넣기 — feature_lab 규칙", "",
              "후보군·정답은 지금 그대로 두고, 특징 = 기준일 전 3년 안에 그 팀이 나온 영상 채널 수. 기준일 하나를 빼고 나머지로 가중치를 고른 뒤 뺀 기준일에 채점(격자 1차·2차 중 나은 쪽), "
              f"짝 부트스트랩 {200}번. 채택 기준: 평균 AUC +{ADOPT_MIN_GAIN} 이상 · 95% 구간 하한 > 0 · 상위 50 적중 안 줄기.", "",
              "| 특징 | 값 있는 후보 | 정답 팀 평균 / 아닌 팀 평균 | 교차 검증 AUC (지금 → 넣으면) | 차이 (95% 구간) | 상위 50 적중 (지금 → 넣으면) | 기준일 이김/짐 | 판정 |",
              "|---|---|---|---|---|---|---|---|"]
    for k, v in fc.items():
        r, d = v["res"], v["desc"]
        lines.append(f"| {k} | {d['nonzero'] * 100:.1f}% | {_f(d['hit_mean'], 2)} / {_f(d['non_mean'], 2)} | {_f(r['base_mean'])} → {_f(r['cv_mean'])} | "
                     f"{v['gain']:+.4f} ({v['lo']:+.4f} ~ {v['hi']:+.4f}) | {r['base_hits']['hits50']} → {r['cv_hits']['hits50']} | "
                     f"{r['wins']}/{r['losses']} | {'✅ 채택 기준 통과' if v['adopt'] else '❌ 채택 안 함'} |")
    lines += ["", "- `video_channels` = 8개 채널 전부, `video_indie` = 아이돌·기성 가수가 대부분인 KBS Kpop·it's Live 를 뺀 6개 채널.",
              "- '정답 팀 평균 / 아닌 팀 평균'은 정답을 보고 낸 참고 숫자(가중치 고르기엔 안 씀)입니다.",
              f"- (나)의 '지금' AUC({_f(next(iter(fc.values()))['res']['base_mean']) if fc else '—'})가 (가)의 지금({_f(m(base, 'auc'))})과 조금 다른 것은 "
              "같은 집안 규칙으로 헬로루키 정답 일부를 적중에서 뺀 상태로 쟀기 때문입니다(영상을 쓰면 그 규칙이 함께 붙음).", "",
              "## 7. 채널별 역할 제안", "",
              f"6개 기준일 성적표(3절)에 `source_review`와 같은 기준을 적용했습니다: 후보 {MIN_TEAMS}팀 미만 → pending(표본 부족), "
              f"배수 {PROMOTE_LIFT:g} 이상 또는 유일 기여 {PROMOTE_MIN_ONLY}팀 이상(배수 1 이상) → discovery, 배수 1 이상 → context, "
              "배수 1 미만이면서 유일 기여 0 → excluded, 그 밖 → context.", "",
              "| 채널 | 제안 | 근거 | 참고 |", "|---|---|---|---|"]
    for c in cov:
        role, why = roles[c["source"]]
        notes = [n for n in (coverage_note(c),) if n]
        if c["source"] in SAME_HOUSE:
            notes.append("같은 집안 짝 등록 필요: `큐레이션:video_ebs_space` ↔ hello_rookie·hello_rookie_year")
        if c["source"] in IDOL_HEAVY:
            notes.append("아이돌·기성 가수 무대가 대부분")
        lines.append(f"| {LABELS.get(c['source'], c['source'])} | **{role}** | {why} | {'; '.join(notes)} |")
    lines += ["", "## 8. 결정할 것 (코디네이터)", "",
              "1. 영상 출처를 `config/source_roles.json` signals에 위 제안대로 등록할지 — 등록하려면 `export_lab_data`가 무대 영상을 `큐레이션:video_<채널>` 신호로 내보내야 합니다(지금은 앱의 영상 목록으로만 씀).",
              "2. 같은 집안 짝 `큐레이션:video_ebs_space` ↔ hello_rookie·hello_rookie_year 추가.",
              f"3. 점수(features.sql): 6절 결과로는 {'특징 채택 기준을 통과한 것이 있어 검토할 만합니다' if adopt_any else '넣을 근거가 없습니다 — 신호로 넣더라도 맥락 정보로만'}.", "",
              "## 9. 한계", "",
              "- 영상은 우리 팀 목록의 이름과 맞는 것만 모았습니다(제목 ↔ 팀 이름 대조). 우리 데이터에 없는 팀의 출연은 처음부터 빠지고, 짧은 이름 팀은 엄격한 규칙 때문에 일부 놓칩니다.",
              "- 업로드일 ≠ 출연일. 채널마다 기록 기간이 달라 기준일마다 채널 구성이 다릅니다: "
              + "; ".join(f"{LABELS.get(c['source'], c['source'])} {coverage_note(c)}" for c in cov if coverage_note(c)) + ".",
              "- 앞쪽 기준일(2023-01)은 영상 기록이 2021-01부터라 '기준일 전 3년' 중 2년만 봅니다."]
    return "\n".join(lines) + "\n"


def run(data_dir: Path = lab_sql.DATA_DIR, raw_dir: Path = RAW_DIR) -> dict:
    import json
    import source_review as sr
    videos = load_stage_videos(raw_dir)
    rows = video_signal_rows(videos, role="discovery")
    data_end = json.loads((data_dir / "meta.json").read_text(encoding="utf-8"))["data_end"]
    recent_cuts, recent_since = sr.review_cutoffs(data_end)
    base = lab_sql.connect(data_dir)
    v2_base = v2_eval(base)
    marked = lab_sql.connect(data_dir)          # 특징 실험: 후보군 그대로, 같은 집안 표시만
    mark_same_house(marked, rows)
    fcv = feature_cv(marked, rows, {"video_channels": None,
                                    "video_indie": {src for src in LABELS if src not in IDOL_HEAVY}})
    con = lab_sql.connect(data_dir)
    add_video_signals(con, rows)
    same_house = con.execute("SELECT COUNT(*) FROM outcomes WHERE same_house_sources LIKE '%video_ebs_space%'").fetchone()[0]
    ctx_con = lab_sql.connect(data_dir)
    add_video_signals(ctx_con, [{**r, "role": "context"} for r in rows])
    return {"cov": channel_coverage(videos), "rows": rows, "data_end": data_end, "same_house": same_house,
            "sc6": scorecard(con, CV_CUTOFFS, CV_SINCE), "sc_recent": scorecard(con, recent_cuts, recent_since),
            "recent_cuts": recent_cuts, "recent_since": recent_since, "debut": debut(con, CV_CUTOFFS),
            "v2_base": v2_base, "v2_disc": v2_eval(con), "v2_ctx": v2_eval(ctx_con), "feature_cv": fcv}


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="무대·라이브 세션 채널 출연 평가 → docs/live_sessions.md")
    ap.add_argument("--data-dir", type=Path, default=lab_sql.DATA_DIR)
    ap.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    ctx = run(args.data_dir, args.raw_dir)
    args.out.write_text(render(ctx), encoding="utf-8")
    print(f"✅ → {args.out} (영상 신호 {len(ctx['rows']):,}행)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
