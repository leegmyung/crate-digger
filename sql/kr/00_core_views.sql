-- 기초 뷰: 네 갈래 신호를 한 표로, 정답에 등급·연차를 붙인다.
-- 실행: psql -d crate_digger -f sql/kr/00_core_views.sql   (먼저 python3 scripts/load_pg.py)
-- 같은 팀 잇기: 모든 뷰에 team_key(팀 대표 키) 칸을 붙인다. 분석 SQL은 team_key 로 팀을 묶는다.
--   ref.artist_xref(아티스트 연결표, python3 scripts/artist_xref.py --load-pg)가 있으면 표기 키 → 대표 키를 그대로 쓰고,
--   없으면 예전 방식(괄호 속 별칭 alias_key → 그 별칭을 가진 이름 키)으로 묶는다. 연결표에 없는 새 이름도 예전 방식으로.
--   연결표를 새로 넣은 뒤에는 이 파일을 다시 실행해야 반영된다 (run_pg_queries.py 가 매번 실행).
-- 날짜: 일부만 아는 날짜는 후보 신호 = 기간 마지막 날(_end), 정답 = 기간 첫날(_start) (시점 누수 방지).

CREATE SCHEMA IF NOT EXISTS core;
DROP VIEW IF EXISTS core.v_artist_status, core.v_outcome_team, core.v_outcome, core.v_artist_profile,
                    core.v_signal, core.v_team_map, core.v_signal_base CASCADE;

-- 1) 신호 이벤트: 팀 × 갈래 × 날짜 (파일 출처를 빼고 UNION으로 합쳐 재수집 중복 제거) — team_key 붙이기 전
CREATE VIEW core.v_signal_base AS
SELECT s.artist_key, s.alias_key, s.artist_text,
       '선정·지원'::text AS branch, s.source, s.program, s.stage, sr.rank AS stage_rank,
       s.announced_end AS signal_date, s.round AS detail
FROM raw.raw_kr_selection s
LEFT JOIN ref.stage_rank sr ON sr.stage = s.stage
UNION   -- 같은 날 다시 돌린 파일의 똑같은 줄은 하나로 (UNION = 중복 제거)
SELECT g.artist_key, g.alias_key, g.artist_text,
       '공연', g.source, NULL, NULL, NULL,
       g.gig_date, split_part(g.venue_text, ' (', 1)
FROM raw.raw_kr_gig g
UNION   -- 같은 날 다시 돌린 파일의 똑같은 줄은 하나로 (UNION = 중복 제거)
SELECT r.artist_key, r.alias_key, r.artist_text,
       '발매', r.source, NULL, NULL, NULL,
       r.released_end, r.title
FROM raw.raw_kr_release r
UNION   -- 같은 날 다시 돌린 파일의 똑같은 줄은 하나로 (UNION = 중복 제거)
SELECT p.artist_key, p.alias_key, p.artist_text,
       CASE WHEN p.pick_label = 'venue_lineup' THEN '공연' ELSE '큐레이션' END, p.source, p.outlet, NULL, NULL,
       left(p.published_at, 10)::date, p.outlet
FROM raw.raw_press p
WHERE coalesce(p.is_sponsored, 0) = 0;          -- 협찬 글은 신호에서 뺀다

-- 1-1) 표기 키 → 팀 대표 키. 연결표가 있으면 연결표 우선, 연결표에 없는 키는 괄호 별칭 규칙으로.
--      (ref.artist_xref 가 없을 때도 돌아가야 해서 있는지 보고 뷰 정의를 고른다)
DO $$
DECLARE
    alias_cte text := $q$
        WITH alias_map AS (                      -- 괄호 속 별칭 키 → 그 별칭을 가진 이름 키 (예: samui → 사뮈)
            SELECT alias_key, MIN(artist_key) AS main_key   -- 예전 a05·a09 의 alias_map 과 같은 규칙 (신호 표 기준)
            FROM core.v_signal_base
            WHERE alias_key IS NOT NULL AND alias_key <> '' AND alias_key <> artist_key
            GROUP BY alias_key
        )$q$;
BEGIN
    IF to_regclass('ref.artist_xref') IS NOT NULL THEN
        EXECUTE 'CREATE VIEW core.v_team_map AS ' || alias_cte || $q$
            SELECT x.variant_key, x.artist_key AS team_key, 'xref'::text AS via
            FROM ref.artist_xref x
            UNION ALL
            SELECT am.alias_key, COALESCE(x2.artist_key, am.main_key), 'alias'
            FROM alias_map am
            LEFT JOIN ref.artist_xref x2 ON x2.variant_key = am.main_key
            WHERE NOT EXISTS (SELECT 1 FROM ref.artist_xref x WHERE x.variant_key = am.alias_key)$q$;
    ELSE
        EXECUTE 'CREATE VIEW core.v_team_map AS ' || alias_cte || $q$
            SELECT alias_key AS variant_key, main_key AS team_key, 'alias'::text AS via FROM alias_map$q$;
    END IF;
