"""거꾸로 따라가기: 정답(raw_outcome) 팀이 정답 전에 우리 신호(raw_kr_selection)에 먼저 나왔는지 본다.

    python3 scripts/backtrace.py                     # 보고서 → docs/backtrace.md
    python3 scripts/backtrace.py --window 2025-01-01  # 이 날짜 이후 정답을 '맞힐 대상'으로

계산하는 것
1. 정답 팀마다 첫 정답일과, 그보다 앞선 신호(선행 일수). 날짜는 scripts/timing.py 규칙(후보=기간 끝, 정답=기간 첫날)
   으로 비교해 '앞섰다'를 부풀리지 않는다. 같은 프로그램 규칙(SAME_PROGRAM)에 걸리는 신호는 뺀다.
2. 정답을 받을 때 첫 발매 후 몇 년 차였나 (멜론 프로필 debut_date·first_release_date) → 신인 기준 검증.
   앨범 수는 '지금' 값이라 정답 당시보다 많을 수 있다 (한계).
3. 신호 프로그램별 적중률: window 이전에 신호를 받은 팀 중 window 이후 정답을 받은 비율.
   정답 팀만 보면 '누구나 가진 신호'를 좋은 신호로 착각하므로, 이 비율로 비교한다.
"""
import argparse
import csv
import glob
import sys
from datetime import date
from pathlib import Path

from collect_artists import name_keys
from csv_schema import excluded_outcomes
from timing import lead_days, outcome_date, signal_date

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
REPORT = ROOT / "docs" / "backtrace.md"
NEWCOMER_YEARS = 2
NEWCOMER_ALBUMS = 5


def _rows(pattern, raw_dir=RAW_DIR):
    out = []
    for f in sorted(glob.glob(str(Path(raw_dir) / pattern))):
        with open(f, encoding="utf-8") as fh:
            out.extend(csv.DictReader(fh))
    return out


def first_outcomes(outcomes):
    """{팀 이름: {date, program, round, keys, programs}} — 키(별칭 포함)가 겹치면 같은 팀."""
    teams, by_key = {}, {}
    for r in sorted(outcomes, key=lambda r: outcome_date(r["announced_at"])):
        keys = name_keys(r["artist_text"])
        name = next((by_key[k] for k in keys if k in by_key), None)
        if name is None:
            name = r["artist_text"]
            teams[name] = {"date": outcome_date(r["announced_at"]), "program": r["program"], "round": r["round"],
                           "keys": set(), "programs": []}
        teams[name]["keys"] |= keys
        teams[name]["programs"].append(r["program"])
        for k in keys:
            by_key[k] = name
    return teams


def _team_of(keys, teams):
    return next((n for n, t in teams.items() if t["keys"] & keys), None)


def prior_signals(selections, teams):
    prior = {n: [] for n in teams}
    for s in selections:
        name = _team_of(name_keys(s["artist_text"]), teams)
        if not name or teams[name]["program"] in excluded_outcomes(s["program"]):
            continue
        days = lead_days(s["announced_at"], teams[name]["date"])
        if days:
            prior[name].append({"program": s["program"], "round": s["round"], "lead_days": days})
    return prior


def career_at_outcome(profiles, teams):
    out = {}
    for p in profiles:
        name = _team_of(name_keys(p["artist_text"]), teams)
        dates = [outcome_date(d) for d in (p.get("debut_date"), p.get("first_release_date")) if outcome_date(d or "")]
        if not name or not dates:
            continue
        years = round((date.fromisoformat(teams[name]["date"]) - date.fromisoformat(min(dates))).days / 365.25, 1)
        albums = int(p["album_count"]) if (p.get("album_count") or "").isdigit() else None
        out[name] = {"years": years, "albums_now": albums,
                     "newcomer_rule": years <= NEWCOMER_YEARS and (albums is None or albums <= NEWCOMER_ALBUMS)}
    return out


