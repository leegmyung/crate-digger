-- 기초 뷰: 네 갈래 신호를 한 표로, 정답에 등급·연차를 붙인다.
-- 실행: psql -d crate_digger -f sql/kr/00_core_views.sql   (먼저 python3 scripts/load_pg.py)
-- 같은 팀 잇기: 모든 뷰에 team_key(팀 대표 키) 칸을 붙인다. 분석 SQL은 team_key 로 팀을 묶는다.
--   ref.artist_xref(아티스트 연결표, python3 scripts/artist_xref.py --load-pg)가 있으면 표기 키 → 대표 키를 그대로 쓰고,
--   없으면 예전 방식(괄호 속 별칭 alias_key → 그 별칭을 가진 이름 키)으로 묶는다. 연결표에 없는 새 이름도 예전 방식으로.
--   연결표를 새로 넣은 뒤에는 이 파일을 다시 실행해야 반영된다 (run_pg_queries.py 가 매번 실행).
-- 날짜: 일부만 아는 날짜는 후보 신호 = 기간 마지막 날(_end), 정답 = 기간 첫날(_start) (시점 누수 방지).
-- (BigQuery 문법으로 자동 변환: scripts/sql_to_bigquery.py — 원문은 sql/kr/ 의 같은 파일)
CREATE SCHEMA IF NOT EXISTS core;

/* 1) 신호 이벤트: 팀 × 갈래 × 날짜 (파일 출처를 빼고 UNION으로 합쳐 재수집 중복 제거) — team_key 붙이기 전 */
CREATE VIEW core.v_signal_base AS
SELECT
  s.artist_key,
  s.alias_key,
  s.artist_text,
  CAST('선정·지원' AS STRING) AS branch,
  s.source,
  s.program,
  s.stage,
  sr.rank AS stage_rank,
  s.announced_end AS signal_date,
  s.round AS detail
FROM raw.raw_kr_selection AS s
LEFT JOIN ref.stage_rank AS sr
  ON sr.stage = s.stage
/* 같은 날 다시 돌린 파일의 똑같은 줄은 하나로 (UNION = 중복 제거) */
UNION DISTINCT
SELECT
  g.artist_key,
  g.alias_key,
  g.artist_text,
  '공연',
  g.source,
  NULL,
  NULL,
  NULL,
  g.gig_date,
  SPLIT_PART(g.venue_text, ' (', 1)
FROM raw.raw_kr_gig AS g
/* 같은 날 다시 돌린 파일의 똑같은 줄은 하나로 (UNION = 중복 제거) */
UNION DISTINCT
SELECT
  r.artist_key,
  r.alias_key,
  r.artist_text,
  '발매',
  r.source,
  NULL,
  NULL,
  NULL,
  r.released_end,
  r.title
FROM raw.raw_kr_release AS r
/* 같은 날 다시 돌린 파일의 똑같은 줄은 하나로 (UNION = 중복 제거) */
UNION DISTINCT
SELECT
  p.artist_key,
  p.alias_key,
  p.artist_text,
  CASE WHEN p.pick_label = 'venue_lineup' THEN '공연' ELSE '큐레이션' END,
  p.source,
  p.outlet,
  NULL,
  NULL,
  CAST(LEFT(p.published_at, 10) AS DATE),
  p.outlet
FROM raw.raw_press AS p
WHERE
  COALESCE(p.is_sponsored, 0) = 0;

/* 협찬 글은 신호에서 뺀다 */;

/* 1-1) 표기 키 → 팀 대표 키. 연결표가 있으면 연결표 우선, 연결표에 없는 키는 괄호 별칭 규칙으로. */
/*      (ref.artist_xref 가 없을 때도 돌아가야 해서 있는지 보고 뷰 정의를 고른다) */
CREATE VIEW core.v_team_map AS
WITH alias_map AS (
  SELECT
    alias_key,
    MIN(artist_key) AS main_key
  FROM core.v_signal_base
  WHERE
    alias_key IS NOT NULL AND alias_key <> '' AND alias_key <> artist_key
  GROUP BY
    alias_key
)
SELECT
  x.variant_key,
  x.artist_key AS team_key,
  'xref' AS via
FROM ref.artist_xref AS x
UNION ALL
SELECT
  am.alias_key,
  COALESCE(x2.artist_key, am.main_key),
  'alias'
FROM alias_map AS am
LEFT JOIN ref.artist_xref AS x2
  ON x2.variant_key = am.main_key
WHERE
  NOT EXISTS(
    SELECT
      1
    FROM ref.artist_xref AS x
    WHERE
      x.variant_key = am.alias_key
  );

/* 1-2) 공연장 표기 → 대표 이름 (ref.venue_xref, python3 scripts/venue_xref.py --load-pg). 표가 없으면 빈 매핑 → detail 그대로 */
CREATE VIEW core.v_venue_map AS
SELECT
  variant,
  venue
FROM ref.venue_xref;

/* 신호 + team_key(팀 대표 키) + venue(공연 갈래의 공연장 대표 이름; 다른 갈래는 NULL, detail 은 원래 표기 그대로) */
CREATE VIEW core.v_signal AS
SELECT
  b.*,
  COALESCE(tm.team_key, b.artist_key) AS team_key,
  CASE WHEN b.branch = '공연' THEN COALESCE(vm.venue, TRIM(b.detail)) END AS venue
FROM core.v_signal_base AS b
LEFT JOIN core.v_team_map AS tm
  ON tm.variant_key = b.artist_key