END $$;

CREATE VIEW core.v_signal AS
SELECT b.*, COALESCE(tm.team_key, b.artist_key) AS team_key
FROM core.v_signal_base b
LEFT JOIN core.v_team_map tm ON tm.variant_key = b.artist_key;

-- 2) 아티스트 첫 발매일·규모 (멜론 프로필). 같은 키에 여러 프로필이면 가장 이른 날짜
CREATE VIEW core.v_artist_profile AS
SELECT artist_key,
       min(least(coalesce(debut_start, first_release_start), coalesce(first_release_start, debut_start))) AS first_release,
       max(album_count) AS album_count,
       max(fan_count) AS fan_count,
       count(DISTINCT artist_source_id) AS profile_count      -- 2 이상이면 동명 팀 가능성
FROM raw.raw_artist_profile
GROUP BY artist_key;

-- 3) 정답 + 등급 + 정답 당시 연차 + 셀지 여부(기성 팀이 섞인 정답은 첫 발매 N년 이내만)
CREATE VIEW core.v_outcome AS
SELECT o.*, t.tier, t.career_filtered, ap.first_release,
       round(((o.announced_start - ap.first_release) / 365.25)::numeric, 1) AS years_at_outcome,
       (NOT t.career_filtered
        OR (ap.first_release IS NOT NULL
            AND (o.announced_start - ap.first_release) / 365.25
                <= (SELECT value FROM ref.settings WHERE name = 'career_filter_years'))) AS counted,
       COALESCE(tm.team_key, o.artist_key) AS team_key
FROM raw.raw_outcome o
JOIN ref.outcome_tier t ON t.program = o.program
LEFT JOIN core.v_artist_profile ap ON ap.artist_key = o.artist_key
LEFT JOIN core.v_team_map tm ON tm.variant_key = o.artist_key;

-- 4) 팀별 첫 정답 (센 정답만, 팀 = team_key)
CREATE VIEW core.v_outcome_team AS
SELECT DISTINCT ON (team_key)
       artist_key, alias_key, artist_text, program AS first_program, tier AS first_tier,
       announced_start AS first_outcome_date, team_key
FROM core.v_outcome
WHERE counted
ORDER BY team_key, announced_start, program;

-- 5) 팀 상태: 유명(제외) / 신인 / 기성 (멜론·스포티파이 프로필 기준, 기준값은 ref.settings)
--    유명 = 멜론 팬 fame_fans 이상, 또는 첫 발매 fame_years 초과 & 팬 fame_years_min_fans 이상 (혁오·잔나비 같은 팀 제외).
--           팬이 적은데 첫 발매만 오래된 팀은 동명의 옛 팀일 수 있어 빼지 않는다(기성, 검수 대상)
--    신인 = 첫 발매 newcomer_years 이내 & 발매 newcomer_albums 이하.  프로필이 없으면 이 뷰에 없음(= 모름)
CREATE VIEW core.v_artist_status AS
WITH cfg AS (
    SELECT max(CASE WHEN name = 'fame_fans' THEN value END) AS fame_fans,
           max(CASE WHEN name = 'fame_years' THEN value END) AS fame_years,
           max(CASE WHEN name = 'fame_years_min_fans' THEN value END) AS fame_years_min_fans,
           max(CASE WHEN name = 'newcomer_years' THEN value END) AS new_years,
           max(CASE WHEN name = 'newcomer_albums' THEN value END) AS new_albums
    FROM ref.settings)
SELECT p.artist_key, p.first_release, p.album_count, p.fan_count,
       round(((current_date - p.first_release) / 365.25)::numeric, 1) AS years_since_first,
       CASE WHEN p.fan_count >= cfg.fame_fans THEN 'famous'
            WHEN p.first_release < current_date - (cfg.fame_years * 365.25)::int
                 AND p.fan_count >= cfg.fame_years_min_fans THEN 'famous'
            WHEN p.first_release >= current_date - (cfg.new_years * 365.25)::int
                 AND coalesce(p.album_count, 0) <= cfg.new_albums THEN 'newcomer'
            WHEN p.first_release IS NULL THEN 'unknown'
            ELSE 'established' END AS status,
       COALESCE(tm.team_key, p.artist_key) AS team_key       -- 팀 대표 키로 찾을 때 (한 팀에 프로필 여러 개일 수 있음)
FROM core.v_artist_profile p CROSS JOIN cfg
LEFT JOIN core.v_team_map tm ON tm.variant_key = p.artist_key;
