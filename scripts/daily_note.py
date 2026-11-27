"""하루 작업 기록을 만든다 (매일 저녁 daily_run.sh 가 실행).

    python3 scripts/daily_note.py            # 오늘
    python3 scripts/daily_note.py 2026-11-26

- 공개용: docs/log/<날짜>.md  (그날 커밋, 수집 결과, 지금 단계, 아직 정할 것)
- 개인용: records/ 엑셀 '작업기록' 시트에 자동 줄 추가 (worklog.py)
- 분류표(config/source_roles.json)에 없는 새 출처가 랩 데이터에 나오면 경고 한 줄 (사람이 역할을 정하도록)
- 월요일, 또는 출처 재분류 제안(docs/data/source_review.json, scripts/source_review.py)이 바뀐 날엔 '출처 재분류 제안 n건'
대화를 바탕으로 한 정리(결정 이유, 지침, 직무 참고)는 Claude가 records/entries/<날짜>.json 으로 따로 남긴다.
"""
import csv
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROLES_FILE = ROOT / "config" / "source_roles.json"
LAB_SIGNALS = ROOT / "docs" / "lab" / "data" / "signals.csv"
SOURCE_REVIEW = ROOT / "docs" / "data" / "source_review.json"
SCORE_REVIEW = ROOT / "docs" / "data" / "score_review.json"   # scripts/score_review.py (월요일)
MONDAY = 0
KST = timezone(timedelta(hours=9))
TABLE_KO = {"raw_kr_release": "발매", "raw_kr_gig": "공연", "raw_press": "평론 신호",
            "raw_kr_selection": "선정·지원", "raw_outcome": "공증"}


def source_key(row):
    """신호 행 → 분류표 키 '갈래:출처' (선정·지원은 '갈래:프로그램'). export_lab_data.signal_role 과 같은 규칙."""
    branch = (row.get("branch") or "").strip()
    name = (row.get("program") if branch == "선정·지원" else row.get("source")) or ""
    return f"{branch}:{name.strip()}" if branch and name.strip() else ""


def unclassified_sources(rows, roles):
    """분류표(roles['signals'])에 없는 출처 키 목록 (중복 없이 정렬)."""
    known = set((roles or {}).get("signals", {}))
    return sorted({k for k in (source_key(r) for r in rows) if k and k not in known})


def new_sources(signals_path=LAB_SIGNALS, roles_path=ROLES_FILE):
    """랩 데이터 신호 중 분류표에 없는 새 출처. 파일이 없으면 빈 목록."""
    try:
        with open(signals_path, encoding="utf-8") as f:
            return unclassified_sources(csv.DictReader(f), _load(Path(roles_path), {}))
    except OSError:
        return []


def review_section(day, review):
    """월요일이거나 제안이 바뀐 날이면 '출처 재분류 제안' 섹션 줄들, 아니면 []."""
    if not review:
        return []
    is_monday = datetime.strptime(day, "%Y-%m-%d").weekday() == MONDAY
    if not (is_monday or review.get("suggestions_changed_on") == day):
        return []
    items = review.get("suggestions", [])
    lines = ["", f"## 출처 재분류 제안 {len(items)}건"]
    lines += [f"- {s['src']} ({s.get('role') or '미분류'}): {s['suggestion']} — {s.get('reason', '')}" for s in items] \
        or ["- 없음 — 지금 분류가 성적표와 맞음"]
    if items:
        lines.append("- 제안만 있음. 바꿀지는 docs/source_roles.md 기준으로 사람이 config/source_roles.json 에서 정함")
    return lines


def score_review_section(day, report):
    """점수 재검토(월요일) 결과에 제안이 있으면, 그 실행일·제안이 바뀐 날에 섹션 줄들."""
    if not report or not report.get("proposals"):
        return []
    if day not in (report.get("run_date"), report.get("proposals_changed_on")):
        return []
    items = report["proposals"]
    lines = ["", f"## 점수 재검토 제안 {len(items)}건"]
    lines += [f"- {p['text']} — {p.get('reason', '')}" for p in items]
    lines.append("- 제안만 있음. 기본 가중치(scripts/lab_sql.py DEFAULTS)는 사람이 바꿈 · 근거: docs/score_tuning.md")
    return lines


