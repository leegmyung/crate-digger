-- 무엇을 찾나: 같은 artist_key인데 원문 표기(artist_text)가 2가지 이상으로 적힌 팀 (모든 raw 표 통틀어).
-- 왜 문제인가: 표기가 여러 개면 매칭 규칙(괄호·공백·대소문자 제거)에 의존하게 되고, 규칙이 바뀌면 같은 팀이 둘로 갈라진다.
-- 결과를 보고 할 일: 표기 수가 많은 팀부터 대표 표기를 정해 별칭 사전(ref)에 등록하고, 다른 팀이 섞였는지 눈으로 확인한다.
-- (BigQuery 문법으로 자동 변환: scripts/sql_to_bigquery.py — 원문은 sql/kr/ 의 같은 파일)
-- 주의: STRING_AGG 안 정렬의 NULLS FIRST/LAST는 BigQuery에서 지원 안 됨 → 이어 붙인 목록의 순서만 다를 수 있음
WITH all_names AS (
  SELECT
    'release' AS tbl,
    artist_key,
    artist_text
  FROM raw.raw_kr_release
  UNION ALL
  SELECT
    'gig',
    artist_key,
    artist_text
  FROM raw.raw_kr_gig
  UNION ALL
  SELECT
    'selection',
    artist_key,
    artist_text
  FROM raw.raw_kr_selection
  UNION ALL
  SELECT
    'press',
    artist_key,
    artist_text
  FROM raw.raw_press
  UNION ALL
  SELECT
    'outcome',
    artist_key,
    artist_text
  FROM raw.raw_outcome
  UNION ALL
  SELECT
    'profile',
    artist_key,
    artist_text
  FROM raw.raw_artist_profile
), spelling AS (
  SELECT
    artist_key,
    artist_text,
    COUNT(*) AS rows_n,
    STRING_AGG(DISTINCT tbl, '/') AS tables
  FROM all_names
  WHERE
    artist_key IS NOT NULL AND artist_key <> '' AND artist_text IS NOT NULL
  GROUP BY
    artist_key,
    artist_text
), ranked AS (
  SELECT
    artist_key,
    COUNT(*) AS variant_count,
    SUM(rows_n) AS total_rows,
    STRING_AGG(
      artist_text || ' [' || rows_n || ', ' || tables || ']', ' | '
      ORDER BY
        rows_n DESC,
        artist_text
    ) AS spellings
  FROM spelling
  GROUP BY
    artist_key
  HAVING
    COUNT(*) >= 2
)
SELECT
  artist_key,
  variant_count,
  total_rows,
  spellings
FROM ranked
ORDER BY
  variant_count DESC NULLS FIRST,
  total_rows DESC NULLS FIRST,
  artist_key NULLS LAST
LIMIT 30;
