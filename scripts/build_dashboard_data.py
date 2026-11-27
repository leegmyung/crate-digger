"""PostgreSQL → 데이터 대시보드용 공개 JSON (docs/data/dashboard.json)

    python3 scripts/load_pg.py                 # 먼저 적재 (뷰도 다시 만듦)
    python3 scripts/build_dashboard_data.py

공개 페이지(GitHub Pages)에 실리므로 집계 숫자와 팀 이름·장르·프로그램·날짜·공개 출처 링크만 내보낸다.
"""
import csv
import io
import json
import math
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import csv_schema  # noqa: E402
import genre as genre_mod  # noqa: E402
from normalize import artist_key as _normalize_artist_key  # noqa: E402

OUT = ROOT / "docs" / "data" / "dashboard.json"
A09_SQL_PATH = ROOT / "sql" / "kr" / "analysis" / "a09_score_v0_backtest.sql"
SQL_README_PATH = ROOT / "docs" / "sql" / "README.md"
PSQL = os.environ.get("PSQL", "/opt/homebrew/opt/postgresql@17/bin/psql")
DB = os.environ.get("PGDATABASE", "crate_digger")
KST = timezone(timedelta(hours=9))
WINDOW = "2025-01-01"          # 이 날 이후 정답을 '맞힐 대상'으로
LOOKBACK_START = "2020-01-01"  # 신호는 그 전 5년

# 같은 팀 잇기: artist_key 또는 괄호 별칭(alias_key)
SAME = "(a.artist_key = b.artist_key OR a.artist_key = b.alias_key OR a.alias_key = b.artist_key)"

STAGE_RANK = csv_schema.STAGE_RANK
STAGE_KR = {
    4: "최종·수상",
    3: "본선·선정",
    2: "무대·쇼케이스",
    1: "서류·예선",
}

# 프로그램 코드 → 한국어 표시 이름 (차트에 영어 코드가 그대로 보이지 않도록)
PROGRAM_NAMES = {
    "superrookie": "슈퍼루키챌린지",
    "band_discovery": "상상마당 밴드 디스커버리",
    "yoojaeha_finalist": "유재하 음악경연대회 본선",
    "muse_sejong": "세종 뮤즈세종",
    "gb_creation": "경북 음악창작소 음반지원",
    "dmz_lineup": "DMZ 피스트레인 출연",
    "burock_rookies": "부산록페 루키즈",
    "indiestance": "인디스땅스 결선",
    "mucon": "뮤콘(MU:CON)",
    "museon_final": "뮤즈온 최종",
    "penta_superrookie": "펜타포트 슈퍼루키",
    "burock_main": "부산록페 본무대",
    "hello_rookie": "헬로루키 월간",
    "hello_rookie_year": "올해의 헬로루키",
    "kma_rookie": "한대음 올해의 신인",
    "kma_genre": "한대음 장르 부문",
    "khha_rookie": "한국힙합어워즈 신인",
    "cj_tuneup": "CJ 튠업",
    "izm_rookie": "이즘 올해의 신인",
    "musicy_rookie": "음악취향Y 올해의 신인",
    "(기준선) 아무 신호": "(기준선) 아무 신호 전체",
}

# 수집 소스 코드 → 한국어 표시 이름
SOURCE_NAMES = {
    "indistreet": "인디스트릿",
    "indiego": "인디고",
    "sangsangmadang": "상상마당",
    "poclanos": "포크라노스",
    "melon": "멜론",
    "bugs": "벅스",
    "genie": "지니",
    "flo": "FLO",
    "visla": "VISLA",
    "musicy": "음악취향Y",
    "rhythmer": "리드머",
    "weiv": "weiv",
    "izm": "IZM",
    "overtone": "오버톤",
    "instagram": "인스타그램",
    "yjh": "유재하음악경연대회",
    "dmz": "DMZ 피스트레인",
    "sejong": "세종 뮤즈세종",
    "gbsound": "경북 음악창작소",
    "busanrock": "부산록페 루키즈",
}

# 프로필 데이터가 아직 수집되지 않아 자동 유명 팀 제외 규칙에 걸리지 않는
# 메이저·베테랑·해외 투어 아티스트 수동 제외 목록 (canonical team_key 기준).
# 프로필이 채워지면 자동 규칙이 대신 처리한다.
MANUAL_FAMOUS_EXCLUDE = {
    "혁오": "수동 제외 (2014 데뷔 메이저 밴드 · 프로필 수집 전)",
    "실리카겔": "수동 제외 (한대음 다관왕 메이저 밴드 · 프로필 수집 전)",
    "colde": "수동 제외 (메이저 R&B 아티스트·WAVY 대표 · 프로필 수집 전)",
    "사이먼도미닉": "수동 제외 (메이저 힙합 아티스트 · 프로필 수집 전)",
    "팔로알토": "수동 제외 (2004 데뷔 베테랑 힙합 아티스트 · 프로필 수집 전)",
    "비프리": "수동 제외 (2009 데뷔 베테랑 힙합 아티스트 · 프로필 수집 전)",
    "김하온": "수동 제외 (메이저 힙합 아티스트 · 프로필 수집 전)",
    "비와이": "수동 제외 (메이저 힙합 아티스트 · 프로필 수집 전)",
    "키드밀리": "수동 제외 (메이저 힙합 아티스트 · 프로필 수집 전)",
    "제네더질라": "수동 제외 (기성 힙합 아티스트 · 프로필 수집 전)",
    "ek": "수동 제외 (2014 데뷔·MBA 크루 기성 힙합 아티스트 · 프로필 수집 전)",
    "수민": "수동 제외 (2015 데뷔·한대음 수상 기성 R&B 아티스트 · 프로필 수집 전)",
    "비비": "수동 제외 (메이저 가수·싱어송라이터 · 프로필 수집 전)",
    "저스트뮤직": "수동 제외 (기성 힙합 레이블 · 프로필 수집 전)",
    "아도이": "수동 제외 (2017 데뷔 기성 밴드 · 프로필 수집 전)",
    "안예은": "수동 제외 (기성 싱어송라이터 · 프로필 수집 전)",
    "스텔라장": "수동 제외 (기성 싱어송라이터 · 프로필 수집 전)",
    "interstellajang": "수동 제외 (스텔라장 인스타 계정 · 프로필 수집 전)",
    "술탄오브더디스코": "수동 제외 (2006 데뷔 베테랑 밴드 · 프로필 수집 전)",
    "sultanofthedisco": "수동 제외 (술탄 오브 더 디스코 영문 표기 · 프로필 수집 전)",
    "이디오테잎": "수동 제외 (2010 데뷔·한대음 수상 베테랑 밴드 · 프로필 수집 전)",
    "허클베리핀": "수동 제외 (1997 데뷔 1세대 인디 밴드 · 프로필 수집 전)",
    "노이즈가든": "수동 제외 (1990년대 베테랑 록 밴드 · 프로필 수집 전)",
    "심현보": "수동 제외 (1998 데뷔 베테랑 싱어송라이터 · 프로필 수집 전)",
    "전기뱀장어": "수동 제외 (2011 데뷔 기성 인디 밴드 · 프로필 수집 전)",
    "키라라": "수동 제외 (2014 데뷔·한대음 수상 베테랑 뮤지션 · 프로필 수집 전)",
    "다브다": "수동 제외 (2014 데뷔 10년+ 매스록 밴드 · 프로필 수집 전)",
    "abtb": "수동 제외 (2016 데뷔·한대음 록 음반 수상 기성 밴드 · 프로필 수집 전)",
    "구름": "수동 제외 (베테랑 프로듀서·뮤지션 · 프로필 수집 전)",
    "한올": "수동 제외 (2014 데뷔 10년+ 싱어송라이터 · 프로필 수집 전)",
    "불고기디스코": "수동 제외 (베테랑 멤버 구성 기성 밴드 · 프로필 수집 전)",
    "shininryu": "수동 제외 (신인류 인스타 계정 · 멜론 팬 1만+ 기제외 팀)",
    "아이브": "수동 제외 (메이저 K-pop 걸그룹)",
    "아일릿": "수동 제외 (메이저 K-pop 걸그룹)",
    "올데이프로젝트": "수동 제외 (메이저 아이돌 그룹)",
    "리센느": "수동 제외 (아이돌 걸그룹)",
    "thelemontwigs": "수동 제외 (해외 내한 아티스트)",
    "tramhaus": "수동 제외 (해외 내한 아티스트)",
    "fuyuniwakarete": "수동 제외 (해외 내한 아티스트)",
    "editors": "수동 제외 (해외 밴드)",
    "ecco2k": "수동 제외 (해외 아티스트)",
    "oyamadasohei": "수동 제외 (해외 내한 아티스트)",
    "sarahjulia": "수동 제외 (해외 아티스트)",
    "billionhappy": "수동 제외 (해외 아티스트)",
}

