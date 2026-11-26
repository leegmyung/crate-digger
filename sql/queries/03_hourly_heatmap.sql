-- 요일 × 시간대(UTC) 판매 건수 (최근 28일)
SELECT
    weekday_utc,                       -- 0=일 ... 6=토
    hour_utc,                          -- 0 ~ 23
    COUNT(*) AS sales
FROM v_sales
WHERE sale_date > (SELECT date(MAX(sale_date), '-28 days') FROM fact_sales)
GROUP BY weekday_utc, hour_utc
ORDER BY weekday_utc, hour_utc;
