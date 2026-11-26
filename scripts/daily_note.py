"""하루 작업 기록을 만든다 (매일 저녁 daily_run.sh 가 실행).

    python3 scripts/daily_note.py            # 오늘
    python3 scripts/daily_note.py 2026-11-26

- 공개용: docs/log/<날짜>.md  (그날 커밋, 수집 결과, 지금 단계, 아직 정할 것)
- 개인용: records/ 엑셀 '작업기록' 시트에 자동 줄 추가 (worklog.py)
대화를 바탕으로 한 정리(결정 이유, 지침, 직무 참고)는 Claude가 records/entries/<날짜>.json 으로 따로 남긴다.
"""
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import worklog

ROOT = Path(__file__).resolve().parent.parent
KST = timezone(timedelta(hours=9))
TABLE_KO = {"raw_kr_release": "발매", "raw_kr_gig": "공연", "raw_press": "평론 신호",
            "raw_kr_selection": "선정·지원", "raw_outcome": "공증"}


def render_note(day, commits, runs, board):
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
    out.write_text(render_note(day, commits, runs, board), encoding="utf-8")
    try:
        worklog.append_entry(worklog.DEFAULT_XLSX, auto_entry(day, commits, runs))
    except (OSError, ValueError) as e:
        print(f"⚠️ 엑셀 기록 실패 (공개 기록은 저장됨): {e}", file=sys.stderr)
    print(f"✅ 일일 기록 → {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
