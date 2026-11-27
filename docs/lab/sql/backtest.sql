-- 백테스트: 기준일 {{cutoff}} 시점 점수로 상위 K팀을 뽑았다면 그중 몇 팀이 이후 정답을 받았나? (기준일 1개당 1번 실행)
-- 비교: 점수 / 공연 수만 / 갈래 수만 / 무작위(= 기준율 × K). 기준일 전에 이미 정답 받은 팀은 후보에서 뺀다.
-- 자리표시자: {{cutoff}} 'YYYY-MM-DD' · {{lookback_years}} · {{newcomer_years}} · {{exclude_famous}} true|false
--   {{outcome_tier}} 'any'|'final'|'mid' · {{horizon_months}} · {{genre}} '' 또는 장르 · {{branches}} ['공연','선정·지원',...]
--   {{w_branch}} {{w_stage}} {{w_peer}} {{w_dmz}} {{w_gigs}} {{w_outlets}} {{outlet_cap}} {{w_recent}} {{w_venues}} {{w_winner}} · {{k_list}} [20,50,100,200]
WITH scored AS (
    SELECT * FROM lab_scored(DATE {{cutoff}}, {{lookback_years}}, {{newcomer_years}}, {{exclude_famous}},
                             {{outcome_tier}}, {{horizon_months}}, {{genre}}, {{branches}},
                             {{w_branch}}, {{w_stage}}, {{w_peer}}, {{w_dmz}}, {{w_gigs}}, {{w_outlets}}, {{outlet_cap}},
                {{w_recent}}, {{w_venues}}, {{w_winner}}, {{w_context}})
    WHERE NOT had_outcome
),
ranked AS (                                     -- 동점은 팀 키 해시로 고정(매번 같은 결과)
    SELECT is_hit,
           ROW_NUMBER() OVER (ORDER BY score    DESC, md5(team_key)) AS r_score,
           ROW_NUMBER() OVER (ORDER BY gigs_1y  DESC, md5(team_key)) AS r_gigs,
           ROW_NUMBER() OVER (ORDER BY n_branch DESC, md5(team_key)) AS r_branch
    FROM scored
),
base AS (SELECT COUNT(*) AS pool_n, COALESCE(SUM(is_hit), 0) AS pool_hits FROM scored),
ks AS (SELECT UNNEST({{k_list}}) AS k),
res AS (
    SELECT k, '점수' AS method,     SUM(CASE WHEN r_score  <= k THEN is_hit ELSE 0 END) AS hits FROM ranked, ks GROUP BY k
    UNION ALL
    SELECT k, '공연 수만',          SUM(CASE WHEN r_gigs   <= k THEN is_hit ELSE 0 END) FROM ranked, ks GROUP BY k
    UNION ALL
    SELECT k, '갈래 수만',          SUM(CASE WHEN r_branch <= k THEN is_hit ELSE 0 END) FROM ranked, ks GROUP BY k
)
SELECT DATE {{cutoff}}                                                AS cutoff,
       res.k, res.method,
       COALESCE(res.hits, 0)                                          AS hits,
       ROUND(100.0 * COALESCE(res.hits, 0) / res.k, 1)                AS hit_rate,
       ROUND(1.0 * b.pool_hits / NULLIF(b.pool_n, 0) * res.k, 2)      AS random_expected,
       ROUND(COALESCE(res.hits, 0) / NULLIF(1.0 * b.pool_hits / b.pool_n * res.k, 0), 1) AS lift,
       b.pool_n, b.pool_hits
FROM res CROSS JOIN base b
ORDER BY res.k, res.method;
