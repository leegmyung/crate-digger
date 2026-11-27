-- 신호별 적중률: 기준일 {{cutoff}} 전 {{lookback_years}}년 안에 이 선정·지원 프로그램에 나온 후보 팀 중,
-- 기준일 뒤 {{horizon_months}}개월 안에 정답을 받은 비율. 기준선 = 아무 신호든 있던 후보 전체.
-- 신뢰구간은 윌슨 95% (표본이 작을 때도 0~100% 밖으로 안 나감). 팀 10곳 미만은 화면에서 흐리게.
WITH pool AS (
    SELECT team_key, is_hit
    FROM lab_scored(DATE {{cutoff}}, {{lookback_years}}, {{newcomer_years}}, {{exclude_famous}},
                    {{outcome_tier}}, {{horizon_months}}, {{genre}}, {{branches}}, 0, 0, 0, 0, 0, 0, 0)
    WHERE NOT had_outcome
),
prog AS (
    SELECT DISTINCT s.program, s.team_key
    FROM signals s
    WHERE s.branch = '선정·지원' AND s.program <> ''
      AND s.signal_date < DATE {{cutoff}}
      AND s.signal_date >= DATE {{cutoff}} - to_years(CAST({{lookback_years}} AS INTEGER))
),
base AS (SELECT COUNT(*) AS n, SUM(is_hit) AS k FROM pool),
per AS (
    SELECT p.program, COUNT(*) AS n, SUM(pl.is_hit) AS k
    FROM prog p JOIN pool pl USING (team_key)
    GROUP BY p.program
    UNION ALL
    SELECT '(기준선) 아무 신호', n, k FROM base
),
z AS (SELECT 1.96 AS z)
SELECT per.program,
       COALESCE(pr.label, per.program)                                         AS label,
       per.n                                                                    AS teams,
       per.k                                                                    AS hits,
       ROUND(100.0 * per.k / per.n, 1)                                          AS rate,
       ROUND(100.0 * ((per.k / per.n + z*z / (2*per.n))
             - z * SQRT(per.k / per.n * (1 - per.k / per.n) / per.n + z*z / (4*per.n*per.n)))
             / (1 + z*z / per.n), 1)                                            AS ci_low,
       ROUND(100.0 * ((per.k / per.n + z*z / (2*per.n))
             + z * SQRT(per.k / per.n * (1 - per.k / per.n) / per.n + z*z / (4*per.n*per.n)))
             / (1 + z*z / per.n), 1)                                            AS ci_high,
       ROUND((1.0 * per.k / per.n) / NULLIF(1.0 * b.k / b.n, 0), 1)             AS lift
FROM per CROSS JOIN base b CROSS JOIN z
LEFT JOIN programs pr ON pr.program = per.program
WHERE per.n > 0
ORDER BY (per.program LIKE '(기준선)%') DESC, rate DESC, teams DESC;
