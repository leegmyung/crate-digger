-- 무엇을 찾나: 동명 팀 의심 — (A) 한 artist_key가 멜론 아티스트 ID 2개 이상에 연결, (B) 2010년 이전 선정 기록과 2024년 이후 공연이 같은 키에 함께 있음.
-- 왜 문제인가: 이름만으로 팀을 잇기 때문에, 다른 두 팀이 한 팀으로 합쳐지면 연차·첫 발매·적중 계산이 모두 틀어진다.
-- 결과를 보고 할 일: 멜론 ID·활동 연도·장르를 비교해 다른 팀이면 별도 키(예: 이름+ID)로 나누는 수동 매핑을 만든다.
WITH multi_profile AS (
    SELECT artist_key,
           count(DISTINCT artist_source_id) AS melon_id_count,
           string_agg(DISTINCT artist_text || ' (id ' || artist_source_id || ', 데뷔 '
                      || COALESCE(debut_date, first_release_date, '?') || ')', ' | ') AS evidence
    FROM raw.raw_artist_profile
    WHERE artist_key IS NOT NULL
    GROUP BY artist_key
    HAVING count(DISTINCT artist_source_id) >= 2
),
old_selection AS (
    SELECT artist_key, min(announced_start) AS first_sel, min(program) AS program
    FROM raw.raw_kr_selection
    WHERE announced_end < DATE '2010-01-01'
    GROUP BY artist_key
),
recent_gig AS (
    SELECT artist_key, max(gig_date) AS last_gig, count(*) AS recent_gigs
    FROM raw.raw_kr_gig
    WHERE gig_date >= DATE '2024-01-01'
    GROUP BY artist_key
)
SELECT 'A: 멜론 ID 여러 개' AS risk_type, artist_key, melon_id_count AS strength, evidence
FROM multi_profile
UNION ALL
SELECT 'B: 2010년 전 선정 + 2024년 후 공연', s.artist_key, g.recent_gigs,
       s.program || ' ' || s.first_sel || ' 선정 / 최근 공연 ' || g.recent_gigs || '회 (마지막 ' || g.last_gig || ')'
FROM old_selection s
JOIN recent_gig g ON g.artist_key = s.artist_key
ORDER BY risk_type, strength DESC, artist_key;
