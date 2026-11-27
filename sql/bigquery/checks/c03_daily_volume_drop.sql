-- 무엇을 찾나: 표·소스·수집일(collected_at 날짜)별 행 수를 세고, 직전 수집일보다 50% 넘게 줄어든 날을 표시한다.
-- 왜 문제인가: 사이트 구조가 바뀌거나 차단되면 수집기는 오류 없이 "적게" 가져온다. 행 수 급감이 가장 빠른 고장 신호다.
-- 결과를 보고 할 일: is_drop = true 인 줄의 수집기를 바로 다시 돌려 보고, 원본 페이지와 파서를 점검한다. (첫 수집일은 비교 대상 없음)
-- (BigQuery 문법으로 자동 변환: scripts/sql_to_bigquery.py — 원문은 sql/kr/ 의 같은 파일)
WITH all_rows AS (
  SELECT
    'raw_kr_release' AS tbl,
    source,
    collected_at
  FROM raw.raw_kr_release
  UNION ALL
  SELECT
    'raw_kr_gig',
    source,
    collected_at
  FROM raw.raw_kr_gig
  UNION ALL
  SELECT
    'raw_kr_selection',
    source,
    collected_at
  FROM raw.raw_kr_selection
  UNION ALL
  SELECT
    'raw_press',
    source,
    collected_at
  FROM raw.raw_press
  UNION ALL
  SELECT
    'raw_outcome',
    source,
    collected_at
  FROM raw.raw_outcome
  UNION ALL
  SELECT
    'raw_artist_profile',
    source,
    collected_at
  FROM raw.raw_artist_profile
), daily AS (
  SELECT
    tbl,
    source,
    CAST(collected_at AS DATE) AS collected_date,
    COUNT(*) AS rows_n
  FROM all_rows
  GROUP BY
    tbl,
    source,
    CAST(collected_at AS DATE)
), with_prev AS (
  SELECT
    d.*,
    LAG(rows_n) OVER (PARTITION BY tbl, source ORDER BY collected_date NULLS LAST) AS prev_rows,
    LAG(collected_date) OVER (PARTITION BY tbl, source ORDER BY collected_date NULLS LAST) AS prev_date
  FROM daily AS d
)
SELECT
  tbl,
  source,
  collected_date,
  rows_n,
  prev_date,
  prev_rows,
  CASE
    WHEN prev_rows IS NULL
    THEN NULL
    ELSE ROUND(100.0 * (
      rows_n - prev_rows
    ) / prev_rows, 1)
  END AS change_pct,
  COALESCE(rows_n < prev_rows * 0.5, FALSE) AS is_drop
FROM with_prev
ORDER BY
  is_drop DESC NULLS FIRST,
  tbl NULLS LAST,
  source NULLS LAST,
  collected_date DESC NULLS FIRST;
