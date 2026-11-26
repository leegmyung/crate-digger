-- 무엇을 찾나: 표·소스·수집일(collected_at 날짜)별 행 수를 세고, 직전 수집일보다 50% 넘게 줄어든 날을 표시한다.
-- 왜 문제인가: 사이트 구조가 바뀌거나 차단되면 수집기는 오류 없이 "적게" 가져온다. 행 수 급감이 가장 빠른 고장 신호다.
-- 결과를 보고 할 일: is_drop = true 인 줄의 수집기를 바로 다시 돌려 보고, 원본 페이지와 파서를 점검한다. (첫 수집일은 비교 대상 없음)
WITH all_rows AS (
    SELECT 'raw_kr_release' AS tbl, source, collected_at FROM raw.raw_kr_release
    UNION ALL SELECT 'raw_kr_gig',         source, collected_at FROM raw.raw_kr_gig
    UNION ALL SELECT 'raw_kr_selection',   source, collected_at FROM raw.raw_kr_selection
    UNION ALL SELECT 'raw_press',          source, collected_at FROM raw.raw_press
    UNION ALL SELECT 'raw_outcome',        source, collected_at FROM raw.raw_outcome
    UNION ALL SELECT 'raw_artist_profile', source, collected_at FROM raw.raw_artist_profile
),
daily AS (
    SELECT tbl, source, CAST(collected_at AS date) AS collected_date, count(*) AS rows_n
    FROM all_rows
    GROUP BY tbl, source, CAST(collected_at AS date)
),
with_prev AS (
    SELECT d.*,
           lag(rows_n)         OVER (PARTITION BY tbl, source ORDER BY collected_date) AS prev_rows,
           lag(collected_date) OVER (PARTITION BY tbl, source ORDER BY collected_date) AS prev_date
    FROM daily d
)
SELECT tbl, source, collected_date, rows_n, prev_date, prev_rows,
       CASE WHEN prev_rows IS NULL THEN NULL
            ELSE round(100.0 * (rows_n - prev_rows) / prev_rows, 1) END AS change_pct,
       COALESCE(rows_n < prev_rows * 0.5, false)                         AS is_drop
FROM with_prev
ORDER BY is_drop DESC, tbl, source, collected_date DESC;
