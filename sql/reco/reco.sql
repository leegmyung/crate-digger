-- =====================================================================
-- 취향 벡터 · 세분화 · Bandcamp 아티스트 추천 점수
--   점수 = 0.55·태그 유사도 + 0.25·팬 공동구매 + 0.10·최근 상승세 + 0.10·발굴(덜 알려진 정도)
--   다양성: 한 취향군에서 최대 4팀, 사용자당 12팀
-- 벡터 표기: (주체, tag, w).  'fam:xxx' 는 취향군 가상 태그 (어휘가 달라도 이어지도록 0.5배)
-- =====================================================================

-- 1) 사용자 × 아티스트 (좋아요 곡 수)
DROP TABLE IF EXISTS user_artist;
CREATE TABLE user_artist AS
SELECT user_id, artist_key, MAX(primary_artist) AS artist_name, COUNT(*) AS likes
FROM user_likes GROUP BY user_id, artist_key;

-- 2) 좋아요 아티스트 벡터 (외부 태그 + 취향군)
DROP TABLE IF EXISTS liked_artist_vec;
CREATE TABLE liked_artist_vec AS
WITH raw AS (
    SELECT artist_key, tag, weight AS w FROM ext_artist_tags
    UNION ALL
    SELECT e.artist_key, 'fam:' || f.family, 0.5 * MAX(e.weight)
    FROM ext_artist_tags e JOIN tag_family f ON f.tag = e.tag
    GROUP BY e.artist_key, f.family
),
n AS (SELECT artist_key, sqrt(SUM(w * w)) AS norm FROM raw GROUP BY artist_key)
SELECT r.artist_key, r.tag, r.w / n.norm AS w
FROM raw r JOIN n USING (artist_key);

-- 3) 사용자 취향 벡터 = Σ(아티스트 좋아요 수 × 아티스트 벡터), 정규화
DROP TABLE IF EXISTS user_taste;
CREATE TABLE user_taste AS
WITH raw AS (
    SELECT ua.user_id, v.tag, SUM(ua.likes * v.w) AS w
    FROM user_artist ua JOIN liked_artist_vec v USING (artist_key)
    GROUP BY ua.user_id, v.tag
),
n AS (SELECT user_id, sqrt(SUM(w * w)) AS norm FROM raw GROUP BY user_id)
SELECT r.user_id, r.tag, r.w / n.norm AS w
FROM raw r JOIN n USING (user_id);

-- 4) 세분화: 사용자별 취향군 비중 (좋아요 곡 × 태그 가중치를 취향군으로 합산)
DROP TABLE IF EXISTS user_segment;
CREATE TABLE user_segment AS
WITH fam AS (
    SELECT ua.user_id, f.family, SUM(ua.likes * e.weight) AS w
    FROM user_artist ua
    JOIN ext_artist_tags e USING (artist_key)
    JOIN tag_family f ON f.tag = e.tag
    GROUP BY ua.user_id, f.family
)
SELECT user_id, family,
       ROUND(100.0 * w / SUM(w) OVER (PARTITION BY user_id), 1)             AS share_pct,
       ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY w DESC)            AS fam_rank
FROM fam;

-- 5) Bandcamp 아티스트 벡터 (상품 태그 빈도, 대표 장르 1.0 / 서브 태그 0.6) + 대표 취향군
DROP TABLE IF EXISTS bc_artist_vec;
CREATE TABLE bc_artist_vec AS
WITH t AS (
    SELECT i.artist_id, it.tag, SUM(CASE WHEN it.is_genre = 1 THEN 1.0 ELSE 0.6 END) AS w
    FROM item_tags it JOIN dim_item i ON i.item_id = it.item_id
    GROUP BY i.artist_id, it.tag
),
raw AS (
    SELECT artist_id, tag, w FROM t
    UNION ALL
    SELECT t.artist_id, 'fam:' || f.family, 0.5 * MAX(t.w)
    FROM t JOIN tag_family f ON f.tag = t.tag
    GROUP BY t.artist_id, f.family
),
n AS (SELECT artist_id, sqrt(SUM(w * w)) AS norm FROM raw GROUP BY artist_id)
SELECT r.artist_id, r.tag, r.w / n.norm AS w
FROM raw r JOIN n USING (artist_id);

DROP TABLE IF EXISTS bc_artist_family;
CREATE TABLE bc_artist_family AS
SELECT artist_id, family FROM (
    SELECT i.artist_id, f.family,
           ROW_NUMBER() OVER (PARTITION BY i.artist_id ORDER BY COUNT(*) DESC, f.family) AS rn
    FROM item_tags it
    JOIN dim_item i   ON i.item_id = it.item_id
    JOIN tag_family f ON f.tag = it.tag
    WHERE it.is_genre = 1
    GROUP BY i.artist_id, f.family
) WHERE rn = 1;