# 인스타 캡션에 자주 태그되는 기관·매체·공연장 계정 (아티스트 언급 목록에서 제외)
NON_ARTIST_PRESS_KEYS = {
    "koccaofficial", "koccamusic", "museon", "nugsmag", "pressworks",
    "liveclubday", "pubmag", "kindiemagazine", "senggistudio", "ageofband",
    "omichive7", "pushplaymag", "debasermagazine", "muzikstreet", "metrokr",
    "k팝", "중국언더그라운드", "홈즈aiai", "homs",
}


# ---------- 팀 키 통일 (artist_xref.py 있으면 사용, 없으면 정규화 키로 안전 동작) ----------

def load_xref_index(path=None):
    """data/raw/state/artist_xref.json 색인을 불러온다. 모듈·파일이 없어도 예외 없이 빈 dict."""
    try:
        import artist_xref  # noqa: E402
        return artist_xref.load_xref(path) if path is not None else artist_xref.load_xref()
    except Exception:
        return {}


def team_key(name, xref=None):
    """팀 이름(또는 기존 키) → 대표 팀 키.
    artist_xref.py + artist_xref.json이 있으면 다른 표기를 대표 키로 묶고,
    없으면 normalize.artist_key 규칙으로 안전하게 동작한다.
    """
    text = str(name or "").strip()
    if not text:
        return ""
    try:
        import artist_xref  # noqa: E402
        return artist_xref.canonical_key(text, xref)
    except Exception:
        k = _normalize_artist_key(text)
        by_key = (xref or {}).get("by_key") or {}
        return by_key.get(k, k)


def program_label(code):
    if not code:
        return ""
    return PROGRAM_NAMES.get(code, code)


def source_label(code):
    if not code:
        return ""
    return SOURCE_NAMES.get(code, code)


# ---------- 점수 v0 · 날짜 표시 · 첫 등장 신인 추정 ----------

def compute_score_v0(n_branch=0, best_stage=0, peer_selected=0, dmz=0, gigs_1y=0, outlets=0):
    """점수 v0 (sql/kr/analysis/a09_score_v0_backtest.sql 과 동일 공식).

    score = 2*(갈래 수-1) + 선정 최고 단계(STAGE_RANK, DMZ 제외)
            + 1*(선정 팀과 같은 날·같은 공연장) + 0.5*DMZ 출연
            + 0.5*ln(1+최근 1년 공연 수) + 1*min(큐레이션 매체 수, 3)
    """
    n_br = max(int(n_branch or 0), 0)
    if isinstance(best_stage, str):
        stg = int(STAGE_RANK.get(best_stage.strip().lower(), 0))
    else:
        stg = max(int(best_stage or 0), 0)
    peer = 1 if peer_selected else 0
    dmz_flag = 1 if dmz else 0
    g1y = max(int(gigs_1y or 0), 0)
    out_n = max(int(outlets or 0), 0)

    pts_branch = 2.0 * max(n_br - 1, 0)
    pts_stage = float(stg)
    pts_peer = float(peer)
    pts_dmz = 0.5 * dmz_flag
    pts_gigs = 0.5 * math.log(1 + g1y) if g1y > 0 else 0.0
    pts_outlets = float(min(out_n, 3))

    total = round(pts_branch + pts_stage + pts_peer + pts_dmz + pts_gigs + pts_outlets, 2)
    parts = []
    if pts_branch > 0:
        parts.append({"label": f"갈래 {n_br}개", "pts": round(pts_branch, 1)})
    if pts_stage > 0:
        parts.append({"label": f"선정({STAGE_KR.get(stg, str(stg) + '단계')})", "pts": round(pts_stage, 1)})
    if pts_peer > 0:
        parts.append({"label": "선정팀 합동무대", "pts": 1.0})
    if pts_dmz > 0:
        parts.append({"label": "DMZ 출연", "pts": 0.5})
    if pts_gigs > 0:
        parts.append({"label": f"최근 1년 공연 {g1y}회", "pts": round(pts_gigs, 2)})
    if pts_outlets > 0:
        parts.append({"label": f"큐레이션 {out_n}매체", "pts": round(pts_outlets, 1)})
    return total, parts


def _parse_iso_date(val):
    if not val:
        return None
    try:
        return date.fromisoformat(str(val)[:10])
    except ValueError:
        return None


def clamp_date_to_today(date_str, today=None):
    """오늘 이후 날짜(연도만 아는 선정의 12-31, 예정 공연 등)를 오늘로 자른다."""
    if not date_str:
        return ""
    today = today or datetime.now(KST).date()
    d = _parse_iso_date(date_str)
    if d is None:
        return str(date_str)
    return min(d, today).isoformat()


def format_signal_date(branch, signal_date, raw_date="", round_text="", today=None):
    """타임라인 표시용 날짜 라벨과 정렬 키를 만든다.

    선정 명단의 연도만 아는 날짜(raw_date='2026' → signal_date='2026-12-31')가
    미래 날짜처럼 보이지 않도록 '2026 선정' 형태로 표시한다.
    """
    today = today or datetime.now(KST).date()
    today_iso = today.isoformat()
    sig_str = str(signal_date or "")[:10]
    raw_str = str(raw_date or "").strip()
    rnd = str(round_text or "").strip()

    if branch == "선정·지원":
        if len(raw_str) == 4 and raw_str.isdigit():
            label = f"{raw_str} 선정" if (not rnd or rnd == raw_str) else f"{raw_str} ({rnd})"
            return label, min(sig_str or today_iso, today_iso)
        if len(raw_str) == 7 and re.match(r"^\d{4}-\d{2}$", raw_str):
            return f"{raw_str} 선정", min(sig_str or today_iso, today_iso)
        if sig_str.endswith("-12-31") and sig_str > today_iso:
            yr = sig_str[:4]
            return f"{yr} 선정", today_iso
        return sig_str or raw_str, min(sig_str or today_iso, today_iso)

    if branch == "공연" and sig_str > today_iso:
        return f"{sig_str} (예정)", sig_str

    return sig_str, min(sig_str or today_iso, today_iso) if sig_str > today_iso else sig_str


