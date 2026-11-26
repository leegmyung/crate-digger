-- 취향 세분화: 사용자별 취향군 비중
SELECT user_id, family, share_pct, fam_rank
FROM user_segment
ORDER BY user_id, fam_rank;
