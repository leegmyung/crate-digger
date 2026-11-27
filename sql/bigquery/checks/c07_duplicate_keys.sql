-- 무엇을 찾나: 표마다 업무상 같은 행(비즈니스 키)이 여러 번 들어간 경우 — 대개 같은 날 수집기를 다시 돌려 생긴 파일(_HHMMSS.csv) 때문.
--   키: 공연 gig_url+artist_text, 발매 source+source_id(없으면 url), 선정 program+round+stage+artist_text, 정답 program+round+result+artist_text,
--       기사 url+artist_text, 프로필 artist_source_id.
-- 왜 문제인가: 중복을 그대로 세면 공연 횟수·신호 수가 부풀려진다. raw는 원본 보존용이므로 뷰(core.*)에서 반드시 중복을 걸러야 한다.
-- 결과를 보고 할 일: 표별 중복 비율을 확인하고, 뷰에 DISTINCT ON(키) ORDER BY collected_at DESC 같은 "최신 1건" 규칙을 넣는다.
-- (BigQuery 문법으로 자동 변환: scripts/sql_to_bigquery.py — 원문은 sql/kr/ 의 같은 파일)
-- 주의: STRING_AGG 안 정렬의 NULLS FIRST/LAST는 BigQuery에서 지원 안 됨 → 이어 붙인 목록의 순서만 다를 수 있음
WITH keyed AS (
  SELECT
    'raw_kr_gig' AS tbl,
    COALESCE(gig_url, source_id) || ' | ' || artist_text AS biz_key,
    source_file
  FROM raw.raw_kr_gig
  UNION ALL
  SELECT
    'raw_kr_release',
    source || ':' || COALESCE(source_id, release_url) || ' | ' || artist_text,
    source_file
  FROM raw.raw_kr_release
  UNION ALL
  SELECT
    'raw_kr_selection',
    program || ' | ' || COALESCE(round, '') || ' | ' || COALESCE(stage, '') || ' | ' || artist_text,
    source_file
  FROM raw.raw_kr_selection
  UNION ALL
  SELECT
    'raw_outcome',
    program || ' | ' || COALESCE(round, '') || ' | ' || COALESCE(result, '') || ' | ' || artist_text,
    source_file
  FROM raw.raw_outcome
  UNION ALL
  SELECT
    'raw_press',
    url || ' | ' || artist_text,
    source_file
  FROM raw.raw_press
  UNION ALL
  SELECT
    'raw_artist_profile',
    source || ':' || artist_source_id,
    source_file
  FROM raw.raw_artist_profile
), dup_keys AS (
  SELECT
    tbl,
    biz_key,
    COUNT(*) AS copies,
    COUNT(DISTINCT source_file) AS files,
    STRING_AGG(DISTINCT source_file, ', ') AS file_list
  FROM keyed
  WHERE
    biz_key IS NOT NULL
  GROUP BY
    tbl,
    biz_key
  HAVING
    COUNT(*) >= 2
), totals AS (
  SELECT
    tbl,
    COUNT(*) AS total_rows
  FROM keyed
  GROUP BY
    tbl
), ranked AS (
  SELECT
    d.*,
    ROW_NUMBER() OVER (PARTITION BY tbl ORDER BY copies DESC NULLS FIRST, biz_key NULLS LAST) AS rn
  FROM dup_keys AS d
)
SELECT
  t.tbl,
  t.total_rows,
  COALESCE(s.dup_keys, 0) AS dup_keys,
  COALESCE(s.extra_rows, 0) AS extra_rows,
  ROUND(100.0 * COALESCE(s.extra_rows, 0) / t.total_rows, 1) AS extra_pct,
  COALESCE(s.cross_file_keys, 0) AS keys_in_2plus_files,
  e.examples
FROM totals AS t
LEFT JOIN (
  SELECT
    tbl,
    COUNT(*) AS dup_keys,
    SUM(copies - 1) AS extra_rows,
    SUM(CASE WHEN files >= 2 THEN 1 ELSE 0 END) AS cross_file_keys
  FROM dup_keys
  GROUP BY
    tbl
) AS s
  ON s.tbl = t.tbl
LEFT JOIN (
  SELECT
    tbl,
    STRING_AGG(
      biz_key || ' x' || copies || ' [' || file_list || ']', CAST(b'\n' AS STRING)
      ORDER BY
        rn
    ) AS examples
  FROM ranked
  WHERE
    rn <= 3
  GROUP BY
    tbl
) AS e
  ON e.tbl = t.tbl
ORDER BY
  extra_rows DESC NULLS FIRST;