def rookie_status_info(profile_status, first_seen_all, today=None):
    """'우리 데이터 첫 등장' 기반 신인 추정 정보 (a09 백테스트의 3년 신인 대용 기준과 동일)."""
    today = today or datetime.now(KST).date()
    d = _parse_iso_date(first_seen_all)
    years = None
    first_seen_text = "정보 수집 중"
    if d is not None:
        days = max((today - d).days, 0)
        years = round(days / 365.25, 1)
        if days < 30:
            first_seen_text = "최근 1개월 내 첫 등장"
        elif years < 1.0:
            months = max(1, round(days / 30.4))
            first_seen_text = f"{months}개월 전 첫 등장"
        else:
            first_seen_text = f"{years:.1f}년 전 첫 등장"

    if profile_status == "신인":
        rookie_label, rookie_code, is_pool = "신인 확인", "confirmed", True
    elif profile_status == "기성":
        rookie_label, rookie_code, is_pool = "기성", "established", False
    elif years is not None and years <= 3.0:
        rookie_label, rookie_code, is_pool = "신인 추정", "inferred", True
    elif years is not None:
        rookie_label, rookie_code, is_pool = "3년+ 활동", "older", False
    else:
        rookie_label, rookie_code, is_pool = "확인 안 됨", "unknown", True

    return {
        "years_in_data": years,
        "first_seen_text": first_seen_text,
        "rookie_label": rookie_label,
        "rookie_code": rookie_code,
        "is_rookie_pool": is_pool,
    }


# 장르 보완 규칙: 멜론·발매 장르가 없을 때만, '신호' 정보로만 붙인다 (2026-11-27).
# 정답(검증용) 프로그램(예: khha_rookie 한국힙합어워즈 신인)으로 장르를 붙이면 장르 분석에 정답이 새어 들어간다
# (docs/genre_bias.md). 그래서 출처 = 큐레이션 발굴·맥락 출처, 프로그램 = 선정·지원 신호 프로그램만 둔다.
# 순서 = 보완 장르가 둘 이상일 때의 우선순위.
GENRE_HINT_PRESS = {"rhythmer": "hiphop"}            # 리드머(맥락 출처) 소개 → 힙합
GENRE_HINT_PROGRAMS = {"band_discovery": "rock"}     # 상상마당 밴드 디스커버리(선정·지원 신호) → 록·밴드


def _split_lower(field) -> list:
    return [s.strip().lower() for s in str(field or "").split("|") if s.strip()]


def _infer_genres(raw_genres, press_sources="", sel_programs=""):
    """멜론·발매 장르를 우선 쓰고, 비었을 때만 오탐 없는 확실한 신호 출처(리드머→힙합, 밴드디스커버리→록·밴드)로 보완.
    정답 프로그램(csv_schema.OUTCOME_TIER)은 보완 근거로 쓰지 않는다."""
    cfg = genre_mod.load_config()["buckets"]
    labels = []
    if raw_genres:
        for b in genre_mod.buckets_of(str(raw_genres)):
            if b in cfg and cfg[b]["label"] not in labels:
                labels.append(cfg[b]["label"])
    if labels:
        return labels
    hints = [GENRE_HINT_PRESS.get(s) for s in _split_lower(press_sources)]
    hints += [GENRE_HINT_PROGRAMS.get(p) for p in _split_lower(sel_programs) if p not in csv_schema.OUTCOME_TIER]
    for b in [*GENRE_HINT_PRESS.values(), *GENRE_HINT_PROGRAMS.values()]:   # 정해진 우선순위대로
        if b in hints and b in cfg and cfg[b]["label"] not in labels:
            labels.append(cfg[b]["label"])
    return labels


# ---------- SQL 빌더 (ref.artist_xref 있으면 사용, 없으면 alias_map 폴백) ----------

def _team_key_cte(use_xref_sql):
    if use_xref_sql:
        return "key_map AS (SELECT variant_key, artist_key AS main_key FROM ref.artist_xref)"
    return """key_map AS (
        SELECT alias_key AS variant_key, MIN(artist_key) AS main_key
        FROM core.v_signal
        WHERE alias_key IS NOT NULL AND alias_key <> '' AND alias_key <> artist_key
        GROUP BY alias_key
    )"""


