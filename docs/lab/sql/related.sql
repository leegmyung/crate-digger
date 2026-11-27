-- 관련 팀: {{team_key}}와 (1) 같은 날·같은 공연장에 함께 선 팀(많이 겹친 순 상위 8), (2) 같은 소속사 팀(상위 8).
-- detail = 함께 선 공연장 목록 또는 소속사 이름. 같은 무대가 많을수록 같은 씬·같은 기획자 주변일 가능성이 크다.
WITH gig AS (
    SELECT DISTINCT team_key, signal_date, venue
    FROM signals
    WHERE branch = '공연' AND COALESCE(venue, '') NOT IN ('', '공연장 미정')
),
stage AS (
    SELECT b.team_key AS related_team, '같은 무대' AS relation,
           COUNT(*) AS shared_count, MAX(a.signal_date) AS last_date,
           STRING_AGG(DISTINCT a.venue, ' · ') AS detail
    FROM gig a
    JOIN gig b ON b.signal_date = a.signal_date AND b.venue = a.venue AND b.team_key <> a.team_key
    WHERE a.team_key = {{team_key}}
    GROUP BY b.team_key
    ORDER BY shared_count DESC, last_date DESC
    LIMIT 8
),
agency AS (
    SELECT o.team_key AS related_team, '같은 소속사' AS relation,
           NULL::BIGINT AS shared_count, NULL::DATE AS last_date, o.agency AS detail
    FROM teams me
    JOIN teams o ON o.agency = me.agency AND o.team_key <> me.team_key
    WHERE me.team_key = {{team_key}} AND COALESCE(me.agency, '') <> ''
    ORDER BY o.first_seen DESC
    LIMIT 8
)
SELECT r.related_team, COALESCE(t.display_name, r.related_team) AS display_name, r.relation,
       r.shared_count, r.last_date, r.detail
FROM (SELECT * FROM stage UNION ALL SELECT * FROM agency) r
LEFT JOIN teams t ON t.team_key = r.related_team
ORDER BY r.relation, r.shared_count DESC NULLS LAST, r.last_date DESC NULLS LAST;
