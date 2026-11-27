-- 질문: 같은 발매(팀 × 제목)가 몇 개 음원 플랫폼(멜론·벅스·지니·플로)에 동시에 잡혔나? 유통사 상위 10곳은 어디고,
--       각 유통사 발매는 몇 %가 여러 플랫폼에 잡혔나?
-- 왜 중요한가: 여러 플랫폼 '신곡' 목록에 동시에 올라온 발매는 유통 힘이 있는(또는 주목받는) 발매다. 유통사별로 보면
--       인디 신인이 주로 어느 유통사를 거치는지, 그 유통사가 노출을 얼마나 넓게 주는지 알 수 있다.
-- 읽는 법: 구분 '플랫폼 수 분포' = N개 플랫폼에 잡힌 발매 수와 전체 대비 비율. 구분 '유통사 상위10' = 그 유통사가 적힌 발매 수와
--       그중 2개 이상 플랫폼에 잡힌 비율. 발매 키 = (artist_key, title_key).
-- 데이터 주의: 2026-11-23~26 며칠치 신곡 목록뿐이라 표본이 작다(약 100개 발매). 포크라노스는 제목 키가 없어 제외.
--       유통사 이름은 플랫폼마다 표기가 달라(예: Dreamus/드림어스) 같은 회사가 따로 셀 수 있다.
-- (BigQuery 문법으로 자동 변환: scripts/sql_to_bigquery.py — 원문은 sql/kr/ 의 같은 파일)
WITH release_rows AS (
  SELECT
    artist_key,
    title_key,
    source,
    NULLIF(TRIM(distributor_text), '') AS distributor
  FROM raw.raw_kr_release
  WHERE
    title_key IS NOT NULL
    AND title_key <> ''
    AND artist_key IS NOT NULL
    AND artist_key <> ''
), release_platforms AS (
  SELECT
    artist_key,
    title_key,
    COUNT(DISTINCT source) AS platform_cnt
  FROM release_rows
  GROUP BY
    artist_key,
    title_key
), platform_dist AS (
  SELECT
    '1) 플랫폼 수 분포' AS 구분,
    CAST(platform_cnt AS STRING) || '개 플랫폼' AS 항목,
    COUNT(*) AS 발매_수,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS 비율_pct,
    platform_cnt AS sort_key
  FROM release_platforms
  GROUP BY
    platform_cnt
), distributor_release AS (
  SELECT DISTINCT
    r.distributor,
    r.artist_key,
    r.title_key,
    rp.platform_cnt
  FROM release_rows AS r
  JOIN release_platforms AS rp
    ON rp.artist_key = r.artist_key AND rp.title_key = r.title_key
  WHERE
    r.distributor IS NOT NULL
), distributor_rank AS (
  SELECT
    distributor,
    COUNT(*) AS release_cnt,
    SUM(CASE WHEN platform_cnt >= 2 THEN 1 ELSE 0 END) AS multi_cnt,
    ROW_NUMBER() OVER (ORDER BY COUNT(*) DESC NULLS FIRST, distributor NULLS LAST) AS rn
  FROM distributor_release
  GROUP BY
    distributor
), distributor_top AS (
  SELECT
    '2) 유통사 상위10' AS 구분,
    distributor AS 항목,
    release_cnt AS 발매_수,
    ROUND(100.0 * multi_cnt / release_cnt, 1) AS 비율_pct, /* 다중 플랫폼 비율 */
    rn AS sort_key
  FROM distributor_rank
  WHERE
    rn <= 10
)
SELECT
  구분,
  항목,
  발매_수,
  비율_pct
FROM (
  SELECT
    *
  FROM platform_dist
  UNION ALL
  SELECT
    *
  FROM distributor_top
) AS x
ORDER BY
  구분 NULLS LAST,
  sort_key NULLS LAST;
