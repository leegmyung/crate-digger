-- raw_tmm_export ─▶ user_likes
-- 주 아티스트 = 'A, B' / 'A & B' / 'A feat. B' / 'A ft. B' / 'A x B' 의 첫 번째 (단, 'Tyler, The Creator'처럼
-- 이름에 쉼표가 들어간 경우는 ext_artist_tags에 있는 전체 이름을 우선)
WITH base AS (
    SELECT r.*,
           trim(r.artist_name) AS a0,
           lower(trim(r.artist_name)) || ' ' AS low
    FROM raw_tmm_export r
    WHERE coalesce(trim(r.track_name), '') <> '' AND coalesce(trim(r.artist_name), '') <> ''
),
cut AS (
    SELECT b.*,
           CASE
             WHEN EXISTS (SELECT 1 FROM ext_artist_tags e WHERE lower(e.artist_name) = lower(b.a0)) THEN b.a0
             ELSE trim(substr(b.a0, 1, MIN(
                    CASE WHEN instr(b.low, ', ')     > 0 THEN instr(b.low, ', ')     ELSE 9999 END,
                    CASE WHEN instr(b.low, ' & ')    > 0 THEN instr(b.low, ' & ')    ELSE 9999 END,
                    CASE WHEN instr(b.low, ' feat.') > 0 THEN instr(b.low, ' feat.') ELSE 9999 END,
                    CASE WHEN instr(b.low, ' ft. ')  > 0 THEN instr(b.low, ' ft. ')  ELSE 9999 END,
                    CASE WHEN instr(b.low, ' x ')    > 0 THEN instr(b.low, ' x ')    ELSE 9999 END
                  ) - 1))
           END AS primary_artist
    FROM base b
)
INSERT OR IGNORE INTO user_likes
    (user_id, platform, track_title, artist_name, primary_artist, artist_key, album_title, isrc)
SELECT
    user_id, platform, trim(track_name), a0, primary_artist,
    -- 매칭 키: 'The ' 제거 → 소문자 → 공백/점/하이픈/아포스트로피 제거
    replace(replace(replace(replace(replace(
        lower(CASE WHEN lower(primary_artist) LIKE 'the %' THEN substr(primary_artist, 5) ELSE primary_artist END),
        ' ', ''), '.', ''), '-', ''), '''', ''), ',', ''),
    nullif(trim(album), ''),
    nullif(trim(isrc), '')
FROM cut;
