-- 출처 성적표: 출처(갈래·출처, 선정은 프로그램)마다 '나중에 상 받을 팀을 먼저, 정확하게 짚었나'.
-- 적중률 = 기준일 {{cutoffs}} 전 3년 안에 이 출처 신호가 있던 후보 팀 중, 기준일 뒤 {{horizon_months}}개월 안에 정답 받은 비율(기준일 합산).
-- 수상 팀 = {{since}} 이후 첫 정답을 받은 팀: 정답 전에 이 출처에 나온 팀 수 / 가장 먼저 잡은 팀 수 / 이 출처만 잡은 팀 수 / 선행 개월(중앙값).
-- 현재 역할(role)은 config/source_roles.json 분류. 판정 힌트: 적중률이 기준선 이하이고 유일 기여가 없으면 '맥락'으로 내릴 후보.
-- '같은 집안' 정답(config same_house: 그 출처와 같은 주최·매체가 준 정답)은 그 출처의 적중·수상 팀으로 세지 않는다.
-- 정답은 센 정답(counted)만, 등급 무관. 후보 기준은 신인 3년·유명 팀 제외(점수와 같음)이되, 신호 역할과 상관없이 모든 출처의 팀을 센다.
WITH cuts AS (SELECT * FROM (VALUES {{cutoffs}}) t(c)),
pool AS (                                       -- 후보군: 역할과 상관없이 기준일 전 3년 안에 신호가 있던 팀 (출처를 공정하게 재려고
    SELECT c.c, t.team_key,                     --   점수용 lab_scored(발굴 신호만)가 아니라 따로 계산), 신인 3년·유명 팀 제외·이미 정답 팀 제외
           MAX(CASE WHEN o.announced_date >= c.c
                     AND o.announced_date < c.c + to_months({{horizon_months}}) THEN 1 ELSE 0 END) AS is_hit
    FROM cuts c
    JOIN signals s ON s.signal_date < c.c AND s.signal_date >= c.c - INTERVAL 3 YEAR
    JOIN teams t ON t.team_key = s.team_key
    LEFT JOIN outcomes o ON o.team_key = t.team_key AND o.counted
    WHERE t.first_seen >= c.c - INTERVAL 3 YEAR AND (c.c < fame_known_from() OR t.profile_status <> 'famous')   -- 유명 판정은 지금 팬 수라 과거 기준일엔 안 씀
      AND NOT EXISTS (SELECT 1 FROM outcomes b WHERE b.team_key = t.team_key AND b.counted AND b.announced_date < c.c)
    GROUP BY c.c, t.team_key
),
keyed AS (
    SELECT team_key, signal_date, role,
           branch || ':' || CASE WHEN branch = '선정·지원' THEN program ELSE source END AS src
    FROM signals
),
src_pool AS (
    SELECT DISTINCT c.c, k.team_key, k.src
    FROM cuts c JOIN keyed k ON k.signal_date < c.c AND k.signal_date >= c.c - INTERVAL 3 YEAR
),
base AS (SELECT 1.0 * SUM(is_hit) / COUNT(*) AS rate FROM pool),
precision AS (
    SELECT sp.src, COUNT(*) AS teams,
           SUM(CASE WHEN EXISTS (SELECT 1 FROM outcomes o
                                 WHERE o.team_key = sp.team_key AND o.counted
                                   AND o.announced_date >= sp.c AND o.announced_date < sp.c + to_months({{horizon_months}})
                                   AND NOT list_contains(string_split(COALESCE(o.same_house_sources, ''), ';'), sp.src))
                    THEN 1 ELSE 0 END) AS hits
    FROM src_pool sp JOIN pool p USING (c, team_key)
    GROUP BY sp.src
),
win AS (
    SELECT team_key, MIN(announced_date) AS fo FROM outcomes WHERE counted
    GROUP BY team_key HAVING MIN(announced_date) >= DATE {{since}}
),
first_src AS (
    SELECT k.team_key, k.src, MIN(k.signal_date) AS d, ANY_VALUE(w.fo) AS fo
    FROM win w JOIN keyed k USING (team_key) WHERE k.signal_date < w.fo
      AND EXISTS (SELECT 1 FROM outcomes o WHERE o.team_key = k.team_key AND o.counted AND o.announced_date = w.fo
                    AND NOT list_contains(string_split(COALESCE(o.same_house_sources, ''), ';'), k.src))
    GROUP BY k.team_key, k.src
),
earliest AS (SELECT team_key, MIN(d) AS d, COUNT(*) AS n_src FROM first_src GROUP BY team_key),
coverage AS (
    SELECT f.src, COUNT(*) AS winners_seen,
           SUM(CASE WHEN f.d = e.d THEN 1 ELSE 0 END) AS first_to_see,
           SUM(CASE WHEN e.n_src = 1 THEN 1 ELSE 0 END) AS only_source,
           MEDIAN(DATE_DIFF('month', f.d, f.fo)) AS median_lead_months
    FROM first_src f JOIN earliest e USING (team_key)
    GROUP BY f.src
),
roles AS (SELECT src, ANY_VALUE(role) AS role, COUNT(*) AS signal_rows, MIN(signal_date) AS since_date
          FROM keyed GROUP BY src)
SELECT r.src, r.role, r.signal_rows, r.since_date,
       COALESCE(p.teams, 0) AS teams, COALESCE(p.hits, 0) AS hits,
       ROUND(100.0 * p.hits / NULLIF(p.teams, 0), 2) AS rate,
       ROUND((1.0 * p.hits / NULLIF(p.teams, 0)) / NULLIF(b.rate, 0), 1) AS lift,
       ROUND(100.0 * b.rate, 2) AS base_rate,
       COALESCE(cv.winners_seen, 0) AS winners_seen, COALESCE(cv.first_to_see, 0) AS first_to_see,
       COALESCE(cv.only_source, 0) AS only_source, ROUND(cv.median_lead_months, 1) AS median_lead_months
FROM roles r
LEFT JOIN precision p USING (src)
LEFT JOIN coverage cv USING (src)
CROSS JOIN base b
ORDER BY COALESCE(cv.winners_seen, 0) DESC, rate DESC NULLS LAST;