def make_queries(use_xref_sql=False):
    km = _team_key_cte(use_xref_sql)
    return {
        # 1. 수집 현황: 갈래·소스별 행 수와 팀 수
        "collection": """
            SELECT branch, source, count(*) AS rows, count(DISTINCT artist_key) AS teams,
                   min(signal_date) AS first_date, max(signal_date) AS last_date
            FROM core.v_signal GROUP BY branch, source ORDER BY branch, rows DESC""",
        # 2. 월별 공연 기록 양
        "gigs_by_month": """
            SELECT to_char(date_trunc('month', signal_date), 'YYYY-MM') AS month, count(*) AS gigs,
                   count(DISTINCT artist_key) AS teams
            FROM core.v_signal
            WHERE branch = '공연' AND signal_date >= DATE '2024-01-01' AND signal_date <= current_date
            GROUP BY 1 ORDER BY 1""",
        # 3. 지금 주목할 후보 + 점수 v0 요소 + 우리 데이터 첫 등장 (상상마당 2010~ 포함)
        "candidates": f"""
            WITH {km},
            sig3y AS (
                SELECT COALESCE(km.main_key, s.artist_key) AS team_key,
                       s.artist_text, s.branch, s.source, s.program, s.stage_rank,
                       LEAST(s.signal_date, current_date) AS eff_date,
                       s.signal_date, s.detail
                FROM core.v_signal s
                LEFT JOIN key_map km ON km.variant_key = s.artist_key
                WHERE s.signal_date BETWEEN current_date - INTERVAL '3 years' AND current_date + 60
                  AND s.artist_key IS NOT NULL AND s.artist_key <> ''
            ),
            recent AS (
                SELECT team_key, MIN(artist_text) AS artist,
                       COUNT(DISTINCT branch) AS n_branch,
                       COUNT(*) AS n_signals,
                       string_agg(DISTINCT branch, ' · ' ORDER BY branch) AS branches,
                       MIN(eff_date) AS first_seen,
                       MAX(eff_date) AS last_seen
                FROM sig3y
                WHERE signal_date >= current_date - 180
                GROUP BY team_key HAVING COUNT(DISTINCT branch) >= 2
            ),
            first_all AS (
                SELECT COALESCE(km.main_key, s.artist_key) AS team_key,
                       MIN(LEAST(s.signal_date, current_date)) AS first_seen_all
                FROM core.v_signal s
                LEFT JOIN key_map km ON km.variant_key = s.artist_key
                WHERE s.artist_key IS NOT NULL AND s.artist_key <> ''
                GROUP BY 1
            ),
            selected_team AS (
                SELECT team_key, MIN(eff_date) AS selected_on
                FROM sig3y WHERE branch = '선정·지원' AND stage_rank >= 3
                GROUP BY 1
            ),
            gig AS (
                SELECT DISTINCT team_key, signal_date AS gig_date, detail AS venue
                FROM sig3y WHERE branch = '공연' AND COALESCE(detail, '') NOT IN ('', '공연장 미정')
            ),
            peer AS (
                SELECT DISTINCT a.team_key
                FROM gig a
                JOIN gig b ON b.gig_date = a.gig_date AND b.venue = a.venue AND b.team_key <> a.team_key
                JOIN selected_team st ON st.team_key = b.team_key AND st.selected_on <= a.gig_date
            ),
            prof_agg AS (
                SELECT COALESCE(km.main_key, st.artist_key) AS team_key,
                       CASE WHEN bool_or(st.status = 'famous') THEN 'famous'
                            WHEN bool_or(st.status = 'newcomer') THEN 'newcomer'
                            WHEN bool_or(st.status = 'established') THEN 'established'
                            ELSE 'unknown' END AS status,
                       MIN(st.first_release) AS first_release,
                       MAX(st.fan_count) AS fan_count
                FROM core.v_artist_status st
                LEFT JOIN key_map km ON km.variant_key = st.artist_key
                GROUP BY 1
            ),
            out_agg AS (
                SELECT COALESCE(km.main_key, o.artist_key) AS team_key, MIN(o.program) AS already_outcome
                FROM core.v_outcome o
                LEFT JOIN key_map km ON km.variant_key = o.artist_key
                WHERE o.counted
                GROUP BY 1
            ),
            genres_prof AS (
                SELECT COALESCE(km.main_key, p.artist_key) AS team_key,
                       string_agg(DISTINCT p.genre, '|') AS g
                FROM raw.raw_artist_profile p
                LEFT JOIN key_map km ON km.variant_key = p.artist_key
                WHERE COALESCE(p.genre, '') <> ''
                GROUP BY 1
            ),
            genres_rel AS (
                SELECT COALESCE(km.main_key, r.artist_key) AS team_key,
                       string_agg(DISTINCT r.genre, '|') AS g
                FROM raw.raw_kr_release r
                LEFT JOIN key_map km ON km.variant_key = r.artist_key
                WHERE COALESCE(r.genre, '') <> ''
                GROUP BY 1
            ),
            feat AS (
                SELECT r.team_key AS artist_key, r.artist, r.n_branch, r.n_signals, r.branches,
                       r.first_seen, r.last_seen, fa.first_seen_all,
                       CASE COALESCE(pa.status, 'unknown') WHEN 'newcomer' THEN '신인'
                            WHEN 'established' THEN '기성' ELSE '확인 안 됨' END AS status,
                       pa.first_release, pa.fan_count, oa.already_outcome,
                       concat_ws('|', gp.g, gr.g) AS raw_genres,
                       string_agg(DISTINCT CASE WHEN s.branch = '큐레이션' THEN s.source END, '|') AS press_sources,
                       string_agg(DISTINCT CASE WHEN s.branch = '선정·지원' THEN s.program END, '|') AS sel_programs,
                       COALESCE(MAX(CASE WHEN s.program <> 'dmz_lineup' THEN s.stage_rank END), 0) AS best_stage,
                       MAX(CASE WHEN s.program = 'dmz_lineup' THEN 1 ELSE 0 END) AS dmz,
                       COUNT(DISTINCT CASE WHEN s.branch = '공연'
                                            AND s.signal_date BETWEEN current_date - 365 AND current_date
                                           THEN s.signal_date END) AS gigs_1y,
                       COUNT(DISTINCT CASE WHEN s.branch = '큐레이션' THEN s.program END) AS outlets,
                       CASE WHEN pe.team_key IS NOT NULL THEN 1 ELSE 0 END AS peer_selected
                FROM recent r
                JOIN sig3y s ON s.team_key = r.team_key
                JOIN first_all fa ON fa.team_key = r.team_key
                LEFT JOIN peer pe ON pe.team_key = r.team_key
                LEFT JOIN prof_agg pa ON pa.team_key = r.team_key
                LEFT JOIN out_agg oa ON oa.team_key = r.team_key
                LEFT JOIN genres_prof gp ON gp.team_key = r.team_key
                LEFT JOIN genres_rel gr ON gr.team_key = r.team_key
                WHERE COALESCE(pa.status, 'unknown') <> 'famous'
                GROUP BY r.team_key, r.artist, r.n_branch, r.n_signals, r.branches, r.first_seen,
                         r.last_seen, fa.first_seen_all, pa.status, pa.first_release, pa.fan_count,
                         oa.already_outcome, gp.g, gr.g, pe.team_key
            )
            SELECT f.*,
                   ROUND((2 * (f.n_branch - 1) + f.best_stage + f.peer_selected + 0.5 * f.dmz
                          + 0.5 * LN(1 + f.gigs_1y) + LEAST(f.outlets, 3))::numeric, 2) AS score_v0
            FROM feat f
            ORDER BY (f.already_outcome IS NULL) DESC, score_v0 DESC, f.n_signals DESC, f.last_seen DESC
            LIMIT 160""",
        # 3-0. 후보별 신호 타임라인 (클릭 시 펼침용: 최근 1년+, 선정은 원문 발표일/회차 포함)
        "candidate_signals": f"""
            WITH {km},
            cand AS (
                SELECT COALESCE(km.main_key, s.artist_key) AS team_key
                FROM core.v_signal s
                LEFT JOIN key_map km ON km.variant_key = s.artist_key
                WHERE s.signal_date BETWEEN current_date - 180 AND current_date + 60
                  AND s.artist_key IS NOT NULL AND s.artist_key <> ''
                GROUP BY 1 HAVING COUNT(DISTINCT s.branch) >= 2
            ),
            ev AS (
                SELECT COALESCE(km.main_key, s.artist_key) AS artist_key,
                       s.announced_end AS signal_date, s.announced_at AS raw_date, s.round,
                       '선정·지원'::text AS branch, s.source, s.program AS title,
                       concat_ws(' · ', s.round, s.stage) AS detail, s.url
                FROM raw.raw_kr_selection s
                LEFT JOIN key_map km ON km.variant_key = s.artist_key
                JOIN cand c ON c.team_key = COALESCE(km.main_key, s.artist_key)
                UNION ALL
                SELECT COALESCE(km.main_key, g.artist_key),
                       g.gig_date, g.gig_date::text, '',
                       '공연', g.source,
                       coalesce(nullif(g.title, ''), split_part(g.venue_text, ' (', 1)),
                       split_part(g.venue_text, ' (', 1), g.gig_url
                FROM raw.raw_kr_gig g
                LEFT JOIN key_map km ON km.variant_key = g.artist_key
                JOIN cand c ON c.team_key = COALESCE(km.main_key, g.artist_key)
                WHERE g.gig_date >= current_date - 365
                UNION ALL
                SELECT COALESCE(km.main_key, r.artist_key),
                       r.released_end, r.released_at, '',
                       '발매', r.source, r.title, r.release_type, r.release_url
                FROM raw.raw_kr_release r
                LEFT JOIN key_map km ON km.variant_key = r.artist_key
                JOIN cand c ON c.team_key = COALESCE(km.main_key, r.artist_key)
                UNION ALL
                SELECT COALESCE(km.main_key, p.artist_key),
                       left(p.published_at, 10)::date, left(p.published_at, 10), '',
                       CASE WHEN p.pick_label = 'venue_lineup' THEN '공연' ELSE '큐레이션' END,
                       p.source, left(p.title, 100), p.outlet, p.url
                FROM raw.raw_press p
                LEFT JOIN key_map km ON km.variant_key = p.artist_key
                JOIN cand c ON c.team_key = COALESCE(km.main_key, p.artist_key)
                WHERE coalesce(p.is_sponsored, 0) = 0 AND left(p.published_at, 10)::date >= current_date - 365
            )
            SELECT DISTINCT ON (artist_key, signal_date, branch, source, coalesce(detail, ''), coalesce(title, ''))
                   artist_key, signal_date, raw_date, round, branch, source, title, detail, url
            FROM ev
            WHERE signal_date IS NOT NULL
            ORDER BY artist_key, signal_date DESC, branch, source, coalesce(detail, ''), coalesce(title, '')""",
        # 3-1. 유명해서 뺀 팀 (투명하게 보여주기)
        "excluded_famous": """
            SELECT DISTINCT ON (st.artist_key) s.artist_text AS artist, st.fan_count, st.years_since_first,
                   CASE WHEN st.fan_count >= (SELECT value FROM ref.settings WHERE name = 'fame_fans') THEN '팬 수 (1만+)'
                        ELSE '활동 연차 (5년+ & 팬 1천+)' END AS reason
            FROM core.v_artist_status st JOIN core.v_signal s ON s.artist_key = st.artist_key
            WHERE st.status = 'famous' AND s.signal_date >= current_date - 180
            ORDER BY st.artist_key, s.signal_date DESC""",
        # 3-2. 최근 매거진·큐레이터·공연장 언급 요약 (raw_press)
        "press_summary": """
            SELECT source,
                   CASE WHEN source <> 'instagram' THEN '웹매거진'
                        WHEN pick_label = 'venue_lineup' THEN '공연장 라인업'
                        ELSE '인스타 큐레이터' END AS kind,
                   count(*) AS total,
                   count(*) FILTER (WHERE left(published_at, 10)::date >= current_date - 30) AS last_30d,
                   count(DISTINCT artist_key) AS teams,
                   max(left(published_at, 10)) AS latest_date
            FROM raw.raw_press
            WHERE coalesce(is_sponsored, 0) = 0
            GROUP BY 1, 2
            ORDER BY last_30d DESC, total DESC""",
        # 3-3. 최근 매거진·큐레이터가 언급한 팀 목록 (웹매거진·인스타·공연장 균형 추출)
        "recent_press": f"""
            WITH {km},
            base AS (
                SELECT COALESCE(km.main_key, p.artist_key) AS artist_key,
                       p.artist_text AS artist, p.source, p.outlet,
                       CASE WHEN p.source <> 'instagram' THEN '웹매거진'
                            WHEN p.pick_label = 'venue_lineup' THEN '공연장 라인업'
                            ELSE '인스타 큐레이터' END AS kind,
                       left(p.published_at, 10) AS published_at, p.pick_label,
                       left(p.title, 120) AS title, p.url,
                       CASE coalesce(st.status, 'unknown') WHEN 'newcomer' THEN '신인' WHEN 'established' THEN '기성'
                            ELSE '확인 안 됨' END AS status,
                       row_number() OVER (
                           PARTITION BY CASE WHEN p.source <> 'instagram' THEN 'web'
                                             WHEN p.pick_label = 'venue_lineup' THEN 'venue' ELSE 'ig' END
                           ORDER BY left(p.published_at, 10) DESC, (st.status = 'newcomer') DESC NULLS LAST, p.source
                       ) AS rn
                FROM raw.raw_press p
                LEFT JOIN key_map km ON km.variant_key = p.artist_key
                LEFT JOIN core.v_artist_status st ON st.artist_key = p.artist_key
                WHERE coalesce(p.is_sponsored, 0) = 0
                  AND coalesce(st.status, 'unknown') <> 'famous'
                  AND p.artist_key IS NOT NULL
                  AND left(p.published_at, 10)::date >= current_date - 90
            )
            SELECT artist_key, artist, source, outlet, kind, published_at, pick_label, title, url, status
            FROM base
            WHERE (kind = '웹매거진' AND rn <= 60)
               OR (kind = '인스타 큐레이터' AND rn <= 50)
               OR (kind = '공연장 라인업' AND rn <= 20)
            ORDER BY published_at DESC, kind""",
        # 4. 신호 적중률: 직전 5년 안 선정 신호 팀 중 이후 정답(센 것)을 받은 비율 (+ 기준선)
        "signal_hit_rates": f"""
            WITH sig AS (
                SELECT DISTINCT CASE WHEN branch = '선정·지원' THEN program ELSE '(기준선) 아무 신호' END AS program,
                       artist_key, alias_key
                FROM core.v_signal
                WHERE signal_date >= DATE '{LOOKBACK_START}' AND signal_date < DATE '{WINDOW}' AND artist_key IS NOT NULL),
            hit AS (
                SELECT DISTINCT a.program, a.artist_key FROM sig a
                JOIN core.v_outcome_team b ON {SAME}
                WHERE b.first_outcome_date >= DATE '{WINDOW}'
                  AND NOT EXISTS (SELECT 1 FROM ref.same_program s
                                  WHERE s.selection_program = a.program AND s.outcome_program = b.first_program))
            SELECT s.program, count(DISTINCT s.artist_key) AS teams, count(DISTINCT h.artist_key) AS hits,
                   round(count(DISTINCT h.artist_key)::numeric / nullif(count(DISTINCT s.artist_key), 0), 3) AS rate
            FROM sig s LEFT JOIN hit h ON h.program = s.program AND h.artist_key = s.artist_key
            GROUP BY s.program ORDER BY rate DESC NULLS LAST""",
        # 5. 중간 정답 → 최종 정답
        "mid_to_final": f"""
            WITH mid AS (SELECT DISTINCT program, artist_key, alias_key, announced_start FROM core.v_outcome
                         WHERE tier = 'mid' AND counted AND announced_start >= DATE '{WINDOW}'),
                 fin AS (SELECT program, artist_key, alias_key, announced_start FROM core.v_outcome
                         WHERE tier = 'final' AND announced_start >= DATE '{WINDOW}')
            SELECT a.program, count(DISTINCT a.artist_key) AS teams,
                   count(DISTINCT CASE WHEN b.artist_key IS NOT NULL THEN a.artist_key END) AS later_final,
                   round(count(DISTINCT CASE WHEN b.artist_key IS NOT NULL THEN a.artist_key END)::numeric
                         / nullif(count(DISTINCT a.artist_key), 0), 3) AS rate
            FROM mid a LEFT JOIN fin b ON {SAME} AND b.announced_start > a.announced_start
                 AND NOT EXISTS (SELECT 1 FROM ref.outcome_same_family f
                                 WHERE f.mid_program = a.program AND f.final_program = b.program)
            GROUP BY a.program ORDER BY rate DESC""",
        # 6. 정답 받을 때 첫 발매 후 연차 (팀별 첫 정답 기준, 표기 통일)
        "career_at_outcome": f"""
            WITH {km},
            t AS (SELECT DISTINCT ON (COALESCE(km.main_key, o.artist_key))
                         COALESCE(km.main_key, o.artist_key) AS team_key, o.years_at_outcome
                  FROM core.v_outcome o
                  LEFT JOIN key_map km ON km.variant_key = o.artist_key
                  WHERE o.counted AND o.years_at_outcome IS NOT NULL
                  ORDER BY 1, o.announced_start)
            SELECT CASE WHEN years_at_outcome <= 1 THEN '1년 차 이내' WHEN years_at_outcome <= 3 THEN '1~3년 차'
                        WHEN years_at_outcome <= 5 THEN '3~5년 차' ELSE '5년 초과' END AS bucket,
                   count(*) AS teams
            FROM t GROUP BY 1 ORDER BY min(years_at_outcome)""",
        # 6-0. 연차 요약 (중앙값 세로선용)
        "career_summary": f"""
            WITH {km},
            t AS (SELECT DISTINCT ON (COALESCE(km.main_key, o.artist_key))
                         COALESCE(km.main_key, o.artist_key) AS team_key, o.years_at_outcome
                  FROM core.v_outcome o
                  LEFT JOIN key_map km ON km.variant_key = o.artist_key
                  WHERE o.counted AND o.years_at_outcome IS NOT NULL
                  ORDER BY 1, o.announced_start)
            SELECT count(*) AS teams,
                   round((percentile_cont(0.5) WITHIN GROUP (ORDER BY years_at_outcome))::numeric, 1) AS median_years,
                   count(*) FILTER (WHERE years_at_outcome <= 3) AS within_3y
            FROM t""",
        # 6-1. 리드타임 (표기 통일 기준)
        "lead_time": f"""
            WITH {km},
            out_canon AS (
                SELECT COALESCE(km.main_key, o.artist_key) AS team_key,
                       MIN(o.announced_start) AS first_outcome_date
                FROM core.v_outcome o
                LEFT JOIN key_map km ON km.variant_key = o.artist_key
                WHERE o.counted
                GROUP BY 1
            ),
            sig_canon AS (
                SELECT COALESCE(km.main_key, s.artist_key) AS team_key, s.signal_date
                FROM core.v_signal s
                LEFT JOIN key_map km ON km.variant_key = s.artist_key
                WHERE s.artist_key IS NOT NULL
            ),
            first_sig AS (
                SELECT b.team_key, b.first_outcome_date, MIN(a.signal_date) AS first_signal
                FROM sig_canon a JOIN out_canon b ON a.team_key = b.team_key
                WHERE a.signal_date < b.first_outcome_date
                GROUP BY b.team_key, b.first_outcome_date
            )
            SELECT CASE WHEN m < 6 THEN '0~6개월' WHEN m < 12 THEN '6~12개월' WHEN m < 24 THEN '12~24개월'
                        WHEN m < 36 THEN '24~36개월' ELSE '36개월 이상' END AS bucket,
                   count(*) AS teams, round(avg(m)::numeric, 1) AS avg_months,
                   min(m) AS sort_key
            FROM (SELECT team_key, (first_outcome_date - first_signal) / 30.4 AS m FROM first_sig) x
            GROUP BY 1 ORDER BY sort_key""",
        # 6-2. 리드타임 요약 (표기 통일 기준 정답 팀 수 + 원본 키 수도 함께 반환)
        "lead_time_summary": f"""
            WITH {km},
            out_canon AS (
                SELECT COALESCE(km.main_key, o.artist_key) AS team_key,
                       MIN(o.announced_start) AS first_outcome_date
                FROM core.v_outcome o
                LEFT JOIN key_map km ON km.variant_key = o.artist_key
                WHERE o.counted
                GROUP BY 1
            ),
            sig_canon AS (
                SELECT COALESCE(km.main_key, s.artist_key) AS team_key, s.signal_date
                FROM core.v_signal s
                LEFT JOIN key_map km ON km.variant_key = s.artist_key
                WHERE s.artist_key IS NOT NULL
            ),
            first_sig AS (
                SELECT b.team_key, MIN(a.signal_date) AS first_signal, MAX(b.first_outcome_date) AS first_outcome
                FROM out_canon b LEFT JOIN sig_canon a ON a.team_key = b.team_key AND a.signal_date < b.first_outcome_date
                GROUP BY b.team_key
            )
            SELECT count(*) AS outcome_teams,
                   (SELECT count(*) FROM core.v_outcome_team) AS raw_outcome_teams,
                   count(first_signal) AS with_prior_signal,
                   round((percentile_cont(0.5) WITHIN GROUP (ORDER BY (first_outcome - first_signal) / 30.4))::numeric, 1)
                       AS median_months,
                   count(*) FILTER (WHERE (first_outcome - first_signal) / 30.4 >= 12) AS over_12m
            FROM first_sig""",
        # 6-3. 월 × 갈래 수집량 (2024년 이후)
        "volume_by_month_branch": """
            SELECT to_char(date_trunc('month', signal_date), 'YYYY-MM') AS month, branch, count(*) AS rows
            FROM core.v_signal WHERE signal_date >= DATE '2024-01-01' AND signal_date <= current_date
            GROUP BY 1, 2 ORDER BY 1, 2""",
        # 6-4. KPI 비교용 최근 30일 vs 직전 30일 추세
        "kpi_trends": """
            SELECT
                count(*) FILTER (WHERE signal_date BETWEEN current_date - 30 AND current_date) AS signals_30d,
                count(*) FILTER (WHERE signal_date BETWEEN current_date - 60 AND current_date - 31) AS signals_prev_30d,
                count(DISTINCT artist_key) FILTER (WHERE signal_date BETWEEN current_date - 30 AND current_date) AS teams_30d,
                count(DISTINCT artist_key) FILTER (WHERE signal_date BETWEEN current_date - 60 AND current_date - 31) AS teams_prev_30d
            FROM core.v_signal""",
        # 7. 공연 많은 공연장 (2025년 이후) + 후보 팀 출연 수
        "top_venues": f"""
            WITH {km},
            cand AS (
                SELECT COALESCE(km.main_key, s.artist_key) AS team_key
                FROM core.v_signal s
                LEFT JOIN key_map km ON km.variant_key = s.artist_key
                WHERE s.signal_date BETWEEN current_date - 180 AND current_date + 60 AND s.artist_key IS NOT NULL
                GROUP BY 1 HAVING count(DISTINCT s.branch) >= 2
            )
            SELECT v.detail AS venue, count(*) AS gigs,
                   count(DISTINCT COALESCE(km.main_key, v.artist_key)) AS teams,
                   count(DISTINCT CASE WHEN c.team_key IS NOT NULL THEN COALESCE(km.main_key, v.artist_key) END) AS candidate_teams
            FROM core.v_signal v
            LEFT JOIN key_map km ON km.variant_key = v.artist_key
            LEFT JOIN cand c ON c.team_key = COALESCE(km.main_key, v.artist_key)
            WHERE v.branch = '공연' AND v.signal_date >= DATE '2025-01-01' AND coalesce(v.detail, '') <> ''
            GROUP BY v.detail ORDER BY gigs DESC LIMIT 15""",
        # 8. 데이터 품질 요약
        "quality": f"""
            WITH {km}
            SELECT '같은 팀인데 표기가 여러 개인 이름 키' AS item,
                   (SELECT count(*) FROM (SELECT artist_key FROM core.v_signal WHERE artist_key IS NOT NULL
                    GROUP BY artist_key HAVING count(DISTINCT artist_text) > 1) x) AS value
            UNION ALL SELECT '유통사가 빈 발매 행',
                   (SELECT count(*) FROM raw.raw_kr_release WHERE distributor_text IS NULL)
            UNION ALL SELECT '연도만 아는 선정 발표일',
                   (SELECT count(*) FROM raw.raw_kr_selection WHERE length(announced_at) = 4)
            UNION ALL SELECT '멜론 프로필이 있는 팀',
                   (SELECT count(*) FROM core.v_artist_profile)
            UNION ALL SELECT '센 정답 팀 (표기 통일 후)',
                   (SELECT count(DISTINCT COALESCE(km.main_key, o.artist_key))
                    FROM core.v_outcome o LEFT JOIN key_map km ON km.variant_key = o.artist_key
                    WHERE o.counted)""",
    }


