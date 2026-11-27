"""PostgreSQL → 데이터 대시보드용 공개 JSON (docs/data/dashboard.json)

    python3 scripts/load_pg.py                 # 먼저 적재 (뷰도 다시 만듦)
    python3 scripts/build_dashboard_data.py

공개 페이지(GitHub Pages)에 실리므로 집계 숫자와 팀 이름·장르·프로그램·날짜·공개 출처 링크만 내보낸다.
"""
import csv
import io
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import genre as genre_mod  # noqa: E402

OUT = ROOT / "docs" / "data" / "dashboard.json"
PSQL = os.environ.get("PSQL", "/opt/homebrew/opt/postgresql@17/bin/psql")
DB = os.environ.get("PGDATABASE", "crate_digger")
KST = timezone(timedelta(hours=9))
WINDOW = "2025-01-01"          # 이 날 이후 정답을 '맞힐 대상'으로
LOOKBACK_START = "2020-01-01"  # 신호는 그 전 5년

# 같은 팀 잇기: artist_key 또는 괄호 별칭(alias_key)
SAME = "(a.artist_key = b.artist_key OR a.artist_key = b.alias_key OR a.alias_key = b.artist_key)"

# 프로그램 코드 → 한국어 표시 이름 (차트에 영어 코드가 그대로 보이지 않도록)
PROGRAM_NAMES = {
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
    "instagram": "인스타그램",
    "yjh": "유재하음악경연대회",
    "dmz": "DMZ 피스트레인",
    "sejong": "세종 뮤즈세종",
    "gbsound": "경북 음악창작소",
    "busanrock": "부산록페 루키즈",
}

