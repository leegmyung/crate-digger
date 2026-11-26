-- 무엇을 찾나: 같은 앨범(artist_key + title_key)이 2개 이상 플랫폼에 올라왔는데 발매일(released_at)이 서로 다른 경우.
-- 왜 문제인가: 플랫폼마다 발매일을 다르게 적으면 "언제 처음 나왔나"가 흔들려 신호 시점·첫 발매 계산이 틀어진다.
-- 결과를 보고 할 일: 날짜 차이가 큰 줄부터 원본 페이지를 확인하고, 앨범 발매일은 가장 이른 날(또는 신뢰 플랫폼)로 정한다.
WITH per_platform AS (
    SELECT artist_key, title_key, source,
           min(released_at) AS released_at,
           min(artist_text) AS artist_text,
           min(title)       AS title
    FROM raw.raw_kr_release
    WHERE artist_key IS NOT NULL AND title_key IS NOT NULL AND title_key <> ''
    GROUP BY artist_key, title_key, source
),
albums AS (
    SELECT artist_key, title_key,
           count(DISTINCT source)      AS platform_count,
           count(DISTINCT released_at) AS date_count,
           min(released_start)         AS earliest,
           max(released_start)         AS latest
    FROM raw.raw_kr_release
    WHERE artist_key IS NOT NULL AND title_key IS NOT NULL AND title_key <> ''
    GROUP BY artist_key, title_key
    HAVING count(DISTINCT source) >= 2 AND count(DISTINCT released_at) >= 2
)
SELECT a.artist_key, p.artist_text, p.title,
       a.platform_count, a.date_count,
       (a.latest - a.earliest)                                         AS gap_days,
       string_agg(p.source || '=' || p.released_at, ', ' ORDER BY p.released_at, p.source) AS dates_by_platform
FROM albums a
JOIN per_platform p ON p.artist_key = a.artist_key AND p.title_key = a.title_key
GROUP BY a.artist_key, a.title_key, p.artist_text, p.title, a.platform_count, a.date_count, a.latest, a.earliest
ORDER BY gap_days DESC NULLS LAST, a.artist_key;
