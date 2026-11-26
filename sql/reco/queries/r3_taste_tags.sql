-- 사용자별 상위 취향 태그 8개 (취향 벡터 가중치, 사용자 내 비중 %)
WITH t AS (
    SELECT user_id, tag, w,
           ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY w DESC) AS rn
    FROM user_taste WHERE tag NOT LIKE 'fam:%'
)
SELECT user_id, tag, rn AS tag_rank,
       ROUND(100.0 * w / SUM(w) OVER (PARTITION BY user_id), 1) AS weight_pct
FROM t WHERE rn <= 8
ORDER BY user_id, rn;
