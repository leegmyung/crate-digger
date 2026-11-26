-- 질문: 선정·지원 프로그램(신호)마다, 2020~2024년(정답 기간 전 5년)에 뽑힌 팀 중
--       2025년 이후 '센 정답'(counted 정답)을 받은 팀은 몇 %인가?
-- 왜 중요한가: 어느 선정·지원 프로그램이 나중 성공을 미리 알려주는 '좋은 신호'인지 고르는 기준이 된다.
--       같은 프로그램 계열(예: 예선 → 본선)은 사실상 같은 대회라 정답에서 뺀다 (ref.same_program).
-- 읽는 법: 맨 아래 '(기준선)' 줄은 같은 기간 아무 갈래에서든 신호가 있던 모든 팀의 적중률. 이보다 높아야 의미 있다.
--       신호_팀수 = 분모, 정답_팀수 = 신호 날짜 뒤에 정답을 받은 팀. 적중률이 높을수록 좋은 신호.
--       분모가 작으면(10팀 미만) 우연일 수 있으니 숫자보다 '0인지 아닌지' 정도로 본다.

WITH params AS (
    SELECT DATE '2025-01-01' AS outcome_from,
           DATE '2020-01-01' AS lookback_from          -- 정답 기간 시작 5년 전
),
sel_signal AS (                                       -- 기간 안 선정·지원 신호 (팀 × 프로그램, 가장 이른 날짜)
    SELECT s.program, s.artist_key, s.alias_key, MIN(s.signal_date) AS signal_date
    FROM core.v_signal s
    CROSS JOIN params p
    WHERE s.branch = '선정·지원'
      AND s.signal_date >= p.lookback_from
      AND s.signal_date <  p.outcome_from
    GROUP BY s.program, s.artist_key, s.alias_key
),
outcome AS (                                          -- 예측 대상 정답 (센 것만)
    SELECT o.program AS outcome_program, o.artist_key, o.alias_key, o.announced_start
    FROM core.v_outcome o
    CROSS JOIN params p
    WHERE o.counted
      AND o.announced_start >= p.outcome_from
),
any_signal AS (                                       -- 기준선: 기간 안 아무 갈래 신호 (팀별 가장 이른 날짜)
    SELECT s.artist_key, s.alias_key, MIN(s.signal_date) AS signal_date
    FROM core.v_signal s
    CROSS JOIN params p
    WHERE s.signal_date >= p.lookback_from
      AND s.signal_date <  p.outcome_from
    GROUP BY s.artist_key, s.alias_key
),
baseline AS (
    SELECT COUNT(DISTINCT a.artist_key) AS signal_teams,
           COUNT(DISTINCT CASE WHEN EXISTS (
               SELECT 1 FROM outcome oc
               WHERE (a.artist_key = oc.artist_key OR a.artist_key = oc.alias_key OR a.alias_key = oc.artist_key)
                 AND a.signal_date < oc.announced_start) THEN a.artist_key END) AS hit_teams
    FROM any_signal a
),
hit AS (                                              -- 신호 뒤에 정답이 온 팀 (같은 프로그램 계열 제외)
    SELECT DISTINCT ss.program, ss.artist_key
    FROM sel_signal ss
    JOIN outcome oc
      ON (ss.artist_key = oc.artist_key
          OR ss.artist_key = oc.alias_key
          OR ss.alias_key  = oc.artist_key)
     AND ss.signal_date < oc.announced_start
    WHERE NOT EXISTS (
        SELECT 1 FROM ref.same_program sp
        WHERE sp.selection_program = ss.program
          AND sp.outcome_program   = oc.outcome_program
    )
),
by_program AS (
    SELECT ss.program                                        AS 선정지원_프로그램,
           COUNT(DISTINCT ss.artist_key)                     AS 신호_팀수,
           COUNT(DISTINCT h.artist_key)                      AS 정답_팀수,
           0                                                 AS sort_group
    FROM sel_signal ss
    LEFT JOIN hit h
      ON h.program = ss.program AND h.artist_key = ss.artist_key
    GROUP BY ss.program
    UNION ALL
    SELECT '(기준선: 모든 신호 팀)', signal_teams, hit_teams, 1
    FROM baseline
)
SELECT 선정지원_프로그램, 신호_팀수, 정답_팀수,
       ROUND(100.0 * 정답_팀수 / NULLIF(신호_팀수, 0), 1) AS 적중률_pct
FROM by_program
ORDER BY sort_group, 적중률_pct DESC, 신호_팀수 DESC;
