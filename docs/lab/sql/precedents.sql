-- 선례: 이 팀({{team_key}})과 같은 길(같은 선정 프로그램·같은 공연장·같은 매체)을 정답 '전에' 밟았던 과거 정답 팀 상위 5.
-- 읽는 법: 겹친 항목이 많고 드물수록 위(많은 팀이 거쳐 가는 큰 공연장은 가중치가 낮음: 1/ln(2+그 항목을 지난 팀 수)).
--   months_signal_to_outcome = 그 과거 팀이 우리 데이터에 처음 나온 뒤 첫 정답까지 걸린 개월 수('이 길이면 보통 얼마나 걸렸나').
-- 주의: 선례는 '비슷한 경로'일 뿐 예측이 아니다. 정답은 센 정답(counted)만.
WITH item AS (                                  -- 신호 1건 → 비교 항목 1개
    SELECT team_key, signal_date,
           CASE WHEN branch = '선정·지원' THEN 'P:' || program
                WHEN branch = '공연'      THEN 'V:' || venue
                WHEN branch = '큐레이션'  THEN 'M:' || program END AS item_key
    FROM signals
    WHERE (branch = '선정·지원' AND program <> '' AND program <> 'dmz_lineup')
       OR (branch = '공연' AND COALESCE(venue, '') NOT IN ('', '공연장 미정'))
       OR (branch = '큐레이션' AND program <> '')
),
rarity AS (
    SELECT item_key, 1.0 / LN(2 + COUNT(DISTINCT team_key)) AS w FROM item GROUP BY item_key
),
target AS (SELECT DISTINCT item_key FROM item WHERE team_key = {{team_key}}),
winner AS (                                     -- 과거 정답 팀과 첫 정답
    SELECT team_key, MIN(announced_date) AS first_outcome FROM outcomes WHERE counted GROUP BY team_key
),
winner_label AS (
    SELECT o.team_key, MIN(o.program_label) AS program_label
    FROM outcomes o JOIN winner w ON w.team_key = o.team_key AND o.announced_date = w.first_outcome
    WHERE o.counted
    GROUP BY o.team_key
),
winner_items AS (                               -- 정답 '전' 신호만
    SELECT DISTINCT i.team_key, i.item_key
    FROM item i JOIN winner w ON w.team_key = i.team_key
    WHERE i.signal_date < w.first_outcome
),
shared AS (
    SELECT wi.team_key, wi.item_key, r.w
    FROM winner_items wi
    JOIN target t ON t.item_key = wi.item_key
    JOIN rarity r ON r.item_key = wi.item_key
    WHERE wi.team_key <> {{team_key}}
),
first_seen AS (SELECT team_key, MIN(signal_date) AS first_signal FROM signals GROUP BY team_key)
SELECT s.team_key                                                               AS past_team,
       COALESCE(tm.display_name, s.team_key)                                    AS display_name,
       wl.program_label                                                         AS outcome_label,
       w.first_outcome                                                          AS outcome_date,
       COUNT(*)                                                                 AS shared_count,
       ROUND(SUM(s.w), 3)                                                       AS similarity,
       STRING_AGG(CASE WHEN s.item_key LIKE 'P:%' THEN COALESCE(pr.label, SUBSTR(s.item_key, 3))
                       WHEN s.item_key LIKE 'V:%' THEN '공연장 ' || SUBSTR(s.item_key, 3)
                       ELSE '매체 ' || SUBSTR(s.item_key, 3) END, ' · ' ORDER BY s.w DESC) AS shared_list,
       DATE_DIFF('month', fs.first_signal, w.first_outcome)                     AS months_signal_to_outcome
FROM shared s
JOIN winner w USING (team_key)
LEFT JOIN winner_label wl USING (team_key)
LEFT JOIN teams tm USING (team_key)
LEFT JOIN first_seen fs USING (team_key)
LEFT JOIN programs pr ON s.item_key = 'P:' || pr.program
GROUP BY s.team_key, tm.display_name, wl.program_label, w.first_outcome, fs.first_signal
ORDER BY similarity DESC, shared_count DESC, outcome_date DESC
LIMIT 5;
