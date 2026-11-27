-- 지금 후보: 기준일 {{as_of}}(보통 오늘) 시점 점수로 정렬한 팀 목록과 점수 구성.
-- {{only_no_outcome}} true면 이미 정답(신인상 등)을 받은 팀은 뺀다. {{limit}} 최대 행 수.
-- 나머지 자리표시자는 backtest.sql과 같다(정답 종류·관찰 기간은 후보 점수에 영향 없음).
SELECT team_key, display_name, ROUND(score, 2) AS score, n_branch, best_stage, peer_selected, dmz, gigs_1y, outlets,
       first_seen, last_seen, primary_genre, profile_status, had_outcome,
       ROUND(pts_branch, 2) AS pts_branch, ROUND(pts_stage, 2) AS pts_stage, ROUND(pts_peer, 2) AS pts_peer,
       ROUND(pts_dmz, 2) AS pts_dmz, ROUND(pts_gigs, 2) AS pts_gigs, ROUND(pts_outlets, 2) AS pts_outlets,
       ROUND(pts_recent, 2) AS pts_recent, ROUND(pts_venues, 2) AS pts_venues, ROUND(pts_winner, 2) AS pts_winner, ROUND(pts_context, 2) AS pts_context, context_outlets,
       recent180, venues, peer_winner
FROM lab_scored(DATE {{as_of}}, {{lookback_years}}, {{newcomer_years}}, {{exclude_famous}},
                'any', 1, {{genre}}, {{branches}},
                {{w_branch}}, {{w_stage}}, {{w_peer}}, {{w_dmz}}, {{w_gigs}}, {{w_outlets}}, {{outlet_cap}},
                {{w_recent}}, {{w_venues}}, {{w_winner}}, {{w_context}})
WHERE NOT ({{only_no_outcome}} AND had_outcome)
ORDER BY score DESC, last_seen DESC, md5(team_key)
LIMIT {{limit}};
