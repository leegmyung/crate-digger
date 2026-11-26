"""작업 기록 엑셀에 하루치 기록을 이어 붙인다 (내 맥에만 두는 개인 기록, 공개 저장소에 안 올라감).

    python3 scripts/worklog.py records/entries/2026-11-26.json
    python3 scripts/worklog.py records/entries/2026-11-26.json --xlsx records/crate-digger_작업기록.xlsx

기록 JSON 형식:
    {"date": "2026-11-26",
     "작업기록": [{"파이프라인 단계": "...", "한 일": "...", ...}],
     "결정사항": [...], "지침": [...], "직무참고": [...]}
같은 내용을 다시 넣어도 중복으로 쌓이지 않는다.
"""
import argparse
import json
import sys
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_XLSX = ROOT / "records" / "crate-digger_작업기록.xlsx"

SHEETS = {
    "작업기록": ["파이프라인 단계", "한 일", "결정한 것", "찾은 빈틈·보완", "다음 할 일", "커밋"],
    "결정사항": ["주제", "결정", "이유"],
    "지침": ["분류", "지침 내용"],
    "직무참고": ["출처", "요구 역량·내용", "프로젝트 반영"],
}
COLUMN_WIDTH = {"날짜": 12, "한 일": 48, "찾은 빈틈·보완": 40, "지침 내용": 70, "요구 역량·내용": 50,
                "프로젝트 반영": 50, "결정": 40, "이유": 40, "다음 할 일": 32}
HEADER_FILL = PatternFill("solid", fgColor="EFEAFD")


def _open(path):
    if path.exists():
        return load_workbook(path)
    wb = Workbook()
    wb.remove(wb.active)
    for name, cols in SHEETS.items():
        ws = wb.create_sheet(name)
        header = ["날짜"] + cols
        ws.append(header)
        for i, col in enumerate(header, start=1):
            cell = ws.cell(row=1, column=i)
            cell.font = Font(bold=True)
            cell.fill = HEADER_FILL
            ws.column_dimensions[cell.column_letter].width = COLUMN_WIDTH.get(col, 18)
        ws.freeze_panes = "A2"
    return wb


def _existing_rows(ws):
    return {tuple("" if v is None else str(v) for v in row) for row in ws.iter_rows(min_row=2, values_only=True)}


def _check(entry):
    if not entry.get("date"):
        raise ValueError("기록에 date 가 없어요")
    for sheet, items in entry.items():
        if sheet == "date":
            continue
        if sheet not in SHEETS:
            raise ValueError(f"모르는 시트: {sheet}")
        for item in items:
            unknown = set(item) - set(SHEETS[sheet])
            if unknown:
                raise ValueError(f"{sheet} 시트에 없는 칸: {', '.join(sorted(unknown))}")


def append_entry(path, entry):
    """기록을 붙이고 시트별로 새로 붙인 줄 수를 돌려준다."""
    _check(entry)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = _open(path)
    added = {name: 0 for name in SHEETS}
    for sheet, cols in SHEETS.items():
        ws = wb[sheet]
        seen = _existing_rows(ws)
        for item in entry.get(sheet, []):
            row = tuple([entry["date"]] + [str(item.get(c, "")) for c in cols])
            if row in seen:
                continue
            ws.append(list(row))
            for cell in ws[ws.max_row]:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
            seen.add(row)
            added[sheet] += 1
    wb.save(path)
    return added


def main(argv):
    ap = argparse.ArgumentParser(description="작업 기록 엑셀에 하루치 기록 추가")
    ap.add_argument("entry", help="기록 JSON 파일")
    ap.add_argument("--xlsx", default=str(DEFAULT_XLSX))
    args = ap.parse_args(argv)
    try:
        entry = json.loads(Path(args.entry).read_text(encoding="utf-8"))
        added = append_entry(Path(args.xlsx), entry)
    except (OSError, ValueError) as e:
        print(f"❌ 기록 실패: {e}", file=sys.stderr)
        return 1
    print("✅ " + ", ".join(f"{k} {v}줄" for k, v in added.items()) + f" 추가 → {args.xlsx}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
