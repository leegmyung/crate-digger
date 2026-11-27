-- 질문: 손으로 정한 점수 v0로 '그때 기준' 상위 K팀을 뽑았다면, 그중 몇 팀이 나중에 실제로 정답(신인상·주요 신인 프로그램)을 받았나? 무작위·단순 기준보다 나은가?
-- 왜 중요한가: 점수가 쓸모 있으려면 '미래를 모르는 상태'에서 뽑은 상위 목록이 무작위보다 정답을 많이 담아야 한다(백테스트).
-- 읽는 법: 기준일(cutoff) 전 3년 신호만으로 점수를 매기고, 기준일 뒤 정답으로 채점한다. 적중률 = 상위 K팀 중 정답 팀 비율,
--       배수 = 적중률 ÷ 기준율(후보 전체의 정답 비율 = 무작위로 K팀 뽑았을 때 기대값). 배수가 1보다 크면 무작위보다 낫다.
--       비교 방법: '점수 v0' / '공연 수만' / '갈래 수만' / '무작위'(기준율 × K).
-- 점수 v0 (가중치는 데이터에 맞춰 조정하지 않은 손 규칙 — 과적합 방지, PROJECT.md 점수 규칙 후보 그대로):
--       2 × (갈래 수 − 1) + 선정 최고 단계(STAGE_RANK 0~4) + 1 × 선정 팀과 같은 무대 + 0.5 × DMZ 출연
--       + 0.5 × ln(1 + 직전 1년 공연 수) + 1 × min(큐레이션 매체 수, 3)
-- 데이터 주의: 정답이 모두 2025년 이후라 '중간 정답 보유'·'이미 정답 팀과 같은 무대' 신호는 기준일 전에 생길 수 없어
--       '선정(selected 이상) 팀과 같은 무대'로 대신했다. 발매 갈래는 2026-11 이후만 있어 백테스트에 안 쓴다.
--       신인 대용: 멜론 프로필이 대부분 없어서 '우리 데이터에 처음 나온 지 3년 이내' 팀만 후보로 둔다(없으면 이센스·9와숫자들 같은
--       기성 팀이 DMZ·큐레이션 덕에 상위를 차지함). DMZ 출연은 선정 단계에서 빼고 0.5 가점으로만 센다.
--       유명 팀 제외는 지금의 멜론 프로필 기준이라 약간의 미래 정보가 섞인다(프로필 없는 팀은 그대로 둔다).
-- 팀 묶기: core 뷰의 team_key (아티스트 연결표 ref.artist_xref, 없으면 괄호 별칭). 유명 팀 판정도 team_key로 찾는다
--       (영문 키로 저장된 프로필 — 예: xdinaryheroes — 도 한글 팀 이름에 붙도록).
--       기준일 뒤 관찰 기간이 2026-11까지로 짧아(17~23개월) 나중에 정답을 받을 팀이 '틀림'으로 세어질 수 있다.