LEFT JOIN core.v_venue_map AS vm
  ON b.branch = '공연' AND vm.variant = TRIM(b.detail)
WHERE
  COALESCE(tm.team_key, '') <> '__non_artist__';

/* 매거진·공연장·기관 계정명으로만 잡힌 줄은 팀 신호가 아님 (artist_xref.NON_ARTIST_KEY) */;

/* 2) 아티스트 첫 발매일·규모 (멜론 프로필). 같은 키에 여러 프로필이면 가장 이른 날짜 */
CREATE VIEW core.v_artist_profile AS
SELECT
  artist_key,
  MIN(
    LEAST(
      COALESCE(debut_start, first_release_start),
      COALESCE(first_release_start, debut_start)
    )
  ) AS first_release,
  MAX(album_count) AS album_count,
  MAX(fan_count) AS fan_count,
  COUNT(DISTINCT artist_source_id) AS profile_count /* 2 이상이면 동명 팀 가능성 */
FROM raw.raw_artist_profile
GROUP BY
  artist_key;

/* 3) 정답 + 등급 + 정답 당시 연차 + 셀지 여부(기성 팀이 섞인 정답은 첫 발매 N년 이내만) */
CREATE VIEW core.v_outcome AS
SELECT
  o.*,
  t.tier,
  t.career_filtered,
  ap.first_release,
  ROUND(CAST((
    (
      o.announced_start - ap.first_release
    ) / 365.25
  ) AS NUMERIC), 1) AS years_at_outcome,
  (
    NOT t.career_filtered
    OR (
      ap.first_release IS NOT NULL
      AND (
        o.announced_start - ap.first_release
      ) / 365.25 <= (
        SELECT
          value
        FROM ref.settings
        WHERE
          name = 'career_filter_years'
      )
    )
  ) AS counted,
  COALESCE(tm.team_key, o.artist_key) AS team_key
FROM raw.raw_outcome AS o
JOIN ref.outcome_tier AS t
  ON t.program = o.program
LEFT JOIN core.v_artist_profile AS ap
  ON ap.artist_key = o.artist_key
LEFT JOIN core.v_team_map AS tm
  ON tm.variant_key = o.artist_key;

/* 4) 팀별 첫 정답 (센 정답만, 팀 = team_key) */
CREATE VIEW core.v_outcome_team AS
SELECT
  artist_key,
  alias_key,
  artist_text,
  first_program,
  first_tier,
  first_outcome_date,
  team_key
FROM (
  SELECT
    artist_key AS artist_key,
    alias_key AS alias_key,
    artist_text AS artist_text,
    program AS first_program,
    tier AS first_tier,
    announced_start AS first_outcome_date,
    team_key AS team_key,
    ROW_NUMBER() OVER (
      PARTITION BY team_key
      ORDER BY team_key NULLS LAST, announced_start NULLS LAST, program NULLS LAST
    ) AS _row_number
  FROM core.v_outcome
  WHERE
    counted
) AS _t
WHERE
  _row_number = 1;

/* 5) 팀 상태: 유명(제외) / 신인 / 기성 (멜론·스포티파이 프로필 기준, 기준값은 ref.settings) */
/*    유명 = 멜론 팬 fame_fans 이상, 또는 첫 발매 fame_years 초과 & 팬 fame_years_min_fans 이상 (혁오·잔나비 같은 팀 제외). */
/*           팬이 적은데 첫 발매만 오래된 팀은 동명의 옛 팀일 수 있어 빼지 않는다(기성, 검수 대상) */
/*    신인 = 첫 발매 newcomer_years 이내 & 발매 newcomer_albums 이하.  프로필이 없으면 이 뷰에 없음(= 모름) */
CREATE VIEW core.v_artist_status AS
WITH cfg AS (
  SELECT
    MAX(CASE WHEN name = 'fame_fans' THEN value END) AS fame_fans,
    MAX(CASE WHEN name = 'fame_years' THEN value END) AS fame_years,
    MAX(CASE WHEN name = 'fame_years_min_fans' THEN value END) AS fame_years_min_fans,
    MAX(CASE WHEN name = 'newcomer_years' THEN value END) AS new_years,
    MAX(CASE WHEN name = 'newcomer_albums' THEN value END) AS new_albums
  FROM ref.settings
)
SELECT
  p.artist_key,
  p.first_release,
  p.album_count,
  p.fan_count,
  ROUND(CAST((
    (
      CURRENT_DATE - p.first_release
    ) / 365.25
  ) AS NUMERIC), 1) AS years_since_first,
  CASE
    WHEN p.fan_count >= cfg.fame_fans
    THEN 'famous'
    WHEN p.first_release < CURRENT_DATE - CAST((
      cfg.fame_years * 365.25
    ) AS INT64)
    AND p.fan_count >= cfg.fame_years_min_fans
    THEN 'famous'
    WHEN p.first_release >= CURRENT_DATE - CAST((
      cfg.new_years * 365.25
    ) AS INT64)
    AND COALESCE(p.album_count, 0) <= cfg.new_albums
    THEN 'newcomer'
    WHEN p.first_release IS NULL
    THEN 'unknown'
    ELSE 'established'
  END AS status,
  COALESCE(tm.team_key, p.artist_key) AS team_key /* 팀 대표 키로 찾을 때 (한 팀에 프로필 여러 개일 수 있음) */
FROM core.v_artist_profile AS p
CROSS JOIN cfg
LEFT JOIN core.v_team_map AS tm
  ON tm.variant_key = p.artist_key;
