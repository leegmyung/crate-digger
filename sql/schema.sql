-- =====================================================================
-- Bandcamp Sales Pulse : 스키마 (SQLite 3.35+ / PostgreSQL 호환 위주)
-- ---------------------------------------------------------------------
-- 흐름:  크롤러 CSV ─▶ stg_salesfeed (원본 그대로)
--                     ─▶ load.sql ─▶ dim_* / fact_sales (정규화)
--                     ─▶ v_sales (분석용 뷰) ─▶ queries/*.sql ─▶ 대시보드
-- PostgreSQL에서 쓸 때: TEXT 날짜 → TIMESTAMPTZ, REAL → NUMERIC(12,2),
--                     INTEGER PRIMARY KEY → BIGSERIAL 로 바꾸면 됩니다.
-- =====================================================================

-- 1) 스테이징: 판매 피드(salesfeed) 이벤트를 크롤링한 원본 그대로 적재
--    컬럼명은 Bandcamp 판매 피드 JSON 필드명을 따름 (크롤 후 실제 키 확인 필요)
DROP TABLE IF EXISTS stg_salesfeed;
CREATE TABLE stg_salesfeed (
    utc_date          TEXT,     -- 판매 시각 (UTC). 예: '2026-11-06 21:14:03'
    artist_name       TEXT,
    album_title       TEXT,     -- 앨범명 (트랙 판매일 때는 소속 앨범)
    item_description  TEXT,     -- 상품명/포맷. 예: 'Vinyl LP', 'Cassette', 'T-Shirt'
    item_type         TEXT,     -- 'a'=디지털 앨범, 't'=디지털 트랙, 'p'=실물(음반·머치)
    url               TEXT,     -- 상품 URL (상품 식별자로 사용)
    item_price        REAL,     -- 정가 (현지 통화)
    amount_paid       REAL,     -- 실제 결제액 (현지 통화)
    amount_paid_usd   REAL,     -- 실제 결제액 (USD 환산)
    currency          TEXT,     -- 'USD', 'GBP', 'EUR', 'JPY' ...
    country           TEXT,     -- 구매자 국가명
    country_code      TEXT,     -- ISO-3166 alpha-2 (소문자/대문자 무관)
    tags              TEXT      -- (선택) 앨범 페이지에서 크롤링한 태그, '|' 구분
);

-- 2) 차원 테이블 ---------------------------------------------------------
DROP TABLE IF EXISTS fact_sales;
DROP TABLE IF EXISTS item_tags;
DROP TABLE IF EXISTS dim_item;
DROP TABLE IF EXISTS dim_artist;
DROP TABLE IF EXISTS dim_country;
DROP TABLE IF EXISTS dim_currency;

CREATE TABLE dim_country (
    country_code  TEXT PRIMARY KEY,          -- 'US', 'KR' ...
    country_name  TEXT NOT NULL,
    region        TEXT                       -- 'North America', 'Europe', 'Asia' ...
);

CREATE TABLE dim_currency (
    currency      TEXT PRIMARY KEY,          -- 'USD'
    usd_rate      REAL                       -- 1 단위 = ? USD (amount_paid_usd 누락 시 보정용)
);

CREATE TABLE dim_artist (
    artist_id     INTEGER PRIMARY KEY,
    artist_name   TEXT NOT NULL,
    subdomain     TEXT UNIQUE                -- 'someband' (https://someband.bandcamp.com)
);

CREATE TABLE dim_item (
    item_id          INTEGER PRIMARY KEY,
    url              TEXT NOT NULL,          -- 실물 상품은 앨범 URL을 공유할 수 있음
    artist_id        INTEGER NOT NULL REFERENCES dim_artist(artist_id),
    title            TEXT,
    item_type        TEXT NOT NULL CHECK (item_type IN ('a','t','p')),
    item_description TEXT,
    format           TEXT NOT NULL           -- 정규화된 포맷 (load.sql의 CASE 규칙)
                     CHECK (format IN ('Digital album','Digital track','Vinyl','CD',
                                       'Cassette','Apparel','Other merch')),
    list_price       REAL,                   -- 정가 (현지 통화)
    currency         TEXT REFERENCES dim_currency(currency),
    UNIQUE (url, item_type, item_description)  -- 같은 앨범의 디지털/바이닐/CD를 구분
);

-- 장르/태그 (판매 피드엔 없음 → 앨범 페이지 data-tralbum 크롤 시 채움)
CREATE TABLE item_tags (
    item_id  INTEGER NOT NULL REFERENCES dim_item(item_id),
    tag      TEXT    NOT NULL,
    is_genre INTEGER NOT NULL DEFAULT 0,     -- 1 = 대표 장르 태그
    PRIMARY KEY (item_id, tag)
);

-- 3) 사실 테이블: 판매 1건 = 1행 -------------------------------------------
CREATE TABLE fact_sales (
    sale_id          INTEGER PRIMARY KEY,
    item_id          INTEGER NOT NULL REFERENCES dim_item(item_id),
    sold_at_utc      TEXT    NOT NULL,       -- ISO 8601
    sale_date        TEXT    NOT NULL,       -- 'YYYY-MM-DD' (UTC)
    country_code     TEXT    REFERENCES dim_country(country_code),
    currency         TEXT    REFERENCES dim_currency(currency),
    item_price       REAL,                   -- 정가 (현지 통화)
    amount_paid      REAL    NOT NULL,       -- 결제액 (현지 통화)
    amount_paid_usd  REAL    NOT NULL,       -- 결제액 (USD)
    item_price_usd   REAL,                   -- 정가 USD 환산 = amount_paid_usd * item_price / amount_paid
    UNIQUE (item_id, sold_at_utc, country_code, amount_paid)  -- 크롤 중복 방지
);

CREATE INDEX ix_sales_date    ON fact_sales(sale_date);
CREATE INDEX ix_sales_country ON fact_sales(country_code);
CREATE INDEX ix_sales_item    ON fact_sales(item_id);

-- 4) 분석용 뷰 ------------------------------------------------------------
DROP VIEW IF EXISTS v_sales;
CREATE VIEW v_sales AS
SELECT
    s.sale_id,
    s.sold_at_utc,
    s.sale_date,
    CAST(strftime('%H', s.sold_at_utc) AS INTEGER) AS hour_utc,   -- PG: EXTRACT(HOUR FROM ...)
    CAST(strftime('%w', s.sold_at_utc) AS INTEGER) AS weekday_utc, -- 0=일 ... 6=토 (PG: EXTRACT(DOW ...))
    s.country_code,
    c.country_name,
    c.region,
    s.currency,
    s.amount_paid,
    s.amount_paid_usd,
    s.item_price_usd,
    CASE WHEN s.item_price_usd > 0
         THEN s.amount_paid_usd / s.item_price_usd END             AS pay_ratio,   -- 1.0 = 정가 그대로
    CASE WHEN s.amount_paid_usd > s.item_price_usd * 1.005
         THEN 1 ELSE 0 END                                         AS paid_over,   -- 정가 초과 결제
    i.item_id,
    i.title,
    i.item_type,
    i.format,
    CASE WHEN i.item_type IN ('a','t') THEN 'Digital' ELSE 'Physical' END AS channel,
    a.artist_id,
    a.artist_name
FROM fact_sales s
JOIN dim_item    i ON i.item_id   = s.item_id
JOIN dim_artist  a ON a.artist_id = i.artist_id
LEFT JOIN dim_country c ON c.country_code = s.country_code;
