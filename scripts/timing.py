"""백테스트 시점 누수(look-ahead) 방지 날짜 규칙.

발표일을 연도나 월까지만 아는 경우가 많다 (announced_at = '2024' 또는 '2024-05').
이걸 1월 1일로 채우면 '후보가 정답보다 먼저 나왔다'는 선행 기간이 부풀려진다. 그래서 항상 보수적으로:

- 후보 신호(raw_kr_selection 등)는 그 기간의 **마지막 날**에 알았다고 본다.  2024 → 2024-12-31
- 정답(raw_outcome)은 그 기간의 **첫날**에 발표됐다고 본다.                   2024 → 2024-01-01
- 선행 기간 = 정답일 - 후보일. 0일 이하이면 '앞섰다'고 세지 않는다 (None).

6단계 검증과 백테스트는 이 함수로만 날짜를 비교한다.
"""
import calendar
import re
from datetime import date

PARTIAL = re.compile(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?$")


def _parts(text):
    m = PARTIAL.match((text or "").strip())
    return (int(m.group(1)), int(m.group(2)) if m.group(2) else None, int(m.group(3)) if m.group(3) else None) if m else None


def signal_date(text):
    p = _parts(text)
    if not p:
        return ""
    y, m, d = p
    if d:
        return date(y, m, d).isoformat()
    m = m or 12
    return date(y, m, calendar.monthrange(y, m)[1]).isoformat()


def outcome_date(text):
    p = _parts(text)
    if not p:
        return ""
    y, m, d = p
    return date(y, m or 1, d or 1).isoformat()


def lead_days(signal_text, outcome_text):
    """후보 신호가 정답보다 며칠 앞섰는지. 앞섰다고 확신할 수 없으면 None."""
    s, o = signal_date(signal_text), outcome_date(outcome_text)
    if not s or not o:
        return None
    days = (date.fromisoformat(o) - date.fromisoformat(s)).days
    return days if days > 0 else None