def render_note(day, commits, runs, board, new_sources=None, review=None, score_review=None):
    now_steps = [s for s in board.get("steps", []) if s.get("status") == "now"]
    todays = [r for r in runs if r["date"] == day]
    open_q = [d["q"] for d in board.get("decisions", []) if d.get("state") == "결정 필요"]
    lines = [f"# {day} 작업 기록", "", "## 지금 단계"]
    lines += [f"- 단계 {s['no']} {s['name']}" for s in now_steps] or ["- (진행 중 단계 없음)"]
    lines += ["", "## 커밋"]
    lines += [f"- {c}" for c in commits] or ["- 커밋 없음"]
    lines += ["", "## 수집", "", "| 소스 | 종류 | 줄 수 | 형식 검사 |", "|---|---|---|---|"] if todays else ["", "## 수집", "- 수집 기록 없음"]
    lines += [f"| {r['source']} | {TABLE_KO.get(r['table'], r['table'])} | {r['rows']} | {'✅' if r['file_ok'] else '❌'} |"
              for r in todays]
    if new_sources:
        lines += ["", f"⚠️ 분류표에 없는 새 출처 {len(new_sources)}개: {', '.join(new_sources)} "
                      "— config/source_roles.json 에 역할(발굴·맥락·제외·검증 대기)을 정해 주세요"]
    lines += review_section(day, review)
    lines += score_review_section(day, score_review)
    lines += ["", "## 아직 정할 것"]
    lines += [f"- {q}" for q in open_q] or ["- 없음"]
    lines += ["", "진행판: https://leegmyung.github.io/crate-digger/", ""]
    return "\n".join(lines)


def auto_entry(day, commits, runs):
    todays = [r for r in runs if r["date"] == day]
    done = ", ".join(f"{r['source']} {r['rows']}줄" for r in todays) or "수집 없음"
    bad = [r["source"] for r in todays if not r["file_ok"]]
    return {"date": day, "작업기록": [{
        "파이프라인 단계": "자동 (매일 저녁)",
        "한 일": f"매일 수집: {done}",
        "결정한 것": "",
        "찾은 빈틈·보완": f"형식 검사 실패: {', '.join(bad)}" if bad else "",
        "다음 할 일": "",
        "커밋": ", ".join(c.split()[0] for c in commits),
    }]}


def todays_commits(day):
    out = subprocess.run(["git", "-C", str(ROOT), "log", f"--since={day} 00:00", f"--until={day} 23:59:59",
                          "--format=%h %s"], capture_output=True, text=True, check=False)
    return [line for line in out.stdout.splitlines() if line.strip()]


def _load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def main(argv):
    day = argv[0] if argv else f"{datetime.now(KST):%Y-%m-%d}"
    commits = todays_commits(day)
    runs = _load(ROOT / "docs" / "data" / "collect.json", {}).get("runs", [])
    board = _load(ROOT / "docs" / "data" / "board.json", {})
    out = ROOT / "docs" / "log" / f"{day}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    review = _load(SOURCE_REVIEW, None)
    out.write_text(render_note(day, commits, runs, board, new_sources(), review, _load(SCORE_REVIEW, None)), encoding="utf-8")
    try:
        import worklog   # 엑셀 도구(openpyxl)는 기록할 때만 — 없으면 아래에서 안내
        worklog.append_entry(worklog.DEFAULT_XLSX, auto_entry(day, commits, runs))
    except (OSError, ValueError, ImportError) as e:
        print(f"⚠️ 엑셀 기록 실패 (공개 기록은 저장됨): {e}", file=sys.stderr)
    print(f"✅ 일일 기록 → {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
