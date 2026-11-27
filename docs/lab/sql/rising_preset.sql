-- '떠오르는 팀' 프리셋 (기준일 {{as_of}}) — 경쟁 서비스(Viberate)의 'Rising on ○○' 추천 차트를 우리 데이터로 옮긴 것.
-- Viberate 의 실제 조건 = (이미 큰 팀 빼기) × (체급 상한) × (짧은 기간의 증가). 문서: docs/peer_rising.md
--
-- 조건 (모두 기준일 '전' 정보만):
--   ① 신인: 우리 신인 규칙 그대로(features.sql lab_scored 와 같음) — "프로필 첫 발매일이 있으면 그 날, 없으면 우리 데이터 첫 등장일이
--      기준일 전 {{newcomer_years}}년 안인 팀". 그리고 기준일에 이미 알려진 팀(기준일 전 신호가 있거나 첫 발매일이 기준일 전).
--   ② 유명 제외: profile_status = famous 는 '지금' 팬 수로 정한 것이라 fame_known_from()(2026-11-26) 이후 기준일에만 뺀다({{exclude_famous}}).
--   ③ 체급 상한: 기준일 전 공연 중 가장 큰 공연장 체급(venue_tiers: S ~150 · M ~400 · L ~1,000 · XL 1,001~)이 {{max_tier}} 이하.
--      체급을 아는 공연장에 선 적이 없으면 통과(모름 ≠ 큼). 수용 인원은 '지금' 값이지만 공연장 크기는 잘 안 바뀐다고 본다.
--      멜론 팬 수 상한 {{max_fans}}: 팬 수도 '지금' 값이라 fame_known_from() 이후 기준일에만 쓴다(팬 수 모름은 통과).
--   ④ 이미 센 정답을 받은 팀 제외({{only_no_outcome}}).
--   ⑤ 증가: 최근 {{window_days}}일 '남의 언급' 수(recent_n) ≥ {{min_recent}} 이고, 그 전 {{window_days}}일(prev_n)보다 많음.
--      '남의 언급' = discovery_stage.sql 과 같은 정의(발매 갈래·제외 출처·DMZ 라인업 빼고, 맥락·검증 대기 출처는 셈).
-- 정렬: 증가 폭 growth = ln(1+recent_n) − ln(1+prev_n) 큰 순 → 최근 언급 수 → 점수 v2.
-- 프리셋 예: 30일(기본, 최근 한 달 사이 갑자기 다뤄지기 시작한 팀) · 90일(window_days=90, 한 분기 동안 꾸준히 늘어난 팀).
WITH params AS (SELECT DATE {{as_of}} AS d, CAST({{window_days}} AS INTEGER) AS w),
tier_rank AS (SELECT * FROM (VALUES ('S', 1), ('M', 2), ('L', 3), ('XL', 4)) AS t(tier, r)),
known AS (                                      -- ① 신인 + 기준일에 알려진 팀
    SELECT t.team_key, COALESCE(t.display_name, t.team_key) AS display_name, t.primary_genre,
           t.first_release, t.first_seen, t.fan_count, t.profile_status,
           CASE WHEN t.first_release IS NOT NULL THEN '첫 발매' ELSE '첫 등장' END AS newcomer_basis
    FROM teams t, params p
    WHERE COALESCE(t.first_release, t.first_seen) >= p.d - to_years(CAST({{newcomer_years}} AS INTEGER))
      AND (t.first_release <= p.d
           OR EXISTS (SELECT 1 FROM signals s WHERE s.team_key = t.team_key AND s.signal_date < p.d
                                                 AND COALESCE(s.role, '') <> 'excluded'))
),
mention AS (                                    -- 기준일 전 '남의 언급' (discovery_stage.sql 과 같은 정의)
    SELECT s.* FROM signals s, params p
    WHERE s.signal_date < p.d AND s.branch <> '발매'
      AND COALESCE(s.role, '') <> 'excluded' AND COALESCE(s.program, '') <> 'dmz_lineup'
),
growth AS (                                     -- ⑤ 최근 창 대 그 전 창
    SELECT m.team_key,
           COUNT(CASE WHEN m.signal_date >= p.d - p.w THEN 1 END)                                    AS recent_n,
           COUNT(CASE WHEN m.signal_date < p.d - p.w AND m.signal_date >= p.d - 2 * p.w THEN 1 END)  AS prev_n,
           COUNT(DISTINCT CASE WHEN m.signal_date >= p.d - p.w THEN m.branch END)                    AS recent_branches,
           MAX(m.signal_date)                                                                         AS last_mention
    FROM mention m, params p
    GROUP BY m.team_key
),
max_venue AS (                                  -- ③ 기준일 전 공연의 가장 큰 체급
    SELECT s.team_key, MAX(tr.r) AS max_r
    FROM signals s
    JOIN venue_tiers vt ON vt.venue = s.venue
    JOIN tier_rank tr ON tr.tier = vt.tier
    CROSS JOIN params p
    WHERE s.branch = '공연' AND s.signal_date < p.d AND COALESCE(s.role, '') <> 'excluded'
    GROUP BY s.team_key
),
had_out AS (                                    -- ④ 기준일 전 센 정답
    SELECT DISTINCT o.team_key FROM outcomes o, params p WHERE o.counted AND o.announced_date < p.d
),
scored AS (                                     -- 점수 v2 (정렬 보조·표시용, 후보군 제한 없이)
    SELECT team_key, score
    FROM lab_scored(DATE {{as_of}}, {{lookback_years}}, 50, false, 'any', 1, '', {{branches}},
                    {{w_branch}}, {{w_stage}}, {{w_peer}}, {{w_dmz}}, {{w_gigs}}, {{w_outlets}}, {{outlet_cap}},
                    {{w_recent}}, {{w_venues}}, {{w_winner}}, {{w_context}}, {{w_collab}})
)
SELECT k.team_key, k.display_name, k.primary_genre, k.first_release, k.first_seen, k.newcomer_basis,
       p.w AS window_days, g.recent_n, g.prev_n, g.recent_branches,
       ROUND(LN(1 + g.recent_n) - LN(1 + g.prev_n), 3) AS growth,
       (SELECT tier FROM tier_rank WHERE r = mv.max_r) AS max_tier,
       CASE WHEN p.d >= fame_known_from() THEN k.fan_count END AS fan_count_used,
       ROUND(sc.score, 2) AS score, g.last_mention
FROM known k
CROSS JOIN params p
JOIN growth g USING (team_key)
LEFT JOIN max_venue mv USING (team_key)
LEFT JOIN had_out ho USING (team_key)
LEFT JOIN scored sc USING (team_key)
WHERE g.recent_n >= {{min_recent}} AND g.recent_n > g.prev_n
  AND NOT ({{exclude_famous}} AND p.d >= fame_known_from() AND COALESCE(k.profile_status, '') = 'famous')
  AND (mv.max_r IS NULL OR mv.max_r <= (SELECT r FROM tier_rank WHERE tier = {{max_tier}}))
  AND (p.d < fame_known_from() OR k.fan_count IS NULL OR k.fan_count <= {{max_fans}})
  AND NOT ({{only_no_outcome}} AND ho.team_key IS NOT NULL)
ORDER BY growth DESC, g.recent_n DESC, sc.score DESC NULLS LAST, k.team_key;
