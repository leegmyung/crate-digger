-- 무엇을 찾나: 한 칸(artist_text)에 여러 사람·팀이 들어간 것처럼 보이는 값 (', ' / ' 외 ' / ' x ' / '&' / '/' 포함).
-- 왜 문제인가: "A, B" 가 통째로 하나의 팀 키가 되어 A·B 각각의 기록에 잡히지 않는다 (신호 누락).
-- 결과를 보고 할 일: 진짜 합동 무대면 행을 팀별로 나누고, "한글 / English" 병기나 이름 자체의 &(예: ~ & the band)는 예외 목록에 넣는다.
--   (HTML 엔티티 &apos; &amp; 는 먼저 풀어서 판정한다 — 엔티티 자체는 c08에서 따로 본다)
-- (BigQuery 문법으로 자동 변환: scripts/sql_to_bigquery.py — 원문은 sql/kr/ 의 같은 파일)
-- 주의: STRING_AGG 안 정렬의 NULLS FIRST/LAST는 BigQuery에서 지원 안 됨 → 이어 붙인 목록의 순서만 다를 수 있음
WITH all_names AS (
  SELECT
    'release' AS tbl,
    artist_text
  FROM raw.raw_kr_release
  UNION ALL
  SELECT
    'gig',
    artist_text
  FROM raw.raw_kr_gig
  UNION ALL
  SELECT
    'selection',
    artist_text
  FROM raw.raw_kr_selection
  UNION ALL
  SELECT
    'press',
    artist_text
  FROM raw.raw_press
  UNION ALL
  SELECT
    'outcome',
    artist_text
  FROM raw.raw_outcome
  UNION ALL
  SELECT
    'profile',
    artist_text
  FROM raw.raw_artist_profile
), decoded AS (
  SELECT
    tbl,
    artist_text,
    REPLACE(REPLACE(REPLACE(artist_text, '&apos;', '\''), '&#39;', '\''), '&amp;', '&') AS name
  FROM all_names
  WHERE
    artist_text IS NOT NULL
), classified AS (
  SELECT
    tbl,
    artist_text,
    CASE
      WHEN name LIKE '% 외 %' OR name LIKE '% 외' OR REGEXP_CONTAINS(name, ' 외 ?[0-9]+명')
      THEN '외 N명'
      WHEN name LIKE '% x %' OR name LIKE '% X %'
      THEN 'x 협업'
      WHEN name LIKE '%, %'
      THEN '쉼표 나열'
      WHEN name LIKE '%&%'
      THEN '& 연결'
      WHEN REGEXP_CONTAINS(name, '^[^/]*[가-힣][^/]* / [^가-힣/]+$')
      OR REGEXP_CONTAINS(name, '^[^가-힣/]+ / [^/]*[가-힣][^/]*$')
      THEN '/ 한영 병기(대개 한 팀)'
      WHEN name LIKE '%/%'
      THEN '/ 나열'
    END AS pattern
  FROM decoded
), flagged AS (
  SELECT
    tbl,
    pattern,
    artist_text,
    COUNT(*) AS rows_n
  FROM classified
  WHERE
    pattern IS NOT NULL
  GROUP BY
    tbl,
    pattern,
    artist_text
), ranked AS (
  SELECT
    f.*,
    ROW_NUMBER() OVER (
      PARTITION BY tbl, pattern
      ORDER BY rows_n DESC NULLS FIRST, artist_text NULLS LAST
    ) AS rn,
    COUNT(*) OVER (PARTITION BY tbl, pattern) AS distinct_values,
    SUM(rows_n) OVER (PARTITION BY tbl, pattern) AS total_rows
  FROM flagged AS f
)
SELECT
  tbl,
  pattern,
  distinct_values,
  total_rows,
  STRING_AGG(artist_text || ' (' || rows_n || ')', ' | '
  ORDER BY
    rn) AS top_examples
FROM ranked
WHERE
  rn <= 5
GROUP BY
  tbl,
  pattern,
  distinct_values,
  total_rows
ORDER BY
  tbl NULLS LAST,
  total_rows DESC NULLS FIRST;