QUERIES = make_queries(use_xref_sql=False)


def _num(v):
    if v in ("", None):
        return None
    if isinstance(v, (int, float)):
        return v
    try:
        return int(v)
    except ValueError:
        try:
            return float(v)
        except ValueError:
            return v


def records(csv_text):
    rows = list(csv.DictReader(io.StringIO(csv_text or "")))
    return [{k: _num(v) for k, v in r.items()} for r in rows]


def _normalize_a09_rows(raw_rows):
    out = []
    for r in raw_rows or []:
        if "기준일" in r:
            out.append({
                "cutoff": str(r.get("기준일") or ""),
                "pool_n": _num(r.get("후보_팀수")),
                "pool_hits": _num(r.get("이후_정답_팀수")),
                "k": _num(r.get("상위_k")),
                "method": str(r.get("방법") or ""),
                "hits": _num(r.get("맞힌_팀수")),
                "hit_rate_pct": _num(r.get("적중률_pct")),
                "random_expected": _num(r.get("무작위_기대_팀수")),
                "lift": _num(r.get("무작위_대비_배수")),
            })
        elif "cutoff" in r:
            out.append(r)
    return out


def parse_a09_markdown(md_text):
    """docs/sql/README.md의 a09_score_v0_backtest 표를 파싱한다 (DB 없을 때 폴백)."""
    if not md_text:
        return []
    m = re.search(r"###\s+a09_score_v0_backtest(.*?)(?:\n##\s|\n###\s|\Z)", md_text, re.S)
    if not m:
        return []
    block = m.group(1)
    rows = []
    headers = None
    for line in block.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if headers is None:
            if "기준일" in cells and "방법" in cells:
                headers = cells
            continue
        if all(set(c) <= {"-", ":"} for c in cells):
            continue
        if len(cells) == len(headers):
            rows.append(dict(zip(headers, cells)))
    return _normalize_a09_rows(rows)


