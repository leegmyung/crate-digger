-- 질문: 2024년에 공연한 팀 기준으로, 어느 공연장의 출연 팀이 2025년 이후 센 정답을 가장 많이 받았나? (상위 15곳)
-- 왜 중요한가: 될성부른 팀을 먼저 세우는 '안목 있는 공연장'을 찾으면, 그 공연장 라인업 자체가 좋은 신호가 된다.
-- 읽는 법: 출연_팀수(최소 20팀) 중 정답_팀수 비율. 기준선_pct(2024년 공연한 모든 팀의 비율)보다 몇 배 높은지(배수)를 본다.
--       공연장 이름은 주소 괄호를 뗀 이름. 빈 값·'공연장 미정'은 뺀다. 정답 팀이 1~2팀만 달라져도 순위가 바뀌니 주의.

WITH params AS (
    SELECT DATE '2024-01-01' AS gig_from, DATE '2024-12-31' AS gig_to,
           DATE '2025-01-01' AS outcome_from, 20 AS min_teams
),
gig_2024 AS (                                        -- 공연장 × 팀 (2024년)
    SELECT DISTINCT
           TRIM(split_part(g.venue_text, ' (', 1)) AS venue,
           COALESCE(tm.team_key, g.artist_key) AS team_key   -- 팀 대표 키
    FROM raw.raw_kr_gig g
    CROSS JOIN params p
    LEFT JOIN core.v_team_map tm ON tm.variant_key = g.artist_key
    WHERE g.gig_date BETWEEN p.gig_from AND p.gig_to
      AND g.artist_key IS NOT NULL AND g.artist_key <> ''
),
gig_clean AS (
    SELECT * FROM gig_2024
    WHERE venue <> '' AND venue <> '공연장 미정'
),
outcome AS (
    SELECT o.team_key
    FROM core.v_outcome o
    CROSS JOIN params p
    WHERE o.counted AND o.announced_start >= p.outcome_from   -- 2024 공연은 항상 2025+ 정답보다 앞선다
),
team_hit AS (                                        -- 팀별 정답 여부 (같은 팀 규칙)
    SELECT t.team_key,
           MAX(CASE WHEN oc.team_key IS NOT NULL THEN 1 ELSE 0 END) AS is_hit
    FROM (SELECT DISTINCT team_key FROM gig_2024) t
    LEFT JOIN outcome oc ON oc.team_key = t.team_key
    GROUP BY t.team_key
),
baseline AS (
    SELECT 100.0 * SUM(is_hit) / COUNT(*) AS base_pct FROM team_hit
),
venue_stat AS (
    SELECT gc.venue,
           COUNT(DISTINCT gc.team_key)                                      AS team_cnt,
           COUNT(DISTINCT CASE WHEN th.is_hit = 1 THEN gc.team_key END)     AS hit_cnt
    FROM gig_clean gc
    JOIN team_hit th ON th.team_key = gc.team_key
    GROUP BY gc.venue
    HAVING COUNT(DISTINCT gc.team_key) >= (SELECT min_teams FROM params)   -- 순위 매기기 전에 거른다
)
SELECT RANK() OVER (ORDER BY 1.0 * v.hit_cnt / v.team_cnt DESC)  AS 순위,
       v.venue                                                    AS 공연장,
       v.team_cnt                                                 AS 출연_팀수,
       v.hit_cnt                                                  AS 정답_팀수,
       ROUND(100.0 * v.hit_cnt / v.team_cnt, 1)                   AS 정답_비율_pct,
       ROUND(CAST(b.base_pct AS numeric), 1)                      AS 기준선_pct,
       ROUND(CAST(100.0 * v.hit_cnt / v.team_cnt / NULLIF(b.base_pct, 0) AS numeric), 1) AS 배수
FROM venue_stat v
CROSS JOIN baseline b
ORDER BY 1.0 * v.hit_cnt / v.team_cnt DESC, v.team_cnt DESC
LIMIT 15;
