-- 기초 뷰: 네 갈래 신호를 한 표로, 정답에 등급·연차를 붙인다.
-- 실행: psql -d crate_digger -f sql/kr/00_core_views.sql   (먼저 python3 scripts/load_pg.py)
-- 같은 팀 잇기: artist_key(끝 괄호 별칭 제거) 또는 alias_key(괄호 속 별칭)가 서로 같으면 같은 팀으로 본다.
-- 날짜: 일부만 아는 날짜는 후보 신호 = 기간 마지막 날(_end), 정답 = 기간 첫날(_start) (시점 누수 방지).

CREATE SCHEMA IF NOT EXISTS core;

-- 1) 신호 이벤트: 팀 × 갈래 × 날짜
CREATE OR REPLACE VIEW core.v_signal AS
SELECT s.artist_key, s.alias_key, s.artist_text,
       '선정·지원'::text AS branch, s.source, s.program, s.stage, sr.rank AS stage_rank,
       s.announced_end AS signal_date, s.round AS detail
FROM raw.raw_kr_selection s
LEFT JOIN ref.stage_rank sr ON sr.stage = s.stage
UNION ALL
SELECT g.artist_key, g.alias_key, g.artist_text,
       '공연', g.source, NULL, NULL, NULL,
       g.gig_date, split_part(g.venue_text, ' (', 1)
FROM raw.raw_kr_gig g
UNION ALL
SELECT r.artist_key, r.alias_key, r.artist_text,
       '발매', r.source, NULL, NULL, NULL,
       r.released_end, r.title
FROM raw.raw_kr_release r
UNION ALL
SELECT p.artist_key, p.alias_key, p.artist_text,
       CASE WHEN p.pick_label = 'venue_lineup' THEN '공연' ELSE '큐레이션' END, p.source, p.outlet, NULL, NULL,
       left(p.published_at, 10)::date, p.outlet
FROM raw.raw_press p
WHERE coalesce(p.is_sponsored, 0) = 0;          -- 협찬 글은 신호에서 뺀다

-- 2) 아티스트 첫 발매일·규모 (멜론 프로필). 같은 키에 여러 프로필이면 가장 이른 날짜
CREATE OR REPLACE VIEW core.v_artist_profile AS
SELECT artist_key,
       min(least(coalesce(debut_start, first_release_start), coalesce(first_release_start, debut_start))) AS first_release,
       max(album_count) AS album_count,
       max(fan_count) AS fan_count,
       count(DISTINCT artist_source_id) AS profile_count      -- 2 이상이면 동명 팀 가능성
FROM raw.raw_artist_profile
GROUP BY artist_key;

-- 3) 정답 + 등급 + 정답 당시 연차 + 셀지 여부(기성 팀이 섞인 정답은 첫 발매 N년 이내만)
CREATE OR REPLACE VIEW core.v_outcome AS
SELECT o.*, t.tier, t.career_filtered, ap.first_release,
       round(((o.announced_start - ap.first_release) / 365.25)::numeric, 1) AS years_at_outcome,
       (NOT t.career_filtered
        OR (ap.first_release IS NOT NULL
            AND (o.announced_start - ap.first_release) / 365.25
                <= (SELECT value FROM ref.settings WHERE name = 'career_filter_years'))) AS counted
FROM raw.raw_outcome o
JOIN ref.outcome_tier t ON t.program = o.program
LEFT JOIN core.v_artist_profile ap ON ap.artist_key = o.artist_key;

-- 4) 팀별 첫 정답 (센 정답만)
CREATE OR REPLACE VIEW core.v_outcome_team AS
SELECT DISTINCT ON (artist_key)
       artist_key, alias_key, artist_text, program AS first_program, tier AS first_tier,
       announced_start AS first_outcome_date
FROM core.v_outcome
WHERE counted
ORDER BY artist_key, announced_start, program;