-- 6) 태그 유사도 (코사인: 두 벡터 모두 정규화되어 있으므로 내적)
DROP TABLE IF EXISTS reco_sim;
CREATE TABLE reco_sim AS
SELECT u.user_id, a.artist_id, SUM(u.w * a.w) AS sim
FROM user_taste u JOIN bc_artist_vec a ON a.tag = u.tag
GROUP BY u.user_id, a.artist_id;

-- 7) 팬 공동구매: 유사도 상위 15팀(시드)을 산 팬들이 함께 산 아티스트 비율
DROP TABLE IF EXISTS reco_cofan;
CREATE TABLE reco_cofan AS
WITH fan_artist AS (
    SELECT DISTINCT c.fan_id, i.artist_id
    FROM bc_fan_collection c JOIN dim_item i ON i.url = c.item_url
),
seed AS (
    SELECT user_id, artist_id FROM (
        SELECT user_id, artist_id, ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY sim DESC) AS rn
        FROM reco_sim) WHERE rn <= 15
),
seed_fans AS (
    SELECT DISTINCT s.user_id, fa.fan_id
    FROM seed s JOIN fan_artist fa ON fa.artist_id = s.artist_id
),
co AS (
    SELECT sf.user_id, fa.artist_id, COUNT(DISTINCT sf.fan_id) AS fans
    FROM seed_fans sf JOIN fan_artist fa ON fa.fan_id = sf.fan_id
    GROUP BY sf.user_id, fa.artist_id
)
SELECT user_id, artist_id, fans,
       1.0 * fans / MAX(fans) OVER (PARTITION BY user_id) AS cofan
FROM co;

-- 8) 판매 지표 (최근 28일 / 최근 7일 vs 직전 7일)
DROP TABLE IF EXISTS bc_artist_stats;
CREATE TABLE bc_artist_stats AS
WITH b AS (SELECT MAX(sale_date) AS d FROM fact_sales),
s AS (
    SELECT i.artist_id,
           SUM(CASE WHEN f.sale_date > date(b.d, '-28 days') THEN 1 ELSE 0 END) AS sales_28d,
           SUM(CASE WHEN f.sale_date > date(b.d, '-7 days')  THEN 1 ELSE 0 END) AS sales_7d,
           SUM(CASE WHEN f.sale_date <= date(b.d, '-7 days')
                     AND f.sale_date >  date(b.d, '-14 days') THEN 1 ELSE 0 END) AS sales_prev7
    FROM fact_sales f JOIN dim_item i ON i.item_id = f.item_id CROSS JOIN b
    GROUP BY i.artist_id
)
SELECT artist_id, sales_28d, sales_7d, sales_prev7,
       -- 상승세 0~1 : (7일 - 직전7일)/(직전7일+5) 를 -1~1로 자르고 0~1로 변환
       (MAX(-1.0, MIN(1.0, 1.0 * (sales_7d - sales_prev7) / (sales_prev7 + 5))) + 1) / 2 AS momentum,
       -- 발굴 0~1 : 판매가 적을수록 높음 (로그 스케일)
       1 - ln(1 + sales_28d) / (SELECT ln(1 + MAX(sales_28d)) FROM s)                     AS discovery
FROM s;

-- 9) 최종 점수
DROP TABLE IF EXISTS reco_score;
CREATE TABLE reco_score AS
WITH m AS (SELECT user_id, MAX(sim) AS max_sim FROM reco_sim GROUP BY user_id)
SELECT s.user_id, s.artist_id, fam.family,
       s.sim / m.max_sim                                  AS tag_score,
       COALESCE(c.cofan, 0)                               AS cofan_score,
       COALESCE(st.momentum, 0.5)                         AS momentum_score,
       COALESCE(st.discovery, 1)                          AS discovery_score,
       COALESCE(st.sales_28d, 0)                          AS sales_28d,
       0.55 * s.sim / m.max_sim + 0.25 * COALESCE(c.cofan, 0)
     + 0.10 * COALESCE(st.momentum, 0.5) + 0.10 * COALESCE(st.discovery, 1) AS score
FROM reco_sim s
JOIN m USING (user_id)
LEFT JOIN reco_cofan c       ON c.user_id = s.user_id AND c.artist_id = s.artist_id
LEFT JOIN bc_artist_stats st ON st.artist_id = s.artist_id
LEFT JOIN bc_artist_family fam ON fam.artist_id = s.artist_id;

