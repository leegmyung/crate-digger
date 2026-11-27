-- 질문: 정답 프로그램별로, 정답 받을 당시 팀은 첫 발매 후 몇 년 차였나? 우리 '신인 기준'(3년 이내 & 앨범 10개 이하)을 몇 %가 통과하나?
-- 왜 중요한가: 정답이 정말 '신인' 대상인지 확인한다. 기성 팀이 많이 섞인 프로그램은 신인 발굴의 정답으로 쓰기 어렵다.
-- 읽는 법: 버전 '전체' = 프로필이 있는 모든 정답, '동명제외' = 같은 이름 프로필이 2개 이상(profile_count>1)인 팀 제외.
--       프로필_있음 / 정답_건수 = 연차를 알 수 있는 비율. 연차 구간 열은 건수, 신인기준_통과율은 프로필 있는 건 중 비율.
-- 데이터 주의: 멜론 프로필이 83개뿐이라 일부 정답은 연차를 모른다. 현재 profile_count>1 인 팀이 없어 두 버전이 같다.
-- (BigQuery 문법으로 자동 변환: scripts/sql_to_bigquery.py — 원문은 sql/kr/ 의 같은 파일)
WITH newcomer_rule AS (
  SELECT
    3 AS max_years,
    10 AS max_albums
), base AS (
  SELECT
    o.program,
    o.artist_key,
    o.years_at_outcome,
    ap.album_count,
    COALESCE(ap.profile_count, 0) AS profile_count
  FROM core.v_outcome AS o
  LEFT JOIN core.v_artist_profile AS ap
    ON ap.artist_key = o.artist_key
  WHERE
    o.counted
), versioned AS (
  SELECT
    '전체' AS version,
    b.*
  FROM base AS b
  UNION ALL
  SELECT
    '동명제외',
    b.*
  FROM base AS b
  WHERE
    b.profile_count <= 1
)
SELECT
  v.version AS 버전,
  v.program AS 정답_프로그램,
  COUNT(*) AS 정답_건수,
  COUNT(v.years_at_outcome) AS 프로필_있음,
  ROUND(
    CAST(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY
      v.years_at_outcome NULLS LAST) AS NUMERIC),
    1
  ) AS 연차_중앙값,
  SUM(CASE WHEN v.years_at_outcome < 1 THEN 1 ELSE 0 END) AS `1년미만`,
  SUM(CASE WHEN v.years_at_outcome >= 1 AND v.years_at_outcome < 3 THEN 1 ELSE 0 END) AS `1_3년`,
  SUM(CASE WHEN v.years_at_outcome >= 3 AND v.years_at_outcome < 5 THEN 1 ELSE 0 END) AS `3_5년`,
  SUM(CASE WHEN v.years_at_outcome >= 5 THEN 1 ELSE 0 END) AS `5년이상`,
  ROUND(
    100.0 * SUM(
      CASE
        WHEN v.years_at_outcome <= r.max_years AND COALESCE(v.album_count, 0) <= r.max_albums
        THEN 1
        ELSE 0
      END
    ) / NULLIF(COUNT(v.years_at_outcome), 0),
    1
  ) AS 신인기준_통과율_pct
FROM versioned AS v
CROSS JOIN newcomer_rule AS r
GROUP BY
  버전,
  정답_프로그램
ORDER BY
  v.version DESC NULLS FIRST,
  정답_건수 DESC NULLS FIRST,
  v.program NULLS LAST;
