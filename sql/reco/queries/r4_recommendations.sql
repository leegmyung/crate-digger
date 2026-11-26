-- 사용자별 Bandcamp 추천 아티스트 Top 12 (점수 구성요소와 추천 이유 포함)
SELECT user_id || '-' || rank AS reco_id, *
FROM reco_final
ORDER BY user_id, rank;
