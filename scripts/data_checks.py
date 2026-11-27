"""매일 데이터 검사 → docs/data_checks.md (+ docs/data/data_checks.json)

매일 자동 실행 뒤 '데이터가 이상하지 않은지' 스스로 검사한다. 각 검사는 이름·기준·오늘 값·통과/경고/실패·고치는 법 한 줄.
경고·실패가 있으면 문서 맨 위 '먼저 볼 것'에 모인다.

    .venv/bin/python scripts/data_checks.py            # 랩 데이터 + PostgreSQL(읽기만)
    .venv/bin/python scripts/data_checks.py --no-pg    # DB 없이 파일만

읽는 것: docs/lab/data/(meta.json·*.csv·snapshots), docs/data/collect.json, config/source_roles.json,
PostgreSQL은 SELECT만 한다(쓰기 없음). 공개 문서라 숫자·출처 이름·팀 키만 쓴다.
실패가 하나라도 있으면 1로 끝난다(문서는 그래도 쓴다).
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Set
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from csv_schema import CAREER_FILTER_YEARS, CAREER_FILTERED  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT_MD = ROOT / "docs" / "data_checks.md"
OUT_JSON = ROOT / "docs" / "data" / "data_checks.json"

Run = Callable[[str], str]

STATUS_KO = {"pass": "통과", "warn": "경고", "fail": "실패", "skip": "건너뜀"}
STATUS_ICON = {"pass": "✅", "warn": "⚠️", "fail": "❌", "skip": "➖"}
STATUS_ORDER = {"fail": 0, "warn": 1, "pass": 2, "skip": 3}

# ---------- 기준값 ----------
COLLECT_WARN_DAYS = 2        # 마지막 성공 수집이 이틀보다 오래되면 경고 (진행 점검표 STALE_DAYS와 같음)
COLLECT_FAIL_DAYS = 7        # 일주일보다 오래되면 실패 (출처가 끊김)
RECENCY_WARN_DAYS = 14       # 매일 받는 갈래(공연·발매·큐레이션)의 가장 최근 신호가 2주보다 오래되면 경고
RECENCY_FAIL_DAYS = 45
RECENCY_SKIP_BRANCHES = {"선정·지원"}   # 선정 명단은 1년에 몇 번만 나와서 신선도 검사 안 함
ROW_MIN_PREV = 20            # 어제 20행 미만인 작은 표는 급변 검사 안 함
ROW_DROP_RATIO = 0.7         # 어제보다 30% 넘게 줄면 실패
ROW_JUMP_RATIO = 1.5         # 어제보다 50% 넘게 늘면 경고 (중복 적재 의심)
META_FAIL_DAYS = 1           # 랩 데이터가 하루보다 오래되면 실패 (매일 갱신돼야 함)
SIDE_ORPHAN_WARN = 0.15      # 링크·사진·영상 중 팀 표에 없는 팀 비율 (신호 없이 프로필만 받은 팀이 일부 있음)
GIG_FUTURE_MAX_DAYS = 365    # 공연은 미래 날짜가 정상이지만 1년 넘게 뒤면 날짜 오류 의심
GENRE_WARN, GENRE_FAIL = 0.20, 0.60          # 프로필 있는 팀 중 장르 미분류 비율
FIRST_RELEASE_WARN, FIRST_RELEASE_FAIL = 0.90, 0.70   # 프로필 있는 팀 중 첫 발매일 보유율
URL_FAIL_RATIO = 0.02        # 주소 모양이 이상한 비율이 2% 넘으면 실패 (하나라도 있으면 경고)
TOP_N = 100
TOP_NO_PROFILE_WARN, TOP_NO_PROFILE_FAIL = 0.30, 0.80
PG_SYNC_TOLERANCE = 0.01     # DB 신호 수와 랩 신호 수가 1% 넘게 다르면 경고
PG_MISSING_WARN = 0.01       # 팀 이름·날짜 없는 신호가 1% 넘으면 경고
EXAMPLES = 8                 # 값 칸에 보여 줄 예시 개수

LINK_HOSTS = {"melon": {"www.melon.com"}, "genie": {"www.genie.co.kr"}, "bugs": {"music.bugs.co.kr"},
              "spotify": {"open.spotify.com"}, "instagram": {"www.instagram.com"},
              "youtube": {"www.youtube.com", "youtube.com", "m.youtube.com"}}
IMAGE_HOSTS = {"i.scdn.co", "i.ytimg.com", "yt3.ggpht.com", "yt3.googleusercontent.com", "cdnimg.melon.co.kr"}


@dataclass(frozen=True)
class Check:
    key: str
    name: str
    rule: str
    value: str
    status: str      # pass / warn / fail / skip
    fix: str


# ---------- 작은 도우미 ----------

def _days(earlier: str, later: str) -> Optional[int]:
    try:
        return (date.fromisoformat(later[:10]) - date.fromisoformat(earlier[:10])).days
    except (TypeError, ValueError):
        return None


def _full_date(text: str) -> str:
    text = (text or "")[:10]
    return {4: text + "-01-01", 7: text + "-01"}.get(len(text), text)


def _pct(part: int, whole: int) -> str:
    return f"{part / whole * 100:.1f}%" if whole else "-"


def _examples(items: Iterable[str], n: int = EXAMPLES) -> str:
    items = list(items)
    more = f" 외 {len(items) - n}" if len(items) > n else ""
    return ", ".join(items[:n]) + more


def _level(ratio: float, warn: float, fail: float, higher_is_bad: bool = True) -> str:
    if higher_is_bad:
        return "fail" if ratio > fail else "warn" if ratio > warn else "pass"
    return "fail" if ratio < fail else "warn" if ratio < warn else "pass"


def squash(key: str) -> str:
    """중복 의심 비교용: 소문자, 앞의 the 떼기, 글자·숫자(한글 자모·일본어·한자 포함)만 남김."""
    k = (key or "").lower().strip()
    if k.startswith("the") and len(re.sub(r"\W", "", k[3:])) >= 3:
        k = k[3:]
    return re.sub(r"[^0-9a-z가-힣ㄱ-ㅎㅏ-ㅣ\u3040-\u30ff\u4e00-\u9fff]", "", k)


# ---------- 신선도·행 수 ----------

def check_collect_freshness(runs: List[dict], today: str) -> Check:
    name, rule = "출처별 마지막 수집", f"성공 수집이 {COLLECT_WARN_DAYS}일 넘으면 경고, {COLLECT_FAIL_DAYS}일 넘으면 실패"
    fix = "records/daily_run.log에서 그 출처 줄의 ⚠️를 찾아 수집기를 직접 다시 돌려 본다"
    last: Dict[str, str] = {}
    for r in runs:
        if (r.get("rows") or 0) > 0 and r.get("date"):
            k = f"{r.get('source')}({r.get('table')})"
            last[k] = max(last.get(k, ""), r["date"])
    if not last:
        return Check("collect_fresh", name, rule, "수집 기록 없음", "skip", fix)
    ages = {k: _days(d, today) or 0 for k, d in last.items()}
    stale = sorted((k for k, a in ages.items() if a > COLLECT_WARN_DAYS), key=lambda k: -ages[k])
    status = "fail" if any(ages[k] > COLLECT_FAIL_DAYS for k in stale) else "warn" if stale else "pass"
    value = f"출처 {len(last)}개 중 오래된 것 {len(stale)}개"
    if stale:
        value += ": " + _examples(f"{k} {ages[k]}일" for k in stale)
    return Check("collect_fresh", name, rule, value, status, fix)


def check_signal_recency(signals: List[dict], today: str) -> Check:
    name = "출처별 가장 최근 신호"
    rule = (f"공연·발매·큐레이션 출처의 오늘 이전 마지막 신호가 {RECENCY_WARN_DAYS}일 넘으면 경고, "
            f"{RECENCY_FAIL_DAYS}일 넘거나 없으면 실패 (선정·지원은 제외)")
    fix = "그 출처 수집기가 새 글을 못 읽는지(사이트 구조 변경) 확인한다 — 원래 드물게 올리는 곳이면 기준에서 뺀다"
    last: Dict[str, str] = {}
    for s in signals:
        if s.get("branch") in RECENCY_SKIP_BRANCHES:
            continue
        k = f"{s.get('branch')}:{s.get('source')}"
        d = (s.get("signal_date") or "")[:10]
        last.setdefault(k, "")
        if d and d <= today:
            last[k] = max(last[k], d)
    if not last:
        return Check("signal_recency", name, rule, "신호 없음", "skip", fix)
    ages = {k: (_days(d, today) if d else None) for k, d in last.items()}
    bad = {k: a for k, a in ages.items() if a is None or a > RECENCY_WARN_DAYS}
    status = "fail" if any(a is None or a > RECENCY_FAIL_DAYS for a in bad.values()) else "warn" if bad else "pass"
    order = sorted(bad, key=lambda k: -(bad[k] if bad[k] is not None else 10 ** 6))
    value = f"출처 {len(last)}개 중 오래된 것 {len(bad)}개"
    if bad:
        value += ": " + _examples(f"{k} {'신호 없음' if bad[k] is None else str(bad[k]) + '일'}" for k in order)
    return Check("signal_recency", name, rule, value, status, fix)


def check_row_change(meta: dict) -> Check:
    name = "전날 대비 행 수"
    rule = (f"어제 {ROW_MIN_PREV}행 이상인 표가 {int(round((1 - ROW_DROP_RATIO) * 100))}% 넘게 줄면 실패, "
            f"{int(round((ROW_JUMP_RATIO - 1) * 100))}% 넘게 늘면 경고")
    fix = "줄었으면 그날 수집·적재 로그 확인(수집 실패·연결표 오류), 늘었으면 같은 행이 두 번 들어갔는지 확인"
    prev, rows = meta.get("prev_rows") or {}, meta.get("rows") or {}
    if not prev:
        return Check("row_change", name, rule, "비교할 어제 값 없음 (meta.json prev_rows 비어 있음)", "skip", fix)
    drops, jumps = [], []
    for k, p in prev.items():
        now = rows.get(k)
        if now is None or (p or 0) < ROW_MIN_PREV:
            continue
        if now < p * ROW_DROP_RATIO:
            drops.append(f"{k} {p:,}→{now:,}")
        elif now > p * ROW_JUMP_RATIO:
            jumps.append(f"{k} {p:,}→{now:,}")
    status = "fail" if drops else "warn" if jumps else "pass"
    changed = [f"{k} {prev[k]:,}→{rows[k]:,}" for k in rows if k in prev and prev[k] != rows[k]]
    value = ("급감: " + ", ".join(drops) + " " if drops else "") + ("급증: " + ", ".join(jumps) if jumps else "")
    value = value.strip() or ("변화: " + _examples(changed) if changed else "어제와 같음")
    return Check("row_change", name, rule, value, status, fix)


def check_meta_rows(meta: dict, counts: Dict[str, int]) -> Check:
    name, rule = "meta.json 행 수 = 실제 CSV 행 수", "다르면 실패 (내보내기가 중간에 끊긴 것)"
    fix = ".venv/bin/python scripts/export_lab_data.py 를 다시 돌린다"
    rows = meta.get("rows") or {}
    diff = [f"{k} 메타 {rows[k]:,}·파일 {counts[k]:,}" for k in rows if k in counts and rows[k] != counts[k]]
    value = "불일치: " + ", ".join(diff) if diff else f"표 {sum(1 for k in rows if k in counts)}개 모두 일치"
    return Check("meta_rows", name, rule, value, "fail" if diff else "pass", fix)


def check_meta_fresh(meta: dict, today: str) -> Check:
    name, rule = "랩 데이터 갱신 시각", f"{META_FAIL_DAYS}일 넘게 안 바뀌면 실패"
    fix = "daily_run.sh의 export_lab_data.py 줄이 실패했는지 records/daily_run.log 확인"
    gen = str(meta.get("generated_at") or "")
    age = _days(gen, today) if gen else None
    if age is None:
        return Check("meta_fresh", name, rule, "생성 시각 없음", "fail", fix)
    return Check("meta_fresh", name, rule, f"{gen[:16].replace('T', ' ')} ({age}일 전)",
                 "fail" if age > META_FAIL_DAYS else "pass", fix)


# ---------- 팀 연결 ----------

def check_orphan_signals(signals: List[dict], team_keys: Set[str], excluded: Set[str]) -> Check:
    name, rule = "신호의 팀이 팀 표에 있나", "제외 목록 팀 말고 팀 표에 없는 신호가 있으면 실패"
    fix = "export_lab_data.py의 signals·teams 쿼리가 같은 sig 조건을 쓰는지 확인 (한쪽만 거르면 생김)"
    orphans = [s["team_key"] for s in signals if s.get("team_key") not in team_keys and s.get("team_key") not in excluded]
    skipped = sum(1 for s in signals if s.get("team_key") in excluded and s.get("team_key") not in team_keys)
    value = f"없는 팀 신호 {len(orphans)}건 / {len(signals):,}건 (제외 목록 팀 신호 {skipped}건은 정상)"
    if orphans:
        value += " — " + _examples(sorted(set(orphans)))
    return Check("orphan_signals", name, rule, value, "fail" if orphans else "pass", fix)


def check_orphan_side(tables: Dict[str, List[dict]], team_keys: Set[str], excluded: Set[str]) -> Check:
    name = "링크·사진·영상의 팀이 팀 표에 있나"
    rule = f"표마다 팀 표에 없는 팀 비율이 {int(SIDE_ORPHAN_WARN * 100)}% 넘으면 경고"
    fix = "신호 없이 프로필만 받은 팀(멜론 보강 명단)인지, 팀 키 표기가 달라 못 이은 것인지 몇 개 열어 본다"
    parts, bad = [], []
    for name_, rows in tables.items():
        if not rows:
            continue
        miss = sum(1 for r in rows if r.get("team_key") not in team_keys and r.get("team_key") not in excluded)
        parts.append(f"{name_} {miss}/{len(rows):,} ({_pct(miss, len(rows))})")
        if miss / len(rows) > SIDE_ORPHAN_WARN:
            bad.append(name_)
    if not parts:
        return Check("orphan_side", name, rule, "표가 비어 있음", "skip", fix)
    return Check("orphan_side", name, rule, " · ".join(parts), "warn" if bad else "pass", fix)


def check_future_signals(signals: List[dict], today: str) -> Check:
    name = "미래 날짜 신호"
    rule = f"공연이 아닌 신호가 미래 날짜면 경고, 공연도 {GIG_FUTURE_MAX_DAYS}일 넘게 뒤면 경고"
    fix = "그 출처 수집기의 날짜 읽기(연도 추정·발표일 대신 행사일)를 확인한다"
    odd: Counter = Counter()
    for s in signals:
        d = (s.get("signal_date") or "")[:10]
        if not d or d <= today:
            continue
        ahead = _days(today, d) or 0
        if s.get("branch") != "공연" or ahead > GIG_FUTURE_MAX_DAYS:
            odd[f"{s.get('branch')}:{s.get('source')}"] += 1
    value = f"{sum(odd.values())}건" + (": " + _examples(f"{k} {n}건" for k, n in odd.most_common()) if odd else "")
    return Check("future_signals", name, rule, value, "warn" if odd else "pass", fix)


def check_duplicate_names(team_keys: Iterable[str]) -> Check:
    name, rule = "같은 팀 중복 의심", "띄어쓰기·대소문자·앞의 the만 다른 팀 키가 있으면 경고"
    fix = "같은 팀이면 config 연결표(아티스트 별칭)에 묶고, 다른 팀이면 '다른 팀' 구역에 적는다"
    groups: Dict[str, List[str]] = defaultdict(list)
    for k in team_keys:
        s = squash(k)
        if s:
            groups[s].append(k)
    dups = sorted(sorted(v) for v in groups.values() if len(v) > 1)
    value = f"{len(dups)}묶음" + (": " + _examples(" = ".join(g) for g in dups) if dups else "")
    return Check("duplicate_names", name, rule, value, "warn" if dups else "pass", fix)


# ---------- 정답 ----------

def _expected_counted(outcome: dict, teams: Dict[str, dict], filtered: Set[str], years: int) -> Optional[bool]:
    if outcome.get("program") not in filtered:
        return True
    t = teams.get(outcome.get("team_key"))
    if t is None:
        return None
    fr = _full_date(t.get("first_release") or "")
    if not fr:
        return False
    age = _days(fr, _full_date(outcome.get("announced_date") or ""))
    return age is not None and age / 365.25 <= years


def check_counted(outcomes: List[dict], teams: Dict[str, dict], filtered: Set[str], years: int) -> Check:
    name = "정답 '셈' 판정 일관성"
    rule = f"기성 팀이 섞인 정답({', '.join(sorted(filtered))})은 첫 발매 {years}년 이내만 셈, 나머지는 모두 셈 — 다르면 실패"
    fix = "sql/kr/00_core_views.sql의 v_outcome·v_team_profile과 export_lab_data.py의 팀 표 첫 발매 규칙이 같은지 확인"
    wrong, unknown = [], 0
    for o in outcomes:
        exp = _expected_counted(o, teams, filtered, years)
        if exp is None:
            unknown += 1
        elif exp != (str(o.get("counted")).lower() == "true"):
            wrong.append(f"{o.get('team_key')}({o.get('program')})")
    value = f"불일치 {len(wrong)}건 · 확인 못 함 {unknown}건(팀 표에 없음) / 정답 {len(outcomes)}행"
    if wrong:
        value += " — " + _examples(wrong)
    return Check("counted", name, rule, value, "fail" if wrong else "pass", fix)


def check_b_grade_rule(roles: dict, filtered: Set[str]) -> Check:
    name = "B등급 정답의 5년 규칙"
    rule = "source_roles.json에서 B등급('첫 발매 5년 이내 팀만 셈')인 정답이 실제 5년 규칙 목록에 없으면 경고"
    fix = "그 정답을 csv_schema.CAREER_FILTERED·ref.outcome_tier에 넣거나, 설명에서 5년 규칙 예외라고 적는다"
    b = sorted(k for k, v in (roles.get("outcomes") or {}).items() if isinstance(v, dict) and v.get("grade") == "B")
    missing = [p for p in b if p not in filtered]
    value = f"B등급 {len(b)}개 중 규칙 밖 {len(missing)}개" + (": " + ", ".join(missing) if missing else "")
    return Check("b_grade_rule", name, rule, value, "warn" if missing else "pass", fix)


def check_same_house(outcomes: List[dict], roles: dict) -> Check:
    name = "'같은 집안' 표시"
    rule = "점수 출처 표시(same_house_scored)는 집안 출처가 있을 때만 — 어긋나면 실패, 규칙이 켜졌는데 표시 0건이면 경고"
    fix = "export_lab_data.same_house_flags와 config same_house(apply=true) 짝을 확인"
    flagged = sum(1 for o in outcomes if o.get("same_house_sources"))
    scored = sum(1 for o in outcomes if str(o.get("same_house_scored")).lower() == "true")
    broken = sum(1 for o in outcomes if str(o.get("same_house_scored")).lower() == "true" and not o.get("same_house_sources"))
    pairs = sum(1 for p in roles.get("same_house") or [] if p.get("apply"))
    value = f"표시 {flagged}건 (점수 출처 포함 {scored}건) · 켜진 짝 {pairs}개" + (f" · 어긋남 {broken}건" if broken else "")
    status = "fail" if broken else "warn" if pairs and not flagged else "pass"
    return Check("same_house", name, rule, value, status, fix)


# ---------- 채움 비율 ----------

def _profiled(teams: List[dict]) -> List[dict]:
    return [t for t in teams if (t.get("profile_status") or "unknown") != "unknown"]


def check_genre(teams: List[dict]) -> Check:
    name = "장르 미분류"
    rule = f"프로필 있는 팀 중 장르 빈칸이 {int(GENRE_WARN * 100)}% 넘으면 경고, {int(GENRE_FAIL * 100)}% 넘으면 실패"
    fix = "build_dashboard_data._infer_genres의 장르 이름표에 새 표기(멜론·스포티파이 장르)를 추가한다"
    prof = _profiled(teams)
    if not prof:
        return Check("genre", name, rule, "프로필 있는 팀 없음", "skip", fix)
    empty = sum(1 for t in prof if not t.get("primary_genre"))
    all_empty = sum(1 for t in teams if not t.get("primary_genre"))
    value = f"프로필 팀 {empty}/{len(prof):,} ({_pct(empty, len(prof))}) · 전체 팀 {_pct(all_empty, len(teams))}"
    return Check("genre", name, rule, value, _level(empty / len(prof), GENRE_WARN, GENRE_FAIL), fix)


def check_first_release(teams: List[dict]) -> Check:
    name = "첫 발매일 보유율"
    rule = (f"프로필 있는 팀 중 첫 발매일이 있는 비율이 {int(FIRST_RELEASE_WARN * 100)}% 밑이면 경고, "
            f"{int(FIRST_RELEASE_FAIL * 100)}% 밑이면 실패")
    fix = "멜론·스포티파이 프로필 수집기가 발매일을 못 읽는지(페이지 구조 변경) 확인한다"
    prof = _profiled(teams)
    if not prof:
        return Check("first_release", name, rule, "프로필 있는 팀 없음", "skip", fix)
    have = sum(1 for t in prof if t.get("first_release"))
    all_have = sum(1 for t in teams if t.get("first_release"))
    value = f"프로필 팀 {have}/{len(prof):,} ({_pct(have, len(prof))}) · 전체 팀 {_pct(all_have, len(teams))}"
    return Check("first_release", name, rule, value,
                 _level(have / len(prof), FIRST_RELEASE_WARN, FIRST_RELEASE_FAIL, higher_is_bad=False), fix)


def _bad_url(url: str, hosts: Set[str]) -> bool:
    p = urlparse(url or "")
    return p.scheme != "https" or p.netloc not in hosts


def check_url_shapes(links: List[dict], images: List[dict]) -> Check:
    name = "링크·사진 주소 모양"
    rule = (f"https가 아니거나 플랫폼 주소가 아니면 이상 — 하나라도 있으면 경고, {int(URL_FAIL_RATIO * 100)}% 넘으면 실패 "
            "(주소를 실제로 열어 보지는 않음)")
    fix = "export_lab_data._link_url·image_rows의 주소 규칙(URL_TEMPLATES·IMAGE_CACHE_HOSTS)을 확인"
    bad = [f"{r.get('platform')}" for r in links if _bad_url(r.get("url", ""), LINK_HOSTS.get(r.get("platform"), set()))]
    bad += [f"사진:{r.get('source')}" for r in images if _bad_url(r.get("url", ""), IMAGE_HOSTS)]
    dup = len(links) - len({(r.get("team_key"), r.get("platform"), r.get("url")) for r in links})
    total = len(links) + len(images)
    if not total:
        return Check("url_shapes", name, rule, "링크·사진 없음", "skip", fix)
    value = f"이상 {len(bad)}건 / {total:,}건 ({_pct(len(bad), total)})" + (f" · 중복 링크 {dup}건" if dup else "")
    if bad:
        value += " — " + _examples(f"{k} {n}" for k, n in Counter(bad).most_common())
    status = "fail" if len(bad) / total > URL_FAIL_RATIO else "warn" if bad or dup else "pass"
    return Check("url_shapes", name, rule, value, status, fix)


def check_top_profile(snapshot: List[dict], teams: Dict[str, dict], top: int = TOP_N) -> Check:
    name = f"점수 상위 {top}팀 중 프로필 없음"
    rule = (f"프로필(멜론·스포티파이)이 없는 팀 비율이 {int(TOP_NO_PROFILE_WARN * 100)}% 넘으면 경고, "
            f"{int(TOP_NO_PROFILE_FAIL * 100)}% 넘으면 실패 — 프로필이 없으면 신인인지 기성인지 모름")
    fix = "scripts/melon_names.py 보강 명단에 점수 상위 팀을 먼저 넣는다 (멜론 상세 페이지 차단이면 스포티파이로)"
    rows = [r for r in snapshot if int(r.get("rank") or 10 ** 6) <= top]
    if not rows:
        return Check("top_profile", name, rule, "점수 스냅샷 없음", "skip", fix)
    missing = [r["team_key"] for r in rows
               if (teams.get(r["team_key"]) or {}).get("profile_status", "unknown") in ("", "unknown")]
    value = f"{len(missing)}/{len(rows)}팀 ({_pct(len(missing), len(rows))})"
    if missing:
        value += " — 상위부터: " + _examples(missing, 5)
    return Check("top_profile", name, rule, value,
                 _level(len(missing) / len(rows), TOP_NO_PROFILE_WARN, TOP_NO_PROFILE_FAIL), fix)


def check_snapshot(dates: List[str], snapshot: List[dict], today: str, team_keys: Set[str], excluded: Set[str]) -> Check:
    name = "점수 스냅샷"
    rule = "오늘 스냅샷이 있어야 하고, 제외 목록 팀이나 팀 표에 없는 팀이 들어 있으면 경고"
    fix = "export_lab_data.py → lab_snapshot.py 순서로 다시 돌린다 (스냅샷이 옛 팀 표로 계산된 것)"
    if not dates:
        return Check("snapshot", name, rule, "스냅샷 없음", "skip", fix)
    problems = []
    if dates[0] != today:
        problems.append(f"최신 {dates[0]} (오늘 것 없음)")
    excl = [r["team_key"] for r in snapshot if r.get("team_key") in excluded]
    ghost = [r["team_key"] for r in snapshot if r.get("team_key") not in team_keys and r.get("team_key") not in excluded]
    if excl:
        problems.append("제외 목록 팀 " + _examples(excl))
    if ghost:
        problems.append("팀 표에 없는 팀 " + _examples(ghost))
    value = f"{dates[0]} · {len(snapshot)}팀" + (" — " + " · ".join(problems) if problems else "")
    return Check("snapshot", name, rule, value, "warn" if problems else "pass", fix)


# ---------- PostgreSQL (읽기만) ----------

def _rows(text: str) -> List[dict]:
    return list(csv.DictReader(io.StringIO(text)))


def _pg_sync_sql(run: Run) -> str:
    from build_dashboard_data import _has_xref_table
    from export_lab_data import queries
    return f"-- dc:sync\nSELECT count(*) AS n FROM ({queries(_has_xref_table(run))['signals']}\n) q"


PG_SQL = {
    "pg_unknown_programs": """-- dc:unknown_programs
        SELECT program, count(*) AS n FROM raw.raw_outcome o
        WHERE NOT EXISTS (SELECT 1 FROM ref.outcome_tier t WHERE t.program = o.program)
        GROUP BY 1 ORDER BY 1""",
    "pg_no_artist": """-- dc:no_artist
        SELECT count(*) AS total,
               count(*) FILTER (WHERE artist_key IS NULL OR artist_key = '') AS no_artist,
               count(*) FILTER (WHERE signal_date IS NULL) AS no_date
        FROM core.v_signal""",
    "pg_career": """-- dc:career
        SELECT program FROM ref.outcome_tier WHERE career_filtered ORDER BY 1""",
}


def _pg_sync(text: str, lab_signals: int) -> Check:
    n = int(_rows(text)[0]["n"])
    off = abs(n - lab_signals) / max(n, 1)
    return Check("pg_sync", "DB 신호 수 = 랩 신호 수", f"차이가 {int(PG_SYNC_TOLERANCE * 100)}% 넘으면 경고",
                 f"DB {n:,}행 · 랩 {lab_signals:,}행", "warn" if off > PG_SYNC_TOLERANCE else "pass",
                 "적재(load_pg.py) 뒤 export_lab_data.py가 안 돌았거나 실패한 것 — 다시 돌린다")


def _pg_unknown(text: str) -> Check:
    rows = _rows(text)
    value = f"{len(rows)}개" + (": " + ", ".join(f"{r['program']} {r['n']}행" for r in rows) if rows else "")
    return Check("pg_unknown_programs", "등록 안 된 정답 프로그램", "ref.outcome_tier에 없는 정답 프로그램이 있으면 실패 (조용히 빠짐)",
                 value, "fail" if rows else "pass", "csv_schema.OUTCOME_TIER에 등급(mid·final)을 추가하고 다시 적재")


def _pg_no_artist(text: str) -> Check:
    r = _rows(text)[0]
    total, miss, nodate = int(r["total"]), int(r["no_artist"]), int(r["no_date"])
    ratio = (miss + nodate) / max(total, 1)
    return Check("pg_no_artist", "팀 이름·날짜 없는 신호", f"합쳐서 {int(PG_MISSING_WARN * 100)}% 넘으면 경고 (랩에서 빠짐)",
                 f"팀 없음 {miss}건 · 날짜 없음 {nodate}건 / {total:,}건 ({_pct(miss + nodate, total)})",
                 "warn" if ratio > PG_MISSING_WARN else "pass", "그 출처 수집기의 이름·날짜 읽기를 확인")


def _pg_career(text: str, filtered: Set[str]) -> Check:
    db = {r["program"] for r in _rows(text)}
    diff = sorted(db ^ filtered)
    return Check("pg_career", "5년 규칙 목록 DB = 코드", "ref.outcome_tier.career_filtered와 csv_schema.CAREER_FILTERED가 다르면 실패",
                 "같음 (" + ", ".join(sorted(db)) + ")" if not diff else "다름: " + ", ".join(diff),
                 "fail" if diff else "pass", "load_pg.py를 다시 돌려 ref 표를 코드 값으로 맞춘다")


def pg_checks(run: Run, lab_signals: int, career_filtered: Set[str]) -> List[Check]:
    try:
        first = _pg_sync(run(_pg_sync_sql(run)), lab_signals)
    except Exception as e:  # noqa: BLE001 — DB가 꺼져 있으면 파일 검사만 한다
        return [Check("pg", "PostgreSQL 검사", "DB에 읽기 연결", f"연결 못 함: {str(e)[:80]}", "skip",
                      "brew services start postgresql@17 확인")]
    makers = {"pg_unknown_programs": _pg_unknown, "pg_no_artist": _pg_no_artist,
              "pg_career": lambda t: _pg_career(t, career_filtered)}
    out = [first]
    for key, sql in PG_SQL.items():
        try:
            out.append(makers[key](run(sql)))
        except Exception as e:  # noqa: BLE001
            out.append(Check(key, key, "DB 읽기", f"읽지 못함: {str(e)[:80]}", "skip", "쿼리·뷰 이름 확인"))
    return out


# ---------- 모으기·쓰기 ----------

def _read_csv(path: Path) -> List[dict]:
    try:
        with open(path, encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except OSError:
        return []


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def run_all(root: Path, today: str, run: Optional[Run]) -> List[Check]:
    lab = root / "docs" / "lab" / "data"
    meta = _read_json(lab / "meta.json")
    roles = _read_json(root / "config" / "source_roles.json")
    excluded = set(((roles.get("candidate_rules") or {}).get("excluded_teams") or {}))
    tables = {n: _read_csv(lab / f"{n}.csv") for n in
              ("signals", "teams", "outcomes", "programs", "links", "videos", "images", "collabs")}
    teams = {t["team_key"]: t for t in tables["teams"]}
    keys = set(teams)
    dates = _read_json(lab / "snapshots" / "index.json").get("dates") or []
    snapshot = _read_csv(lab / "snapshots" / f"{dates[0]}.csv") if dates else []
    data_day = str(meta.get("data_end") or today)
    checks = [
        check_meta_fresh(meta, today),
        check_meta_rows(meta, {k: len(v) for k, v in tables.items()}),
        check_row_change(meta),
        check_collect_freshness(_read_json(root / "docs" / "data" / "collect.json").get("runs") or [], today),
        check_signal_recency(tables["signals"], data_day),
        check_future_signals(tables["signals"], data_day),
        check_orphan_signals(tables["signals"], keys, excluded),
        check_orphan_side({n: tables[n] for n in ("links", "images", "videos", "collabs")}, keys, excluded),
        check_duplicate_names(keys),
        check_counted(tables["outcomes"], teams, set(CAREER_FILTERED), CAREER_FILTER_YEARS),
        check_b_grade_rule(roles, set(CAREER_FILTERED)),
        check_same_house(tables["outcomes"], roles),
        check_genre(tables["teams"]),
        check_first_release(tables["teams"]),
        check_url_shapes(tables["links"], tables["images"]),
        check_top_profile(snapshot, teams),
        check_snapshot(dates, snapshot, data_day, keys, excluded),
    ]
    if run is None:
        checks.append(Check("pg", "PostgreSQL 검사", "DB에 읽기 연결", "--no-pg로 건너뜀", "skip", "-"))
    else:
        checks += pg_checks(run, len(tables["signals"]), set(CAREER_FILTERED))
    return checks


def summary_line(checks: List[Check]) -> str:
    n = Counter(c.status for c in checks)
    return f"통과 {n['pass']} · 경고 {n['warn']} · 실패 {n['fail']}"


def _cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def render(checks: List[Check], today: str, meta: dict) -> str:
    gen = str(meta.get("generated_at") or "")[:16].replace("T", " ") or "?"
    skipped = sum(1 for c in checks if c.status == "skip")
    lines = ["# 데이터 검사 (매일 자동)", "",
             f"_자동 생성: `.venv/bin/python scripts/data_checks.py` · 검사일 {today} · "
             f"랩 데이터 {gen} 기준 (데이터 끝 {meta.get('data_end', '?')})_", "",
             f"**결과: {summary_line(checks)}**" + (f" (건너뜀 {skipped})" if skipped else ""), ""]
    problems = sorted((c for c in checks if c.status in ("fail", "warn")), key=lambda c: STATUS_ORDER[c.status])
    if problems:
        lines += ["## 먼저 볼 것", ""]
        lines += [f"- {STATUS_ICON[c.status]} **{c.name}** — {c.value}  \n  → 고치는 법: {c.fix}" for c in problems]
        lines.append("")
    else:
        lines += ["모든 검사 통과 — 오늘 데이터에서 규칙 위반을 찾지 못했어요.", ""]
    lines += ["## 전체 검사", "", "| 상태 | 검사 | 기준 | 오늘 값 | 고치는 법 |", "|---|---|---|---|---|"]
    lines += [f"| {STATUS_ICON[c.status]} {STATUS_KO[c.status]} | {_cell(c.name)} | {_cell(c.rule)} | {_cell(c.value)} | {_cell(c.fix)} |"
              for c in checks]
    lines += ["", "기준값은 `scripts/data_checks.py` 맨 위 상수에 있어요. 주소는 모양만 보고 실제로 열어 보지는 않아요.", ""]
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="매일 데이터 검사 → docs/data_checks.md")
    ap.add_argument("--no-pg", action="store_true", help="PostgreSQL 검사 건너뛰기")
    ap.add_argument("--today", default=None, help="검사 기준일 (기본: 오늘)")
    ap.add_argument("--out", type=Path, default=OUT_MD)
    ap.add_argument("--json", type=Path, default=OUT_JSON)
    args = ap.parse_args(argv)
    today = args.today or date.today().isoformat()
    run = None
    if not args.no_pg:
        from build_dashboard_data import psql_csv
        run = psql_csv
    checks = run_all(ROOT, today, run)
    meta = _read_json(ROOT / "docs" / "lab" / "data" / "meta.json")
    args.out.write_text(render(checks, today, meta), encoding="utf-8")
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps({"today": today, "generated": datetime.now().astimezone().isoformat(timespec="minutes"),
                                     "summary": summary_line(checks),
                                     "checks": [asdict(c) for c in checks]}, ensure_ascii=False, indent=1),
                         encoding="utf-8")
    shown = args.out.relative_to(ROOT) if args.out.resolve().is_relative_to(ROOT) else args.out.name
    print(f"데이터 검사: {summary_line(checks)} → {shown}")
    return 1 if any(c.status == "fail" for c in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