def load_score_v0_backtest(run=None):
    """a09_score_v0_backtest.sql 실행 → 실패/빈 결과면 docs/sql/README.md 표로 안전 폴백."""
    if run is not None and A09_SQL_PATH.exists():
        try:
            sql = A09_SQL_PATH.read_text(encoding="utf-8")
            rows = _normalize_a09_rows(records(run(sql)))
            if rows:
                return rows
        except Exception:
            pass
    if SQL_README_PATH.exists():
        try:
            return parse_a09_markdown(SQL_README_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def apply_manual_exclusions(candidates, excluded_famous, xref=None):
    """프로필 미수집으로 자동 제외에 안 걸린 메이저·기성·해외 팀을 수동 제외 목록으로 분리."""
    kept = []
    excluded = list(excluded_famous or [])
    seen_excl = {team_key(e.get("artist"), xref) for e in excluded if e.get("artist")}
    for row in candidates or []:
        raw_key = str(row.get("artist_key") or "").strip().lower()
        ck = team_key(row.get("artist_key") or row.get("artist") or "", xref)
        reason = MANUAL_FAMOUS_EXCLUDE.get(ck) or MANUAL_FAMOUS_EXCLUDE.get(raw_key)
        if reason:
            artist = row.get("artist") or ck or raw_key
            if ck not in seen_excl:
                excluded.append({
                    "artist": artist,
                    "fan_count": row.get("fan_count"),
                    "years_since_first": None,
                    "reason": reason,
                })
                seen_excl.add(ck)
            continue
        kept.append(row)
    return kept, excluded


def enrich_candidates(candidates, candidate_signals, xref=None, today=None):
    """후보 목록에 점수 v0·분해, 첫 등장 신인 추정, 안전 장르, 날짜 정제 타임라인을 붙이고 점수 v0 순 정렬."""
    today = today or datetime.now(KST).date()
    by_key = defaultdict(list)
    for ev in candidate_signals or []:
        raw_k = ev.get("artist_key")
        if not raw_k:
            continue
        ck = team_key(raw_k, xref) if xref else str(raw_k)
        branch = ev.get("branch") or ""
        title = ev.get("title") or ""
        if branch == "선정·지원":
            title = program_label(title)
        date_label, sort_date = format_signal_date(
            branch=branch,
            signal_date=ev.get("signal_date") or "",
            raw_date=ev.get("raw_date") or "",
            round_text=ev.get("round") or "",
            today=today,
        )
        by_key[ck].append({
            "date": ev.get("signal_date") or "",
            "date_label": date_label,
            "sort_date": sort_date,
            "branch": branch,
            "source": ev.get("source") or "",
            "source_label": source_label(ev.get("source")),
            "title": str(title),
            "detail": str(ev.get("detail") or ""),
            "url": ev.get("url") or "",
        })

    enriched = []
    for row in candidates or []:
        if "artist_key" not in row:
            enriched.append(row)
            continue
        c = dict(row)
        ck = team_key(c["artist_key"], xref) if xref else str(c["artist_key"])
        c["artist_key"] = ck

        # 오늘 이후 날짜(선정 12-31 등)는 오늘로 자름
        c["last_seen"] = clamp_date_to_today(c.get("last_seen"), today=today)
        c["first_seen"] = clamp_date_to_today(c.get("first_seen"), today=today)

        # 장르 (멜론·발매 우선 + 오탐 없는 안전한 출처 폴백)
        genres = _infer_genres(
            c.pop("raw_genres", None),
            c.pop("press_sources", None),
            c.pop("sel_programs", None),
        )
        c["genres"] = genres
        c["primary_genre"] = genres[0] if genres else ""

        if c.get("already_outcome"):
            c["already_outcome_label"] = program_label(c["already_outcome"])
        else:
            c["already_outcome_label"] = ""

        # 우리 데이터 첫 등장 기반 신인 추정 (a09 3년 기준)
        r_info = rookie_status_info(c.get("status"), c.get("first_seen_all"), today=today)
        c.update(r_info)

        # 점수 v0 + 항목별 구성
        score_val, score_parts = compute_score_v0(
            n_branch=c.get("n_branch"),
            best_stage=c.get("best_stage"),
            peer_selected=c.get("peer_selected"),
            dmz=c.get("dmz"),
            gigs_1y=c.get("gigs_1y"),
            outlets=c.get("outlets"),
        )
        c["score_v0"] = score_val
        c["score_parts"] = score_parts

        # 최신순(정제 날짜 기준) 정렬 후 최대 15건 타임라인
        evs = sorted(by_key.get(ck, []), key=lambda x: str(x["sort_date"]), reverse=True)[:15]
        c["signals"] = evs

        # '왜 후보인가' 한 줄 요약
        if score_parts:
            c["why"] = " · ".join(f"{p['label']} +{p['pts']:g}" for p in score_parts)
        else:
            c["why"] = f"최근 180일 · {c.get('n_branch') or 0}갈래 ({c.get('branches') or ''})"
        enriched.append(c)

    # 정렬: 미수상 우선 → 신인 풀(확인 또는 3년 이내 첫 등장) 우선 → 점수 v0 내림차순 → 신호 수 → 최근 신호
    enriched.sort(
        key=lambda c: (
            0 if not c.get("already_outcome") else 1,
            0 if c.get("is_rookie_pool", True) else 1,
            -(c.get("score_v0") or 0.0),
            -(c.get("n_signals") or 0),
            str(c.get("last_seen") or ""),
        )
    )
    return enriched


def filter_recent_press(press_rows, candidate_keys=None, xref=None, limit=60):
    """매거진·큐레이터 최근 언급에서 수동 제외 유명 팀과 기관 계정을 거르고 중복 게시물을 정리."""
    candidate_keys = set(candidate_keys or ())
    cleaned = []
    seen_artist_url = set()
    url_counts = Counter()
    kind_counts = Counter()
    kind_caps = {"웹매거진": 28, "인스타 큐레이터": 22, "공연장 라인업": 10}
    for row in press_rows or []:
        if "artist_key" not in row:
            cleaned.append(row)
            continue
        raw_k = str(row.get("artist_key") or "").strip().lower()
        ck = team_key(row.get("artist_key") or row.get("artist") or "", xref) if xref else raw_k
        if (
            not ck
            or ck in MANUAL_FAMOUS_EXCLUDE
            or raw_k in MANUAL_FAMOUS_EXCLUDE
            or ck in NON_ARTIST_PRESS_KEYS
            or raw_k in NON_ARTIST_PRESS_KEYS
        ):
            continue
        kind = row.get("kind") or "웹매거진"
        if kind in kind_caps and kind_counts[kind] >= kind_caps[kind]:
            continue
        url = row.get("url") or ""
        dedup = (ck, url or row.get("title") or "")
        if dedup in seen_artist_url:
            continue
        # 같은 인스타 게시물 하나에 여러 계정이 태그돼 도배되는 것 방지 (게시물당 최대 2팀)
        if url and row.get("source") == "instagram" and url_counts[url] >= 2:
            continue
        seen_artist_url.add(dedup)
        if url:
            url_counts[url] += 1
        kind_counts[kind] += 1
        item = dict(row)
        item["artist_key"] = ck
        item["source_label"] = source_label(item.get("source"))
        item["is_candidate"] = ck in candidate_keys
        cleaned.append(item)
        if len(cleaned) >= limit:
            break
    return cleaned


def _attach_program_labels(rows):
    out = []
    for r in rows or []:
        item = dict(r)
        if "program" in item:
            item["program_label"] = program_label(item["program"])
        out.append(item)
    return out


def _annotate_quality(rows, raw_outcome_teams=None):
    raw_note = (
        f"표기 통일 기준 정답 풀 (원본 키 {raw_outcome_teams}개 중 한·영 중복 묶음 · backtrace.md 88팀과 묶기 방식 차이)"
        if raw_outcome_teams
        else "표기 통일 기준 정답 풀 (2025~2026 발표분)"
    )
    rules = {
        "같은 팀인데 표기가 여러 개인 이름 키": ("warn", "연결표(artist_xref)로 자동 묶음 처리 중 · 동명 팀은 추후 검수"),
        "유통사가 빈 발매 행": ("warn", "일부 음원 플랫폼 미기재 행"),
        "연도만 아는 선정 발표일": ("info", "시점 누수 방지(백테스트 연말 계산) · 화면엔 '2026 선정'으로 표시"),
        "멜론 프로필이 있는 팀": ("info", "신인·유명 팀 판별 기준 데이터 · 프로필 없으면 첫 등장 3년 이내로 추정"),
        "센 정답 팀 (표기 통일 후)": ("ok", raw_note),
        "센 정답 팀 (연차 필터 후)": ("ok", raw_note),
    }
    out = []
    for r in rows or []:
        item = dict(r)
        if "item" in item:
            st, note = rules.get(item["item"], ("info", ""))
            item["level"] = st
            item["note"] = note
        out.append(item)
    return out


def _compute_deltas(sections, prev):
    if not prev or not isinstance(prev, dict):
        return {"prev_generated": None, "candidates": None, "total_rows": None, "profiles": None}
    prev_sec = prev.get("sections") or {}

    def _sum_rows(sec):
        return sum((r.get("rows") or 0) for r in (sec.get("collection") or []))

    def _profiles(sec):
        for q in sec.get("quality") or []:
            if str(q.get("item") or "").startswith("멜론 프로필"):
                return q.get("value")
        return None

    cur_rows = _sum_rows(sections)
    prev_rows = _sum_rows(prev_sec)
    cur_cands = len(sections.get("candidates") or [])
    prev_cands = len(prev_sec.get("candidates") or [])
    cur_prof = _profiles(sections)
    prev_prof = _profiles(prev_sec)

    return {
        "prev_generated": prev.get("generated"),
        "candidates": cur_cands - prev_cands,
        "total_rows": cur_rows - prev_rows,
        "profiles": (cur_prof - prev_prof) if (cur_prof is not None and prev_prof is not None) else None,
    }


def psql_csv(sql):
    proc = subprocess.run([PSQL, "-v", "ON_ERROR_STOP=1", "-q", "--csv", "-d", DB, "-c", sql],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip()[:300])
    return proc.stdout


def _has_xref_table(run):
    try:
        rows = records(run("SELECT to_regclass('ref.artist_xref') AS t"))
        return bool(rows and rows[0].get("t"))
    except Exception:
        return False


def build(run=psql_csv, prev=None, use_xref_sql=None, xref=None):
    if xref is None:
        xref = load_xref_index()
    if use_xref_sql is None:
        use_xref_sql = _has_xref_table(run)

    queries = make_queries(use_xref_sql=use_xref_sql)
    sections, errors = {}, []
    for name, sql in queries.items():
        try:
            sections[name] = records(run(sql))
        except RuntimeError as e:
            sections[name] = []
            errors.append(f"{name}: {e}")

    # 점수 v0 백테스트 (a09 SQL 실행, DB 없거나 실패하면 docs/sql/README.md 표 폴백)
    sections["score_v0_backtest"] = load_score_v0_backtest(run=run)

    # 파이썬 후처리: 유명 팀 수동 제외 → 점수 v0·첫 등장·장르·타임라인 보강 → 프로그램 한국어 라벨 → 매거진 정제
    cands, excl = apply_manual_exclusions(sections.get("candidates"), sections.get("excluded_famous"), xref=xref)
    cands = enrich_candidates(cands, sections.get("candidate_signals"), xref=xref)
    sections["candidates"] = cands[:80]
    sections["excluded_famous"] = excl
    # 타임라인 원본은 후보 객체에 이미 붙였으므로 중복 용량을 줄인다
    sections["candidate_signals"] = []

    cand_keys = {c.get("artist_key") for c in sections["candidates"] if c.get("artist_key")}
    sections["recent_press"] = filter_recent_press(sections.get("recent_press"), candidate_keys=cand_keys, xref=xref)
    sections["signal_hit_rates"] = _attach_program_labels(sections.get("signal_hit_rates"))
    sections["mid_to_final"] = _attach_program_labels(sections.get("mid_to_final"))

    lt0 = (sections.get("lead_time_summary") or [{}])[0]
    sections["quality"] = _annotate_quality(sections.get("quality"), raw_outcome_teams=lt0.get("raw_outcome_teams"))

    deltas = _compute_deltas(sections, prev)
    return {
        "generated": datetime.now(KST).isoformat(timespec="seconds"),
        "window_from": WINDOW,
        "lookback_from": LOOKBACK_START,
        "xref_active": bool(use_xref_sql or (xref or {}).get("by_key")),
        "deltas": deltas,
        "errors": errors,
        "sections": sections,
    }


def _load_prev(path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def main():
    prev = _load_prev(OUT)
    data = build(prev=prev)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    n = sum(len(v) for v in data["sections"].values())
    c_n = len(data["sections"].get("candidates", []))
    e_n = len(data["sections"].get("excluded_famous", []))
    p_n = len(data["sections"].get("recent_press", []))
    bt_n = len(data["sections"].get("score_v0_backtest", []))
    print(f"저장: {OUT} (섹션 {len(data['sections'])}개, 후보 {c_n}팀, 제외 {e_n}팀, 최근언급 {p_n}건, 백테스트 {bt_n}행, 총 {n}행, 오류 {len(data['errors'])}개)")
    if data["errors"]:
        print("오류:", "; ".join(data["errors"]))
        sys.exit(1)


if __name__ == "__main__":
    main()
