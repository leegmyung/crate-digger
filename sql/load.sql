-- =====================================================================
-- stg_salesfeed (크롤 원본) ─▶ 차원/사실 테이블 적재
-- 여러 번 실행해도 중복이 생기지 않도록 INSERT OR IGNORE / UNIQUE 사용
-- (PostgreSQL: INSERT ... ON CONFLICT DO NOTHING)
-- =====================================================================

-- 0) 정리: 공백 제거, 국가코드 대문자, 결제액 없는 행 제외
DROP TABLE IF EXISTS tmp_clean;
CREATE TEMP TABLE tmp_clean AS
SELECT
    replace(trim(utc_date), 'T', ' ')                    AS sold_at_utc,
    trim(artist_name)                                    AS artist_name,
    trim(album_title)                                    AS album_title,
    COALESCE(trim(item_description), '')                 AS item_description,
    lower(trim(item_type))                               AS item_type,
    trim(url)                                            AS url,
    item_price,
    amount_paid,
    amount_paid_usd,
    upper(trim(currency))                                AS currency,
    trim(country)                                        AS country,
    upper(trim(country_code))                            AS country_code,
    tags,
    -- 서브도메인: https://<sub>.bandcamp.com/... (커스텀 도메인이면 NULL)
    CASE WHEN instr(url, '.bandcamp.com') > 0
         THEN substr(url, instr(url, '://') + 3,
                     instr(url, '.bandcamp.com') - instr(url, '://') - 3) END AS subdomain
FROM stg_salesfeed
WHERE amount_paid IS NOT NULL AND url IS NOT NULL AND utc_date IS NOT NULL;

-- 1) 국가: 주요 국가는 지역 매핑, 나머지는 'Other'
INSERT OR IGNORE INTO dim_country (country_code, country_name, region) VALUES
 ('US','United States','North America'), ('CA','Canada','North America'), ('MX','Mexico','Latin America'),
 ('BR','Brazil','Latin America'), ('AR','Argentina','Latin America'), ('CL','Chile','Latin America'),
 ('GB','United Kingdom','Europe'), ('DE','Germany','Europe'), ('FR','France','Europe'),
 ('NL','Netherlands','Europe'), ('BE','Belgium','Europe'), ('IT','Italy','Europe'), ('ES','Spain','Europe'),
 ('SE','Sweden','Europe'), ('NO','Norway','Europe'), ('DK','Denmark','Europe'), ('FI','Finland','Europe'),
 ('IE','Ireland','Europe'), ('CH','Switzerland','Europe'), ('AT','Austria','Europe'), ('PL','Poland','Europe'),
 ('JP','Japan','Asia'), ('KR','South Korea','Asia'), ('CN','China','Asia'), ('TW','Taiwan','Asia'),
 ('SG','Singapore','Asia'), ('ID','Indonesia','Asia'), ('PH','Philippines','Asia'), ('IN','India','Asia'),
 ('AU','Australia','Oceania'), ('NZ','New Zealand','Oceania'), ('ZA','South Africa','Africa');

INSERT OR IGNORE INTO dim_country (country_code, country_name, region)
SELECT country_code, MAX(country), 'Other'
FROM tmp_clean WHERE country_code IS NOT NULL AND country_code <> ''
GROUP BY country_code;

-- 2) 통화: 크롤 데이터에서 평균 환율 역산 (amount_paid_usd / amount_paid)
INSERT OR IGNORE INTO dim_currency (currency, usd_rate)
SELECT currency, AVG(amount_paid_usd / amount_paid)
FROM tmp_clean
WHERE amount_paid > 0 AND amount_paid_usd > 0
GROUP BY currency;

-- 3) 아티스트 (서브도메인 기준, 없으면 이름 기준)
INSERT OR IGNORE INTO dim_artist (artist_name, subdomain)
SELECT MAX(artist_name), COALESCE(subdomain, lower(replace(artist_name, ' ', '')))
FROM tmp_clean
GROUP BY COALESCE(subdomain, lower(replace(artist_name, ' ', '')));

