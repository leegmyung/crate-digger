-- 무엇을 찾나: 동명 팀 의심 — (A) 같은 플랫폼 안에서 한 artist_key가 아티스트 번호 2개 이상에 연결,
--   (C) 플랫폼끼리 첫 발매(데뷔) 연도가 3년 이상 차이(멜론 vs 스포티파이), (B) 2010년 이전 선정 기록과 2024년 이후 공연이 같은 키에 함께 있음.
--   (이전 판은 멜론 번호·스포티파이 번호·인스타 계정을 모두 '멜론 ID'로 세어, 플랫폼마다 번호가 다른 같은 팀을 잘못 잡았음)
-- 왜 문제인가: 이름만으로 팀을 잇기 때문에, 다른 두 팀이 한 팀으로 합쳐지면 연차·첫 발매·적중 계산이 모두 틀어진다.
-- 결과를 보고 할 일: 번호·활동 연도·장르를 비교해 다른 팀이면 별도 키(예: 이름+번호)로 나누는 수동 매핑을 만든다.
WITH multi_profile AS (                         -- (A) 같은 플랫폼 안 여러 번호
    SELECT artist_key, source,
           count(DISTINCT artist_source_id) AS id_count,
           string_agg(DISTINCT artist_text || ' (' || source || ' ' || artist_source_id || ', 데뷔 '
                      || COALESCE(debut_date, first_release_date, '?') || ')', ' | ') AS evidence
    FROM raw.raw_artist_profile
    WHERE artist_key IS NOT NULL AND source IN ('melon', 'spotify')
    GROUP BY artist_key, source
    HAVING count(DISTINCT artist_source_id) >= 2
),
debut AS (                                      -- 플랫폼별 가장 이른 데뷔 연도
    SELECT artist_key, source,
           min(left(COALESCE(NULLIF(debut_date, ''), NULLIF(first_release_date, '')), 4))::int AS y
    FROM raw.raw_artist_profile
    WHERE artist_key IS NOT NULL AND source IN ('melon', 'spotify')
      AND COALESCE(NULLIF(debut_date, ''), NULLIF(first_release_date, '')) ~ '^[0-9]{4}'
    GROUP BY artist_key, source
),
debut_gap AS (                                  -- (C) 멜론과 스포티파이의 데뷔 연도 차이
    SELECT m.artist_key, abs(m.y - s.y) AS gap, '멜론 ' || m.y || ' / 스포티파이 ' || s.y AS evidence
    FROM debut m JOIN debut s ON s.artist_key = m.artist_key AND s.source = 'spotify'
    WHERE m.source = 'melon' AND abs(m.y - s.y) >= 3
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
SELECT 'A: 같은 플랫폼 번호 여러 개' AS risk_type, artist_key, id_count AS strength, evidence
FROM multi_profile
UNION ALL
SELECT 'C: 플랫폼별 데뷔 3년+ 차이', artist_key, gap, evidence
FROM debut_gap
UNION ALL
SELECT 'B: 2010년 전 선정 + 2024년 후 공연', s.artist_key, g.recent_gigs,
       s.program || ' ' || s.first_sel || ' 선정 / 최근 공연 ' || g.recent_gigs || '회 (마지막 ' || g.last_gig || ')'
FROM old_selection s
JOIN recent_gig g ON g.artist_key = s.artist_key
ORDER BY risk_type, strength DESC, artist_key;
