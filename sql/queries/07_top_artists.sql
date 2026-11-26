-- 매출 상위 아티스트 Top 15 (최근 28일): 점유율, 최대 구매 국가, 실물 매출 비중
WITH recent AS (
    SELECT * FROM v_sales
    WHERE sale_date > (SELECT date(MAX(sale_date), '-28 days') FROM fact_sales)
),
by_artist AS (
    SELECT artist_id, artist_name,
           COUNT(*)                                                         AS sales,
           SUM(amount_paid_usd)                                             AS revenue,
           SUM(CASE WHEN channel = 'Physical' THEN amount_paid_usd END)     AS physical_rev
    FROM recent GROUP BY artist_id, artist_name
),
by_artist_country AS (
    SELECT artist_id, country_code,
           ROW_NUMBER() OVER (PARTITION BY artist_id ORDER BY COUNT(*) DESC, country_code) AS rn
    FROM recent GROUP BY artist_id, country_code
)
SELECT
    RANK() OVER (ORDER BY a.revenue DESC)                              AS rank,
    a.artist_name,
    a.sales,
    ROUND(a.revenue, 0)                                                AS revenue_usd,
    ROUND(100.0 * a.revenue / (SELECT SUM(amount_paid_usd) FROM recent), 2) AS revenue_share_pct,
    c.country_code                                                     AS top_country,
    ROUND(100.0 * COALESCE(a.physical_rev, 0) / a.revenue, 0)          AS physical_share_pct
FROM by_artist a
JOIN by_artist_country c ON c.artist_id = a.artist_id AND c.rn = 1
ORDER BY a.revenue DESC
LIMIT 15;
