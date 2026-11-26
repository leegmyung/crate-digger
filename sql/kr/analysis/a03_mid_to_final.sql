-- 질문: 중간 정답(mid) 프로그램마다, 받은 팀 중 그 뒤 최종 정답(final)까지 받은 팀은 몇 %인가?
-- 왜 중요한가: 중간 정답이 최종 정답의 '디딤돌'인지 알면, 중간 정답을 받은 팀을 다음 후보로 바로 올릴 수 있다.
--       같은 계열(예: 헬로루키 월간 → 헬로루키 올해의)은 한 대회 안의 승급이라 뺀다 (ref.outcome_same_family).
-- 읽는 법: 중간을 신호로 보므로 중간 날짜 = 기간 마지막 날(announced_end), 최종 날짜 = 기간 첫날(announced_start).
--       최종_전환율이 높을수록 좋은 디딤돌. 중간 정답이 2025~2026에만 있어 '뒤에 올 시간'이 짧다는 점에 주의.

WITH mid AS (                                        -- 팀 × 중간 프로그램 (가장 이른 날짜)
    SELECT program AS mid_program, artist_key, alias_key,
           MIN(COALESCE(announced_end, announced_start)) AS mid_date
    FROM core.v_outcome
    WHERE counted AND tier = 'mid'
    GROUP BY program, artist_key, alias_key
),
final_o AS (
    SELECT program AS final_program, artist_key, alias_key, announced_start AS final_date
    FROM core.v_outcome
    WHERE counted AND tier = 'final'
),
converted AS (                                       -- 중간 뒤에 (다른 계열) 최종을 받은 팀
    SELECT m.mid_program, m.artist_key,
           MIN(f.final_date - m.mid_date) AS days_to_final
    FROM mid m
    JOIN final_o f
      ON (m.artist_key = f.artist_key
          OR m.artist_key = f.alias_key
          OR m.alias_key  = f.artist_key)
     AND m.mid_date < f.final_date
    WHERE NOT EXISTS (
        SELECT 1 FROM ref.outcome_same_family fam
        WHERE fam.mid_program   = m.mid_program
          AND fam.final_program = f.final_program
    )
    GROUP BY m.mid_program, m.artist_key
)
SELECT m.mid_program                                       AS 중간_프로그램,
       COUNT(DISTINCT m.artist_key)                        AS 중간_팀수,
       COUNT(DISTINCT c.artist_key)                        AS 최종까지_팀수,
       ROUND(100.0 * COUNT(DISTINCT c.artist_key)
             / NULLIF(COUNT(DISTINCT m.artist_key), 0), 1) AS 최종_전환율_pct,
       ROUND(AVG(c.days_to_final) / 30.44, 1)              AS 평균_걸린_개월,
       MIN(m.mid_date)                                     AS 중간_첫날짜,
       MAX(m.mid_date)                                     AS 중간_끝날짜
FROM mid m
LEFT JOIN converted c
  ON c.mid_program = m.mid_program AND c.artist_key = m.artist_key
GROUP BY m.mid_program
ORDER BY 최종_전환율_pct DESC, 중간_팀수 DESC;
