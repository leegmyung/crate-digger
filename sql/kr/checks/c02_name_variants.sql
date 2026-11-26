-- 무엇을 찾나: 같은 artist_key인데 원문 표기(artist_text)가 2가지 이상으로 적힌 팀 (모든 raw 표 통틀어).
-- 왜 문제인가: 표기가 여러 개면 매칭 규칙(괄호·공백·대소문자 제거)에 의존하게 되고, 규칙이 바뀌면 같은 팀이 둘로 갈라진다.
-- 결과를 보고 할 일: 표기 수가 많은 팀부터 대표 표기를 정해 별칭 사전(ref)에 등록하고, 다른 팀이 섞였는지 눈으로 확인한다.
WITH all_names AS (
    SELECT 'release' AS tbl, artist_key, artist_text FROM raw.raw_kr_release
    UNION ALL SELECT 'gig',       artist_key, artist_text FROM raw.raw_kr_gig
    UNION ALL SELECT 'selection', artist_key, artist_text FROM raw.raw_kr_selection
    UNION ALL SELECT 'press',     artist_key, artist_text FROM raw.raw_press
    UNION ALL SELECT 'outcome',   artist_key, artist_text FROM raw.raw_outcome
    UNION ALL SELECT 'profile',   artist_key, artist_text FROM raw.raw_artist_profile
),
spelling AS (
    SELECT artist_key, artist_text,
           count(*) AS rows_n,
           string_agg(DISTINCT tbl, '/') AS tables
    FROM all_names
    WHERE artist_key IS NOT NULL AND artist_key <> '' AND artist_text IS NOT NULL
    GROUP BY artist_key, artist_text
),
ranked AS (
    SELECT artist_key,
           count(*)    AS variant_count,
           sum(rows_n) AS total_rows,
           string_agg(artist_text || ' [' || rows_n || ', ' || tables || ']', ' | ' ORDER BY rows_n DESC, artist_text) AS spellings
    FROM spelling
    GROUP BY artist_key
    HAVING count(*) >= 2
)
SELECT artist_key, variant_count, total_rows, spellings
FROM ranked
ORDER BY variant_count DESC, total_rows DESC, artist_key
LIMIT 30;
