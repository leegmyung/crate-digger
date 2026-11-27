-- 무엇을 찾나: (A) HTML 특수문자 코드(&amp; &#39; 등)가 그대로 남은 이름, (B) 인스타그램 계정명처럼 보이는 이름(소문자·숫자·_·. 만, 공백·한글 없음).
-- 왜 문제인가: "a&amp;b" 와 "a&b", "@band_official" 과 "밴드" 는 다른 키가 되어 같은 팀인데 이어지지 않는다.
-- 결과를 보고 할 일: (A)는 적재 전에 HTML 디코딩을 넣고, (B)는 계정명→팀 이름 매핑표(ref)를 만들어 키를 바꾼다.
-- (BigQuery 문법으로 자동 변환: scripts/sql_to_bigquery.py — 원문은 sql/kr/ 의 같은 파일)
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
), flagged AS (
  SELECT
    tbl,
    artist_text,
    CASE
      WHEN REGEXP_CONTAINS(artist_text, '&(#[0-9]+|#x[0-9a-fA-F]+|[a-zA-Z]+);')
      THEN 'A: HTML 엔티티'
      WHEN REGEXP_CONTAINS(artist_text, '^@?[a-z0-9._]+$')
      AND REGEXP_CONTAINS(artist_text, '[._]' /* 계정명 특징: _ 또는 . 포함 */)
      AND REGEXP_CONTAINS(artist_text, '[a-z]')
      THEN 'B: 인스타 계정명 모양'
    END AS issue,
    COUNT(*) AS rows_n
  FROM all_names
  WHERE
    artist_text IS NOT NULL
  GROUP BY
    tbl,
    artist_text
)
SELECT
  issue,
  tbl,
  artist_text,
  rows_n
FROM flagged
WHERE
  issue IS NOT NULL
ORDER BY
  issue NULLS LAST,
  rows_n DESC NULLS FIRST,
  tbl NULLS LAST,
  artist_text NULLS LAST;
