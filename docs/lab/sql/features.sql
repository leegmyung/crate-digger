-- 랩 공통 계산식 (DuckDB). 페이지가 처음 열릴 때 한 번 실행해서 매크로 lab_scored(...)를 만든다.
-- 표: signals(team_key, branch, source, program, stage_rank, signal_date, venue)
--     teams(team_key, display_name, first_seen, first_release, fan_count, album_count, profile_status, primary_genre)
--     outcomes(team_key, program, program_label, tier, announced_date, counted)
--
-- lab_scored(기준일, 신호 보는 기간(년), 신인 기준(첫 등장 N년), 유명 팀 제외, 정답 종류, 관찰 기간(개월), 장르, 갈래 목록,
--            가중치 6개, 큐레이션 매체 상한, 추가 가중치 3개(최근 활동·공연장 다양성·수상 팀과 같은 무대))
--   → 기준일 시점의 후보 팀 1팀 = 1행: 특징·점수 구성·점수, is_hit(기준일 뒤 관찰 기간 안에 정답), had_outcome(기준일 전 정답)
-- 점수 = w_branch×(갈래 수−1) + w_stage×선정 최고 단계(DMZ 제외, 0~4) + w_peer×이미 선정된 팀과 같은 날·같은 공연장
--      + w_dmz×DMZ 출연 + w_gigs×ln(1+직전 1년 공연 일수) + w_outlets×min(큐레이션 매체 수, 상한)
--      + w_recent×ln(1+직전 180일 신호 수) + w_venues×ln(1+서로 다른 공연장 수)
--      + w_winner×(공연 당시 이미 정답을 받은 팀과 같은 날·같은 공연장)   ← 2021~ 정답이 있어 쓸 수 있음
-- 신호 역할: signals.role = discovery 만 점수에 쓴다 (맥락·제외·검증 대기 출처 분류는 config/source_roles.json).
-- 시점 누수 방지: 신호는 기준일 '전'만, 정답은 기준일 '이후'만. 선정 날짜는 기간의 마지막 날로 저장돼 있어 보수적.

CREATE OR REPLACE MACRO lab_scored(cutoff, lookback_years, newcomer_years, exclude_famous, outcome_tier,
                                   horizon_months, genre, branches,
                                   w_branch, w_stage, w_peer, w_dmz, w_gigs, w_outlets, outlet_cap,
                                   w_recent := 0, w_venues := 0, w_winner := 0, w_context := 0) AS TABLE   -- 안 넘기면 0
