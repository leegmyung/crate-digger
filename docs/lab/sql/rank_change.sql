-- 순위 변화 (기준일 {{as_of}}) — 경쟁 서비스(Viberate)의 '순위 옆 지난달 대비 ▲▼'를 우리 점수 스냅샷으로 옮긴 것. 문서: docs/peer_rising.md
-- 표: snapshots(snap_date, team_key, score, rank) = docs/lab/data/snapshots/<날짜>.csv 모음(매일 상위 300팀, scripts/lab_snapshot.py)
--     team_cities(team_key, home_city …) = 팀별 활동 도시(scripts/city_profiles.py) — 없으면 빈 표(지역 안 순위 NULL)
--
-- 비교 시점: 지금 = 기준일 이전(같은 날 포함) 가장 최근 스냅샷, 지난주 = 지금보다 7일 이상 앞선 가장 최근 스냅샷,
--   지난달 = 30일 이상 앞선 가장 최근 스냅샷. 해당 스냅샷이 없으면 그 칸은 비어 있다.
-- 변화 = 그때 순위 − 지금 순위 (양수 = 올라감). 표시: ▲n · ▼n · –(그대로) · NEW(그때 상위 300 밖).
-- 잡음 처리: 점수가 그대로인데(차이 < 0.005) 순위만 움직였으면 = 다른 팀이 오르내려서 밀린 것 → 변화 NULL, 표시 ''(안 보여 줌).
-- 장르 안 순위: teams.primary_genre 가 빈칸·미분류면 NULL. 지역 안 순위: team_cities.home_city 가 없으면 NULL.
--   그때의 장르·지역 안 순위도 '지금'의 장르·도시로 묶어 계산한다(같은 무리끼리 비교).
WITH params AS (SELECT DATE {{as_of}} AS d),
dates AS (
    SELECT MAX(snap_date) AS now_date FROM snapshots, params p WHERE snap_date <= p.d
),
dates2 AS (
    SELECT dt.now_date,
           (SELECT MAX(snap_date) FROM snapshots WHERE snap_date <= dt.now_date - 7)  AS week_date,
           (SELECT MAX(snap_date) FROM snapshots WHERE snap_date <= dt.now_date - 30) AS month_date
    FROM dates dt WHERE dt.now_date IS NOT NULL
),
grp AS (                                        -- 팀의 장르·도시 (지금 기준)
    SELECT t.team_key,
           CASE WHEN TRIM(COALESCE(t.primary_genre, '')) IN ('', '미분류') THEN NULL ELSE TRIM(t.primary_genre) END AS genre_key,
           NULLIF(TRIM(COALESCE(tc.home_city, '')), '') AS city
    FROM teams t LEFT JOIN team_cities tc USING (team_key)
),
snap AS (                                       -- 세 시점 스냅샷 + 장르·지역 안 순위
    SELECT s.snap_date, s.team_key, s.score, s.rank, g.genre_key, g.city,
           CASE WHEN g.genre_key IS NOT NULL THEN RANK() OVER (PARTITION BY s.snap_date, g.genre_key ORDER BY s.score DESC) END AS genre_rank,
           CASE WHEN g.genre_key IS NOT NULL THEN COUNT(*) OVER (PARTITION BY s.snap_date, g.genre_key) END AS genre_n,
           CASE WHEN g.city IS NOT NULL THEN RANK() OVER (PARTITION BY s.snap_date, g.city ORDER BY s.score DESC) END AS city_rank,
           CASE WHEN g.city IS NOT NULL THEN COUNT(*) OVER (PARTITION BY s.snap_date, g.city) END AS city_n
    FROM snapshots s
    JOIN dates2 d2 ON s.snap_date IN (d2.now_date, d2.week_date, d2.month_date)
    LEFT JOIN grp g USING (team_key)
),
joined AS (
    SELECT n.*, d2.week_date, d2.month_date,
           w.rank AS w_rank, w.score AS w_score, w.genre_rank AS w_genre_rank, w.city_rank AS w_city_rank,
           m.rank AS m_rank, m.score AS m_score, m.genre_rank AS m_genre_rank, m.city_rank AS m_city_rank
    FROM dates2 d2
    JOIN snap n ON n.snap_date = d2.now_date
    LEFT JOIN snap w ON w.snap_date = d2.week_date AND w.team_key = n.team_key
    LEFT JOIN snap m ON m.snap_date = d2.month_date AND m.team_key = n.team_key
),
changes AS (                                    -- 점수 그대로면(동점 이동) 변화 NULL
    SELECT *,
           CASE WHEN w_rank IS NOT NULL AND ABS(score - w_score) >= 0.005 THEN w_rank - rank END               AS week_change,
           CASE WHEN m_rank IS NOT NULL AND ABS(score - m_score) >= 0.005 THEN m_rank - rank END               AS month_change,
           CASE WHEN w_genre_rank IS NOT NULL AND ABS(score - w_score) >= 0.005 THEN w_genre_rank - genre_rank END AS genre_week_change,
           CASE WHEN m_genre_rank IS NOT NULL AND ABS(score - m_score) >= 0.005 THEN m_genre_rank - genre_rank END AS genre_month_change,
           CASE WHEN w_city_rank IS NOT NULL AND ABS(score - w_score) >= 0.005 THEN w_city_rank - city_rank END  AS city_week_change,
           CASE WHEN m_city_rank IS NOT NULL AND ABS(score - m_score) >= 0.005 THEN m_city_rank - city_rank END  AS city_month_change
    FROM joined
)
SELECT c.team_key, COALESCE(t.display_name, c.team_key) AS display_name, c.snap_date, c.score, c.rank,
       c.week_date, c.week_change,
       CASE WHEN c.week_date IS NULL THEN '' WHEN c.w_rank IS NULL THEN 'NEW' WHEN c.week_change IS NULL THEN ''
            WHEN c.week_change > 0 THEN '▲' || c.week_change WHEN c.week_change < 0 THEN '▼' || (-c.week_change)
            ELSE '–' END AS week_label,
       c.month_date, c.month_change,
       CASE WHEN c.month_date IS NULL THEN '' WHEN c.m_rank IS NULL THEN 'NEW' WHEN c.month_change IS NULL THEN ''
            WHEN c.month_change > 0 THEN '▲' || c.month_change WHEN c.month_change < 0 THEN '▼' || (-c.month_change)
            ELSE '–' END AS month_label,
       c.genre_key AS genre, c.genre_rank, c.genre_n, c.genre_week_change, c.genre_month_change,
       c.city, c.city_rank, c.city_n, c.city_week_change, c.city_month_change
FROM changes c
LEFT JOIN teams t USING (team_key)
ORDER BY c.rank, c.team_key;
