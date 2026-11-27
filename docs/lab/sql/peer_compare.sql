-- 이웃 비교 (기준일 {{as_of}}) — 경쟁 서비스(Viberate)의 '커리어 건강도'를 우리 데이터로 옮긴 것. 문서: docs/peer_rising.md
-- 팀마다 '비슷한 처지'의 이웃 안에서 점수와 점수 항목이 몇 %인지, 위아래 5팀이 누구인지 보여 준다. 점수 계산은 바꾸지 않는다.
--
-- 이웃(비교군):
--   장르를 아는 팀   = 같은 발굴 단계 + 같은 장르(teams.primary_genre)            → peer_scope '단계+장르'
--   장르 빈칸·미분류 = 같은 발굴 단계 전체(장르를 아는 팀 포함)                    → peer_scope '단계'
--   (장르 오분류 위험: 장르를 모르는 팀을 억지로 한 장르에 넣지 않는다. 외부 장르 표기는 쓰지 않는다.)
-- 발굴 단계: discovery_stage.sql 과 같은 정의(0 백지 · 1 첫 신호 · 2 여러 갈래 · 3 선정·중간 정답 · 4 졸업),
--   tests/test_peer_rising.py 가 두 파일의 단계가 같은지 확인한다.
-- 대상 팀: 점수 v2(lab_scored, features.sql) 후보군 = 신인 + 기준일 전 신호 + 유명 제외(기준일 시점 규칙 그대로).
--
-- 등급(상위 몇 % = top_share): 탁월 ≤10% · 훌륭 ≤30% · 평균 ≤70% · 평균 이하 >70%.
--   top_share = 동점 구간의 '가운데' 순위 / 이웃 수 = (가장 좋은 공동 순위/n + 나 이상 점수 팀 비율)/2.
--   (1단계 팀은 신호 하나뿐이라 같은 점수가 수천 팀 — 공동 1등식으로 세면 대부분이 '훌륭'이 되어 버린다.)
--   이웃이 {{min_peers}}팀(기본 30) 미만이면 등급 대신 '비교군 작음'(백분위는 참고로 그대로 준다).
-- 백분위(*_pct, 0~1, 클수록 좋음) = 이웃 안 PERCENT_RANK. 동점은 같은 값(낮은 쪽) — 0점 동점이 좋아 보이지 않게.
-- 위아래 5팀: 이웃 안 점수 순서(동점은 md5(team_key)로 고정)에서 바로 위 5팀(neighbors_above, 마지막이 바로 위)·아래 5팀.
-- {{team}} = '' 이면 전체, 팀 키를 주면 그 팀 한 줄(이웃 계산은 전체 기준).
WITH params AS (SELECT DATE {{as_of}} AS d),
scored AS (
    SELECT team_key, display_name, primary_genre, score, pts_branch, pts_stage, pts_outlets, pts_venues,
           pts_winner, pts_context, gigs_1y
    FROM lab_scored(DATE {{as_of}}, {{lookback_years}}, {{newcomer_years}}, {{exclude_famous}},
                    'any', 1, '', {{branches}},
                    {{w_branch}}, {{w_stage}}, {{w_peer}}, {{w_dmz}}, {{w_gigs}}, {{w_outlets}}, {{outlet_cap}},
                    {{w_recent}}, {{w_venues}}, {{w_winner}}, {{w_context}}, {{w_collab}})
),
-- ↓ 발굴 단계: discovery_stage.sql 의 mention·ment·past_out·stage 와 같은 정의 (바꿀 땐 두 곳 같이)
mention AS (
    SELECT s.* FROM signals s, params p
    WHERE s.signal_date < p.d AND s.branch <> '발매'
      AND COALESCE(s.role, '') <> 'excluded' AND COALESCE(s.program, '') <> 'dmz_lineup'
),
ment AS (
    SELECT team_key, COUNT(DISTINCT branch) AS n_mention_branches,
           COALESCE(MAX(CASE WHEN branch = '선정·지원' THEN stage_rank END), 0) AS best_selection
    FROM mention GROUP BY team_key
),
past_out AS (
    SELECT o.team_key, MAX(CASE o.grade WHEN 'S' THEN 3 WHEN 'A' THEN 2 WHEN 'B' THEN 1 ELSE 0 END) AS best_grade_rank
    FROM outcomes o, params p
    WHERE o.counted AND o.announced_date < p.d
    GROUP BY o.team_key
),
base AS (
    SELECT sc.*, t.profile_status,
           CASE
               WHEN COALESCE(po.best_grade_rank, 0) >= 2
                 OR (p.d >= fame_known_from() AND COALESCE(t.profile_status, '') = 'famous') THEN 4
               WHEN COALESCE(po.best_grade_rank, 0) = 1 OR COALESCE(m.best_selection, 0) >= 3 THEN 3
               WHEN COALESCE(m.n_mention_branches, 0) >= 2 THEN 2
               WHEN COALESCE(m.n_mention_branches, 0) = 1 THEN 1
               ELSE 0
           END AS stage,
           CASE WHEN TRIM(COALESCE(sc.primary_genre, '')) IN ('', '미분류') THEN NULL
                ELSE TRIM(sc.primary_genre) END AS genre_key
    FROM scored sc
    JOIN teams t USING (team_key)
    CROSS JOIN params p
    LEFT JOIN ment m USING (team_key)
    LEFT JOIN past_out po USING (team_key)
),
-- ↑ 발굴 단계 끝
levels AS (                                     -- 비교군 두 층: 단계 전체(모든 팀) · 단계+장르(장르 아는 팀만)
    SELECT *, '단계' AS scope, CAST(stage AS VARCHAR) AS grp FROM base
    UNION ALL
    SELECT *, '단계+장르' AS scope, CAST(stage AS VARCHAR) || '|' || genre_key AS grp FROM base WHERE genre_key IS NOT NULL
),
ranked AS (
    SELECT *,
           COUNT(*) OVER (PARTITION BY scope, grp)                            AS peer_n,
           RANK() OVER (PARTITION BY scope, grp ORDER BY score DESC)          AS peer_rank,
           CUME_DIST() OVER (PARTITION BY scope, grp ORDER BY score DESC)     AS ge_share,   -- 나 이상 점수 팀 비율
           ROW_NUMBER() OVER (PARTITION BY scope, grp ORDER BY score DESC, md5(team_key)) AS rn,
           PERCENT_RANK() OVER (PARTITION BY scope, grp ORDER BY score)       AS score_pct,
           PERCENT_RANK() OVER (PARTITION BY scope, grp ORDER BY pts_branch)  AS branch_pct,
           PERCENT_RANK() OVER (PARTITION BY scope, grp ORDER BY pts_stage)   AS stage_pct,
           PERCENT_RANK() OVER (PARTITION BY scope, grp ORDER BY pts_outlets) AS outlets_pct,
           PERCENT_RANK() OVER (PARTITION BY scope, grp ORDER BY pts_venues)  AS venues_pct,
           PERCENT_RANK() OVER (PARTITION BY scope, grp ORDER BY pts_winner)  AS winner_pct,
           PERCENT_RANK() OVER (PARTITION BY scope, grp ORDER BY pts_context) AS context_pct,
           PERCENT_RANK() OVER (PARTITION BY scope, grp ORDER BY gigs_1y)     AS gigs_pct
    FROM levels
),
chosen AS (                                     -- 팀마다 쓸 층: 장르를 알면 단계+장르, 모르면 단계
    SELECT *, (peer_rank / peer_n + ge_share) / 2 AS top_share_raw FROM ranked
    WHERE scope = CASE WHEN genre_key IS NULL THEN '단계' ELSE '단계+장르' END
),
neigh AS (
    SELECT c.team_key,
           list(COALESCE(n.display_name, n.team_key) ORDER BY n.rn) FILTER (WHERE n.rn < c.rn) AS above,
           list(COALESCE(n.display_name, n.team_key) ORDER BY n.rn) FILTER (WHERE n.rn > c.rn) AS below
    FROM chosen c
    JOIN ranked n ON n.scope = c.scope AND n.grp = c.grp AND n.team_key <> c.team_key
                 AND n.rn BETWEEN c.rn - 5 AND c.rn + 5
    GROUP BY c.team_key
)
SELECT c.team_key, COALESCE(c.display_name, c.team_key) AS display_name, c.primary_genre, c.stage,
       CASE c.stage WHEN 0 THEN '백지' WHEN 1 THEN '첫 신호' WHEN 2 THEN '여러 갈래'
                    WHEN 3 THEN '선정·중간 정답' ELSE '졸업' END AS stage_label,
       c.scope AS peer_scope, c.peer_n, c.peer_rank,
       ROUND(c.top_share_raw, 3) AS top_share,
       CASE WHEN c.peer_n < {{min_peers}} THEN '비교군 작음'
            WHEN c.top_share_raw <= 0.10 THEN '탁월'
            WHEN c.top_share_raw <= 0.30 THEN '훌륭'
            WHEN c.top_share_raw <= 0.70 THEN '평균'
            ELSE '평균 이하' END AS grade,
       ROUND(c.score, 2) AS score, ROUND(c.score_pct, 3) AS score_pct,
       ROUND(c.branch_pct, 3) AS branch_pct, ROUND(c.stage_pct, 3) AS stage_pct,
       ROUND(c.outlets_pct, 3) AS outlets_pct, ROUND(c.venues_pct, 3) AS venues_pct,
       ROUND(c.winner_pct, 3) AS winner_pct, ROUND(c.context_pct, 3) AS context_pct, ROUND(c.gigs_pct, 3) AS gigs_pct,
       COALESCE(nb.above, []) AS neighbors_above, COALESCE(nb.below, []) AS neighbors_below
FROM chosen c
LEFT JOIN neigh nb USING (team_key)
WHERE {{team}} = '' OR c.team_key = {{team}}
ORDER BY c.stage DESC, c.score DESC, md5(c.team_key);
