-- 나의 취향 리포트: 취향 지표 + 이번 추천을 만든 알고리즘 기여도 (사용자당 1행)
WITH seg AS (
    SELECT user_id,
           -- 취향 다양성 지수: 취향군 비중의 정규화 엔트로피 (0 = 한 장르만, 100 = 12개 장르에 고르게)
           ROUND(100.0 * -SUM((share_pct / 100.0) * ln(share_pct / 100.0)) / ln(12), 0) AS diversity_idx
    FROM user_segment WHERE share_pct > 0 GROUP BY user_id
),
hidden AS (   -- 의외의 취향: 3위 이하 중 비중 3% 이상인 가장 큰 취향군
    SELECT user_id, family AS hidden_family, share_pct AS hidden_share_pct FROM (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY share_pct DESC) AS rn
        FROM user_segment WHERE fam_rank >= 3 AND share_pct >= 3)
    WHERE rn = 1
),
fav AS (      -- 최애 아티스트: 좋아요 곡이 가장 많은 아티스트
    SELECT user_id, artist_name AS fav_artist, likes AS fav_likes FROM (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY likes DESC, artist_name) AS rn FROM user_artist)
    WHERE rn = 1
),
sig AS (      -- 시그니처 태그: 취향 벡터 1위 태그
    SELECT user_id, tag AS signature_tag FROM (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY w DESC) AS rn
        FROM user_taste WHERE tag NOT LIKE 'fam:%')
    WHERE rn = 1
),
algo AS (     -- 추천 12팀 점수에서 각 요소가 차지한 몫 (가중치 × 점수의 합 기준)
    SELECT user_id,
           SUM(0.55 * tag_pct)       AS c_tag,
           SUM(0.25 * cofan_pct)     AS c_cofan,
           SUM(0.10 * momentum_pct)  AS c_mom,
           SUM(0.10 * discovery_pct) AS c_disc,
           AVG(discovery_pct)        AS avg_discovery,
           AVG(sales_28d)            AS avg_sales,
           COUNT(DISTINCT family)    AS reco_families
    FROM reco_final GROUP BY user_id
),
fans AS (     -- 내 취향과 닮은 Bandcamp 팬 수 (유사도 상위 15팀을 산 팬)
    SELECT s.user_id, COUNT(DISTINCT c.fan_id) AS twin_fans
    FROM (SELECT user_id, artist_id FROM (
            SELECT user_id, artist_id, ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY sim DESC) AS rn FROM reco_sim)
          WHERE rn <= 15) s
    JOIN dim_item i ON i.artist_id = s.artist_id
    JOIN bc_fan_collection c ON c.item_url = i.url
    GROUP BY s.user_id
)
SELECT u.user_id,
       f.fav_artist, f.fav_likes,
       sg.signature_tag,
       s.diversity_idx,
       h.hidden_family, h.hidden_share_pct,
       fa.twin_fans,
       a.reco_families,
       ROUND(a.avg_discovery, 0)                                         AS avg_discovery,
       ROUND(a.avg_sales, 0)                                             AS avg_reco_sales_28d,
       ROUND(100 * a.c_tag   / (a.c_tag + a.c_cofan + a.c_mom + a.c_disc), 0) AS share_tag_pct,
       ROUND(100 * a.c_cofan / (a.c_tag + a.c_cofan + a.c_mom + a.c_disc), 0) AS share_cofan_pct,
       ROUND(100 * a.c_mom   / (a.c_tag + a.c_cofan + a.c_mom + a.c_disc), 0) AS share_momentum_pct,
       ROUND(100 * a.c_disc  / (a.c_tag + a.c_cofan + a.c_mom + a.c_disc), 0) AS share_discovery_pct
FROM (SELECT DISTINCT user_id FROM user_likes) u
LEFT JOIN fav f    USING (user_id)
LEFT JOIN sig sg   USING (user_id)
LEFT JOIN seg s    USING (user_id)
LEFT JOIN hidden h USING (user_id)
LEFT JOIN fans fa  USING (user_id)
LEFT JOIN algo a   USING (user_id)
ORDER BY u.user_id;
