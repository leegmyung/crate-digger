-- "원하는 만큼 내기": 정가 대비 실제 결제 비율 분포 (디지털 상품, 최근 28일)
WITH b AS (
    SELECT CASE
             WHEN pay_ratio < 1.005 THEN 1
             WHEN pay_ratio < 1.25  THEN 2
             WHEN pay_ratio < 1.5   THEN 3
             WHEN pay_ratio < 2.0   THEN 4
             ELSE 5
           END AS bucket_order
    FROM v_sales
    WHERE channel = 'Digital' AND pay_ratio IS NOT NULL
      AND sale_date > (SELECT date(MAX(sale_date), '-28 days') FROM fact_sales)
)
SELECT
    bucket_order,
    CASE bucket_order
      WHEN 1 THEN '정가'
      WHEN 2 THEN '+1~24%'
      WHEN 3 THEN '+25~49%'
      WHEN 4 THEN '+50~99%'
      ELSE        '2배 이상'
    END                                                       AS bucket,
    COUNT(*)                                                  AS sales,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1)        AS share_pct
FROM b
GROUP BY bucket_order
ORDER BY bucket_order;
