"""주간 엑셀 보고서 → docs/report/crate-digger_weekly.xlsx (공개 가능: 팀 이름·공개 출처 숫자만)

    .venv/bin/python scripts/export_excel.py

숫자는 앱과 같은 계산(docs/lab/sql/*.sql, scripts/lab_sql.py 의 DuckDB)으로 낸다.
시트: 요약 · 후보 TOP100 · 이번 주 변화 · 다가오는 공연 · 출처 성적표 · 점수 검증 · 정의
- 새 후보·상승 팀: 최신 점수 스냅샷과 7일 전 스냅샷(없으면 가장 가까운 이전 것) 비교
  (규칙은 앱 getSnapshotDiff 와 같음: 점수가 올랐거나 순위가 3계단 이상 오름)
- 2주 내 후보 공연: 기준일~14일, 같은 날·같은 공연장을 한 줄로, 후보(점수 상위 300팀)가 낀 공연만 (앱 '이번 주' 화면과 같음)
"""
from __future__ import annotations

import csv
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab_sql  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "report" / "crate-digger_weekly.xlsx"
TUNING = ROOT / "docs" / "score_tuning.md"
SHEETS = ("요약", "후보 TOP100", "이번 주 변화", "다가오는 공연", "출처 성적표", "점수 검증", "정의")
FONT = "맑은 고딕"
CANDIDATE_POOL = 300          # 앱과 같이 상위 300팀을 '후보'로 (공연 묶음·순위 표시)
TOP_N = 100                   # 시트에 싣는 후보 수
GIG_DAYS = 14                 # '다가오는 공연' 범위 (앱 '이번 주' 화면과 같음)
RISE_RANKS = 3                # 순위가 이만큼 오르면 '상승' (앱 규칙)
COMPARE_DAYS = 7              # 주간 보고서: 스냅샷이 매일 쌓이므로 7일 전과 비교 (어제 대비가 아니라 '이번 주' 변화)
BACKTEST_CUTOFFS = ("2024-07-01", "2025-01-01", "2025-07-01")   # docs/source_roles.md 성적표와 같은 기준일
SCORECARD_SINCE = "2024-01-01"
WEIGHT_LABELS = {"w_branch": "갈래 수", "w_stage": "선정 단계", "w_peer": "선정 팀과 같은 무대", "w_dmz": "DMZ 출연",
                 "w_gigs": "1년 공연 일수", "w_outlets": "발굴 매거진 수", "w_recent": "최근 180일 활동",
                 "w_venues": "공연장 다양성", "w_winner": "수상 팀과 같은 무대", "w_context": "맥락 매거진 수",
                 "w_collab": "기성 파트너 협업"}
PTS_COLS = ("pts_branch", "pts_stage", "pts_peer", "pts_dmz", "pts_gigs", "pts_outlets", "pts_recent",
            "pts_venues", "pts_winner", "pts_context")
STATUS_KO = {"newcomer": "신인", "established": "기성", "famous": "유명", "unknown": "모름(첫 등장 기준)"}
ROLE_KO = {"discovery": "발굴", "context": "맥락", "excluded": "제외", "pending": "검증 대기"}
DEFINITIONS = [
    ("발굴 (discovery)", "나중에 상 받을 팀을 기준선보다 정확하게, 또는 먼저·유일하게 짚은 출처. 점수에 씀"),
    ("맥락 (context)", "예측력은 기준선 수준 이하지만 팀 이해에 도움 되는 출처. 점수에 약하게(0.5)만 씀"),
    ("검증 대기 (pending)", "기록이 짧아 아직 성적을 잴 수 없는 출처. 모으기만 하고 점수엔 안 씀"),
    ("제외 (excluded)", "후보 팀이 충분한데 적중이 0이라 효과 없다고 본 출처. 점수에서 뺌"),
    ("정답", "신인상·주요 신인 프로그램 선정. 신호가 이것을 '먼저' 맞혔는지로 평가"),
    ("정답 등급 S (가중치 3)", "전국 단위 최종 수상·선정 (한대음 신인, 올해의 헬로루키, 한국힙합어워즈 신인, CJ 튠업)"),
    ("정답 등급 A (가중치 2)", "주요 신인 프로그램 결선·최종, 평론 매체 올해의 신인"),
    ("정답 등급 B (가중치 1)", "기성 팀이 섞이거나 단계가 낮은 정답 (첫 발매 5년 이내 팀만 셈)"),
    ("AUC", "정답 팀 하나와 아닌 팀 하나를 골랐을 때 정답 팀 점수가 더 높을 확률. 0.5 = 무작위, 1 = 완벽"),
    ("등급 가중 AUC", "AUC 를 계산할 때 S 등급 정답은 3배, A 는 2배 무게로 셈"),
    ("기준선 / 배수(lift)", "기준선 = 후보 전체의 적중률. 배수 = 적중률 ÷ 기준선 (1보다 커야 쓸모 있음)"),
    ("백테스트", "과거 기준일을 정해 그 전 신호만으로 점수를 매기고, 그 뒤 실제 정답으로 채점"),
    ("교차 검증", "기준일 하나를 빼고 나머지로 가중치를 고른 뒤, 뺀 기준일로 채점 (고를 때 안 본 시점)"),
    ("새 후보 / 상승", "최신 점수 스냅샷을 7일 전(없으면 가장 가까운 이전) 스냅샷과 비교: 새로 상위 300에 든 팀 / 점수가 올랐거나 순위가 3계단 이상 오른 팀"),
    ("신인 기준", "첫 발매 3년 이내 & 발매 10개 이하 (프로필이 없으면 우리 데이터 첫 등장 3년 이내)"),
]


