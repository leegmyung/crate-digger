-- 갓 데뷔 후보: 기준일 {{as_of}} 전 12개월 안에 첫 발매를 냈고, 첫 발매 '이전' 신호가 하나도 없는 백지 신인.
-- 앱 '후보 > 갓 데뷔'(docs/app/db.js queryDebutCandidates)와 같은 정의 — 주간 엑셀 보고서(scripts/export_excel.py)가 lab_sql 로 돌린다.
-- 백지 판정은 데뷔 코호트 성적표(source_scorecard_debut.sql)와 같다: 첫 발매 전 신호 없음, 유명 팀 제외(exclude_famous),
-- 기준일 전 정답 받은 팀 제외(only_no_outcome). 점수는 점수 v2(lab_scored, features.sql)를 상위 제한 없이 붙인다(신호가 없으면 NULL).
-- 한 줄 = 팀 × 언급 출처 (첫 발매 뒤 ~ 기준일 사이 신호). 언급이 없는 팀은 src 가 NULL 인 한 줄.
WITH blank AS (
    SELECT t.team_key, COALESCE(t.display_name, t.team_key) AS display_name, t.primary_genre,
           t.first_release, t.profile_status,
           EXISTS (SELECT 1 FROM outcomes o
                   WHERE o.team_key = t.team_key AND o.counted AND o.announced_date < DATE {{as_of}}) AS had_outcome
    FROM teams t
    WHERE t.first_release IS NOT NULL
      AND t.first_release >= DATE {{as_of}} - to_months(12)
      AND t.first_release <= DATE {{as_of}}
      AND NOT ({{exclude_famous}} AND COALESCE(t.profile_status, '') = 'famous')
      AND ({{genre}} = '' OR t.primary_genre = {{genre}})
      AND NOT EXISTS (SELECT 1 FROM signals s WHERE s.team_key = t.team_key AND s.signal_date < t.first_release)
),
filtered AS (SELECT * FROM blank WHERE NOT ({{only_no_outcome}} AND had_outcome)),
scored AS (
    SELECT team_key, ROUND(score, 2) AS score
    FROM lab_scored(DATE {{as_of}}, {{lookback_years}}, 50, false, 'any', 1, '', {{branches}},
                    {{w_branch}}, {{w_stage}}, {{w_peer}}, {{w_dmz}}, {{w_gigs}}, {{w_outlets}}, {{outlet_cap}},
                    {{w_recent}}, {{w_venues}}, {{w_winner}}, {{w_context}}, {{w_collab}})
),
post_mentions AS (
    SELECT f.team_key,
           s.branch || ':' || CASE WHEN s.branch = '선정·지원' THEN s.program ELSE s.source END AS src,
           ANY_VALUE(s.role) AS role,
           MIN(s.signal_date) AS first_mention_date,
           DATE_DIFF('day', f.first_release, MIN(s.signal_date))::INT AS days_to_mention,
           COUNT(*)::INT AS mention_cnt
    FROM filtered f
    JOIN signals s ON s.team_key = f.team_key
                  AND s.signal_date >= f.first_release
                  AND s.signal_date <= DATE {{as_of}}
    GROUP BY f.team_key, f.first_release, src
)
SELECT f.team_key, f.display_name, f.primary_genre, f.first_release, f.profile_status, f.had_outcome,
       sc.score, pm.src, pm.role, pm.first_mention_date, pm.days_to_mention, pm.mention_cnt
FROM filtered f
LEFT JOIN scored sc ON sc.team_key = f.team_key
LEFT JOIN post_mentions pm ON pm.team_key = f.team_key
ORDER BY COALESCE(sc.score, -1) DESC, f.first_release DESC, pm.days_to_mention ASC NULLS LAST, pm.src ASC;