WITH sig_all AS (                               -- 발굴 + 맥락 신호 (제외·검증 대기 출처는 빼고, config/source_roles.json)
    SELECT * FROM signals
    WHERE role IN ('discovery', 'context')
      AND signal_date < cutoff
      AND signal_date >= cutoff - to_years(CAST(lookback_years AS INTEGER))
      AND list_contains(branches, branch)
),
sig AS (SELECT * FROM sig_all WHERE role = 'discovery'),   -- 점수 특징은 발굴 신호로만
context_cnt AS (                                -- 맥락 매체(기준선 이하 큰 매거진) 수: 약한 가중치로 따로 (차등)
    SELECT team_key, COUNT(DISTINCT program) AS context_outlets
    FROM sig_all WHERE role = 'context' AND branch = '큐레이션' GROUP BY team_key
),
selected AS (                                   -- 선정(selected 이상) 팀과 처음 선정된 날
    SELECT team_key, MIN(signal_date) AS selected_on
    FROM sig WHERE branch = '선정·지원' AND stage_rank >= 3
    GROUP BY team_key
),
gig AS (
    SELECT DISTINCT team_key, signal_date AS gig_date, venue
    FROM sig WHERE branch = '공연' AND COALESCE(venue, '') NOT IN ('', '공연장 미정')
),
peer AS (                                       -- 공연 당시 이미 선정된 다른 팀과 같은 무대
    SELECT DISTINCT a.team_key
    FROM gig a
    JOIN gig b ON b.gig_date = a.gig_date AND b.venue = a.venue AND b.team_key <> a.team_key
    JOIN selected st ON st.team_key = b.team_key AND st.selected_on <= a.gig_date
),
winner_first AS (                               -- 정답 팀과 첫 정답일 (기준일 전 것만 의미 있음)
    SELECT team_key, MIN(announced_date) AS first_outcome FROM outcomes
    WHERE counted AND announced_date < cutoff GROUP BY team_key
),
peer_winner AS (                                -- 공연 당시 이미 정답을 받은 다른 팀과 같은 무대
    SELECT DISTINCT a.team_key
    FROM gig a
    JOIN gig b ON b.gig_date = a.gig_date AND b.venue = a.venue AND b.team_key <> a.team_key
    JOIN winner_first wf ON wf.team_key = b.team_key AND wf.first_outcome <= a.gig_date
),
feat AS (
    SELECT team_key,
           COUNT(DISTINCT branch)                                                         AS n_branch,
           COALESCE(MAX(CASE WHEN program <> 'dmz_lineup' THEN stage_rank END), 0)        AS best_stage,
           MAX(CASE WHEN program = 'dmz_lineup' THEN 1 ELSE 0 END)                        AS dmz,
           COUNT(DISTINCT CASE WHEN branch = '공연' AND signal_date >= cutoff - INTERVAL 1 YEAR
                               THEN signal_date END)                                      AS gigs_1y,
           COUNT(DISTINCT CASE WHEN branch = '큐레이션' THEN program END)                  AS outlets,
           COUNT(CASE WHEN signal_date >= cutoff - INTERVAL 180 DAY THEN 1 END)          AS recent180,
           COUNT(DISTINCT CASE WHEN branch = '공연' AND COALESCE(venue, '') NOT IN ('', '공연장 미정')
                               THEN venue END)                                            AS venues,
           MAX(signal_date)                                                               AS last_seen
    FROM sig GROUP BY team_key
),
feat_all AS (                                   -- 맥락 매체에만 나온 팀도 후보군에 남긴다 (특징은 0)
    SELECT k.team_key, COALESCE(f.n_branch, 1) AS n_branch, COALESCE(f.best_stage, 0) AS best_stage,
           COALESCE(f.dmz, 0) AS dmz, COALESCE(f.gigs_1y, 0) AS gigs_1y, COALESCE(f.outlets, 0) AS outlets,
           COALESCE(f.recent180, 0) AS recent180, COALESCE(f.venues, 0) AS venues,
           COALESCE(f.last_seen, k.last_seen) AS last_seen, COALESCE(cc.context_outlets, 0) AS context_outlets
    FROM (SELECT team_key, MAX(signal_date) AS last_seen FROM sig_all GROUP BY team_key) k
    LEFT JOIN feat f USING (team_key)
    LEFT JOIN context_cnt cc USING (team_key)
),
outcome_ok AS (                                 -- 센 정답만, 정답 종류 필터
    SELECT team_key, announced_date, weight FROM outcomes
    WHERE counted AND (outcome_tier = 'any' OR tier = outcome_tier)
),
before_cut AS (                                 -- 기준일 전에 이미 받은 정답(어떤 종류든)
    SELECT DISTINCT team_key FROM outcomes WHERE counted AND announced_date < cutoff
),
after_cut AS (                                  -- 기준일 뒤 정답 + 가장 높은 등급 가중치(S=3, A=2, B=1)
    SELECT team_key, MAX(weight) AS hit_weight FROM outcome_ok
    WHERE announced_date >= cutoff
      AND announced_date < cutoff + to_months(CAST(horizon_months AS INTEGER))
    GROUP BY team_key
),
pool AS (
    SELECT f.*, t.display_name, t.first_seen, t.primary_genre, t.profile_status,
           CASE WHEN pe.team_key IS NOT NULL THEN 1 ELSE 0 END                            AS peer_selected,
           CASE WHEN pw.team_key IS NOT NULL THEN 1 ELSE 0 END                            AS peer_winner,
           CASE WHEN ac.team_key IS NOT NULL THEN 1 ELSE 0 END                            AS is_hit,
           COALESCE(ac.hit_weight, 0)                                                     AS hit_weight,
           bc.team_key IS NOT NULL                                                        AS had_outcome
    FROM feat_all f
    JOIN teams t USING (team_key)
    LEFT JOIN peer pe USING (team_key)
    LEFT JOIN peer_winner pw USING (team_key)
    LEFT JOIN after_cut ac USING (team_key)
    LEFT JOIN before_cut bc USING (team_key)
    WHERE t.first_seen >= cutoff - to_years(CAST(newcomer_years AS INTEGER))
      AND (NOT exclude_famous OR t.profile_status <> 'famous')
      AND (genre = '' OR t.primary_genre = genre)
)
SELECT *,
       w_branch  * (n_branch - 1)                AS pts_branch,
       w_stage   * best_stage                    AS pts_stage,
       w_peer    * peer_selected                 AS pts_peer,
       w_dmz     * dmz                           AS pts_dmz,
       w_gigs    * LN(1 + gigs_1y)               AS pts_gigs,
       w_outlets * LEAST(outlets, outlet_cap)    AS pts_outlets,
       w_recent  * LN(1 + recent180)             AS pts_recent,
       w_venues  * LN(1 + venues)                AS pts_venues,
       w_winner  * peer_winner                   AS pts_winner,
       w_context * LEAST(context_outlets, outlet_cap) AS pts_context,
       w_branch * (n_branch - 1) + w_stage * best_stage + w_peer * peer_selected + w_dmz * dmz
       + w_gigs * LN(1 + gigs_1y) + w_outlets * LEAST(outlets, outlet_cap)
       + w_recent * LN(1 + recent180) + w_venues * LN(1 + venues) + w_winner * peer_winner
       + w_context * LEAST(context_outlets, outlet_cap) AS score
FROM pool;
