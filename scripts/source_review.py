"""출처 재분류 제안 — 출처 성적표가 분류표(config/source_roles.json)와 어긋나면 자동으로 알려 준다.

    .venv/bin/python scripts/source_review.py      # → docs/data/source_review.json (공개: 출처 이름·숫자·제안만)

- 성적표: docs/lab/sql/source_scorecard.sql 을 scripts/lab_sql.py(DuckDB)로 실행.
  기준일 = 데이터 끝 날짜에서 18·12·6개월 전을 반기 시작일(1/1·7/1)로 내린 3개, since = 가장 이른 기준일 − 6개월, 관찰 24개월.
- 제안만 한다. 분류를 실제로 바꾸는 것은 사람이 config/source_roles.json 에서 (docs/source_roles.md 기준).
- 일일 기록(daily_note.py)이 월요일, 또는 제안 목록이 바뀐 날에 '출처 재분류 제안 n건'을 쓴다.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parent.parent
ROLES_FILE = ROOT / "config" / "source_roles.json"
META_FILE = ROOT / "docs" / "lab" / "data" / "meta.json"
OUT = ROOT / "docs" / "data" / "source_review.json"

CUTOFF_MONTHS_BACK = (18, 12, 6)   # 관찰 기간을 확보하려고 데이터 끝보다 반년~1년 반 앞선 기준일 3개
SINCE_MONTHS_BEFORE = 6            # 수상 팀(먼저 잡았나)은 가장 이른 기준일 반년 전부터 센다
HORIZON_MONTHS = 24                # 기준일 뒤 24개월 안 정답 = 적중 (점수 백테스트와 같은 값)

# 판정 기준 (docs/source_roles.md 의 판정 기준과 같은 뜻)
DEMOTE_LIFT = 1.0        # 발굴인데 기준선보다 못 맞히고(배수 < 1) …
DEMOTE_MAX_ONLY = 0      # … 이 출처만 잡은 수상 팀도 없으면(0) 빼도 잃는 게 없음 → 맥락으로 내릴 후보
PROMOTE_LIFT = 2.0       # 맥락인데 기준선의 2배 이상 맞히거나 …
PROMOTE_MIN_ONLY = 3     # … 이 출처만 잡은 수상 팀이 3팀 이상이면서
PROMOTE_ONLY_MIN_LIFT = 1.0   # … 정확도도 기준선 이상일 때만 (기준선 이하 출처를 '유일 기여'만으로 올리지 않음)
READY_DAYS = 90          # 검증 대기 출처는 기록 3개월(90일)이 지나고 …
READY_MIN_TEAMS = 30     # … 성적표 후보 팀이 30팀 이상 쌓이면 평가 가능
MIN_TEAMS = 20           # 후보 팀이 20팀 미만이면 1~2팀 차이로 배수가 크게 흔들림 → 제안 대신 '표본 부족'

PUBLIC_SOURCE_FIELDS = ("src", "role", "since_date", "signal_rows", "teams", "hits", "rate", "lift",
                        "winners_seen", "first_to_see", "only_source")
RULES = {"demote": f"발굴인데 배수 < {DEMOTE_LIFT:g} 이고 유일 기여 {DEMOTE_MAX_ONLY}팀 → 맥락으로 내릴 후보",
         "promote": f"맥락인데 배수 ≥ {PROMOTE_LIFT:g}, 또는 유일 기여 ≥ {PROMOTE_MIN_ONLY}팀이면서 배수 ≥ {PROMOTE_ONLY_MIN_LIFT:g} → 발굴로 올릴 후보",
         "recheck": "제외인데 적중이 생김 → 재검토",
         "ready": f"검증 대기인데 기록 {READY_DAYS}일 이상·후보 {READY_MIN_TEAMS}팀 이상 → 평가 가능",
         "unclassified": "분류표에 없는 출처 → 미분류",
         "small_sample": f"후보 {MIN_TEAMS}팀 미만이면 제안 대신 표본 부족"}


def _half_start(months_index: int) -> date:
    year, month0 = divmod(months_index, 12)
    return date(year, 1 if month0 < 6 else 7, 1)


def review_cutoffs(data_end: str) -> Tuple[List[str], str]:
    """데이터 끝 날짜 → (기준일 3개, since). 각 기준일은 N개월 전을 반기 시작일로 내린 날."""
    d = date.fromisoformat(data_end)
    idx = d.year * 12 + d.month - 1
    cuts = [_half_start(idx - n).isoformat() for n in CUTOFF_MONTHS_BACK]
    first = date.fromisoformat(cuts[0])
    since = _half_start(first.year * 12 + first.month - 1 - SINCE_MONTHS_BEFORE)
    return cuts, since.isoformat()


def cutoffs_sql(cuts: List[str]) -> str:
    return ",".join(f"(DATE '{c}')" for c in cuts)


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _item(r: dict, role: str, kind: str, suggestion: str, reason: str) -> dict:
    return {"src": r["src"], "role": role, "kind": kind, "suggestion": suggestion, "reason": reason}


def _judge(r: dict, role: str, data_end: str) -> Optional[Tuple[str, str, str]]:
    teams, hits, only, lift = _num(r.get("teams")), _num(r.get("hits")), _num(r.get("only_source")), r.get("lift")
    lift_v = None if lift is None or lift == "" else _num(lift)
    nums = f"후보 {teams:g}팀·적중 {hits:g}·배수 {'—' if lift_v is None else f'{lift_v:g}'}·유일 기여 {only:g}팀"
    if role == "discovery" and lift_v is not None and lift_v < DEMOTE_LIFT and only <= DEMOTE_MAX_ONLY:
        return "demote", "context로 내릴 후보", nums
    if role == "context" and lift_v is not None and (
            lift_v >= PROMOTE_LIFT or (only >= PROMOTE_MIN_ONLY and lift_v >= PROMOTE_ONLY_MIN_LIFT)):
        return "promote", "discovery로 올릴 후보", nums
    if role == "excluded" and hits > 0:
        return "recheck", "재검토 (제외했는데 적중이 생김)", nums
    if role == "pending":
        since = str(r.get("since_date") or "")[:10]
        try:
            days = (date.fromisoformat(data_end) - date.fromisoformat(since)).days
        except ValueError:
            return None
        if days >= READY_DAYS and teams >= READY_MIN_TEAMS:
            return "ready", "평가 가능 — 성적표로 판정", f"기록 {days}일·{nums}"
    return None


def suggest(rows: List[dict], roles: dict, data_end: str) -> List[dict]:
    """성적표 행 + 분류표 → 제안 목록. 역할은 성적표의 role 칸이 아니라 지금 분류표에서 읽는다."""
    table = (roles or {}).get("signals", {})
    out = []
    for r in rows:
        if r["src"] not in table:
            out.append(_item(r, "", "unclassified", "미분류 — 역할을 정해 주세요",
                             f"분류표에 없음 (기록 시작 {str(r.get('since_date') or '')[:10]})"))
            continue
        role = table[r["src"]].get("role", "")
        verdict = _judge(r, role, data_end)
        if not verdict:
            continue
        kind, text, reason = verdict
        if kind != "ready" and _num(r.get("teams")) < MIN_TEAMS:
            kind, text = "small_sample", f"표본 부족 (후보 {MIN_TEAMS}팀 미만) — '{text}'로 보이지만 보류"
        out.append(_item(r, role, kind, text, reason))
    return out


def _public(r: dict) -> dict:
    out = {}
    for k in PUBLIC_SOURCE_FIELDS:
        v = r.get(k)
        out[k] = v.isoformat() if hasattr(v, "isoformat") else v
    return out


def build_report(rows: List[dict], suggestions: List[dict], data_end: str, cuts: List[str], since: str,
                 prev: Optional[dict]) -> dict:
    """공개용 결과. 제안 목록이 지난번과 같으면 '바뀐 날'을 그대로 둔다 (일일 기록이 그날만 알리게)."""
    key = lambda items: sorted((s["src"], s["kind"]) for s in items)   # noqa: E731
    changed_on = data_end
    if prev and key(prev.get("suggestions", [])) == key(suggestions):
        changed_on = prev.get("suggestions_changed_on") or data_end
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "data_end": data_end, "cutoffs": cuts, "since": since, "horizon_months": HORIZON_MONTHS,
        "rules": RULES, "suggestions_changed_on": changed_on,
        "suggestions": suggestions, "sources": [_public(r) for r in rows],
    }


def run_scorecard(cuts: List[str], since: str) -> List[dict]:
    import lab_sql

    con = lab_sql.connect()
    return lab_sql.query(con, "source_scorecard.sql", cutoffs=cutoffs_sql(cuts), since=f"'{since}'",
                         horizon_months=str(HORIZON_MONTHS))


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def main() -> int:
    data_end = _load(META_FILE, {}).get("data_end") or date.today().isoformat()
    cuts, since = review_cutoffs(data_end)
    try:
        rows = run_scorecard(cuts, since)
    except ImportError:
        print("❌ duckdb가 없어요 (.venv/bin/python 으로 실행)", file=sys.stderr)
        return 1
    suggestions = suggest(rows, _load(ROLES_FILE, {}), data_end)
    report = build_report(rows, suggestions, data_end, cuts, since, prev=_load(OUT, None))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"✅ 출처 재분류 제안 {len(suggestions)}건 (기준일 {', '.join(cuts)}, since {since}) → {OUT.relative_to(ROOT)}")
    for s in suggestions:
        print(f"  - {s['src']} ({s['role'] or '미분류'}): {s['suggestion']} · {s['reason']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