# 프로필 데이터가 아직 수집되지 않아 자동 유명 팀 제외 규칙에 걸리지 않는
# 메이저·베테랑·해외 투어 아티스트 수동 제외 목록 (artist_key 기준).
# 프로필이 채워지면 자동 규칙이 대신 처리한다.
MANUAL_FAMOUS_EXCLUDE = {
    "혁오": "수동 제외 (2014 데뷔 메이저 밴드 · 프로필 수집 전)",
    "실리카겔": "수동 제외 (한대음 다관왕 메이저 밴드 · 프로필 수집 전)",
    "colde": "수동 제외 (메이저 R&B 아티스트·WAVY 대표 · 프로필 수집 전)",
    "사이먼도미닉": "수동 제외 (메이저 힙합 아티스트 · 프로필 수집 전)",
    "팔로알토": "수동 제외 (2004 데뷔 베테랑 힙합 아티스트 · 프로필 수집 전)",
    "비프리": "수동 제외 (2009 데뷔 베테랑 힙합 아티스트 · 프로필 수집 전)",
    "김하온": "수동 제외 (메이저 힙합 아티스트 · 프로필 수집 전)",
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
    "구름": "수동 제외 (베테랑 프로듀서·뮤지션 · 프로필 수집 전)",
    "한올": "수동 제외 (2014 데뷔 10년+ 싱어송라이터 · 프로필 수집 전)",
    "불고기디스코": "수동 제외 (베테랑 멤버 구성 기성 밴드 · 프로필 수집 전)",
    "shininryu": "수동 제외 (신인류 인스타 계정 · 멜론 팬 1만+ 기제외 팀)",
    "아이브": "수동 제외 (메이저 K-pop 걸그룹)",
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


def program_label(code):
    if not code:
        return ""
    return PROGRAM_NAMES.get(code, code)


def source_label(code):
    if not code:
        return ""
    return SOURCE_NAMES.get(code, code)


QUERIES = {
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
    # 3. 지금 주목할 후보: 최근 180일 안에 2개 이상 갈래에 나온 팀. 유명 팀은 제외
    "candidates": """
        WITH recent AS (
            SELECT artist_key, min(artist_text) AS artist, count(DISTINCT branch) AS n_branch,
                   count(*) AS n_signals,
                   string_agg(DISTINCT branch, ' · ' ORDER BY branch) AS branches,
                   min(signal_date) AS first_seen, max(signal_date) AS last_seen
            FROM core.v_signal
            WHERE signal_date BETWEEN current_date - 180 AND current_date + 60 AND artist_key IS NOT NULL
            GROUP BY artist_key HAVING count(DISTINCT branch) >= 2)
        SELECT r.artist_key, r.artist, r.n_branch, r.n_signals, r.branches, r.first_seen, r.last_seen,
               CASE coalesce(st.status, 'unknown') WHEN 'newcomer' THEN '신인' WHEN 'established' THEN '기성'
                    ELSE '확인 안 됨' END AS status,
               st.first_release, st.fan_count,
               (SELECT min(o.program) FROM core.v_outcome o WHERE o.counted AND o.artist_key = r.artist_key) AS already_outcome,
               concat_ws('|',
                   (SELECT string_agg(DISTINCT p.genre, '|') FROM raw.raw_artist_profile p
                    WHERE p.artist_key = r.artist_key AND coalesce(p.genre, '') <> ''),
                   (SELECT string_agg(DISTINCT rel.genre, '|') FROM raw.raw_kr_release rel
                    WHERE rel.artist_key = r.artist_key AND coalesce(rel.genre, '') <> '')
               ) AS raw_genres
        FROM recent r LEFT JOIN core.v_artist_status st ON st.artist_key = r.artist_key
        WHERE coalesce(st.status, 'unknown') <> 'famous'
        ORDER BY CASE coalesce(st.status, 'unknown') WHEN 'newcomer' THEN 0 WHEN 'unknown' THEN 1 ELSE 2 END,
                 ((SELECT min(o.program) FROM core.v_outcome o WHERE o.counted AND o.artist_key = r.artist_key) IS NULL) DESC,
                 r.n_branch DESC, r.n_signals DESC, r.last_seen DESC
        LIMIT 120""",
    # 3-0. 후보별 신호 타임라인 (클릭 시 펼침용: 최근 1년+, 출처 링크 포함)
    "candidate_signals": """
        WITH cand AS (
            SELECT artist_key FROM core.v_signal
            WHERE signal_date BETWEEN current_date - 180 AND current_date + 60 AND artist_key IS NOT NULL
            GROUP BY artist_key HAVING count(DISTINCT branch) >= 2
        ),
        ev AS (
            SELECT s.artist_key, s.announced_end AS signal_date, '선정·지원'::text AS branch,
                   s.source, s.program AS title, concat_ws(' · ', s.round, s.stage) AS detail, s.url
            FROM raw.raw_kr_selection s JOIN cand c ON c.artist_key = s.artist_key
            UNION ALL
            SELECT g.artist_key, g.gig_date, '공연', g.source,
                   coalesce(nullif(g.title, ''), split_part(g.venue_text, ' (', 1)),
                   split_part(g.venue_text, ' (', 1), g.gig_url
            FROM raw.raw_kr_gig g JOIN cand c ON c.artist_key = g.artist_key
            WHERE g.gig_date >= current_date - 365
            UNION ALL
            SELECT r.artist_key, r.released_end, '발매', r.source, r.title, r.release_type, r.release_url
            FROM raw.raw_kr_release r JOIN cand c ON c.artist_key = r.artist_key
            UNION ALL
            SELECT p.artist_key, left(p.published_at, 10)::date,
                   CASE WHEN p.pick_label = 'venue_lineup' THEN '공연' ELSE '큐레이션' END,
                   p.source, left(p.title, 100), p.outlet, p.url
            FROM raw.raw_press p JOIN cand c ON c.artist_key = p.artist_key
            WHERE coalesce(p.is_sponsored, 0) = 0 AND left(p.published_at, 10)::date >= current_date - 365
        )
        SELECT DISTINCT ON (artist_key, signal_date, branch, source, coalesce(detail, ''), coalesce(title, ''))
               artist_key, signal_date, branch, source, title, detail, url
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
    "recent_press": """
        WITH base AS (
            SELECT p.artist_key, p.artist_text AS artist, p.source, p.outlet,
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
    # 6. 정답 받을 때 첫 발매 후 연차 (팀별 첫 정답 기준)
    "career_at_outcome": """
        WITH t AS (SELECT DISTINCT ON (artist_key) artist_key, years_at_outcome FROM core.v_outcome
                   WHERE counted AND years_at_outcome IS NOT NULL ORDER BY artist_key, announced_start)
        SELECT CASE WHEN years_at_outcome <= 1 THEN '1년 차 이내' WHEN years_at_outcome <= 3 THEN '1~3년 차'
                    WHEN years_at_outcome <= 5 THEN '3~5년 차' ELSE '5년 초과' END AS bucket,
               count(*) AS teams
        FROM t GROUP BY 1 ORDER BY min(years_at_outcome)""",
    # 6-0. 연차 요약 (중앙값 세로선용)
    "career_summary": """
        WITH t AS (SELECT DISTINCT ON (artist_key) artist_key, years_at_outcome FROM core.v_outcome
                   WHERE counted AND years_at_outcome IS NOT NULL ORDER BY artist_key, announced_start)
        SELECT count(*) AS teams,
               round((percentile_cont(0.5) WITHIN GROUP (ORDER BY years_at_outcome))::numeric, 1) AS median_years,
               count(*) FILTER (WHERE years_at_outcome <= 3) AS within_3y
        FROM t""",
    # 6-1. 리드타임: 정답 팀이 첫 정답 몇 개월 전에 우리 신호에 처음 나왔나 (갈래 무관)
    "lead_time": f"""
        WITH first_sig AS (
            SELECT b.artist_key, b.first_outcome_date, min(a.signal_date) AS first_signal
            FROM core.v_signal a JOIN core.v_outcome_team b ON {SAME}
            WHERE a.signal_date < b.first_outcome_date
            GROUP BY b.artist_key, b.first_outcome_date)
        SELECT CASE WHEN m < 6 THEN '0~6개월' WHEN m < 12 THEN '6~12개월' WHEN m < 24 THEN '12~24개월'
                    WHEN m < 36 THEN '24~36개월' ELSE '36개월 이상' END AS bucket,
               count(*) AS teams, round(avg(m)::numeric, 1) AS avg_months,
               min(m) AS sort_key
        FROM (SELECT artist_key, (first_outcome_date - first_signal) / 30.4 AS m FROM first_sig) x
        GROUP BY 1 ORDER BY sort_key""",
    # 6-2. 리드타임 요약: 정답 팀 수, 신호가 먼저 있던 팀 수, 중앙값, 1년 이상 선행 팀 수
    "lead_time_summary": f"""
        WITH first_sig AS (
            SELECT b.artist_key, min(a.signal_date) AS first_signal, max(b.first_outcome_date) AS first_outcome
            FROM core.v_outcome_team b LEFT JOIN core.v_signal a ON {SAME} AND a.signal_date < b.first_outcome_date
            GROUP BY b.artist_key)
        SELECT count(*) AS outcome_teams, count(first_signal) AS with_prior_signal,
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
    "top_venues": """
        WITH cand AS (
            SELECT artist_key FROM core.v_signal
            WHERE signal_date BETWEEN current_date - 180 AND current_date + 60 AND artist_key IS NOT NULL
            GROUP BY artist_key HAVING count(DISTINCT branch) >= 2
        )
        SELECT v.detail AS venue, count(*) AS gigs, count(DISTINCT v.artist_key) AS teams,
               count(DISTINCT CASE WHEN c.artist_key IS NOT NULL THEN v.artist_key END) AS candidate_teams
        FROM core.v_signal v LEFT JOIN cand c ON c.artist_key = v.artist_key
        WHERE v.branch = '공연' AND v.signal_date >= DATE '2025-01-01' AND coalesce(v.detail, '') <> ''
        GROUP BY v.detail ORDER BY gigs DESC LIMIT 15""",
    # 8. 데이터 품질 요약
    "quality": """
        SELECT '같은 팀인데 표기가 여러 개인 이름 키' AS item,
               (SELECT count(*) FROM (SELECT artist_key FROM core.v_signal WHERE artist_key IS NOT NULL
                GROUP BY artist_key HAVING count(DISTINCT artist_text) > 1) x) AS value
        UNION ALL SELECT '유통사가 빈 발매 행',
               (SELECT count(*) FROM raw.raw_kr_release WHERE distributor_text IS NULL)
        UNION ALL SELECT '연도만 아는 선정 발표일',
               (SELECT count(*) FROM raw.raw_kr_selection WHERE length(announced_at) = 4)
        UNION ALL SELECT '멜론 프로필이 있는 팀',
               (SELECT count(*) FROM core.v_artist_profile)
        UNION ALL SELECT '센 정답 팀 (연차 필터 후)',
               (SELECT count(*) FROM core.v_outcome_team)""",
}


def _num(v):
    if v in ("", None):
        return None
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


def _genre_labels(raw_genres):
    if not raw_genres:
        return []
    buckets = genre_mod.buckets_of(str(raw_genres))
    cfg = genre_mod.load_config()["buckets"]
    return [cfg[b]["label"] for b in buckets if b in cfg]


def apply_manual_exclusions(candidates, excluded_famous):
    """프로필 미수집으로 자동 제외에 안 걸린 메이저·기성·해외 팀을 수동 제외 목록으로 분리."""
    kept = []
    excluded = list(excluded_famous or [])
    seen_excl = {str(e.get("artist") or "").strip().lower() for e in excluded}
    for row in candidates or []:
        key = str(row.get("artist_key") or "").strip().lower()
        if key and key in MANUAL_FAMOUS_EXCLUDE:
            artist = row.get("artist") or key
            if str(artist).strip().lower() not in seen_excl:
                excluded.append({
                    "artist": artist,
                    "fan_count": row.get("fan_count"),
                    "years_since_first": None,
                    "reason": MANUAL_FAMOUS_EXCLUDE[key],
                })
                seen_excl.add(str(artist).strip().lower())
            continue
        kept.append(row)
    return kept, excluded


def enrich_candidates(candidates, candidate_signals):
    """후보 목록에 한국어 장르 갈래, 신호 타임라인, '왜 후보인가' 한 줄 요약을 붙인다."""
    by_key = defaultdict(list)
    for ev in candidate_signals or []:
        key = ev.get("artist_key")
        if not key:
            continue
        title = ev.get("title") or ""
        if ev.get("branch") == "선정·지원":
            title = program_label(title)
        by_key[key].append({
            "date": ev.get("signal_date") or "",
            "branch": ev.get("branch") or "",
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
        genres = _genre_labels(c.pop("raw_genres", None))
        c["genres"] = genres
        c["primary_genre"] = genres[0] if genres else ""
        if c.get("already_outcome"):
            c["already_outcome_label"] = program_label(c["already_outcome"])
        else:
            c["already_outcome_label"] = ""

        # 최신순 정렬 후 최대 15건만 타임라인에 포함
        evs = sorted(by_key.get(c["artist_key"], []), key=lambda x: str(x["date"]), reverse=True)[:15]
        c["signals"] = evs

        # '왜 후보인가' 한 줄 요약
        b_counts = Counter(e["branch"] for e in evs)
        parts = [f"{b} {cnt}" for b, cnt in b_counts.most_common()]
        n_b = c.get("n_branch") or 0
        if parts:
            c["why"] = f"{n_b}갈래 포착 · 기록 {len(evs)}건 ({' · '.join(parts)})"
        else:
            c["why"] = f"최근 180일 · {n_b}갈래 ({c.get('branches') or ''})"
        enriched.append(c)
    return enriched


def filter_recent_press(press_rows, candidate_keys=None, limit=60):
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
        key = str(row.get("artist_key") or "").strip().lower()
        if not key or key in MANUAL_FAMOUS_EXCLUDE or key in NON_ARTIST_PRESS_KEYS:
            continue
        kind = row.get("kind") or "웹매거진"
        if kind in kind_caps and kind_counts[kind] >= kind_caps[kind]:
            continue
        url = row.get("url") or ""
        dedup = (key, url or row.get("title") or "")
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
        item["source_label"] = source_label(item.get("source"))
        item["is_candidate"] = row.get("artist_key") in candidate_keys
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


def _annotate_quality(rows):
    rules = {
        "같은 팀인데 표기가 여러 개인 이름 키": ("warn", "이름 키로 자동 묶음 처리 중 · 동명 팀은 추후 검수"),
        "유통사가 빈 발매 행": ("warn", "일부 음원 플랫폼 미기재 행"),
        "연도만 아는 선정 발표일": ("info", "시점 누수 방지 규칙 적용(후보는 연말, 정답은 연초로 계산)"),
        "멜론 프로필이 있는 팀": ("info", "신인·유명 팀 판별 기준 데이터 · 계속 수집 중"),
        "센 정답 팀 (연차 필터 후)": ("ok", "검증 기준 정답 풀 (2025~2026 발표분)"),
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


def build(run=psql_csv, prev=None):
    sections, errors = {}, []
    for name, sql in QUERIES.items():
        try:
            sections[name] = records(run(sql))
        except RuntimeError as e:
            sections[name] = []
            errors.append(f"{name}: {e}")

    # 파이썬 후처리: 유명 팀 수동 제외 → 장르·타임라인 보강 → 프로그램 한국어 라벨 → 매거진 정제
    cands, excl = apply_manual_exclusions(sections.get("candidates"), sections.get("excluded_famous"))
    cands = enrich_candidates(cands, sections.get("candidate_signals"))
    sections["candidates"] = cands[:70]
    sections["excluded_famous"] = excl
    # 타임라인 원본은 후보 객체에 이미 붙였으므로 중복 용량을 줄인다
    sections["candidate_signals"] = []

    cand_keys = {c.get("artist_key") for c in sections["candidates"] if c.get("artist_key")}
    sections["recent_press"] = filter_recent_press(sections.get("recent_press"), candidate_keys=cand_keys)
    sections["signal_hit_rates"] = _attach_program_labels(sections.get("signal_hit_rates"))
    sections["mid_to_final"] = _attach_program_labels(sections.get("mid_to_final"))
    sections["quality"] = _annotate_quality(sections.get("quality"))

    deltas = _compute_deltas(sections, prev)
    return {
        "generated": datetime.now(KST).replace(microsecond=0).isoformat(),
        "window": WINDOW,
        "deltas": deltas,
        "sections": sections,
        "errors": errors,
    }


def _load_prev(path=OUT):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def main():
    prev = _load_prev(OUT)
    data = build(prev=prev)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"✅ {OUT.relative_to(ROOT)}" + (f" (실패 {len(data['errors'])}개: {data['errors']})" if data["errors"] else ""))
    return 1 if data["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
