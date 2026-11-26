-- 질문: 정답(센 것)을 받은 팀은, 정답 몇 개월 전에 처음 우리 레이더(신호)에 잡혔나?
-- 왜 중요한가: 리드타임(미리 알아챈 기간)이 길수록 '남보다 먼저 발굴'했다는 뜻이다. 갈래별로 비교하면
--       어느 갈래가 가장 일찍 신호를 주는지 알 수 있다.
-- 읽는 법: 갈래 = 그 갈래의 첫 신호 기준, '(전체)' = 갈래 무관 가장 이른 신호. 중앙값_개월 = 절반의 팀이 이보다 일찍 잡힘.
--       6/12/24개월_이상_pct = 그만큼 미리 잡힌 팀 비율. 신호는 2020-01-01 이후 · 정답 날짜보다 앞선 것만,
--       정답과 같은 프로그램 계열의 선정 신호(ref.same_program)는 뺀다.
-- 데이터 주의: 발매·큐레이션은 2026-11 수집분뿐이라 정답보다 앞선 신호가 거의 없다(사실상 공연·선정 비교).

WITH params AS (
    SELECT DATE '2025-01-01' AS outcome_from,
           DATE '2020-01-01' AS lookback_from
),
outcome_team AS (                                    -- 팀별 첫 정답 (2025년 이후)
    SELECT t.artist_key, t.alias_key, t.first_program, t.first_outcome_date
    FROM core.v_outcome_team t
    CROSS JOIN params p
    WHERE t.first_outcome_date >= p.outcome_from
),
first_signal AS (                                    -- 팀 × 갈래별 정답 전 첫 신호
    SELECT ot.artist_key, s.branch, ot.first_outcome_date,
           MIN(s.signal_date) AS first_signal_date
    FROM outcome_team ot
    CROSS JOIN params p
    JOIN core.v_signal s
      ON (s.artist_key = ot.artist_key
          OR s.artist_key = ot.alias_key
          OR s.alias_key  = ot.artist_key)
     AND s.signal_date <  ot.first_outcome_date
     AND s.signal_date >= p.lookback_from
    WHERE NOT EXISTS (
        SELECT 1 FROM ref.same_program sp
        WHERE sp.selection_program = s.program
          AND sp.outcome_program   = ot.first_program
    )
    GROUP BY ot.artist_key, s.branch, ot.first_outcome_date
),
lead AS (                                            -- 갈래별 + 갈래 무관(전체) 리드타임(개월)
    SELECT branch, artist_key,
           (first_outcome_date - first_signal_date) / 30.44 AS lead_months
    FROM first_signal
    UNION ALL
    SELECT '(전체)', artist_key,
           (MAX(first_outcome_date) - MIN(first_signal_date)) / 30.44
    FROM first_signal
    GROUP BY artist_key
)
SELECT l.branch                                                       AS 갈래,
       COUNT(*)                                                       AS 팀수,
       (SELECT COUNT(*) FROM outcome_team)                            AS 정답_팀_전체,
       ROUND(CAST(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY l.lead_months) AS numeric), 1) AS 중앙값_개월,
       ROUND(CAST(MIN(l.lead_months) AS numeric), 1)                  AS 최소_개월,
       ROUND(CAST(MAX(l.lead_months) AS numeric), 1)                  AS 최대_개월,
       ROUND(100.0 * SUM(CASE WHEN l.lead_months >= 6  THEN 1 ELSE 0 END) / COUNT(*), 1) AS "6개월_이상_pct",
       ROUND(100.0 * SUM(CASE WHEN l.lead_months >= 12 THEN 1 ELSE 0 END) / COUNT(*), 1) AS "12개월_이상_pct",
       ROUND(100.0 * SUM(CASE WHEN l.lead_months >= 24 THEN 1 ELSE 0 END) / COUNT(*), 1) AS "24개월_이상_pct"
FROM lead l
GROUP BY l.branch
ORDER BY CASE WHEN l.branch = '(전체)' THEN 0 ELSE 1 END, 팀수 DESC;