-- 10) 다양성 적용한 최종 추천 + 추천 이유
DROP TABLE IF EXISTS reco_final;
CREATE TABLE reco_final AS
WITH ranked AS (
    SELECT r.*, ROW_NUMBER() OVER (PARTITION BY user_id, family ORDER BY score DESC) AS fam_rn
    FROM reco_score r
),
picked AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY score DESC) AS rank
    FROM ranked WHERE fam_rn <= 4
),
top AS (SELECT * FROM picked WHERE rank <= 12),
-- 가장 닮은 '내가 좋아요한 아티스트'
bridge AS (
    SELECT t.user_id, t.artist_id, ua.artist_name AS liked_artist,
           ROW_NUMBER() OVER (PARTITION BY t.user_id, t.artist_id ORDER BY SUM(l.w * a.w) DESC, ua.likes DESC) AS rn
    FROM top t
    JOIN user_artist ua      ON ua.user_id = t.user_id
    JOIN liked_artist_vec l  ON l.artist_key = ua.artist_key AND l.tag NOT LIKE 'fam:%'
    JOIN bc_artist_vec a     ON a.artist_id = t.artist_id AND a.tag = l.tag
    GROUP BY t.user_id, t.artist_id, ua.artist_key
),
-- 겹치는 태그 상위 2개
shared AS (
    SELECT user_id, artist_id, group_concat(tag, ', ') AS tags FROM (
        SELECT t.user_id, t.artist_id, u.tag,
               ROW_NUMBER() OVER (PARTITION BY t.user_id, t.artist_id ORDER BY u.w * a.w DESC) AS rn
        FROM top t
        JOIN user_taste u    ON u.user_id = t.user_id AND u.tag NOT LIKE 'fam:%'
        JOIN bc_artist_vec a ON a.artist_id = t.artist_id AND a.tag = u.tag
    ) WHERE rn <= 2 GROUP BY user_id, artist_id
),
-- 대표 앨범 (가장 많이 팔린 디지털 앨범) + 앨범 페이지 상세
album AS (
    SELECT artist_id, title, url, price FROM (
        SELECT i.artist_id, i.title, i.url, i.list_price * COALESCE(c.usd_rate, 1) AS price,
               ROW_NUMBER() OVER (PARTITION BY i.artist_id ORDER BY COUNT(f.sale_id) DESC, i.item_id) AS rn
        FROM dim_item i
        LEFT JOIN fact_sales f   ON f.item_id = i.item_id
        LEFT JOIN dim_currency c ON c.currency = i.currency
        WHERE i.item_type = 'a'
        GROUP BY i.item_id
    ) WHERE rn = 1
),
-- 같은 앨범 URL로 파는 실물 포맷 (바이닐/CD/카세트)
formats AS (
    SELECT al.url, group_concat(DISTINCT i.format) AS physical_formats
    FROM album al JOIN dim_item i ON i.url = al.url AND i.item_type = 'p'
    GROUP BY al.url
),
-- 앨범 서포터(이 앨범을 컬렉션에 담은 팬) 수
supporters AS (
    SELECT al.url, COUNT(*) AS supporters
    FROM album al JOIN bc_fan_collection c ON c.item_url = al.url
    GROUP BY al.url
),
-- 앨범 태그 상위 3개 (대표 장르 먼저)
album_tags AS (
    SELECT url, group_concat(tag, ', ') AS tags FROM (
        SELECT al.url, it.tag,
               ROW_NUMBER() OVER (PARTITION BY al.url ORDER BY it.is_genre DESC, it.tag) AS rn
        FROM album al
        JOIN dim_item i   ON i.url = al.url AND i.item_type = 'a'
        JOIN item_tags it ON it.item_id = i.item_id
    ) WHERE rn <= 3 GROUP BY url
)
SELECT t.user_id, t.rank, ar.artist_name, t.family,
       al.title AS album_title, al.url AS album_url, ROUND(al.price, 2) AS album_price_usd,
       dt.art_url, dt.release_date, dt.track_count,
       CAST(dt.duration_sec / 60 AS INTEGER)  AS duration_min,
       COALESCE(dt.label, '자체 발매')         AS label,
       dt.location, dt.about,
       fm.physical_formats, COALESCE(sp.supporters, 0) AS supporters, atg.tags AS album_tags,
       ROUND(100 * t.score, 1)            AS score,
       ROUND(100 * t.tag_score, 0)        AS tag_pct,
       ROUND(100 * t.cofan_score, 0)      AS cofan_pct,
       ROUND(100 * t.momentum_score, 0)   AS momentum_pct,
       ROUND(100 * t.discovery_score, 0)  AS discovery_pct,
       t.sales_28d,
       b.liked_artist                     AS because_artist,
       sh.tags                            AS because_tags
FROM top t
JOIN dim_artist ar ON ar.artist_id = t.artist_id
LEFT JOIN bridge b  ON b.user_id = t.user_id AND b.artist_id = t.artist_id AND b.rn = 1
LEFT JOIN shared sh ON sh.user_id = t.user_id AND sh.artist_id = t.artist_id
LEFT JOIN album al  ON al.artist_id = t.artist_id
LEFT JOIN bc_album_detail dt ON dt.url = al.url
LEFT JOIN formats fm    ON fm.url = al.url
LEFT JOIN supporters sp ON sp.url = al.url
LEFT JOIN album_tags atg ON atg.url = al.url;
