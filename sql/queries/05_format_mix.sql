-- 포맷별 판매: 디지털 앨범/트랙, 바이닐, CD, 카세트, 의류, 기타 굿즈 (최근 28일)
WITH base AS (
    SELECT format, channel,
           COUNT(*)              AS sales,
           SUM(amount_paid_usd)  AS revenue,
           AVG(amount_paid_usd)  AS avg_paid,
           AVG(item_price_usd)   AS avg_list,
           AVG(paid_over)        AS overpay
    FROM v_sales
    WHERE sale_date > (SELECT date(MAX(sale_date), '-28 days') FROM fact_sales)
    GROUP BY format, channel
)
SELECT
    format,
    channel,
    sales,
    ROUND(revenue, 0)                                        AS revenue_usd,
    ROUND(avg_paid, 2)                                       AS avg_paid_usd,
    ROUND(avg_list, 2)                                       AS avg_list_usd,
    ROUND(100.0 * overpay, 1)                                AS overpay_rate_pct,
    ROUND(100.0 * revenue / SUM(revenue) OVER (), 1)         AS revenue_share_pct,
    ROUND(100.0 * sales   / SUM(sales)   OVER (), 1)         AS sales_share_pct
FROM base
ORDER BY revenue DESC;