def signal_hit_rates(selections, outcomes, window_start, lookback_years=None):
    """lookback_years: window 직전 몇 년 안의 신호만 (오래전 팀이 섞여 비율이 낮아지는 것 방지)."""
    earliest = f"{int(window_start[:4]) - lookback_years}{window_start[4:]}" if lookback_years else ""
    teams = first_outcomes([o for o in outcomes if outcome_date(o["announced_at"]) >= window_start])
    rates = {}
    for s in selections:
        sd = signal_date(s["announced_at"])
        if not sd or sd >= window_start or sd < earliest:
            continue
        r = rates.setdefault(s["program"], {"teams": 0, "hits": 0, "hit_names": [], "_seen": set()})
        keys = frozenset(name_keys(s["artist_text"]))
        if not keys or keys in r["_seen"]:
            continue
        r["_seen"].add(keys)
        r["teams"] += 1
        name = _team_of(set(keys), teams)
        if name and teams[name]["program"] not in excluded_outcomes(s["program"]):
            r["hits"] += 1
            r["hit_names"].append(name)
    for r in rates.values():
        r.pop("_seen")
        r["rate"] = round(r["hits"] / r["teams"], 3) if r["teams"] else 0.0
    return rates


def report(raw_dir, window, lookback=5):
    outcomes, sels, profs = _rows("raw_outcome_*.csv", raw_dir), _rows("raw_kr_selection_*.csv", raw_dir), \
        _rows("raw_artist_profile_*.csv", raw_dir)
    teams = first_outcomes([o for o in outcomes if outcome_date(o["announced_at"]) >= window])
    prior, career = prior_signals(sels, teams), career_at_outcome(profs, teams)
    rates = signal_hit_rates(sels, outcomes, window, lookback)
    with_prior = {n: p for n, p in prior.items() if p}
    years = sorted(c["years"] for c in career.values())
    lines = [f"# 거꾸로 따라가기 결과 (정답 기간: {window} 이후)", "",
             f"- 정답 팀 {len(teams)}팀 · 멜론 프로필로 연차를 안 팀 {len(career)}팀 · 정답 전에 우리 선정 신호가 있던 팀 {len(with_prior)}팀", ""]
    if years:
        rule = sum(1 for c in career.values() if c["newcomer_rule"])
        lines += ["## 정답 받을 때 첫 발매 후 연차", "",
                  f"- 중앙값 {years[len(years) // 2]}년 · 2년 이내 {sum(1 for y in years if y <= 2)}팀 / {len(years)}팀 "
                  f"· 우리 신인 기준(2년 이내 & 앨범 5개 이하) 통과 {rule}팀",
                  f"- 구간: 1년 이내 {sum(1 for y in years if y <= 1)} · 1~3년 {sum(1 for y in years if 1 < y <= 3)} "
                  f"· 3~5년 {sum(1 for y in years if 3 < y <= 5)} · 5년 초과 {sum(1 for y in years if y > 5)}", ""]
    lines += [f"## 신호 프로그램별 적중률 (정답 기간 직전 {lookback}년 안에 신호를 받은 팀 중 기간 안에 정답을 받은 비율)", "",
              "| 신호 | 팀 | 적중 | 비율 | 적중 팀 |", "|---|---|---|---|---|"]
    for prog, r in sorted(rates.items(), key=lambda x: -x[1]["rate"]):
        lines.append(f"| {prog} | {r['teams']} | {r['hits']} | {r['rate']:.1%} | {', '.join(r['hit_names'][:8])} |")
    lines += ["", "## 정답 전에 신호가 있던 팀", "", "| 팀 | 첫 정답 | 앞선 신호 (선행 일수) |", "|---|---|---|"]
    for n, p in sorted(with_prior.items(), key=lambda x: -max(s["lead_days"] for s in x[1])):
        t = teams[n]
        sig = ", ".join(f"{s['program']} {s['round']} ({s['lead_days']}일)" for s in sorted(p, key=lambda s: -s["lead_days"]))
        lines.append(f"| {n} | {t['program']} {t['date']} | {sig} |")
    return "\n".join(lines) + "\n"


def main(argv):
    ap = argparse.ArgumentParser(description="정답 팀 거꾸로 따라가기")
    ap.add_argument("--window", default="2025-01-01")
    ap.add_argument("--lookback", type=int, default=5, help="정답 기간 직전 몇 년의 신호만 적중률에 넣을지")
    args = ap.parse_args(argv)
    text = report(RAW_DIR, args.window, args.lookback)
    REPORT.write_text(text, encoding="utf-8")
    print(text[:3000])
    print(f"→ {REPORT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