-- 4) 상품: item_description 텍스트로 포맷 분류
INSERT OR IGNORE INTO dim_item (url, artist_id, title, item_type, item_description, format, list_price, currency)
SELECT
    t.url,
    a.artist_id,
    MAX(t.album_title),
    t.item_type,
    t.item_description,
    CASE
      WHEN MAX(t.item_type) = 'a' THEN 'Digital album'
      WHEN MAX(t.item_type) = 't' THEN 'Digital track'
      WHEN lower(MAX(t.item_description)) LIKE '%vinyl%'
        OR lower(MAX(t.item_description)) LIKE '%lp%'
        OR lower(MAX(t.item_description)) LIKE '%7"%'   THEN 'Vinyl'
      WHEN lower(MAX(t.item_description)) LIKE '%cassette%'
        OR lower(MAX(t.item_description)) LIKE '%tape%' THEN 'Cassette'
      WHEN lower(MAX(t.item_description)) LIKE '%cd%'
        OR lower(MAX(t.item_description)) LIKE '%compact disc%' THEN 'CD'
      WHEN lower(MAX(t.item_description)) LIKE '%shirt%'
        OR lower(MAX(t.item_description)) LIKE '%hoodie%'
        OR lower(MAX(t.item_description)) LIKE '%sweat%' THEN 'Apparel'
      ELSE 'Other merch'
    END,
    MAX(t.item_price),
    MAX(t.currency)
FROM tmp_clean t
JOIN dim_artist a
  ON a.subdomain = COALESCE(t.subdomain, lower(replace(t.artist_name, ' ', '')))
GROUP BY t.url, t.item_type, t.item_description, a.artist_id;

-- 5) 판매
INSERT OR IGNORE INTO fact_sales
    (item_id, sold_at_utc, sale_date, country_code, currency,
     item_price, amount_paid, amount_paid_usd, item_price_usd)
SELECT
    i.item_id,
    t.sold_at_utc,
    substr(t.sold_at_utc, 1, 10),
    NULLIF(t.country_code, ''),
    t.currency,
    t.item_price,
    t.amount_paid,
    COALESCE(t.amount_paid_usd, t.amount_paid * cur.usd_rate),
    CASE WHEN t.amount_paid > 0
         THEN COALESCE(t.amount_paid_usd, t.amount_paid * cur.usd_rate) * t.item_price / t.amount_paid
         ELSE t.item_price * cur.usd_rate END
FROM tmp_clean t
JOIN dim_item i          ON i.url = t.url AND i.item_type = t.item_type
                        AND i.item_description = t.item_description
LEFT JOIN dim_currency cur ON cur.currency = t.currency;

-- 6) 태그 (있을 때만): 'ambient|electronic|drone' → 행 분리, 첫 태그를 대표 장르로
WITH RECURSIVE split(url, item_type, item_description, tag, rest, pos) AS (
    SELECT DISTINCT url, item_type, item_description, '', tags || '|', 0
    FROM tmp_clean WHERE tags IS NOT NULL AND tags <> ''
    UNION ALL
    SELECT url, item_type, item_description,
           trim(substr(rest, 1, instr(rest, '|') - 1)),
           substr(rest, instr(rest, '|') + 1),
           pos + 1
    FROM split WHERE rest <> ''
)
INSERT OR IGNORE INTO item_tags (item_id, tag, is_genre)
SELECT i.item_id, lower(s.tag), MAX(CASE WHEN s.pos = 1 THEN 1 ELSE 0 END)
FROM split s
JOIN dim_item i ON i.url = s.url AND i.item_type = s.item_type
               AND i.item_description = s.item_description
WHERE s.tag <> ''
GROUP BY i.item_id, lower(s.tag);

DROP TABLE IF EXISTS tmp_clean;
