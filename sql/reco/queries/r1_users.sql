-- 사용자 요약: 플랫폼, 좋아요 수, 태그 매칭률, 취향 유형(페르소나)
WITH likes AS (
    SELECT user_id, MAX(platform) AS platform,
           COUNT(*) AS liked_tracks, COUNT(DISTINCT artist_key) AS liked_artists
    FROM user_likes GROUP BY user_id
),
matched AS (
    SELECT ua.user_id, COUNT(*) AS tagged_artists
    FROM user_artist ua
    WHERE EXISTS (SELECT 1 FROM ext_artist_tags e WHERE e.artist_key = ua.artist_key)
    GROUP BY ua.user_id
),
seg AS (
    SELECT user_id,
           MAX(CASE WHEN fam_rank = 1 THEN family END)        AS top_family,
           MAX(CASE WHEN fam_rank = 1 THEN share_pct END)     AS top_share_pct,
           MAX(CASE WHEN fam_rank = 2 THEN family END)        AS second_family,
           SUM(CASE WHEN share_pct >= 12 THEN 1 ELSE 0 END)   AS segments
    FROM user_segment GROUP BY user_id
)
SELECT l.user_id, l.platform, l.liked_tracks, l.liked_artists,
       ROUND(100.0 * COALESCE(m.tagged_artists, 0) / l.liked_artists, 0) AS tag_match_pct,
       s.top_family, s.top_share_pct, s.second_family, s.segments,
       -- 취향 유형: 1위 취향군 비중이 60% 이상이면 한 우물형, 12% 이상 취향군이 3개 이상이면 탐험형
       CASE WHEN s.top_share_pct >= 60 THEN '한 우물형'
            WHEN s.segments >= 3       THEN '탐험형'
            ELSE '두 갈래형' END                                     AS persona
FROM likes l
LEFT JOIN matched m USING (user_id)
LEFT JOIN seg s     USING (user_id)
ORDER BY l.user_id;
