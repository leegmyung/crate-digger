-- 핵심 지표: 최근 7일 vs 직전 7일 (데이터의 마지막 날짜 기준)
WITH bounds AS (
    SELECT MAX(sale_date) AS end_date FROM fact_sales
),
tagged AS (
    SELECT v.*,
           CASE WHEN v.sale_date >  date(b.end_date, '-7 days')  THEN 'cur'
                WHEN v.sale_date >  date(b.end_date, '-14 days') THEN 'prev' END AS period
    FROM v_sales v CROSS JOIN bounds b
),
agg AS (
    SELECT period,
           COUNT(*)                          AS sales,
           SUM(amount_paid_usd)              AS revenue,
           AVG(amount_paid_usd)              AS avg_paid,
           100.0 * AVG(paid_over)            AS overpay_rate,
           COUNT(DISTINCT artist_id)         AS artists,
           COUNT(DISTINCT country_code)      AS countries
    FROM tagged WHERE period IS NOT NULL
    GROUP BY period
)
SELECT
    (SELECT date(end_date, '-6 days') FROM bounds)                      AS period_start,
    (SELECT end_date FROM bounds)                                       AS period_end,
    c.sales                                                             AS sales_cur,
    p.sales                                                             AS sales_prev,
    ROUND(100.0 * (c.sales - p.sales) / p.sales, 1)                     AS sales_chg_pct,
    ROUND(c.revenue, 0)                                                 AS revenue_cur,
    ROUND(p.revenue, 0)                                                 AS revenue_prev,
    ROUND(100.0 * (c.revenue - p.revenue) / p.revenue, 1)               AS revenue_chg_pct,
    ROUND(c.avg_paid, 2)                                                AS avg_paid_cur,
    ROUND(p.avg_paid, 2)                                                AS avg_paid_prev,
    ROUND(100.0 * (c.avg_paid - p.avg_paid) / p.avg_paid, 1)            AS avg_paid_chg_pct,
    ROUND(c.overpay_rate, 1)                                            AS overpay_rate_cur,
    ROUND(p.overpay_rate, 1)                                            AS overpay_rate_prev,
    ROUND(c.overpay_rate - p.overpay_rate, 1)                           AS overpay_chg_pt,
    c.artists                                                           AS artists_cur,
    c.countries                                                         AS countries_cur
FROM agg c JOIN agg p ON c.period = 'cur' AND p.period = 'prev';
