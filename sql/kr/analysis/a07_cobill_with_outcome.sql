-- 질문: '같은 무대 동료' — 같은 날·같은 공연장에서 정답 받은 팀과 함께 선 적 있는 팀은, 그렇지 않은 팀보다 나중에 정답을 더 많이 받나?
-- 왜 중요한가: 잘되는 팀과 자주 같은 무대에 서는 팀은 같은 씬·같은 기획자 눈에 든 팀일 가능성이 크다(네트워크 신호).
-- 읽는 법: 동료_유형 3가지 — '이미 정답 팀과 같이 섬' = 공연 당시 상대가 이미 정답을 받은 상태(지금 시점에서도 쓸 수 있는 신호),
--       '나중 정답 팀과만 같이 섬' = 상대가 공연 뒤에 정답을 받음(그때는 몰랐던 정보라 예측 신호로는 못 쓰고 '씬 근접도' 참고용),
--       '정답 팀과 같이 선 적 없음' = 비교 기준. 정답_비율이 기준보다 높으면 동료 신호가 있다는 뜻.
-- 데이터 주의: 정답이 모두 2025년 이후라 2024 공연에서는 '이미 정답' 그룹이 생길 수 없다. 그래서 2025 상반기 공연을
--       두 번째 기간으로 함께 본다(그 기간 전에 이미 정답을 받은 팀은 후보에서 뺀다). 페스티벌처럼 출연 팀이 많은 날도 그대로 센다.
--       '나중 정답' 그룹에는 서로가 둘 다 나중에 정답을 받은 경우(같은 쇼케이스 출신 등)도 섞여 비율이 부풀 수 있다.

WITH periods AS (
    SELECT '2024 공연' AS period, DATE '2024-01-01' AS gig_from, DATE '2024-12-31' AS gig_to
    UNION ALL
    SELECT '2025 상반기 공연', DATE '2025-01-01', DATE '2025-06-30'
),
outcome_team AS (                                    -- 팀별 첫 센 정답 날짜
    SELECT artist_key, alias_key, first_outcome_date
    FROM core.v_outcome_team
),
gig AS (                                             -- 공연 1회 = 날짜 × 공연장, 출연 팀
    SELECT DISTINCT p.period, g.gig_date,
           TRIM(split_part(g.venue_text, ' (', 1)) AS venue,
           g.artist_key, g.alias_key
    FROM raw.raw_kr_gig g
    JOIN periods p ON g.gig_date BETWEEN p.gig_from AND p.gig_to
    WHERE g.artist_key IS NOT NULL AND g.artist_key <> ''
      AND TRIM(split_part(g.venue_text, ' (', 1)) NOT IN ('', '공연장 미정')
),
gig_with_outcome AS (                                -- 공연 출연 팀에 '첫 정답 날짜' 붙이기
    SELECT gg.*, ot.first_outcome_date
    FROM gig gg
    LEFT JOIN outcome_team ot
      ON (gg.artist_key = ot.artist_key
          OR gg.artist_key = ot.alias_key
          OR gg.alias_key  = ot.artist_key)
),
cobill AS (                                          -- 팀 A × 같은 무대의 정답 팀 B
    SELECT a.period, a.artist_key,
           MAX(CASE WHEN b.first_outcome_date <= a.gig_date THEN 1 ELSE 0 END) AS with_already,
           MAX(CASE WHEN b.first_outcome_date >  a.gig_date THEN 1 ELSE 0 END) AS with_later
    FROM gig_with_outcome a
    JOIN gig_with_outcome b
      ON b.period = a.period AND b.gig_date = a.gig_date AND b.venue = a.venue
     AND b.artist_key <> a.artist_key
     AND COALESCE(b.alias_key, '#') <> a.artist_key
     AND COALESCE(a.alias_key, '#') <> b.artist_key
    WHERE b.first_outcome_date IS NOT NULL
    GROUP BY a.period, a.artist_key
),
candidate AS (                                       -- 기간 안 출연 팀 (기간 시작 전에 이미 정답 받은 팀 제외)
    SELECT gw.period, gw.artist_key,
           MIN(gw.gig_date)            AS first_gig,
           MIN(gw.first_outcome_date)  AS own_outcome_date
    FROM gig_with_outcome gw
    JOIN periods p ON p.period = gw.period
    GROUP BY gw.period, gw.artist_key, p.gig_from
    HAVING MIN(gw.first_outcome_date) IS NULL OR MIN(gw.first_outcome_date) >= p.gig_from
),
labeled AS (
    SELECT c.period, c.artist_key,
           CASE WHEN cb.with_already = 1 THEN '1) 이미 정답 팀과 같이 섬'
                WHEN cb.with_later   = 1 THEN '2) 나중 정답 팀과만 같이 섬'
                ELSE                          '3) 정답 팀과 같이 선 적 없음' END AS peer_type,
           CASE WHEN c.own_outcome_date > c.first_gig
                 AND c.own_outcome_date >= DATE '2025-01-01' THEN 1 ELSE 0 END AS is_hit
    FROM candidate c
    LEFT JOIN cobill cb ON cb.period = c.period AND cb.artist_key = c.artist_key
)
SELECT period                                       AS 기간,
       peer_type                                    AS 동료_유형,
       COUNT(*)                                     AS 팀수,
       SUM(is_hit)                                  AS 이후_정답_팀수,
       ROUND(100.0 * SUM(is_hit) / COUNT(*), 1)     AS 정답_비율_pct
FROM labeled
GROUP BY period, peer_type
ORDER BY period, peer_type;
