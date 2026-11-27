"""휴면 점검 — 후보 상위 팀 중 해체·활동 중단이 의심되는 팀을 고른다 (제안만, 규칙 적용은 사람이 확인한 팀만).

    .venv/bin/python scripts/dormant_check.py            # → docs/dormant_check.md (자동 칸만 다시 씀)
    .venv/bin/python scripts/dormant_check.py --top 500

기준(셋 다): 점수 v2 상위 TOP_N 안 · 마지막 신호가 기준일보다 1년 이상 전 · 최근 1년 공연 0.
마지막 신호·1년 공연은 점수와 달리 '검증 대기' 출처(인디고·인스타 등)까지 모든 신호로 센다 (activity).
인스타: 연결표(links.csv)에 팀 인스타 계정이 있는지만 본다 — 아티스트 계정의 게시물 날짜는 아직 모으지 않는다.
웹 확인 결과(해체 기사·해외 팀·기성 팀 등)는 config/dormant_review.json 에 사람이 적고, 확실한 팀만
config/source_roles.json candidate_rules.excluded_teams 에 이유·근거 링크와 함께 넣는다.
앱 '휴면' 꼬리표(docs/app/ui.js isDormantTeam: 최근 180일 신호 0 + 최근 1년 공연 0)와 숫자를 비교한다.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "dormant_check.md"
REVIEW = ROOT / "config" / "dormant_review.json"
ROLES = ROOT / "config" / "source_roles.json"
TOP_N = 300
SILENT_DAYS = 365          # 마지막 신호가 이만큼 이전이면 '1년 넘게 조용함'


def _day(v) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])


def is_dormant(row: dict, as_of: date, days: int = SILENT_DAYS) -> bool:
    return _day(row["last_seen"]) <= as_of - timedelta(days=days) and int(row.get("gigs_1y") or 0) == 0


def activity(signals, as_of: date) -> Dict[str, Tuple[str, int]]:
    """팀별 (기준일까지 마지막 신호 날짜, 최근 1년 공연 일수) — 역할(검증 대기 포함)을 가리지 않고 모든 신호로 센다."""
    end, start = as_of.isoformat(), (as_of - timedelta(days=SILENT_DAYS)).isoformat()
    last: Dict[str, str] = {}
    gig_days: Dict[str, set] = defaultdict(set)
    for s in signals:
        d = str(s.get("signal_date") or "")[:10]
        if not d or d > end:
            continue
        k = s["team_key"]
        last[k] = max(last.get(k, ""), d)
        if s.get("branch") == "공연" and d > start:
            gig_days[k].add(d)
    return {k: (d, len(gig_days[k])) for k, d in last.items()}


def merge_activity(row: dict, act: Dict[str, Tuple[str, int]]) -> dict:
    """점수 행의 마지막 신호·1년 공연을 모든 신호 기준 값으로 바꾼 새 행 (원래 행은 그대로)."""
    if row["team_key"] not in act:
        return dict(row)
    last, gigs = act[row["team_key"]]
    return {**row, "last_seen": max(_day(row["last_seen"]), _day(last)), "gigs_1y": max(int(row.get("gigs_1y") or 0), gigs),
            "scored_gigs_1y": row.get("gigs_1y")}            # 앱 휴면 비교는 점수(앱) 값으로


def is_app_dormant(row: dict) -> bool:
    """docs/app/ui.js isDormantTeam 과 같은 규칙: 최근 180일 신호 0 + 최근 1년 공연 0."""
    return int(row.get("recent180") or 0) == 0 and int(row.get("scored_gigs_1y", row.get("gigs_1y")) or 0) == 0


def compare(rows: Sequence[dict], as_of: date) -> Dict[str, List[str]]:
    rule = {r["team_key"] for r in rows if is_dormant(r, as_of)}
    app = {r["team_key"] for r in rows if is_app_dormant(r)}
    order = [r["team_key"] for r in rows]
    return {"both": [k for k in order if k in rule and k in app],
            "rule_only": [k for k in order if k in rule and k not in app],
            "app_only": [k for k in order if k in app and k not in rule]}


def insta_status(team_key: str, links: Dict[str, Dict[str, str]]) -> str:
    return "계정 있음 (게시물 확인 안 함)" if (links.get(team_key) or {}).get("instagram") else "계정 없음"


def review_cell(team_key: str, review: Dict[str, dict]) -> str:
    r = review.get(team_key)
    if not r:
        return "아직 안 봄"
    text = r.get("status", "")
    if r.get("note"):
        text += f" — {r['note']}"
    if r.get("url"):
        text += f" ([근거]({r['url']}))"
    return text


def already_excluded(review: Dict[str, dict], excluded: Dict[str, str]) -> List[str]:
    return [k for k in review if k in excluded]


def timeless_share(row: dict) -> float:
    """기간 제한 없이 쌓이는 점수(서로 다른 공연장 수 + 정답 팀과 같은 무대)가 점수에서 차지하는 비중."""
    score = float(row.get("score") or 0)
    timeless = float(row.get("pts_venues") or 0) + float(row.get("pts_winner") or 0)
    return round(timeless / score, 2) if score > 0 else 0.0


def replace_block(text: str, name: str, body: str) -> str:
    start, end = f"<!-- AUTO:{name}:START -->", f"<!-- AUTO:{name}:END -->"
    pat = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)
    block = f"{start}\n{body}\n{end}"
    if not pat.search(text):
        return (text.rstrip() + "\n\n" if text.strip() else "") + block + "\n"
    return pat.sub(lambda _: block, text, count=1)


def _team_table(ranked: Sequence[Tuple[int, dict]], as_of: date, links, review, excluded) -> List[str]:
    lines = ["| 순위 | 팀 | 점수 | 마지막 신호 | 기간 없는 점수 비중 | 인스타 | 웹 확인 |", "|---|---|---|---|---|---|---|"]
    for rank, r in ranked:
        if not is_dormant(r, as_of):
            continue
        lines.append(f"| {rank} | {r['display_name']} | {float(r['score']):.2f} | {_day(r['last_seen'])} | "
                     f"{timeless_share(r):.0%} | {insta_status(r['team_key'], links)} | {review_cell(r['team_key'], review)}"
                     f"{' → **후보 제외 목록에 넣음**' if r['team_key'] in excluded else ''} |")
    return lines


def render(ranked: Sequence[Tuple[int, dict]], as_of: date, links, review, excluded, top: int) -> str:
    rows = [r for _, r in ranked]
    cmp = compare(rows, as_of)
    names = {r["team_key"]: r["display_name"] for r in rows}
    hits = [r for r in rows if is_dormant(r, as_of)]
    shares = sorted(timeless_share(r) for r in hits)
    out = [f"기준일 {as_of} · 점수 v2 상위 {top}팀 중 **마지막 신호 1년 이상 전 + 최근 1년 공연 0** = **{len(hits)}팀**", ""]
    out += _team_table(ranked, as_of, links, review, excluded)
    out += ["", "**앱 '휴면' 꼬리표와 비교** (앱: 최근 180일 신호 0 + 최근 1년 공연 0)", "",
            "| 구분 | 팀 수 | 팀 |", "|---|---|---|",
            f"| 둘 다 | {len(cmp['both'])} | — |",
            f"| 이 점검에만 | {len(cmp['rule_only'])} | {', '.join(names[k] for k in cmp['rule_only']) or '—'} |",
            f"| 앱 휴면에만 (반년~1년 조용하거나, 최근 기록이 검증 대기 출처에만 있음) | {len(cmp['app_only'])} | {', '.join(names[k] for k in cmp['app_only']) or '—'} |"]
    if shares:
        out += ["", f"이 팀들 점수에서 **기간 제한 없는 점수**('서로 다른 공연장 수' + '정답 팀과 같은 무대')가 차지하는 비중: "
                    f"중앙값 {shares[len(shares) // 2]:.0%} — 두 점수는 최근 1년이 아니라 관찰 기간 전체로 세서, "
                    f"오래전 여러 공연장·좋은 무대에 섰던 팀이 지금도 위에 남는다."]
    done = already_excluded(review, excluded)
    if done:
        out += ["", "**웹 확인 뒤 후보 제외 목록에 넣은 팀** (`candidate_rules.excluded_teams` — 다음 랩 데이터 내보내기부터 팀 표·후보에서 빠짐): "
                + ", ".join(f"{k} ({review[k].get('status', '')})" for k in done)]
    return "\n".join(out)


def _links(path: Path) -> Dict[str, Dict[str, str]]:
    out: Dict[str, Dict[str, str]] = defaultdict(dict)
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out[r["team_key"]][r["platform"]] = r["url"]
    return out


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def main(argv=None) -> int:
    import lab_sql
    ap = argparse.ArgumentParser(description="휴면 점검 (제안만)")
    ap.add_argument("--top", type=int, default=TOP_N, help="몇 위까지 볼지")
    args = ap.parse_args(argv)
    con = lab_sql.connect()
    meta = _load_json(lab_sql.DATA_DIR / "meta.json")
    as_of = _day(meta.get("data_end") or date.today().isoformat())
    cands = lab_sql.query(con, "candidates.sql", as_of=f"'{as_of}'", limit=str(args.top))
    review = {k: v for k, v in _load_json(REVIEW).items() if not k.startswith("_")}
    excluded = (_load_json(ROLES).get("candidate_rules") or {}).get("excluded_teams") or {}
    with open(lab_sql.DATA_DIR / "signals.csv", encoding="utf-8") as fh:
        act = activity(csv.DictReader(fh), as_of)
    cands = [merge_activity(r, act) for r in cands]
    body = render(list(enumerate(cands, 1)), as_of, _links(lab_sql.DATA_DIR / "links.csv"), review, excluded, args.top)
    text = DOC.read_text(encoding="utf-8") if DOC.exists() else ""
    DOC.write_text(replace_block(text, "LIST", body), encoding="utf-8")
    hits = sum(1 for r in cands if is_dormant(r, as_of))
    print(f"✅ 휴면 의심 {hits}팀 / 상위 {args.top} → {DOC.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
