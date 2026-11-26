"""PostgreSQL → 데이터 대시보드용 공개 JSON (docs/data/dashboard.json)

    python3 scripts/load_pg.py                 # 먼저 적재 (뷰도 다시 만듦)
    python3 scripts/build_dashboard_data.py

공개 페이지(GitHub Pages)에 실리므로 집계 숫자와 팀 이름·프로그램·날짜만 내보낸다 (원본 행·주소·계정 정보 제외).
"""
import csv
import io
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "data" / "dashboard.json"
PSQL = os.environ.get("PSQL", "/opt/homebrew/opt/postgresql@17/bin/psql")
DB = os.environ.get("PGDATABASE", "crate_digger")
KST = timezone(timedelta(hours=9))
WINDOW = "2025-01-01"          # 이 날 이후 정답을 '맞힐 대상'으로
LOOKBACK_START = "2020-01-01"  # 신호는 그 전 5년

# 같은 팀 잇기: artist_key 또는 괄호 별칭(alias_key)
SAME = "(a.artist_key = b.artist_key OR a.artist_key = b.alias_key OR a.alias_key = b.artist_key)"

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
    # 3. 지금 주목할 후보: 최근 180일 안에 2개 이상 갈래에 나온 팀. 유명 팀(팬 1만+ 또는 첫 발매 5년 초과)은 뺀다
    "candidates": """
        WITH recent AS (
            SELECT artist_key, min(artist_text) AS artist, count(DISTINCT branch) AS n_branch,
                   string_agg(DISTINCT branch, ' · ') AS branches, max(signal_date) AS last_seen
            FROM core.v_signal
            WHERE signal_date BETWEEN current_date - 180 AND current_date + 60 AND artist_key IS NOT NULL
            GROUP BY artist_key HAVING count(DISTINCT branch) >= 2)
        SELECT r.artist, r.n_branch, r.branches, r.last_seen,
               CASE coalesce(st.status, 'unknown') WHEN 'newcomer' THEN '신인' WHEN 'established' THEN '기성'
                    ELSE '모름' END AS status,
               st.first_release, st.fan_count,
               (SELECT min(o.program) FROM core.v_outcome o WHERE o.counted AND o.artist_key = r.artist_key) AS already_outcome
        FROM recent r LEFT JOIN core.v_artist_status st ON st.artist_key = r.artist_key
        WHERE coalesce(st.status, 'unknown') <> 'famous'
        ORDER BY (st.status = 'newcomer') DESC NULLS LAST, r.n_branch DESC, r.last_seen DESC LIMIT 60""",
    # 3-1. 유명해서 뺀 팀 (투명하게 보여주기)
    "excluded_famous": """
        SELECT DISTINCT ON (st.artist_key) s.artist_text AS artist, st.fan_count, st.years_since_first,
               CASE WHEN st.fan_count >= (SELECT value FROM ref.settings WHERE name = 'fame_fans') THEN '팬 수'
                    ELSE '활동 연차' END AS reason
        FROM core.v_artist_status st JOIN core.v_signal s ON s.artist_key = st.artist_key
        WHERE st.status = 'famous' AND s.signal_date >= current_date - 180
        ORDER BY st.artist_key, s.signal_date DESC""",
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
        SELECT CASE WHEN years_at_outcome <= 1 THEN '1년 이내' WHEN years_at_outcome <= 3 THEN '1~3년'
                    WHEN years_at_outcome <= 5 THEN '3~5년' ELSE '5년 초과' END AS bucket,
               count(*) AS teams
        FROM t GROUP BY 1 ORDER BY min(years_at_outcome)""",
    # 7. 공연 많은 공연장 (2025년 이후)
    "top_venues": """
        SELECT detail AS venue, count(*) AS gigs, count(DISTINCT artist_key) AS teams
        FROM core.v_signal WHERE branch = '공연' AND signal_date >= DATE '2025-01-01' AND coalesce(detail, '') <> ''
        GROUP BY detail ORDER BY gigs DESC LIMIT 15""",
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


def psql_csv(sql):
    proc = subprocess.run([PSQL, "-v", "ON_ERROR_STOP=1", "-q", "--csv", "-d", DB, "-c", sql],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip()[:300])
    return proc.stdout


def build(run=psql_csv):
    sections, errors = {}, []
    for name, sql in QUERIES.items():
        try:
            sections[name] = records(run(sql))
        except RuntimeError as e:
            sections[name] = []
            errors.append(f"{name}: {e}")
    return {"generated": datetime.now(KST).replace(microsecond=0).isoformat(), "window": WINDOW,
            "sections": sections, "errors": errors}


def main():
    data = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"✅ {OUT.relative_to(ROOT)}" + (f" (실패 {len(data['errors'])}개: {data['errors']})" if data["errors"] else ""))
    return 1 if data["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
