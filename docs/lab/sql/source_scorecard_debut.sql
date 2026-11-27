-- 데뷔 코호트 성적표: 과거 이력 없는 '백지 신인'이 첫 발매를 낸 뒤, 어느 출처가 {{mention_months}}개월 안에 먼저 언급했나
-- → 그 팀이 기준일 뒤 {{horizon_months}}개월 안에 정답을 받았나. (출처 성적표 source_scorecard.sql 의 '데뷔 시점' 버전)
--
-- 코호트(기준일 {{cutoffs}}마다): teams.first_release 가 [기준일 − (N+6)개월, 기준일 − N개월) 안이고 (N = {{mention_months}}),
--   첫 발매 '이전' 신호가 하나도 없고(백지), 유명 팀이 아니고, 기준일 전에 정답을 받지 않은 팀.
--   → 언급 창 [첫 발매, 첫 발매 + N개월)이 늘 기준일 전에 끝나서 미래 정보가 섞이지 않는다.
--   → 기준일을 6개월 간격으로 두면 한 팀이 두 기준일에 겹쳐 들어가지 않는다(N=6 이면 '기준일 전 1년 안 첫 발매').
-- 출처별: 언급한 코호트 팀 수(teams)·그중 정답(hits)·적중률·배수(코호트 전체 기준율 대비)·
--   첫 발매에서 첫 언급까지 일수 중앙값(median_days)·그 팀을 가장 먼저 언급한 출처였던 횟수(first_mention, 같은 날이면 모두).
-- '(언급 없음)' 줄 = 창 안에서 어느 출처에도 안 나온 코호트 팀. 신호 역할과 상관없이 모든 출처를 센다. 정답은 센 정답(counted)만.
-- 한계: first_release 는 멜론·스포티파이 프로필이 있는 팀에만 있다(프로필은 정답 팀 위주로 모았음 → 기준율이 높게 나옴).
WITH cuts AS (SELECT * FROM (VALUES {{cutoffs}}) t(c)),
cohort AS (
    SELECT c.c, t.team_key, t.first_release,
           MAX(CASE WHEN o.announced_date >= c.c
                     AND o.announced_date < c.c + to_months({{horizon_months}}) THEN 1 ELSE 0 END) AS is_hit
    FROM cuts c
    JOIN teams t ON t.first_release >= c.c - to_months({{mention_months}} + 6)
                AND t.first_release <  c.c - to_months({{mention_months}})
    LEFT JOIN outcomes o ON o.team_key = t.team_key AND o.counted
    WHERE COALESCE(t.profile_status, '') <> 'famous'
      AND NOT EXISTS (SELECT 1 FROM signals s WHERE s.team_key = t.team_key AND s.signal_date < t.first_release)
      AND NOT EXISTS (SELECT 1 FROM outcomes b WHERE b.team_key = t.team_key AND b.counted AND b.announced_date < c.c)
    GROUP BY c.c, t.team_key, t.first_release
),
keyed AS (
    SELECT team_key, signal_date, role,
           branch || ':' || CASE WHEN branch = '선정·지원' THEN program ELSE source END AS src
    FROM signals
),
mention AS (                                    -- 코호트 팀 × 출처: 언급 창 안의 첫 언급일
    SELECT co.c, co.team_key, k.src, MIN(k.signal_date) AS d,
           ANY_VALUE(co.first_release) AS fr, ANY_VALUE(co.is_hit) AS is_hit
    FROM cohort co
    JOIN keyed k ON k.team_key = co.team_key
                AND k.signal_date >= co.first_release
                AND k.signal_date <  co.first_release + to_months({{mention_months}})
    GROUP BY co.c, co.team_key, k.src
),
first_m AS (SELECT c, team_key, MIN(d) AS d FROM mention GROUP BY c, team_key),
base AS (SELECT COUNT(*) AS n, SUM(is_hit) AS hits FROM cohort),
per_src AS (
    SELECT m.src, COUNT(*) AS teams, SUM(m.is_hit) AS hits,
           MEDIAN(DATE_DIFF('day', m.fr, m.d)) AS median_days,
           SUM(CASE WHEN m.d = f.d THEN 1 ELSE 0 END) AS first_mention
    FROM mention m JOIN first_m f USING (c, team_key)
    GROUP BY m.src
),
unmentioned AS (
    SELECT '(언급 없음)' AS src, COUNT(*) AS teams, SUM(is_hit) AS hits,
           CAST(NULL AS DOUBLE) AS median_days, CAST(NULL AS BIGINT) AS first_mention
    FROM cohort co
    WHERE NOT EXISTS (SELECT 1 FROM mention m WHERE m.c = co.c AND m.team_key = co.team_key)
),
roles AS (SELECT src, ANY_VALUE(role) AS role FROM keyed GROUP BY src)
SELECT x.src, r.role, x.teams, COALESCE(x.hits, 0) AS hits,
       ROUND(100.0 * x.hits / NULLIF(x.teams, 0), 2) AS rate,
       ROUND((1.0 * x.hits / NULLIF(x.teams, 0)) / NULLIF(1.0 * b.hits / NULLIF(b.n, 0), 0), 1) AS lift,
       ROUND(100.0 * b.hits / NULLIF(b.n, 0), 2) AS base_rate,
       b.n AS cohort_teams, COALESCE(b.hits, 0) AS cohort_hits,
       x.median_days, x.first_mention
FROM (SELECT * FROM per_src UNION ALL SELECT * FROM unmentioned) x
LEFT JOIN roles r USING (src)
CROSS JOIN base b
ORDER BY (x.src = '(언급 없음)'), x.teams DESC, x.src;