# ---------- 계산 (테스트 가능한 순수 함수) ----------

def snapshot_diff(latest: Dict[str, Tuple[float, int]], prev: Dict[str, Tuple[float, int]]):
    """{팀: (점수, 순위)} 두 개 → (새 후보, 상승 팀). 앱 getSnapshotDiff 와 같은 규칙."""
    new, rising = [], []
    for k, (score, rank) in latest.items():
        if k not in prev:
            new.append({"team_key": k, "rank_now": rank, "score_now": score})
            continue
        old_score, old_rank = prev[k]
        rank_gain, score_gain = old_rank - rank, round(score - old_score, 2)
        if score_gain > 0 or rank_gain >= RISE_RANKS:
            rising.append({"team_key": k, "rank_now": rank, "rank_prev": old_rank, "rank_gain": rank_gain,
                           "score_now": score, "score_gain": score_gain})
    new.sort(key=lambda r: r["rank_now"])
    rising.sort(key=lambda r: (-r["score_gain"], -r["rank_gain"], r["rank_now"]))
    return new, rising


def compare_date(dates: List[str]) -> Optional[str]:
    """스냅샷 날짜들 → 비교할 날짜: 최신보다 COMPARE_DAYS 이상 이전 중 가장 늦은 것, 없으면 최신 바로 앞 것."""
    ds = sorted(dates)
    if len(ds) < 2:
        return None
    target = (date.fromisoformat(ds[-1]) - timedelta(days=COMPARE_DAYS)).isoformat()
    before = [d for d in ds[:-1] if d <= target]
    return before[-1] if before else ds[-2]


def group_gigs(rows: List[dict], cand_rank: Dict[str, int]) -> List[dict]:
    """예정 공연 행 → 같은 날·같은 공연장 묶음 중 후보가 낀 것만 (날짜·공연장 순)."""
    events: Dict[Tuple[str, str], dict] = {}
    for r in rows:
        day = str(r.get("signal_date") or "")[:10]
        venue = (r.get("venue") or "").strip() or "공연장 미정"
        ev = events.setdefault((day, venue), {"date": day, "venue": venue, "seen": set(), "cands": [], "others": []})
        if r["team_key"] in ev["seen"]:
            continue
        ev["seen"].add(r["team_key"])
        name = r.get("display_name") or r["team_key"]
        if r["team_key"] in cand_rank:
            ev["cands"].append((cand_rank[r["team_key"]], name))
        else:
            ev["others"].append(name)
    out = []
    for (day, venue), ev in sorted(events.items()):
        if ev["cands"]:
            out.append({"date": day, "venue": venue, "candidates": [f"{n} ({rk}위)" for rk, n in sorted(ev["cands"])],
                        "others": sorted(ev["others"])})
    return out


