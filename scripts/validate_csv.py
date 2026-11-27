"""수집한 CSV가 형식 정의(csv_schema.py, docs/csv_spec.md)대로인지 검사.

    python3 scripts/validate_csv.py data/raw/raw_kr_release_2026-11-26_bugs.csv [...]

파일 이름 앞부분(raw_kr_release_ 등)으로 테이블을 고른다.
오류가 하나라도 있으면 종료 코드 1. 모르는 칸은 경고만 한다.
"""
import csv
import re
import sys
from collections import namedtuple
from datetime import date, datetime
from pathlib import Path

from csv_schema import TABLES

Issue = namedtuple("Issue", "level row column message")

DATETIME_TZ = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(Z|[+-]\d{2}:\d{2})$")
DATE_PARTIAL = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")
TIME_HM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def table_for(path):
    name = Path(path).name
    matches = [t for t in TABLES if name.startswith(t + "_")]
    return max(matches, key=len) if matches else None


def _is_real_date(text):
    parts = text.split("-")
    try:
        date(int(parts[0]), int(parts[1]) if len(parts) > 1 else 1, int(parts[2]) if len(parts) > 2 else 1)
        return True
    except ValueError:
        return False


def _is_datetime_tz(text):
    if not DATETIME_TZ.match(text):
        return False
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def check_value(field, value):
    """문제가 있으면 한국어 설명을, 없으면 None을 돌려준다."""
    kind = field.kind
    if kind == "datetime_tz" and not _is_datetime_tz(value):
        return "날짜·시간은 2026-11-26T09:30:00+09:00 처럼 시간대까지 적어 주세요"
    if kind == "date" and not (len(value) == 10 and DATE_PARTIAL.match(value) and _is_real_date(value)):
        return "날짜는 2026-11-26 형식이어야 해요"
    if kind == "date_partial" and not (DATE_PARTIAL.match(value) and _is_real_date(value)):
        return "날짜는 2026-11-26, 2026-11, 2026 중 하나의 형식이어야 해요"
    if kind == "date_or_datetime" and not (
        (len(value) == 10 and DATE_PARTIAL.match(value) and _is_real_date(value)) or _is_datetime_tz(value)
    ):
        return "2026-11-26 또는 2026-11-26T09:30:00+09:00 형식이어야 해요"
    if kind == "time_hm" and not TIME_HM.match(value):
        return "시간은 19:30 처럼 24시간 형식이어야 해요"
    if kind == "url" and not re.match(r"^https?://\S+$", value):
        return "http:// 또는 https:// 로 시작하는 주소여야 해요"
    if kind == "int_pos" and not (value.isdigit() and int(value) > 0):
        return "1 이상의 숫자여야 해요"
    if kind == "int0" and not value.isdigit():
        return "0 이상의 숫자여야 해요"
    if kind == "handle" and not re.match(r"^@[A-Za-z0-9._]{1,30}$", value):
        return "인스타 계정은 @abc_123 형식이어야 해요"
    if kind == "flag01" and value not in ("0", "1"):
        return "0 또는 1 이어야 해요"
    if kind == "code" and value not in field.choices:
        return "허용된 값이 아니에요: " + ", ".join(sorted(field.choices))
    return None


def check_header(header, fields):
    names = {f.name for f in fields}
    missing = [Issue("error", 1, f.name, "필수 칸이 없어요") for f in fields if f.required and f.name not in header]
    extra = [Issue("warning", 1, h, "정의에 없는 칸이라 무시돼요") for h in header if h not in names]
    return missing + extra


def check_rows(rows, header, spec):
    fields = [f for f in spec["fields"] if f.name in header]
    issues, seen = [], {}
    for line_no, row in enumerate(rows, start=2):
        for f in fields:
            value = (row.get(f.name) or "").strip()
            if not value:
                if f.required:
                    issues.append(Issue("error", line_no, f.name, "비어 있으면 안 돼요"))
                continue
            problem = check_value(f, value)
            if problem:
                issues.append(Issue("error", line_no, f.name, problem + " (값: " + value + ")"))
        key = tuple((row.get(k) or "").strip() for k in spec["key"])
        if all(key):
            if key in seen:
                issues.append(Issue("error", line_no, ",".join(spec["key"]), f"{seen[key]}행과 중복이에요"))
            else:
                seen[key] = line_no
    return issues


AUX_PREFIXES = ("raw_video_", "raw_collab_")   # 보조 파일: 형식은 각 수집기 테스트가 지키고, 적재 대상 표가 아님


def is_auxiliary(path):
    return Path(path).name.startswith(AUX_PREFIXES)


def validate_file(path):
    if is_auxiliary(path):
        return []
    table = table_for(path)
    if table is None:
        known = ", ".join(t + "_" for t in TABLES)
        return [Issue("error", 0, "", f"파일 이름이 테이블 이름으로 시작해야 해요 ({known})")]
    spec = TABLES[table]
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        header = [h.strip() for h in (reader.fieldnames or [])]
        reader.fieldnames = header
        rows = list(reader)
    return check_header(header, spec["fields"]) + check_rows(rows, header, spec)


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    has_error = False
    for path in argv:
        issues = validate_file(path)
        errors = [i for i in issues if i.level == "error"]
        has_error = has_error or bool(errors)
        if is_auxiliary(path):
            print(f"➖ {Path(path).name}: 보조 파일 (형식 검사 건너뜀)")
            continue
        print(f"{'❌' if errors else '✅'} {Path(path).name}: 오류 {len(errors)}개, 경고 {len(issues) - len(errors)}개")
        for i in issues:
            where = f"{i.row}행" if i.row else "파일"
            print(f"   [{'오류' if i.level == 'error' else '경고'}] {where} {i.column}: {i.message}")
    return 1 if has_error else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
