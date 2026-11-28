"""상위 후보 중 '데뷔 5년 넘어 보이는' 기성 팀 점검 → docs/newcomer_audit_<날짜>.md (새 수집 없이 이미 있는 자료로)

    .venv/bin/python scripts/newcomer_audit.py               # 상위 300, 표를 화면에
    .venv/bin/python scripts/newcomer_audit.py --top 300 --out docs/newcomer_audit_2026-11-28.md

팀마다 출처별 가장 이른 근거 날짜를 모은다: 프로필 첫 발매(teams.csv), 멜론 데뷔일·첫 발매(프로필 원본),
스포티파이 첫 발매(프로필 원본), iTunes 첫 발매 연도, 우리 신호 첫 날짜(signals.csv), 정답·후보 프로그램 발표일(outcomes.csv).
기준일 5년 전보다 이른 출처가 하나면 '의심', 둘 이상이면 '확실'(데뷔일 덮어쓰기 후보 — 적용은 사람이 근거 확인 뒤 config/debut_overrides.json 에).
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
LAB = ROOT / "docs" / "lab" / "data"
RAW = ROOT / "data" / "raw"
YEARS = 5
SOURCE_LABEL = {
    "profile": "프로필 첫 발매", "melon_debut": "멜론 데뷔일", "melon_first": "멜론 첫 발매",
    "spotify": "스포티파이 첫 발매", "itunes": "iTunes 첫 발매 연도", "signal": "우리 신호 첫 날짜", "outcome": "프로그램 발표",
}
Evidence = Dict[str, Tuple[str, str]]   # 출처 → (날짜, 설명)


def norm_date(raw: str) -> Optional[str]:
    """'2015' · '2015.03' · '2015-03-07…' → 'YYYY-MM-DD' (모르는 달·일은 01). 못 읽으면 None."""
    m = re.match(r"^\s*(\d{4})(?:[.\-/](\d{1,2}))?(?:[.\-/](\d{1,2}))?", raw or "")
    if not m or not 1900 < int(m.group(1)) < 2100:
        return None
    return f"{m.group(1)}-{int(m.group(2) or 1):02d}-{int(m.group(3) or 1):02d}"


def earliest_by_source(rows: Iterable[Tuple[str, str, str, str]]) -> Dict[str, Evidence]:
    """(팀, 날짜, 출처, 설명) → 팀 → 출처 → 가장 이른 (날짜, 설명)."""
    out: Dict[str, Evidence] = {}
    for team, raw, source, detail in rows:
        d = norm_date(raw)
        if not team or not d:
            continue
        cur = out.setdefault(team, {}).get(source)
        if cur is None or d < cur[0]:
            out[team][source] = (d, detail)
    return out


def flag_old(ev: Evidence, as_of: str, years: int = YEARS) -> Optional[dict]:
    """기준일 years 년 전보다 이른 출처가 있으면 {earliest, old_sources, sure(2개 이상)}, 없으면 None."""
    y, m, d = map(int, as_of.split("-"))
    cutoff = date(y - years, m, min(d, 28) if m == 2 else d).isoformat()
    old = [s for s, (day, _) in ev.items() if day < cutoff]
    if not old:
        return None
    return {"earliest": min(ev[s][0] for s in old), "old_sources": old, "sure": len(old) >= 2}


def _csv(path) -> List[dict]:
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def gather_rows(key_of) -> List[Tuple[str, str, str, str]]:
    rows: List[Tuple[str, str, str, str]] = []
    for t in _csv(LAB / "teams.csv"):
        rows.append((t["team_key"], t.get("first_release") or "", "profile", ""))
    for f in sorted(glob.glob(str(RAW / "raw_artist_profile_*_melon*.csv"))):
        for r in _csv(f):
            k = key_of(r.get("artist_text") or "")
            rows += [(k, r.get("debut_date") or "", "melon_debut", r.get("debut_title") or ""),
                     (k, r.get("first_release_date") or "", "melon_first", "")]
    for f in sorted(glob.glob(str(RAW / "raw_artist_profile_*_spotify*.csv"))):
        rows += [(key_of(r.get("artist_text") or ""), r.get("first_release_date") or "", "spotify", r.get("url") or "")
                 for r in _csv(f)]
    itunes = json.loads((RAW / "state" / "itunes.json").read_text(encoding="utf-8"))
    rows += [(k, str(v.get("first_year") or ""), "itunes", v.get("artist_name") or "") for k, v in itunes.items()]
    rows += [(s["team_key"], s["signal_date"], "signal", f"{s['branch']} {s['program'] or s['source']}") for s in _csv(LAB / "signals.csv")]
    rows += [(o["team_key"], o["announced_date"], "outcome", o["program_label"]) for o in _csv(LAB / "outcomes.csv")]
    return rows


def report(top: List[dict], ev: Dict[str, Evidence], teams: Dict[str, dict], overrides: set, as_of: str) -> str:
    lines, flagged = [], []
    for t in top:
        k = t["team_key"]
        f = flag_old(ev.get(k, {}), as_of)
        if f and k not in overrides:
            flagged.append((t, f))
    sure = [x for x in flagged if x[1]["sure"]]
    top50 = [x for x in flagged if int(x[0]["rank"]) <= 50]
    lines.append(f"상위 {len(top)}팀 중 데뷔 {YEARS}년 넘어 보이는 팀 **{len(flagged)}팀** (확실 {len(sure)} · 의심 {len(flagged) - len(sure)}), "
                 f"상위 50 안 **{len(top50)}팀** (확실 {sum(1 for x in top50 if x[1]['sure'])}). 이미 덮어쓰기에 있는 팀 제외.\n")
    cross: Dict[Tuple[str, str], int] = {}
    for t, f in flagged:
        nc = teams.get(t["team_key"], {}).get("newcomer_check") or "(팀 표에 없음)"
        cross[(nc, "확실" if f["sure"] else "의심")] = cross.get((nc, "확실" if f["sure"] else "의심"), 0) + 1
    lines.append("| 지금 newcomer_check | 확실 | 의심 |\n|---|---|---|")
    for nc in sorted({c[0] for c in cross}):
        lines.append(f"| {nc} | {cross.get((nc, '확실'), 0)} | {cross.get((nc, '의심'), 0)} |")
    lines.append("\n| 순위 | 팀 | 판정 | 가장 이른 근거 | 5년 넘은 출처 (날짜) | 지금 first_release · newcomer_check |\n|---|---|---|---|---|---|")
    for t, f in sorted(flagged, key=lambda x: int(x[0]["rank"])):
        e = ev[t["team_key"]]
        srcs = " · ".join(f"{SOURCE_LABEL[s]} {e[s][0][:7]}" + (f" ({e[s][1][:24]})" if s in ('melon_debut', 'outcome', 'signal') and e[s][1] else "")
                          for s in sorted(f["old_sources"], key=lambda s: e[s][0]))
        tm = teams.get(t["team_key"], {})
        lines.append(f"| {t['rank']} | {t.get('display_name') or t['team_key']} | {'확실' if f['sure'] else '의심'} | {f['earliest']} | {srcs} | "
                     f"{tm.get('first_release') or '—'} · {tm.get('newcomer_check') or '—'} |")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="상위 후보 기성 팀 점검")
    ap.add_argument("--top", type=int, default=300)
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from artist_xref import canonical_key, load_xref
    index = load_xref()
    key_of = lambda n: canonical_key(n, index) if n else ""  # noqa: E731
    cov = json.loads((RAW / "state" / "coverage_targets.json").read_text(encoding="utf-8"))
    top = [t for t in cov["teams"] if int(t.get("rank") or 10**9) <= args.top]
    teams = {t["team_key"]: t for t in _csv(LAB / "teams.csv")}
    overrides = set(json.loads((ROOT / "config" / "debut_overrides.json").read_text(encoding="utf-8")).get("teams", {}))
    text = report(top, earliest_by_source(gather_rows(key_of)), teams, overrides, cov.get("as_of") or date.today().isoformat())
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
