-- =====================================================================
-- 취향 기반 Bandcamp 추천: 스키마 (기존 bandcamp.db에 추가)
-- 흐름: TuneMyMusic CSV ─▶ raw_tmm_export ─▶ user_likes ─▶ user_taste
--       Bandcamp(dim_artist·dim_item·item_tags·fact_sales·bc_fan_collection) ─▶ bc_artist_vec
--       ─▶ reco_score ─▶ 추천
-- =====================================================================

-- 1) TuneMyMusic 파일 내보내기 원본 (Spotify / Apple Music / YouTube Music 공통)
DROP TABLE IF EXISTS raw_tmm_export;
CREATE TABLE raw_tmm_export (
    user_id        TEXT NOT NULL,
    platform       TEXT NOT NULL,      -- 'Spotify' | 'Apple Music' | 'YouTube Music'
    track_name     TEXT,
    artist_name    TEXT,
    album          TEXT,
    playlist_name  TEXT,               -- 'Liked Songs' 등
    item_type      TEXT,               -- TuneMyMusic 'Type' 컬럼
    isrc           TEXT
);

-- 2) 정규화된 좋아요
DROP TABLE IF EXISTS user_likes;
CREATE TABLE user_likes (
    like_id        INTEGER PRIMARY KEY,
    user_id        TEXT NOT NULL,
    platform       TEXT NOT NULL,
    track_title    TEXT NOT NULL,
    artist_name    TEXT NOT NULL,      -- 원문 ('A, B' / 'A feat. B' 포함)
    primary_artist TEXT NOT NULL,      -- 첫 번째 아티스트
    artist_key     TEXT NOT NULL,      -- 매칭 키: 소문자, 'the ' 제거, 공백·기호 제거
    album_title    TEXT,
    isrc           TEXT,
    UNIQUE (user_id, platform, track_title, artist_key)
);

-- 3) 외부 아티스트 태그 (실서비스: Last.fm artist.getTopTags / MusicBrainz)
DROP TABLE IF EXISTS ext_artist_tags;
CREATE TABLE ext_artist_tags (
    artist_key  TEXT NOT NULL,
    artist_name TEXT NOT NULL,
    tag         TEXT NOT NULL,
    weight      REAL NOT NULL,         -- 0~1
    PRIMARY KEY (artist_key, tag)
);

-- 4) 태그 → 상위 취향군 (플랫폼 태그와 Bandcamp 태그를 잇는 다리)
DROP TABLE IF EXISTS tag_family;
CREATE TABLE tag_family (
    tag     TEXT PRIMARY KEY,
    family  TEXT NOT NULL
);
INSERT INTO tag_family (tag, family) VALUES
 ('rock','rock'),('indie rock','rock'),('shoegaze','rock'),('post-rock','rock'),('alternative','rock'),('korean indie','rock'),
 ('pop','pop'),('synth-pop','pop'),('bedroom pop','pop'),('dream pop','pop'),('k-pop','pop'),('city pop','pop'),
 ('electronic','electronic'),('techno','electronic'),('house','electronic'),('idm','electronic'),('downtempo','electronic'),
 ('ambient','ambient'),('drone','ambient'),('new age','ambient'),('field recordings','ambient'),
 ('hip-hop','hip-hop'),('boom bap','hip-hop'),('instrumental hip-hop','hip-hop'),('lo-fi','hip-hop'),
 ('conscious hip-hop','hip-hop'),('underground hip-hop','hip-hop'),('uk hip-hop','hip-hop'),
 ('r&b/soul','r&b/soul'),('neo-soul','r&b/soul'),('funk','r&b/soul'),('soul','r&b/soul'),('alternative r&b','r&b/soul'),
 ('jazz','jazz'),('spiritual jazz','jazz'),('free jazz','jazz'),('jazz fusion','jazz'),
 ('punk','punk'),('hardcore','punk'),('post-punk','punk'),('diy','punk'),
 ('metal','metal'),('black metal','metal'),('doom','metal'),('death metal','metal'),
 ('folk','folk'),('singer-songwriter','folk'),('americana','folk'),('psych folk','folk'),
 ('experimental','experimental'),('noise','experimental'),('avant-garde','experimental'),('improvisation','experimental'),
 ('soundtrack','soundtrack'),('film score','soundtrack'),('video game music','soundtrack'),('library music','soundtrack');

-- 5) Bandcamp 팬 컬렉션 (앨범 페이지 'supported by' → 팬 페이지 크롤)
DROP TABLE IF EXISTS bc_fan_collection;
CREATE TABLE bc_fan_collection (
    fan_id    TEXT NOT NULL,
    item_url  TEXT NOT NULL,
    PRIMARY KEY (fan_id, item_url)
);
CREATE INDEX ix_fan_url ON bc_fan_collection(item_url);

-- 6) 앨범 상세 (앨범 페이지 data-tralbum / ld+json 크롤)
--    art_url: 실제 커버 이미지 주소 (Bandcamp는 art_id로 https://f4.bcbits.com/img/a<art_id>_10.jpg 형태 — 크롤 후 확인)
DROP TABLE IF EXISTS bc_album_detail;
CREATE TABLE bc_album_detail (
    url           TEXT PRIMARY KEY,     -- 앨범 URL (dim_item.url 과 조인)
    art_id        TEXT,
    art_url       TEXT,
    release_date  TEXT,                 -- 'YYYY-MM-DD'
    track_count   INTEGER,
    duration_sec  INTEGER,
    label         TEXT,                 -- 없으면 NULL (자체 발매)
    location      TEXT,                 -- 아티스트 지역 'Seoul, South Korea'
    about         TEXT                  -- 앨범 소개 (첫 문장 정도)
);
