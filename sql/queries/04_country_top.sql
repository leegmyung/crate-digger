-- 국가별 매출 순위 Top 15 (최근 28일) + 매출 점유율
WITH base AS (
    SELECT country_code, country_name, region,
           COUNT(*)              AS sales,
           SUM(amount_paid_usd)  AS revenue
    FROM v_sales
    WHERE sale_date > (SELECT date(MAX(sale_date), '-28 days') FROM fact_sales)
    GROUP BY country_code, country_name, region
)
SELECT
    RANK() OVER (ORDER BY revenue DESC)                      AS rank,
    country_code,
    country_name,
    region,
    sales,
    ROUND(revenue, 0)                                        AS revenue_usd,
    ROUND(revenue / sales, 2)                                AS avg_paid_usd,
    ROUND(100.0 * revenue / SUM(revenue) OVER (), 1)         AS revenue_share_pct
FROM base
ORDER BY revenue DESC
LIMIT 15;
