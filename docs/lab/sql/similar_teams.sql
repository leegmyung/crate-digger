-- 비슷한 팀: {{team_key}}와 닮은 팀을 유사도 %로 (Chartmetric 'similar artists'를 우리 데이터로). {{as_of}} = DATE '...' 기준일.
-- 정답(outcomes)은 쓰지 않는다 — 수상 여부로 비슷함을 매기면 '이미 뜬 팀 찾기'가 되고 검증이 새기 때문.
-- 네 가지를 0~1로 재서 가중합(합 1.0):
--   같은 무대 0.40  같은 날·같은 공연장에 함께 선 횟수, 3번이면 꽉 참
--   같은 출처 0.25  공연 말고 이름이 나온 곳(선정 프로그램·매체·큐레이터)의 자카드(겹친 수 ÷ 합친 수)
--   같은 장르 0.20  확인된 장르(멜론 프로필·보도)가 같으면 1 — 추정·리뷰 장르는 분석에 안 씀(peer_compare.sql 과 같은 규칙)
--   비슷한 체급 0.15  첫 신호 시기(1년 안 1, 2년 안 0.5)와 신호 갈래 수 차이(1 − 차이/3)의 평균
-- 후보 = 같은 무대나 같은 출처가 하나라도 있는 팀. 제외(excluded) 역할 신호와 기준일 뒤 신호는 세지 않는다.
-- {{sim_limit}} = 최대 행 수(앱 12). f_stage·f_source·f_level 은 0~1 원재료 — 가중치 검증(scripts/similar_validate.py, docs/similar_teams.md)용.
WITH params AS (
    SELECT {{team_key}} AS me, {{as_of}} AS as_of
),
sig AS (
    SELECT s.team_key, s.branch, s.source, s.program, s.signal_date, s.venue
    FROM signals s, params p
    WHERE s.signal_date <= p.as_of AND COALESCE(s.role, '') <> 'excluded'
),
gig AS (
    SELECT DISTINCT team_key, signal_date, venue
    FROM sig
    WHERE branch = '공연' AND COALESCE(venue, '') NOT IN ('', '공연장 미정')
),
src AS (
    SELECT DISTINCT team_key, COALESCE(NULLIF(program, ''), source) AS src
    FROM sig
    WHERE branch <> '공연' AND COALESCE(NULLIF(program, ''), source, '') <> ''
),
stage_share AS (
    SELECT b.team_key AS other, COUNT(*) AS shared_stages, MAX(a.signal_date) AS last_shared
    FROM gig a
    JOIN gig b ON b.signal_date = a.signal_date AND b.venue = a.venue AND b.team_key <> a.team_key
    JOIN params p ON a.team_key = p.me
    GROUP BY b.team_key
),
my_src AS (
    SELECT s.src FROM src s JOIN params p ON s.team_key = p.me
),
src_share AS (
    SELECT o.team_key AS other, COUNT(*) AS shared_sources, STRING_AGG(o.src, ' · ' ORDER BY o.src) AS source_names
    FROM src o
    JOIN my_src m ON m.src = o.src
    JOIN params p ON o.team_key <> p.me
    GROUP BY o.team_key
),
src_count AS (
    SELECT team_key, COUNT(*) AS n_src FROM src GROUP BY team_key
),
lvl AS (
    SELECT team_key, MIN(signal_date) AS first_sig, COUNT(DISTINCT branch) AS n_branch FROM sig GROUP BY team_key
),
gen AS (
    SELECT team_key,
           CASE WHEN COALESCE(primary_genre, '') NOT IN ('', '미분류')
                 AND COALESCE(genre_confidence, '') IN ('', 'profile', 'press') THEN primary_genre END AS g
    FROM teams
),
cand AS (
    SELECT other FROM stage_share UNION SELECT other FROM src_share
),
feat AS (
    SELECT c.other,
           COALESCE(ss.shared_stages, 0) AS shared_stages,
           ss.last_shared,
           COALESCE(sr.shared_sources, 0) AS shared_sources,
           COALESCE(sr.source_names, '') AS source_names,
           LEAST(COALESCE(ss.shared_stages, 0) / 3.0, 1.0) AS f_stage,
           COALESCE(COALESCE(sr.shared_sources, 0)
                    / NULLIF(COALESCE(mc.n_src, 0) + COALESCE(oc.n_src, 0) - COALESCE(sr.shared_sources, 0), 0), 0) AS f_source,
           COALESCE(gm.g IS NOT NULL AND gm.g = go.g, false) AS same_genre,
           (CASE WHEN ABS(DATE_DIFF('day', lm.first_sig, lo.first_sig)) <= 365 THEN 1.0
                 WHEN ABS(DATE_DIFF('day', lm.first_sig, lo.first_sig)) <= 730 THEN 0.5 ELSE 0.0 END
            + GREATEST(0.0, 1.0 - ABS(lm.n_branch - lo.n_branch) / 3.0)) / 2.0 AS f_level
    FROM cand c
    CROSS JOIN params p
    LEFT JOIN stage_share ss ON ss.other = c.other
    LEFT JOIN src_share sr ON sr.other = c.other
    LEFT JOIN src_count mc ON mc.team_key = p.me
    LEFT JOIN src_count oc ON oc.team_key = c.other
    LEFT JOIN gen gm ON gm.team_key = p.me
    LEFT JOIN gen go ON go.team_key = c.other
    LEFT JOIN lvl lm ON lm.team_key = p.me
    LEFT JOIN lvl lo ON lo.team_key = c.other
)
SELECT f.other AS related_team,
       COALESCE(t.display_name, f.other) AS display_name,
       t.primary_genre,
       t.profile_status,
       CAST(ROUND(100 * (0.40 * f.f_stage + 0.25 * f.f_source + 0.20 * CASE WHEN f.same_genre THEN 1 ELSE 0 END
                         + 0.15 * COALESCE(f.f_level, 0))) AS INTEGER) AS sim_pct,
       CAST(ROUND(100 * 0.40 * f.f_stage) AS INTEGER) AS part_stage,
       CAST(ROUND(100 * 0.25 * f.f_source) AS INTEGER) AS part_source,
       CASE WHEN f.same_genre THEN 20 ELSE 0 END AS part_genre,
       CAST(ROUND(100 * 0.15 * COALESCE(f.f_level, 0)) AS INTEGER) AS part_level,
       f.shared_stages, f.last_shared, f.shared_sources, f.source_names, f.same_genre,
       ROUND(f.f_stage, 4) AS f_stage, ROUND(f.f_source, 4) AS f_source, ROUND(COALESCE(f.f_level, 0), 4) AS f_level
FROM feat f
LEFT JOIN teams t ON t.team_key = f.other
ORDER BY sim_pct DESC, f.shared_stages DESC, f.shared_sources DESC, f.other
LIMIT {{sim_limit}};
