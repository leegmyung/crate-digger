-- 무엇을 찾나: 같은 앨범(artist_key + title_key)이 2개 이상 플랫폼에 올라왔는데 발매일(released_at)이 서로 다른 경우.
-- 왜 문제인가: 플랫폼마다 발매일을 다르게 적으면 "언제 처음 나왔나"가 흔들려 신호 시점·첫 발매 계산이 틀어진다.
-- 결과를 보고 할 일: 날짜 차이가 큰 줄부터 원본 페이지를 확인하고, 앨범 발매일은 가장 이른 날(또는 신뢰 플랫폼)로 정한다.
-- (BigQuery 문법으로 자동 변환: scripts/sql_to_bigquery.py — 원문은 sql/kr/ 의 같은 파일)
-- 주의: STRING_AGG 안 정렬의 NULLS FIRST/LAST는 BigQuery에서 지원 안 됨 → 이어 붙인 목록의 순서만 다를 수 있음
WITH per_platform AS (
  SELECT
    artist_key,
    title_key,
    source,
    MIN(released_at) AS released_at,
    MIN(artist_text) AS artist_text,
    MIN(title) AS title
  FROM raw.raw_kr_release
  WHERE
    artist_key IS NOT NULL AND title_key IS NOT NULL AND title_key <> ''
  GROUP BY
    artist_key,
    title_key,
    source
), albums AS (
  SELECT
    artist_key,
    title_key,
    COUNT(DISTINCT source) AS platform_count,
    COUNT(DISTINCT released_at) AS date_count,
    MIN(released_start) AS earliest,
    MAX(released_start) AS latest
  FROM raw.raw_kr_release
  WHERE
    artist_key IS NOT NULL AND title_key IS NOT NULL AND title_key <> ''
  GROUP BY
    artist_key,
    title_key
  HAVING
    COUNT(DISTINCT source) >= 2 AND COUNT(DISTINCT released_at) >= 2
)
SELECT
  a.artist_key,
  p.artist_text,
  p.title,
  a.platform_count,
  a.date_count,
  (
    a.latest - a.earliest
  ) AS gap_days,
  STRING_AGG(p.source || '=' || p.released_at, ', '
  ORDER BY
    p.released_at,
    p.source) AS dates_by_platform
FROM albums AS a
JOIN per_platform AS p
  ON p.artist_key = a.artist_key AND p.title_key = a.title_key
GROUP BY
  a.artist_key,
  a.title_key,
  p.artist_text,
  p.title,
  a.platform_count,
  a.date_count,
  a.latest,
  a.earliest
ORDER BY
  gap_days DESC,
  a.artist_key NULLS LAST;