def _read_csv(path: Path) -> List[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _snapshot(path: Optional[Path]) -> Dict[str, Tuple[float, int]]:
    return {r["team_key"]: (float(r["score"]), int(r["rank"])) for r in _read_csv(path)} if path else {}


def tuning_summary(text: str) -> List[str]:
    """docs/score_tuning.md 의 교차 검증 요약 줄(평균 AUC·상위 50 적중·추천 가중치)을 그대로 인용."""
    out = [re.sub(r"\*\*", "", line).strip() for line in text.splitlines()
           if line.startswith("**평균 AUC") or line.startswith("**상위 50")]
    m = re.search(r"## 추천 가중치.*?\n\n`([^`]+)`", text, re.S)
    if m:
        out.append(f"추천 가중치(기준일 전체로 고름): {m.group(1)}")
    return out


def load_context(data_dir: Path = lab_sql.DATA_DIR, tuning_text: Optional[str] = None) -> dict:
    """보고서에 필요한 숫자를 모두 계산 (DuckDB, 앱과 같은 SQL)."""
    meta = json.loads((data_dir / "meta.json").read_text(encoding="utf-8")) if (data_dir / "meta.json").exists() else {}
    as_of = meta.get("data_end") or date.today().isoformat()
    con = lab_sql.connect(data_dir)
    cands = lab_sql.query(con, "candidates.sql", as_of=f"'{as_of}'", limit=str(CANDIDATE_POOL))
    rank = {r["team_key"]: i + 1 for i, r in enumerate(cands)}
    teams = {t["team_key"]: t for t in _read_csv(data_dir / "teams.csv")}
    end = (date.fromisoformat(as_of) + timedelta(days=GIG_DAYS)).isoformat()
    upcoming = [r for r in _read_csv(data_dir / "signals.csv")
                if r.get("branch") == "공연" and as_of <= r.get("signal_date", "") <= end]
    for r in upcoming:
        r["display_name"] = teams.get(r["team_key"], {}).get("display_name") or r["team_key"]
    next_gig: Dict[str, str] = {}
    for r in sorted(upcoming, key=lambda r: (r["signal_date"], r.get("venue") or "")):
        next_gig.setdefault(r["team_key"], f"{r['signal_date']} {(r.get('venue') or '').strip() or '공연장 미정'}")
    spotify = {r["team_key"]: r["url"] for r in _read_csv(data_dir / "links.csv") if r.get("platform") == "spotify"}
    snaps = sorted((data_dir / "snapshots").glob("????-??-??.csv")) if (data_dir / "snapshots").is_dir() else []
    prev_day = compare_date([p.stem for p in snaps])
    prev_path = next((p for p in snaps if p.stem == prev_day), None)
    latest, prev = (_snapshot(snaps[-1]) if snaps else {}), _snapshot(prev_path)
    new, rising = snapshot_diff(latest, prev)
    for r in new + rising:
        r["display_name"] = teams.get(r["team_key"], {}).get("display_name") or r["team_key"]
    cut_sql = ",".join(f"(DATE '{c}')" for c in BACKTEST_CUTOFFS)
    scorecard = lab_sql.query(con, "source_scorecard.sql", cutoffs=cut_sql, since=f"'{SCORECARD_SINCE}'")
    backtests = [row for c in BACKTEST_CUTOFFS for row in lab_sql.query(con, "backtest.sql", cutoff=f"'{c}'")]
    if tuning_text is None:
        tuning_text = TUNING.read_text(encoding="utf-8") if TUNING.exists() else ""
    weights = {k: lab_sql.DEFAULTS[k] for k in WEIGHT_LABELS if k in lab_sql.DEFAULTS}
    return {"as_of": as_of, "candidates": cands, "rank": rank, "teams": teams, "next_gig": next_gig,
            "spotify": spotify, "new": new, "rising": rising,
            "snap_dates": [d for d in (prev_day, snaps[-1].stem if snaps else None) if d],
            "gig_events": group_gigs(upcoming, rank), "scorecard": scorecard, "backtests": backtests,
            "tuning": tuning_summary(tuning_text), "weights": weights}


# ---------- 엑셀 쓰기 ----------

def _styles():
    from openpyxl.styles import Alignment, Font, PatternFill
    return {"font": Font(name=FONT, size=10), "head": Font(name=FONT, size=10, bold=True, color="FFFFFF"),
            "head_fill": PatternFill("solid", fgColor="2F4F6F"), "title": Font(name=FONT, size=14, bold=True),
            "bold": Font(name=FONT, size=10, bold=True), "red": PatternFill("solid", fgColor="F8D7DA"),
            "link": Font(name=FONT, size=10, color="0563C1", underline="single"),
            "wrap": Alignment(wrap_text=True, vertical="top")}


def _table(ws, header: List[str], rows: List[list], st: dict, start_row: int = 1) -> None:
    from openpyxl.styles import Alignment
    for j, h in enumerate(header, 1):
        c = ws.cell(row=start_row, column=j, value=h)
        c.font, c.fill = st["head"], st["head_fill"]
    for i, row in enumerate(rows, start_row + 1):
        for j, v in enumerate(row, 1):
            c = ws.cell(row=i, column=j, value=v)
            c.font = st["font"]
            if isinstance(v, (int, float)):
                c.alignment = Alignment(horizontal="right")


def _autosize(ws, max_width: int = 60) -> None:
    from openpyxl.utils import get_column_letter
    widths: Dict[int, int] = {}
    for row in ws.iter_rows():
        for c in row:
            if c.value is None:
                continue
            text = str(c.value)
            w = sum(2 if ord(ch) > 0x2E80 else 1 for ch in text)   # 한글은 두 칸
            widths[c.column] = max(widths.get(c.column, 0), w)
    for col, w in widths.items():
        ws.column_dimensions[get_column_letter(col)].width = min(max(8, w + 2), max_width)


def _finish(ws, freeze: bool = True) -> None:
    if freeze and ws.max_row > 1:
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
    _autosize(ws)


def _summary(ws, ctx: dict, st: dict) -> None:
    ws["A1"], ws["A1"].font = "Crate Digger 주간 보고서", st["title"]
    events = ctx["gig_events"]
    gig_teams = {c for ev in events for c in ev["candidates"]}
    rows = [("기준일 (데이터 끝)", ctx["as_of"]),
            ("비교한 점수 스냅샷", " → ".join(ctx["snap_dates"]) or "—"),
            ("새 후보 (상위 300에 새로 듦)", len(ctx["new"])),
            ("순위·점수 상승", len(ctx["rising"])),
            (f"{GIG_DAYS}일 안 후보 공연 (같은 날·같은 공연장 묶음)", len(events)),
            (f"{GIG_DAYS}일 안 공연이 있는 후보", len(gig_teams))]
    for i, (k, v) in enumerate(rows, 3):
        ws.cell(row=i, column=1, value=k).font = st["bold"]
        c = ws.cell(row=i, column=2, value=v)
        c.font = st["font"]
    r = len(rows) + 4
    ws.cell(row=r, column=1, value="점수 v2 가중치").font = st["bold"]
    _table(ws, ["특징", "가중치"], [[WEIGHT_LABELS[k], float(v)] for k, v in ctx["weights"].items()], st, start_row=r + 1)
    r += len(ctx["weights"]) + 3
    ws.cell(row=r, column=1, value="한 줄 결론").font = st["bold"]
    top = ctx["candidates"][:3]
    top_txt = ", ".join("{}({})".format(c["display_name"], c["score"]) for c in top)
    lines = [f"점수 상위 3팀: {top_txt}" if top else "후보 없음",
             f"이번 주 새 후보 {len(ctx['new'])}팀, 상승 {len(ctx['rising'])}팀"
             + (f" — 새 후보 1위 {ctx['new'][0]['display_name']}" if ctx["new"] else ""),
             f"{GIG_DAYS}일 안 후보가 서는 공연 {len(events)}건 ({len(gig_teams)}팀)"
             + (f" — 가장 가까운 공연 {events[0]['date']} {events[0]['venue']}" if events else ""),
             *[f"점수 검증: {t}" for t in ctx["tuning"][:2]]]
    for i, line in enumerate(lines, r + 1):
        ws.cell(row=i, column=1, value=line).font = st["font"]
    _autosize(ws, max_width=70)


def _candidates(ws, ctx: dict, st: dict) -> None:
    from openpyxl.formatting.rule import DataBarRule
    header = ["순위", "팀", "장르", "점수", *PTS_COLS, "첫 등장", "첫 발매", "다음 공연", "스포티파이", "신인 여부"]
    rows = []
    for i, c in enumerate(ctx["candidates"][:TOP_N], 1):
        t = ctx["teams"].get(c["team_key"], {})
        rows.append([i, c["display_name"], c.get("primary_genre") or "", float(c["score"] or 0),
                     *[float(c.get(p) or 0) for p in PTS_COLS], str(c.get("first_seen") or "")[:10],
                     t.get("first_release") or "", ctx["next_gig"].get(c["team_key"], ""),
                     "열기" if c["team_key"] in ctx["spotify"] else "",
                     STATUS_KO.get(c.get("profile_status") or "", c.get("profile_status") or "")])
    _table(ws, header, rows, st)
    link_col = header.index("스포티파이") + 1
    for i, c in enumerate(ctx["candidates"][:TOP_N], 2):
        url = ctx["spotify"].get(c["team_key"])
        if url:
            cell = ws.cell(row=i, column=link_col)
            cell.hyperlink, cell.font = url, st["link"]
    if rows:
        ws.conditional_formatting.add(f"D2:D{len(rows) + 1}",
                                      DataBarRule(start_type="min", end_type="max", color="5B9BD5"))
    _finish(ws)


def _changes(ws, ctx: dict, st: dict) -> None:
    rows = [["새로 들어옴", r["display_name"], r["rank_now"], "", r["score_now"], ""] for r in ctx["new"]]
    rows += [["상승", r["display_name"], r["rank_now"], r["rank_prev"], r["score_now"], r["score_gain"]]
             for r in ctx["rising"]]
    _table(ws, ["구분", "팀", "지금 순위", "지난 순위", "지금 점수", "점수 변화"], rows, st)
    _finish(ws)


def _gigs(ws, ctx: dict, st: dict) -> None:
    rows = [[ev["date"], ev["venue"], len(ev["candidates"]), ", ".join(ev["candidates"]), ", ".join(ev["others"])]
            for ev in ctx["gig_events"]]
    _table(ws, ["날짜", "공연장", "후보 수", "후보 (순위)", "함께 서는 팀"], rows, st)
    _finish(ws)


def _scorecard(ws, ctx: dict, st: dict) -> None:
    cols = ["src", "role", "since_date", "signal_rows", "teams", "hits", "rate", "lift", "base_rate",
            "winners_seen", "first_to_see", "only_source", "median_lead_months"]
    header = ["출처", "역할", "기록 시작", "신호 수", "후보 팀", "적중", "적중률(%)", "배수", "기준선(%)",
              "먼저 잡은 수상 팀", "가장 먼저", "유일 기여", "선행 개월(중앙값)"]
    rows = []
    for r in ctx["scorecard"]:
        row = []
        for k in cols:
            v = r.get(k)
            v = ROLE_KO.get(v, v) if k == "role" else v
            row.append(v.isoformat() if hasattr(v, "isoformat") else (float(v) if isinstance(v, (int, float)) and k in ("rate", "lift", "base_rate", "median_lead_months") else v))
        rows.append(row)
    _table(ws, header, rows, st)
    lift_col = header.index("배수") + 1
    for i, r in enumerate(ctx["scorecard"], 2):
        if r.get("lift") is not None and float(r["lift"]) < 1:
            for j in range(1, len(header) + 1):
                ws.cell(row=i, column=j).fill = st["red"]
    ws.cell(row=len(rows) + 3, column=1,
            value=f"기준일 {', '.join(BACKTEST_CUTOFFS)} 합산, 수상 팀은 {SCORECARD_SINCE} 이후. 빨간 줄 = 배수 1 미만(기준선 이하)").font = st["font"]
    _ = lift_col
    _finish(ws)


def _validation(ws, ctx: dict, st: dict) -> None:
    rows = [[str(r["cutoff"])[:10], r["k"], r["method"], r["hits"], float(r["hit_rate"] or 0),
             None if r["random_expected"] is None else float(r["random_expected"]),
             None if r["lift"] is None else float(r["lift"]), r["pool_n"], r["pool_hits"]] for r in ctx["backtests"]]
    _table(ws, ["기준일", "상위 K", "방법", "맞힌 팀", "적중률(%)", "무작위 기대", "무작위 대비 배수", "후보 팀", "이후 정답 팀"], rows, st)
    r = len(rows) + 3
    ws.cell(row=r, column=1, value="교차 검증 요약 (docs/score_tuning.md 인용)").font = st["bold"]
    for i, line in enumerate(ctx["tuning"] or ["(docs/score_tuning.md 없음)"], r + 1):
        ws.cell(row=i, column=1, value=line).font = st["font"]
    if ws.max_row > 1:
        ws.freeze_panes = "A2"
    _autosize(ws, max_width=40)


def _definitions(ws, st: dict) -> None:
    _table(ws, ["용어", "뜻"], [list(d) for d in DEFINITIONS], st)
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = st["wrap"]
    _autosize(ws, max_width=80)


def build_workbook(ctx: dict):
    from openpyxl import Workbook
    st = _styles()
    wb = Workbook()
    wb.remove(wb.active)
    sheets = {name: wb.create_sheet(name) for name in SHEETS}
    _summary(sheets["요약"], ctx, st)
    _candidates(sheets["후보 TOP100"], ctx, st)
    _changes(sheets["이번 주 변화"], ctx, st)
    _gigs(sheets["다가오는 공연"], ctx, st)
    _scorecard(sheets["출처 성적표"], ctx, st)
    _validation(sheets["점수 검증"], ctx, st)
    _definitions(sheets["정의"], st)
    return wb


def main() -> int:
    try:
        ctx = load_context()
        wb = build_workbook(ctx)
    except ImportError as e:
        print(f"❌ {e} — .venv/bin/python 으로 실행 (openpyxl·duckdb 필요)", file=sys.stderr)
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT)
    counts = {name: wb[name].max_row for name in SHEETS}
    print(f"✅ 주간 엑셀 → {OUT.relative_to(ROOT)} (기준일 {ctx['as_of']}) 시트별 행 수 {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
