-- 팀 관계망(1-hop ego network): {{team_key}}를 중심으로 기간 [{{since_date}}, {{until_date}}] 안의
-- 같은 무대 팀(co_stage), 같은 소속사 팀(same_agency), 선 공연장(venue),
-- 받은 정답(outcome), 선정·지원 프로그램(program), 소개한 매체(outlet)를 반환한다.
-- 종류별 최대 {{limit_per_kind}}건. 속한 씬 묶음(scene)은 앱에서 scene_map.json과 합친다.
WITH gig AS (
    SELECT DISTINCT team_key, signal_date, TRIM(venue) AS venue
    FROM signals
    WHERE branch = '공연'
      AND COALESCE(TRIM(venue), '') NOT IN ('', '공연장 미정')
      AND signal_date >= DATE {{since_date}}
      AND signal_date <= DATE {{until_date}}
),
co_stage AS (
    SELECT 'team:' || b.team_key                    AS node_id,
           'team'                                   AS node_type,
           b.team_key                               AS node_key,
           COALESCE(t.display_name, b.team_key)     AS label,
           'co_stage'                               AS relation,
           COUNT(*)::DOUBLE                         AS weight,
           ''                                       AS grade,
           STRING_AGG(DISTINCT a.venue, ' · ')      AS detail,
           MAX(a.signal_date)                       AS last_date,
           COALESCE(t.primary_genre, '')            AS primary_genre
    FROM gig a
    JOIN gig b
      ON b.signal_date = a.signal_date
     AND b.venue = a.venue
     AND b.team_key <> a.team_key
    LEFT JOIN teams t ON t.team_key = b.team_key
    WHERE a.team_key = {{team_key}}
    GROUP BY b.team_key, t.display_name, t.primary_genre
    ORDER BY weight DESC, last_date DESC, label ASC
    LIMIT {{limit_per_kind}}
),
same_agency AS (
    SELECT 'team:' || o.team_key                    AS node_id,
           'team'                                   AS node_type,
           o.team_key                               AS node_key,
           COALESCE(o.display_name, o.team_key)     AS label,
           'same_agency'                            AS relation,
           1.0::DOUBLE                              AS weight,
           ''                                       AS grade,
           o.agency                                 AS detail,
           o.first_seen                             AS last_date,
           COALESCE(o.primary_genre, '')            AS primary_genre
    FROM teams me
    JOIN teams o
      ON o.agency = me.agency
     AND o.team_key <> me.team_key
    WHERE me.team_key = {{team_key}}
      AND COALESCE(TRIM(me.agency), '') <> ''
    ORDER BY o.first_seen DESC NULLS LAST, label ASC
    LIMIT {{limit_per_kind}}
),
venues AS (
    SELECT 'venue:' || g.venue                      AS node_id,
           'venue'                                  AS node_type,
           g.venue                                  AS node_key,
           g.venue                                  AS label,
           'venue'                                  AS relation,
           COUNT(*)::DOUBLE                         AS weight,
           ''                                       AS grade,
           COUNT(*)::VARCHAR || '회 공연'            AS detail,
           MAX(g.signal_date)                       AS last_date,
           ''                                       AS primary_genre
    FROM gig g
    WHERE g.team_key = {{team_key}}
    GROUP BY g.venue
    ORDER BY weight DESC, last_date DESC, g.venue ASC
    LIMIT {{limit_per_kind}}
),
my_outcomes AS (
    SELECT 'outcome:' || o.program                                                      AS node_id,
           'outcome'                                                                    AS node_type,
           o.program                                                                    AS node_key,
           COALESCE(MAX(o.program_label), o.program)                                    AS label,
           'outcome'                                                                    AS relation,
           COALESCE(MAX(o.weight), 1)::DOUBLE                                           AS weight,
           COALESCE(ARG_MAX(o.grade, o.weight), '')                                     AS grade,
           STRING_AGG(DISTINCT COALESCE(NULLIF(o.result, ''), o.tier, ''), ', ')        AS detail,
           MAX(o.announced_date)                                                        AS last_date,
           ''                                                                           AS primary_genre
    FROM outcomes o
    WHERE o.team_key = {{team_key}}
      AND o.counted
      AND o.announced_date >= DATE {{since_date}}
      AND o.announced_date <= DATE {{until_date}}
    GROUP BY o.program
    ORDER BY weight DESC, last_date DESC, label ASC
    LIMIT {{limit_per_kind}}
),
my_programs AS (
    SELECT 'program:' || s.program                                                      AS node_id,
           'program'                                                                    AS node_type,
           s.program                                                                    AS node_key,
           COALESCE(MAX(pr.label), s.program)                                           AS label,
           'program'                                                                    AS relation,
           COUNT(DISTINCT s.signal_date)::DOUBLE                                        AS weight,
           ''                                                                           AS grade,
           COALESCE(ANY_VALUE(s.role), '')                                              AS detail,
           MAX(s.signal_date)                                                           AS last_date,
           ''                                                                           AS primary_genre
    FROM signals s
    LEFT JOIN programs pr ON pr.program = s.program
    WHERE s.team_key = {{team_key}}
      AND s.branch = '선정·지원'
      AND COALESCE(TRIM(s.program), '') <> ''
      AND s.signal_date >= DATE {{since_date}}
      AND s.signal_date <= DATE {{until_date}}
    GROUP BY s.program
    ORDER BY last_date DESC, weight DESC, label ASC
    LIMIT {{limit_per_kind}}
),
my_outlets AS (
    SELECT 'outlet:' || s.branch || ':' || s.source                                     AS node_id,
           'outlet'                                                                     AS node_type,
           s.branch || ':' || s.source                                                  AS node_key,
           s.branch || ':' || s.source                                                  AS label,
           'outlet'                                                                     AS relation,
           COUNT(*)::DOUBLE                                                             AS weight,
           ''                                                                           AS grade,
           COALESCE(ANY_VALUE(s.role), '')                                              AS detail,
           MAX(s.signal_date)                                                           AS last_date,
           ''                                                                           AS primary_genre
    FROM signals s
    WHERE s.team_key = {{team_key}}
      AND s.branch IN ('큐레이션', '발매')
      AND COALESCE(TRIM(s.source), '') <> ''
      AND COALESCE(s.role, '') <> 'excluded'
      AND s.signal_date >= DATE {{since_date}}
      AND s.signal_date <= DATE {{until_date}}
    GROUP BY s.branch, s.source
    ORDER BY weight DESC, last_date DESC, label ASC
    LIMIT {{limit_per_kind}}
)
SELECT * FROM co_stage
UNION ALL SELECT * FROM same_agency
UNION ALL SELECT * FROM venues
UNION ALL SELECT * FROM my_outcomes
UNION ALL SELECT * FROM my_programs
UNION ALL SELECT * FROM my_outlets;
