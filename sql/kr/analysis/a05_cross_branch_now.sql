-- 질문: 최근 180일 안에 2개 이상 갈래(공연 / 선정·지원 / 발매 / 큐레이션)에 동시에 나온 팀은 누구인가?
-- 왜 중요한가: 여러 갈래에서 동시에 보이는 팀은 '움직이고 있는' 팀이다. 지금 시점의 발굴 후보 미리보기.
-- 읽는 법: 갈래_수가 많고 최근_날짜가 가까울수록 위. 이미_정답 = 이미 센 정답을 받은 팀(발굴 의미가 적음).
--       기준일은 오늘(CURRENT_DATE). 미래 날짜(예정 공연 등)는 뺀다. 같은 팀은 artist_key/alias_key로 묶는다.

WITH params AS (
    SELECT CURRENT_DATE AS as_of, CURRENT_DATE - 180 AS window_from
),
alias_map AS (                                       -- 별칭 키 → 대표 키 (예: samui → 사뮈)
    SELECT alias_key, MIN(artist_key) AS main_key
    FROM core.v_signal
    WHERE alias_key IS NOT NULL AND alias_key <> artist_key
    GROUP BY alias_key
),
recent AS (
    SELECT COALESCE(am.main_key, s.artist_key) AS team_key,
           s.artist_text, s.branch, s.signal_date
    FROM core.v_signal s
    CROSS JOIN params p
    LEFT JOIN alias_map am ON am.alias_key = s.artist_key
    WHERE s.signal_date >= p.window_from
      AND s.signal_date <= p.as_of
      AND s.artist_key IS NOT NULL AND s.artist_key <> ''
),
team AS (
    SELECT team_key,
           MIN(artist_text)                                   AS 표시_이름,
           COUNT(DISTINCT branch)                             AS 갈래_수,
           STRING_AGG(DISTINCT branch, ', ')                  AS 갈래_목록,
           COUNT(*)                                           AS 신호_건수,
           MAX(signal_date)                                   AS 최근_날짜
    FROM recent
    GROUP BY team_key
    HAVING COUNT(DISTINCT branch) >= 2
)
SELECT t.표시_이름, t.team_key AS 팀_키, t.갈래_수, t.갈래_목록, t.신호_건수, t.최근_날짜,
       CASE WHEN EXISTS (
           SELECT 1 FROM core.v_outcome_team o
           WHERE o.artist_key = t.team_key OR o.alias_key = t.team_key
       ) THEN 'Y' ELSE '' END                                 AS 이미_정답
FROM team t
ORDER BY t.갈래_수 DESC, t.최근_날짜 DESC, t.신호_건수 DESC
LIMIT 50;
