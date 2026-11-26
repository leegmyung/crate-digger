-- 대표 장르별 매출 (최근 28일) — item_tags가 채워져 있을 때만 결과가 나옴
WITH recent AS (
    SELECT * FROM v_sales
    WHERE sale_date > (SELECT date(MAX(sale_date), '-28 days') FROM fact_sales)
)
SELECT
    t.tag                                                    AS genre,
    COUNT(*)                                                 AS sales,
    ROUND(SUM(r.amount_paid_usd), 0)                         AS revenue_usd,
    ROUND(AVG(r.amount_paid_usd), 2)                         AS avg_paid_usd,
    ROUND(100.0 * SUM(r.amount_paid_usd)
          / SUM(SUM(r.amount_paid_usd)) OVER (), 1)          AS revenue_share_pct
FROM recent r
JOIN item_tags t ON t.item_id = r.item_id AND t.is_genre = 1
GROUP BY t.tag
ORDER BY revenue_usd DESC
LIMIT 12;
