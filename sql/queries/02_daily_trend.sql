-- 일별 판매 추이 (최근 28일): 디지털 vs 실물 매출
SELECT
    sale_date,
    COUNT(*)                                                         AS sales,
    ROUND(SUM(amount_paid_usd), 2)                                   AS revenue_usd,
    ROUND(SUM(CASE WHEN channel = 'Digital'  THEN amount_paid_usd ELSE 0 END), 2) AS digital_usd,
    ROUND(SUM(CASE WHEN channel = 'Physical' THEN amount_paid_usd ELSE 0 END), 2) AS physical_usd
FROM v_sales
WHERE sale_date > (SELECT date(MAX(sale_date), '-28 days') FROM fact_sales)
GROUP BY sale_date
ORDER BY sale_date;
