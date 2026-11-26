-- 무엇을 찾나: 핵심 칸이 비었거나 덜 정확한 비율 — 공연(장소·시각), 발매(유통사·레이블·장르), 선정(연도만 아는 날짜), 정답(연·월만 아는 날짜).
-- 왜 문제인가: 빈 칸이 많은 소스는 장소·장르 분석에서 빠지고, 날짜가 거칠면 "신호가 정답보다 먼저였나" 판정이 흐려진다.
-- 결과를 보고 할 일: 비율이 높은 소스부터 수집기에서 해당 칸을 더 가져올 수 있는지 보고, 안 되면 다른 소스로 보충한다.
WITH checks AS (
    SELECT 'raw_kr_gig' AS tbl, source, 'venue_text 없음' AS check_name,
           count(*) AS total_rows,
           sum(CASE WHEN COALESCE(trim(venue_text), '') = '' THEN 1 ELSE 0 END) AS problem_rows
    FROM raw.raw_kr_gig GROUP BY source
    UNION ALL
    SELECT 'raw_kr_gig', source, 'gig_time 없음', count(*),
           sum(CASE WHEN COALESCE(trim(gig_time), '') = '' THEN 1 ELSE 0 END)
    FROM raw.raw_kr_gig GROUP BY source
    UNION ALL
    SELECT 'raw_kr_release', source, 'distributor_text 없음', count(*),
           sum(CASE WHEN COALESCE(trim(distributor_text), '') = '' THEN 1 ELSE 0 END)
    FROM raw.raw_kr_release GROUP BY source
    UNION ALL
    SELECT 'raw_kr_release', source, 'label_text 없음', count(*),
           sum(CASE WHEN COALESCE(trim(label_text), '') = '' THEN 1 ELSE 0 END)
    FROM raw.raw_kr_release GROUP BY source
    UNION ALL
    SELECT 'raw_kr_release', source, 'genre 없음', count(*),
           sum(CASE WHEN COALESCE(trim(genre), '') = '' THEN 1 ELSE 0 END)
    FROM raw.raw_kr_release GROUP BY source
    UNION ALL
    SELECT 'raw_kr_selection', source, 'announced_at 연도만(YYYY)', count(*),
           sum(CASE WHEN length(trim(announced_at)) = 4 THEN 1 ELSE 0 END)
    FROM raw.raw_kr_selection GROUP BY source
    UNION ALL
    SELECT 'raw_kr_selection', source, 'announced_at 비어 있음', count(*),
           sum(CASE WHEN COALESCE(trim(announced_at), '') = '' THEN 1 ELSE 0 END)
    FROM raw.raw_kr_selection GROUP BY source
    UNION ALL
    SELECT 'raw_outcome', program, 'announced_at 연·월만(YYYY 또는 YYYY-MM)', count(*),
           sum(CASE WHEN length(trim(announced_at)) IN (4, 7) THEN 1 ELSE 0 END)
    FROM raw.raw_outcome GROUP BY program
)
SELECT tbl, source AS source_or_program, check_name, total_rows, problem_rows,
       round(100.0 * problem_rows / NULLIF(total_rows, 0), 1) AS problem_pct
FROM checks
ORDER BY tbl, check_name, problem_pct DESC, source;
