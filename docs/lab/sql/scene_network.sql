-- 씬 네트워크(전체/장르별): 기준일 {{as_of}} 기준 상위 {{limit}}팀(후보 + 정답 팀 포함)과
-- 그 팀들 사이의 같은 무대 연결(겹친 횟수 = weight)을 한 번에 반환한다.
-- row_kind = 'node' (팀 노드) / 'edge' (같은 무대 연결).
-- teams 표에 존재하는 팀만 포함되며, 씬 묶음 색상은 앱에서 scene_map.json과 결합한다.
WITH scored_all AS (
    SELECT sc.team_key,
           COALESCE(sc.display_name, t.display_name, sc.team_key) AS display_name,
           ROUND(sc.score, 2)::DOUBLE                             AS score,
           sc.n_branch::INT                                       AS n_branch,
           sc.gigs_1y::INT                                        AS gigs_1y,
           sc.venues::INT                                         AS venues,
           COALESCE(sc.primary_genre, t.primary_genre, '')        AS primary_genre,
           COALESCE(sc.had_outcome, false)                        AS had_outcome,
           sc.last_seen,
           CASE WHEN NOT COALESCE(sc.had_outcome, false)
                THEN ROW_NUMBER() OVER (
                    PARTITION BY COALESCE(sc.had_outcome, false)
                    ORDER BY sc.score DESC, sc.last_seen DESC, md5(sc.team_key)
                )::INT
                ELSE NULL::INT
           END                                                    AS cand_rank
    FROM lab_scored(DATE {{as_of}}, {{lookback_years}}, {{newcomer_years}}, {{exclude_famous}},
                    'any', 1, {{genre}}, {{branches}},
                    {{w_branch}}, {{w_stage}}, {{w_peer}}, {{w_dmz}}, {{w_gigs}}, {{w_outlets}}, {{outlet_cap}},
                    {{w_recent}}, {{w_venues}}, {{w_winner}}, {{w_context}}, {{w_collab}}) sc
    JOIN teams t ON t.team_key = sc.team_key
),
pool AS (
    SELECT *
    FROM scored_all
    ORDER BY score DESC, last_seen DESC, md5(team_key)
    LIMIT {{limit}}
),
best_outcome AS (
    SELECT team_key,
           COALESCE(ARG_MAX(grade, weight), '')                   AS outcome_grade,
           COALESCE(ARG_MAX(program_label, weight), '')           AS outcome_label
    FROM outcomes
    WHERE counted
    GROUP BY team_key
),
gig AS (
    SELECT DISTINCT s.team_key, s.signal_date, TRIM(s.venue) AS venue
    FROM signals s
    JOIN pool p ON p.team_key = s.team_key
    WHERE s.branch = '공연'
      AND COALESCE(TRIM(s.venue), '') NOT IN ('', '공연장 미정')
      AND s.signal_date >= DATE {{as_of}} - to_years({{lookback_years}})
      AND s.signal_date <= DATE {{until_date}}
),
edges AS (
    SELECT a.team_key                                             AS source_key,
           b.team_key                                             AS target_key,
           COUNT(*)::DOUBLE                                       AS weight,
           STRING_AGG(DISTINCT a.venue, ' · ')                    AS detail,
           MAX(a.signal_date)                                     AS last_date
    FROM gig a
    JOIN gig b
      ON b.signal_date = a.signal_date
     AND b.venue = a.venue
     AND b.team_key > a.team_key
    GROUP BY a.team_key, b.team_key
)
SELECT 'node'                                                     AS row_kind,
       p.team_key                                                 AS team_key,
       ''                                                         AS target_key,
       p.display_name                                             AS display_name,
       p.score                                                    AS score,
       p.cand_rank                                                AS cand_rank,
       p.primary_genre                                            AS primary_genre,
       p.had_outcome                                              AS had_outcome,
       COALESCE(bo.outcome_grade, '')                             AS outcome_grade,
       COALESCE(bo.outcome_label, '')                             AS outcome_label,
       p.gigs_1y                                                  AS gigs_1y,
       p.venues                                                   AS venues,
       p.n_branch                                                 AS n_branch,
       0.0::DOUBLE                                                AS weight,
       ''                                                         AS detail,
       p.last_seen                                                AS last_date
FROM pool p
LEFT JOIN best_outcome bo ON bo.team_key = p.team_key
UNION ALL
SELECT 'edge'                                                     AS row_kind,
       e.source_key                                               AS team_key,
       e.target_key                                               AS target_key,
       ''                                                         AS display_name,
       0.0::DOUBLE                                                AS score,
       NULL::INT                                                  AS cand_rank,
       ''                                                         AS primary_genre,
       false                                                      AS had_outcome,
       ''                                                         AS outcome_grade,
       ''                                                         AS outcome_label,
       0::INT                                                     AS gigs_1y,
       0::INT                                                     AS venues,
       0::INT                                                     AS n_branch,
       e.weight                                                   AS weight,
       e.detail                                                   AS detail,
       e.last_date                                                AS last_date
FROM edges e;