WITH params AS (
    SELECT DATE '2025-01-01' AS cutoff UNION ALL
    SELECT DATE '2025-07-01'
),
sig AS (                                              -- 기준일 전 3년 신호, 팀 키 통일
    SELECT p.cutoff, s.team_key,                     -- 팀 대표 키 (core 뷰: 연결표 → 괄호 별칭)
           s.branch, s.program, s.stage_rank, s.signal_date, s.detail
    FROM core.v_signal s
    JOIN params p ON s.signal_date <  p.cutoff
                 AND s.signal_date >= p.cutoff - INTERVAL '3 years'
    WHERE s.artist_key IS NOT NULL AND s.artist_key <> ''
),
outcome AS (                                          -- 센 정답, 팀 키 통일
    SELECT o.team_key, MIN(o.announced_start) AS first_outcome
    FROM core.v_outcome o
    WHERE o.counted
    GROUP BY 1
),
selected_team AS (                                    -- 선정(selected 이상)된 팀과 그 날짜
    SELECT cutoff, team_key, MIN(signal_date) AS selected_on
    FROM sig WHERE branch = '선정·지원' AND stage_rank >= 3
    GROUP BY 1, 2
),
gig AS (
    SELECT DISTINCT cutoff, team_key, signal_date AS gig_date, detail AS venue
    FROM sig WHERE branch = '공연' AND COALESCE(detail, '') NOT IN ('', '공연장 미정')
),
peer AS (                                             -- 공연 당시 이미 선정된 다른 팀과 같은 날·같은 공연장에 섬
    SELECT DISTINCT a.cutoff, a.team_key
    FROM gig a
    JOIN gig b ON b.cutoff = a.cutoff AND b.gig_date = a.gig_date AND b.venue = a.venue AND b.team_key <> a.team_key
    JOIN selected_team st ON st.cutoff = b.cutoff AND st.team_key = b.team_key AND st.selected_on <= a.gig_date
),
feat AS (
    SELECT s.cutoff, s.team_key,
           COUNT(DISTINCT s.branch)                                                        AS n_branch,
           COALESCE(MAX(CASE WHEN s.program <> 'dmz_lineup' THEN s.stage_rank END), 0)     AS best_stage,   -- DMZ는 아래 가점으로만
           MAX(CASE WHEN s.program = 'dmz_lineup' THEN 1 ELSE 0 END)                       AS dmz,
           COUNT(DISTINCT CASE WHEN s.branch = '공연' AND s.signal_date >= s.cutoff - INTERVAL '1 year'
                               THEN s.signal_date END)                                     AS gigs_1y,
           COUNT(DISTINCT CASE WHEN s.branch = '큐레이션' THEN s.program END)               AS outlets
    FROM sig s
    GROUP BY s.cutoff, s.team_key
),
first_seen AS (                                       -- 우리 데이터 전체에서 팀이 처음 나온 날 (상상마당 공연은 2010~)
    SELECT s.team_key, MIN(s.signal_date) AS first_seen
    FROM core.v_signal s
    WHERE s.artist_key IS NOT NULL AND s.artist_key <> ''
    GROUP BY 1
),
pool AS (                                             -- 후보: 기준일 전에 정답 없음, 유명 팀 아님, 처음 나온 지 3년 이내(신인 대용)
    SELECT f.*,
           CASE WHEN pe.team_key IS NOT NULL THEN 1 ELSE 0 END AS peer_selected,
           CASE WHEN o.first_outcome >= f.cutoff THEN 1 ELSE 0 END AS is_hit
    FROM feat f
    LEFT JOIN peer pe ON pe.cutoff = f.cutoff AND pe.team_key = f.team_key
    LEFT JOIN outcome o ON o.team_key = f.team_key
    JOIN first_seen fs ON fs.team_key = f.team_key
    WHERE fs.first_seen >= f.cutoff - INTERVAL '3 years'
      AND (o.first_outcome IS NULL OR o.first_outcome >= f.cutoff)
      AND NOT EXISTS (SELECT 1 FROM core.v_artist_status st             -- 유명 팀 제외 (팀 대표 키로, 프로필 중 하나라도 유명이면)
                      WHERE st.team_key = f.team_key AND st.status = 'famous')
),
scored AS (
    SELECT p.*,
           2 * (n_branch - 1) + best_stage + peer_selected + 0.5 * dmz
           + 0.5 * LN(1 + gigs_1y) + LEAST(outlets, 3)                                     AS score_v0
    FROM pool p
),
ranked AS (                                           -- 동점은 팀 키 해시로 고정(매번 같은 결과)
    SELECT cutoff, is_hit,
           ROW_NUMBER() OVER (PARTITION BY cutoff ORDER BY score_v0 DESC, MD5(team_key)) AS r_score,
           ROW_NUMBER() OVER (PARTITION BY cutoff ORDER BY gigs_1y  DESC, MD5(team_key)) AS r_gigs,
           ROW_NUMBER() OVER (PARTITION BY cutoff ORDER BY n_branch DESC, MD5(team_key)) AS r_branch
    FROM scored
),
base AS (
    SELECT cutoff, COUNT(*) AS pool_n, SUM(is_hit) AS pool_hits, 1.0 * SUM(is_hit) / COUNT(*) AS base_rate
    FROM scored GROUP BY cutoff
),
ks AS (SELECT 20 AS k UNION ALL SELECT 50 UNION ALL SELECT 100 UNION ALL SELECT 200),
result AS (
    SELECT r.cutoff, ks.k, '점수 v0' AS method, SUM(CASE WHEN r.r_score  <= ks.k THEN r.is_hit ELSE 0 END) AS hits
    FROM ranked r CROSS JOIN ks GROUP BY 1, 2
    UNION ALL
    SELECT r.cutoff, ks.k, '공연 수만', SUM(CASE WHEN r.r_gigs   <= ks.k THEN r.is_hit ELSE 0 END)
    FROM ranked r CROSS JOIN ks GROUP BY 1, 2
    UNION ALL
    SELECT r.cutoff, ks.k, '갈래 수만', SUM(CASE WHEN r.r_branch <= ks.k THEN r.is_hit ELSE 0 END)
    FROM ranked r CROSS JOIN ks GROUP BY 1, 2
)
SELECT res.cutoff                                         AS 기준일,
       b.pool_n                                           AS 후보_팀수,
       b.pool_hits                                        AS 이후_정답_팀수,
       res.k                                              AS 상위_k,
       res.method                                         AS 방법,
       res.hits                                           AS 맞힌_팀수,
       ROUND(100.0 * res.hits / res.k, 1)                 AS 적중률_pct,
       ROUND(b.base_rate * res.k, 1)                      AS 무작위_기대_팀수,
       ROUND(res.hits / NULLIF(b.base_rate * res.k, 0), 1) AS 무작위_대비_배수
FROM result res
JOIN base b ON b.cutoff = res.cutoff
ORDER BY res.cutoff, res.k, res.method;
