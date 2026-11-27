# SQL 분석·검증 결과 (PostgreSQL)

_자동 생성: `python3 scripts/run_pg_queries.py` · 2026-11-27 10:34 기준 데이터_

모든 쿼리는 `sql/kr/`에 원문이 있어요. 같은 팀 잇기는 대표 팀 키(`team_key` — 연결표 `ref.artist_xref` 우선, 없으면 괄호 별칭), 날짜는 후보 신호 = 기간 끝, 정답 = 기간 첫날로 비교해요 (`sql/kr/00_core_views.sql`).

## 분석 SQL

신호가 나중의 성공(정답)을 얼마나 먼저 알려 주는지

### a01_signal_hit_rate

- 질문: 선정·지원 프로그램(신호)마다, 2020~2024년(정답 기간 전 5년)에 뽑힌 팀 중
- 2025년 이후 '센 정답'(counted 정답)을 받은 팀은 몇 %인가?
- 왜 중요한가: 어느 선정·지원 프로그램이 나중 성공을 미리 알려주는 '좋은 신호'인지 고르는 기준이 된다.
- 같은 프로그램 계열(예: 예선 → 본선)은 사실상 같은 대회라 정답에서 뺀다 (ref.same_program).
- 읽는 법: 맨 아래 '(기준선)' 줄은 같은 기간 아무 갈래에서든 신호가 있던 모든 팀의 적중률. 이보다 높아야 의미 있다.
- 신호_팀수 = 분모, 정답_팀수 = 신호 날짜 뒤에 정답을 받은 팀. 적중률이 높을수록 좋은 신호.
- 분모가 작으면(10팀 미만) 우연일 수 있으니 숫자보다 '0인지 아닌지' 정도로 본다.

<details><summary>쿼리 보기</summary>

```sql
WITH params AS (
    SELECT DATE '2025-01-01' AS outcome_from,
           DATE '2020-01-01' AS lookback_from          -- 정답 기간 시작 5년 전
),
sel_signal AS (                                       -- 기간 안 선정·지원 신호 (팀 × 프로그램, 가장 이른 날짜)
    SELECT s.program, s.team_key, MIN(s.signal_date) AS signal_date
    FROM core.v_signal s
    CROSS JOIN params p
    WHERE s.branch = '선정·지원'
      AND s.signal_date >= p.lookback_from
      AND s.signal_date <  p.outcome_from
    GROUP BY s.program, s.team_key
),
outcome AS (                                          -- 예측 대상 정답 (센 것만)
    SELECT o.program AS outcome_program, o.team_key, o.announced_start
    FROM core.v_outcome o
    CROSS JOIN params p
    WHERE o.counted
      AND o.announced_start >= p.outcome_from
),
any_signal AS (                                       -- 기준선: 기간 안 아무 갈래 신호 (팀별 가장 이른 날짜)
    SELECT s.team_key, MIN(s.signal_date) AS signal_date
    FROM core.v_signal s
    CROSS JOIN params p
    WHERE s.signal_date >= p.lookback_from
      AND s.signal_date <  p.outcome_from
    GROUP BY s.team_key
),
baseline AS (
    SELECT COUNT(DISTINCT a.team_key) AS signal_teams,
           COUNT(DISTINCT CASE WHEN EXISTS (
               SELECT 1 FROM outcome oc
               WHERE a.team_key = oc.team_key
                 AND a.signal_date < oc.announced_start) THEN a.team_key END) AS hit_teams
    FROM any_signal a
),
hit AS (                                              -- 신호 뒤에 정답이 온 팀 (같은 프로그램 계열 제외)
    SELECT DISTINCT ss.program, ss.team_key
    FROM sel_signal ss
    JOIN outcome oc
      ON ss.team_key = oc.team_key
     AND ss.signal_date < oc.announced_start
    WHERE NOT EXISTS (
        SELECT 1 FROM ref.same_program sp
        WHERE sp.selection_program = ss.program
          AND sp.outcome_program   = oc.outcome_program
    )
),
by_program AS (
    SELECT ss.program                                        AS 선정지원_프로그램,
           COUNT(DISTINCT ss.team_key)                     AS 신호_팀수,
           COUNT(DISTINCT h.team_key)                      AS 정답_팀수,
           0                                                 AS sort_group
    FROM sel_signal ss
    LEFT JOIN hit h
      ON h.program = ss.program AND h.team_key = ss.team_key
    GROUP BY ss.program
    UNION ALL
    SELECT '(기준선: 모든 신호 팀)', signal_teams, hit_teams, 1
    FROM baseline
)
SELECT 선정지원_프로그램, 신호_팀수, 정답_팀수,
       ROUND(100.0 * 정답_팀수 / NULLIF(신호_팀수, 0), 1) AS 적중률_pct
FROM by_program
ORDER BY sort_group, 적중률_pct DESC, 신호_팀수 DESC;
```

</details>

결과 6행

| 선정지원_프로그램 | 신호_팀수 | 정답_팀수 | 적중률_pct |
|---|---|---|---|
| band_discovery | 23 | 2 | 8.7 |
| yoojaeha_finalist | 51 | 3 | 5.9 |
| muse_sejong | 24 | 1 | 4.2 |
| dmz_lineup | 52 | 0 | 0.0 |
| gb_creation | 21 | 0 | 0.0 |
| (기준선: 모든 신호 팀) | 2797 | 41 | 1.5 |

### a02_lead_time

- 질문: 정답(센 것)을 받은 팀은, 정답 몇 개월 전에 처음 우리 레이더(신호)에 잡혔나?
- 왜 중요한가: 리드타임(미리 알아챈 기간)이 길수록 '남보다 먼저 발굴'했다는 뜻이다. 갈래별로 비교하면
- 어느 갈래가 가장 일찍 신호를 주는지 알 수 있다.
- 읽는 법: 갈래 = 그 갈래의 첫 신호 기준, '(전체)' = 갈래 무관 가장 이른 신호. 중앙값_개월 = 절반의 팀이 이보다 일찍 잡힘.
- 6/12/24개월_이상_pct = 그만큼 미리 잡힌 팀 비율. 신호는 2020-01-01 이후 · 정답 날짜보다 앞선 것만,
- 정답과 같은 프로그램 계열의 선정 신호(ref.same_program)는 뺀다.
- 데이터 주의: 발매·큐레이션은 2026-11 수집분뿐이라 정답보다 앞선 신호가 거의 없다(사실상 공연·선정 비교).

<details><summary>쿼리 보기</summary>

```sql
WITH params AS (
    SELECT DATE '2025-01-01' AS outcome_from,
           DATE '2020-01-01' AS lookback_from
),
outcome_team AS (                                    -- 팀별 첫 정답 (2025년 이후)
    SELECT t.team_key, t.first_program, t.first_outcome_date
    FROM core.v_outcome_team t
    CROSS JOIN params p
    WHERE t.first_outcome_date >= p.outcome_from
),
first_signal AS (                                    -- 팀 × 갈래별 정답 전 첫 신호
    SELECT ot.team_key, s.branch, ot.first_outcome_date,
           MIN(s.signal_date) AS first_signal_date
    FROM outcome_team ot
    CROSS JOIN params p
    JOIN core.v_signal s
      ON s.team_key = ot.team_key
     AND s.signal_date <  ot.first_outcome_date
     AND s.signal_date >= p.lookback_from
    WHERE NOT EXISTS (
        SELECT 1 FROM ref.same_program sp
        WHERE sp.selection_program = s.program
          AND sp.outcome_program   = ot.first_program
    )
    GROUP BY ot.team_key, s.branch, ot.first_outcome_date
),
lead AS (                                            -- 갈래별 + 갈래 무관(전체) 리드타임(개월)
    SELECT branch, team_key,
           (first_outcome_date - first_signal_date) / 30.44 AS lead_months
    FROM first_signal
    UNION ALL
    SELECT '(전체)', team_key,
           (MAX(first_outcome_date) - MIN(first_signal_date)) / 30.44
    FROM first_signal
    GROUP BY team_key
)
SELECT l.branch                                                       AS 갈래,
       COUNT(*)                                                       AS 팀수,
       (SELECT COUNT(*) FROM outcome_team)                            AS 정답_팀_전체,
       ROUND(CAST(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY l.lead_months) AS numeric), 1) AS 중앙값_개월,
       ROUND(CAST(MIN(l.lead_months) AS numeric), 1)                  AS 최소_개월,
       ROUND(CAST(MAX(l.lead_months) AS numeric), 1)                  AS 최대_개월,
       ROUND(100.0 * SUM(CASE WHEN l.lead_months >= 6  THEN 1 ELSE 0 END) / COUNT(*), 1) AS "6개월_이상_pct",
       ROUND(100.0 * SUM(CASE WHEN l.lead_months >= 12 THEN 1 ELSE 0 END) / COUNT(*), 1) AS "12개월_이상_pct",
       ROUND(100.0 * SUM(CASE WHEN l.lead_months >= 24 THEN 1 ELSE 0 END) / COUNT(*), 1) AS "24개월_이상_pct"
FROM lead l
GROUP BY l.branch
ORDER BY CASE WHEN l.branch = '(전체)' THEN 0 ELSE 1 END, 팀수 DESC;
```

</details>

결과 4행

| 갈래 | 팀수 | 정답_팀_전체 | 중앙값_개월 | 최소_개월 | 최대_개월 | 6개월_이상_pct | 12개월_이상_pct | 24개월_이상_pct |
|---|---|---|---|---|---|---|---|---|
| (전체) | 68 | 86 | 13.2 | 0.1 | 46.6 | 76.5 | 54.4 | 27.9 |
| 공연 | 50 | 86 | 12.4 | 0.1 | 44.3 | 76.0 | 54.0 | 16.0 |
| 큐레이션 | 36 | 86 | 9.0 | 0.1 | 39.8 | 66.7 | 41.7 | 25.0 |
| 선정·지원 | 8 | 86 | 32.1 | 1.3 | 46.6 | 87.5 | 75.0 | 62.5 |

### a03_mid_to_final

- 질문: 중간 정답(mid) 프로그램마다, 받은 팀 중 그 뒤 최종 정답(final)까지 받은 팀은 몇 %인가?
- 왜 중요한가: 중간 정답이 최종 정답의 '디딤돌'인지 알면, 중간 정답을 받은 팀을 다음 후보로 바로 올릴 수 있다.
- 같은 계열(예: 헬로루키 월간 → 헬로루키 올해의)은 한 대회 안의 승급이라 뺀다 (ref.outcome_same_family).
- 읽는 법: 중간을 신호로 보므로 중간 날짜 = 기간 마지막 날(announced_end), 최종 날짜 = 기간 첫날(announced_start).
- 최종_전환율이 높을수록 좋은 디딤돌. 중간 정답이 2025~2026에만 있어 '뒤에 올 시간'이 짧다는 점에 주의.

<details><summary>쿼리 보기</summary>

```sql
WITH mid AS (                                        -- 팀 × 중간 프로그램 (가장 이른 날짜)
    SELECT program AS mid_program, team_key,
           MIN(COALESCE(announced_end, announced_start)) AS mid_date
    FROM core.v_outcome
    WHERE counted AND tier = 'mid'
    GROUP BY program, team_key
),
final_o AS (
    SELECT program AS final_program, team_key, announced_start AS final_date
    FROM core.v_outcome
    WHERE counted AND tier = 'final'
),
converted AS (                                       -- 중간 뒤에 (다른 계열) 최종을 받은 팀
    SELECT m.mid_program, m.team_key,
           MIN(f.final_date - m.mid_date) AS days_to_final
    FROM mid m
    JOIN final_o f
      ON m.team_key = f.team_key
     AND m.mid_date < f.final_date
    WHERE NOT EXISTS (
        SELECT 1 FROM ref.outcome_same_family fam
        WHERE fam.mid_program   = m.mid_program
          AND fam.final_program = f.final_program
    )
    GROUP BY m.mid_program, m.team_key
)
SELECT m.mid_program                                       AS 중간_프로그램,
       COUNT(DISTINCT m.team_key)                        AS 중간_팀수,
       COUNT(DISTINCT c.team_key)                        AS 최종까지_팀수,
       ROUND(100.0 * COUNT(DISTINCT c.team_key)
             / NULLIF(COUNT(DISTINCT m.team_key), 0), 1) AS 최종_전환율_pct,
       ROUND(AVG(c.days_to_final) / 30.44, 1)              AS 평균_걸린_개월,
       MIN(m.mid_date)                                     AS 중간_첫날짜,
       MAX(m.mid_date)                                     AS 중간_끝날짜
FROM mid m
LEFT JOIN converted c
  ON c.mid_program = m.mid_program AND c.team_key = m.team_key
GROUP BY m.mid_program
ORDER BY 최종_전환율_pct DESC, 중간_팀수 DESC;
```

</details>

결과 7행

| 중간_프로그램 | 중간_팀수 | 최종까지_팀수 | 최종_전환율_pct | 평균_걸린_개월 | 중간_첫날짜 | 중간_끝날짜 |
|---|---|---|---|---|---|---|
| kma_genre | 5 | 3 | 60.0 | 6.0 | 2025-02-06 | 2026-02-05 |
| indiestance | 10 | 4 | 40.0 | 0.7 | 2025-08-17 | 2026-10-17 |
| mucon | 3 | 1 | 33.3 | 0.3 | 2025-06-16 | 2026-07-13 |
| museon_final | 25 | 6 | 24.0 | 6.2 | 2025-05-12 | 2026-06-04 |
| penta_superrookie | 20 | 3 | 15.0 | 6.7 | 2025-06-09 | 2026-05-30 |
| burock_main | 13 | 1 | 7.7 | 0.9 | 2026-09-04 | 2026-09-04 |
| hello_rookie | 10 | 0 | 0.0 |  | 2026-04-28 | 2026-08-31 |

### a04_career_at_outcome

- 질문: 정답 프로그램별로, 정답 받을 당시 팀은 첫 발매 후 몇 년 차였나? 우리 '신인 기준'(3년 이내 & 앨범 10개 이하)을 몇 %가 통과하나?
- 왜 중요한가: 정답이 정말 '신인' 대상인지 확인한다. 기성 팀이 많이 섞인 프로그램은 신인 발굴의 정답으로 쓰기 어렵다.
- 읽는 법: 버전 '전체' = 프로필이 있는 모든 정답, '동명제외' = 같은 이름 프로필이 2개 이상(profile_count>1)인 팀 제외.
- 프로필_있음 / 정답_건수 = 연차를 알 수 있는 비율. 연차 구간 열은 건수, 신인기준_통과율은 프로필 있는 건 중 비율.
- 데이터 주의: 멜론 프로필이 83개뿐이라 일부 정답은 연차를 모른다. 현재 profile_count>1 인 팀이 없어 두 버전이 같다.

<details><summary>쿼리 보기</summary>

```sql
WITH newcomer_rule AS (
    SELECT 3 AS max_years, 10 AS max_albums
),
base AS (                                            -- 센 정답 1건 = 1행, 정답 당시 연차·앨범 수
    SELECT o.program, o.artist_key, o.years_at_outcome,
           ap.album_count, COALESCE(ap.profile_count, 0) AS profile_count
    FROM core.v_outcome o
    LEFT JOIN core.v_artist_profile ap ON ap.artist_key = o.artist_key
    WHERE o.counted
),
versioned AS (                                       -- 두 버전을 세로로 쌓기
    SELECT '전체' AS version, b.* FROM base b
    UNION ALL
    SELECT '동명제외', b.* FROM base b WHERE b.profile_count <= 1
)
SELECT v.version                                                      AS 버전,
       v.program                                                      AS 정답_프로그램,
       COUNT(*)                                                       AS 정답_건수,
       COUNT(v.years_at_outcome)                                      AS 프로필_있음,
       ROUND(CAST(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY v.years_at_outcome) AS numeric), 1) AS 연차_중앙값,
       SUM(CASE WHEN v.years_at_outcome <  1 THEN 1 ELSE 0 END)       AS "1년미만",
       SUM(CASE WHEN v.years_at_outcome >= 1 AND v.years_at_outcome < 3 THEN 1 ELSE 0 END) AS "1_3년",
       SUM(CASE WHEN v.years_at_outcome >= 3 AND v.years_at_outcome < 5 THEN 1 ELSE 0 END) AS "3_5년",
       SUM(CASE WHEN v.years_at_outcome >= 5 THEN 1 ELSE 0 END)       AS "5년이상",
       ROUND(100.0 * SUM(CASE WHEN v.years_at_outcome <= r.max_years
                               AND COALESCE(v.album_count, 0) <= r.max_albums THEN 1 ELSE 0 END)
             / NULLIF(COUNT(v.years_at_outcome), 0), 1)               AS 신인기준_통과율_pct
FROM versioned v
CROSS JOIN newcomer_rule r
GROUP BY v.version, v.program
ORDER BY v.version DESC, 정답_건수 DESC, v.program;
```

</details>

결과 26행

| 버전 | 정답_프로그램 | 정답_건수 | 프로필_있음 | 연차_중앙값 | 1년미만 | 1_3년 | 3_5년 | 5년이상 | 신인기준_통과율_pct |
|---|---|---|---|---|---|---|---|---|---|
| 전체 | museon_final | 25 | 16 | 2.6 | 1 | 8 | 5 | 2 | 37.5 |
| 전체 | hello_rookie_year | 21 | 11 | 1.8 | 4 | 7 | 0 | 0 | 90.9 |
| 전체 | penta_superrookie | 20 | 13 | 2.6 | 1 | 7 | 1 | 4 | 46.2 |
| 전체 | khha_rookie | 14 | 0 |  | 0 | 0 | 0 | 0 |  |
| 전체 | burock_main | 13 | 13 | 2.7 | 2 | 5 | 6 | 0 | 46.2 |
| 전체 | kma_rookie | 13 | 6 | 0.8 | 3 | 2 | 1 | 0 | 66.7 |
| 전체 | cj_tuneup | 12 | 8 | 5.6 | 0 | 1 | 0 | 7 | 0.0 |
| 전체 | hello_rookie | 10 | 4 | 1.1 | 2 | 2 | 0 | 0 | 75.0 |
| 전체 | indiestance | 10 | 7 | 2.6 | 1 | 3 | 2 | 1 | 28.6 |
| 전체 | kma_genre | 6 | 6 | 2.3 | 2 | 1 | 3 | 0 | 50.0 |
| 전체 | musicy_rookie | 5 | 0 |  | 0 | 0 | 0 | 0 |  |
| 전체 | mucon | 3 | 3 | 3.6 | 0 | 1 | 1 | 1 | 0.0 |
| 전체 | izm_rookie | 1 | 0 |  | 0 | 0 | 0 | 0 |  |
| 동명제외 | museon_final | 15 | 6 | 2.5 | 0 | 3 | 3 | 0 | 16.7 |
| 동명제외 | khha_rookie | 14 | 0 |  | 0 | 0 | 0 | 0 |  |

_26행 중 15행만 표시_

### a05_cross_branch_now

- 질문: 최근 180일 안에 2개 이상 갈래(공연 / 선정·지원 / 발매 / 큐레이션)에 동시에 나온 팀은 누구인가?
- 왜 중요한가: 여러 갈래에서 동시에 보이는 팀은 '움직이고 있는' 팀이다. 지금 시점의 발굴 후보 미리보기.
- 읽는 법: 갈래_수가 많고 최근_날짜가 가까울수록 위. 이미_정답 = 이미 센 정답을 받은 팀(발굴 의미가 적음).
- 기준일은 오늘(CURRENT_DATE). 미래 날짜(예정 공연 등)는 뺀다. 같은 팀은 team_key(아티스트 연결표, 없으면 괄호 별칭)로 묶는다.

<details><summary>쿼리 보기</summary>

```sql
WITH params AS (
    SELECT CURRENT_DATE AS as_of, CURRENT_DATE - 180 AS window_from
),
recent AS (
    SELECT s.team_key,                                   -- 팀 대표 키 (core 뷰: 연결표 → 괄호 별칭)
           s.artist_text, s.branch, s.signal_date
    FROM core.v_signal s
    CROSS JOIN params p
    WHERE s.signal_date >= p.window_from
      AND s.signal_date <= p.as_of
      AND s.artist_key IS NOT NULL AND s.artist_key <> ''
),
team AS (
    SELECT team_key,
           MIN(artist_text)                                   AS 표시_이름,
           COUNT(DISTINCT branch)                             AS 갈래_수,
           STRING_AGG(DISTINCT branch, ', ')                  AS 갈래_목록,
           COUNT(*)                                           AS 신호_건수,
           MAX(signal_date)                                   AS 최근_날짜
    FROM recent
    GROUP BY team_key
    HAVING COUNT(DISTINCT branch) >= 2
)
SELECT t.표시_이름, t.team_key AS 팀_키, t.갈래_수, t.갈래_목록, t.신호_건수, t.최근_날짜,
       CASE WHEN EXISTS (
           SELECT 1 FROM core.v_outcome_team o
           WHERE o.team_key = t.team_key
       ) THEN 'Y' ELSE '' END                                 AS 이미_정답
FROM team t
ORDER BY t.갈래_수 DESC, t.최근_날짜 DESC, t.신호_건수 DESC
LIMIT 50;
```

</details>

결과 50행

| 표시_이름 | 팀_키 | 갈래_수 | 갈래_목록 | 신호_건수 | 최근_날짜 | 이미_정답 |
|---|---|---|---|---|---|---|
| 다다다 | 다다다 | 3 | 공연, 발매, 선정·지원 | 9 | 2026-11-27 | Y |
| 신인류 | 신인류 | 3 | 공연, 발매, 큐레이션 | 11 | 2026-11-25 | Y |
| 혁오 | 혁오 | 3 | 공연, 발매, 큐레이션 | 6 | 2026-11-25 |  |
| 다브다 | 다브다 | 3 | 공연, 발매, 큐레이션 | 5 | 2026-11-24 |  |
| 이케이 (EK) | ek | 3 | 공연, 발매, 큐레이션 | 4 | 2026-11-24 |  |
| 술탄 오브 더 디스코 | 술탄오브더디스코 | 3 | 공연, 발매, 큐레이션 | 5 | 2026-11-23 |  |
| 피치트럭하이재커스 | 피치트럭하이재커스 | 3 | 공연, 선정·지원, 큐레이션 | 8 | 2026-11-19 | Y |
| 키라라 | 키라라 | 2 | 공연, 큐레이션 | 8 | 2026-11-27 |  |
| 대소콜링 | 대소콜링 | 2 | 공연, 발매 | 5 | 2026-11-27 |  |
| 빈스프라우트 | 빈스프라우트 | 2 | 공연, 큐레이션 | 4 | 2026-11-27 |  |
| 도빛나리 | 도빛나리 | 2 | 공연, 큐레이션 | 3 | 2026-11-27 |  |
| 킬카이저 | 킬카이저 | 2 | 공연, 큐레이션 | 3 | 2026-11-27 |  |
| 나이테 | 나이테 | 2 | 공연, 큐레이션 | 14 | 2026-11-26 | Y |
| 고고학 (Gogohawk) | 고고학 | 2 | 공연, 발매 | 8 | 2026-11-26 | Y |
| 블낫블 | 블낫블 | 2 | 공연, 큐레이션 | 6 | 2026-11-26 | Y |

_50행 중 15행만 표시_

### a06_tastemaker_venues

- 질문: 2024년에 공연한 팀 기준으로, 어느 공연장의 출연 팀이 2025년 이후 센 정답을 가장 많이 받았나? (상위 15곳)
- 왜 중요한가: 될성부른 팀을 먼저 세우는 '안목 있는 공연장'을 찾으면, 그 공연장 라인업 자체가 좋은 신호가 된다.
- 읽는 법: 출연_팀수(최소 20팀) 중 정답_팀수 비율. 기준선_pct(2024년 공연한 모든 팀의 비율)보다 몇 배 높은지(배수)를 본다.
- 공연장 이름은 주소 괄호를 뗀 이름. 빈 값·'공연장 미정'은 뺀다. 정답 팀이 1~2팀만 달라져도 순위가 바뀌니 주의.

<details><summary>쿼리 보기</summary>

```sql
WITH params AS (
    SELECT DATE '2024-01-01' AS gig_from, DATE '2024-12-31' AS gig_to,
           DATE '2025-01-01' AS outcome_from, 20 AS min_teams
),
gig_2024 AS (                                        -- 공연장 × 팀 (2024년)
    SELECT DISTINCT
           TRIM(split_part(g.venue_text, ' (', 1)) AS venue,
           COALESCE(tm.team_key, g.artist_key) AS team_key   -- 팀 대표 키
    FROM raw.raw_kr_gig g
    CROSS JOIN params p
    LEFT JOIN core.v_team_map tm ON tm.variant_key = g.artist_key
    WHERE g.gig_date BETWEEN p.gig_from AND p.gig_to
      AND g.artist_key IS NOT NULL AND g.artist_key <> ''
),
gig_clean AS (
    SELECT * FROM gig_2024
    WHERE venue <> '' AND venue <> '공연장 미정'
),
outcome AS (
    SELECT o.team_key
    FROM core.v_outcome o
    CROSS JOIN params p
    WHERE o.counted AND o.announced_start >= p.outcome_from   -- 2024 공연은 항상 2025+ 정답보다 앞선다
),
team_hit AS (                                        -- 팀별 정답 여부 (같은 팀 규칙)
    SELECT t.team_key,
           MAX(CASE WHEN oc.team_key IS NOT NULL THEN 1 ELSE 0 END) AS is_hit
    FROM (SELECT DISTINCT team_key FROM gig_2024) t
    LEFT JOIN outcome oc ON oc.team_key = t.team_key
    GROUP BY t.team_key
),
baseline AS (
    SELECT 100.0 * SUM(is_hit) / COUNT(*) AS base_pct FROM team_hit
),
venue_stat AS (
    SELECT gc.venue,
           COUNT(DISTINCT gc.team_key)                                      AS team_cnt,
           COUNT(DISTINCT CASE WHEN th.is_hit = 1 THEN gc.team_key END)     AS hit_cnt
    FROM gig_clean gc
    JOIN team_hit th ON th.team_key = gc.team_key
    GROUP BY gc.venue
    HAVING COUNT(DISTINCT gc.team_key) >= (SELECT min_teams FROM params)   -- 순위 매기기 전에 거른다
)
SELECT RANK() OVER (ORDER BY 1.0 * v.hit_cnt / v.team_cnt DESC)  AS 순위,
       v.venue                                                    AS 공연장,
       v.team_cnt                                                 AS 출연_팀수,
       v.hit_cnt                                                  AS 정답_팀수,
       ROUND(100.0 * v.hit_cnt / v.team_cnt, 1)                   AS 정답_비율_pct,
       ROUND(CAST(b.base_pct AS numeric), 1)                      AS 기준선_pct,
       ROUND(CAST(100.0 * v.hit_cnt / v.team_cnt / NULLIF(b.base_pct, 0) AS numeric), 1) AS 배수
FROM venue_stat v
CROSS JOIN baseline b
ORDER BY 1.0 * v.hit_cnt / v.team_cnt DESC, v.team_cnt DESC
LIMIT 15;
```

</details>

결과 15행

| 순위 | 공연장 | 출연_팀수 | 정답_팀수 | 정답_비율_pct | 기준선_pct | 배수 |
|---|---|---|---|---|---|---|
| 1 | 언드 | 52 | 3 | 5.8 | 2.0 | 2.9 |
| 2 | A.O.R | 72 | 4 | 5.6 | 2.0 | 2.7 |
| 3 | 무신사개러지 | 97 | 5 | 5.2 | 2.0 | 2.5 |
| 4 | 무대륙 | 24 | 1 | 4.2 | 2.0 | 2.1 |
| 5 | Club FF | 315 | 13 | 4.1 | 2.0 | 2.0 |
| 6 | 석촌호수 아뜰리에 | 26 | 1 | 3.8 | 2.0 | 1.9 |
| 7 | 오방가르드 | 117 | 4 | 3.4 | 2.0 | 1.7 |
| 8 | Cafe PPnF | 48 | 1 | 2.1 | 2.0 | 1.0 |
| 9 | Club 빵 | 291 | 6 | 2.1 | 2.0 | 1.0 |
| 10 | Bender | 63 | 1 | 1.6 | 2.0 | 0.8 |
| 11 | Club Victim | 268 | 4 | 1.5 | 2.0 | 0.7 |
| 12 | 서브라이엇 해방촌 | 61 | 0 | 0.0 | 2.0 | 0.0 |
| 12 | 롤링홀 | 45 | 0 | 0.0 | 2.0 | 0.0 |
| 12 | 베이비돌 | 27 | 0 | 0.0 | 2.0 | 0.0 |
| 12 | 프리즘홀 | 26 | 0 | 0.0 | 2.0 | 0.0 |

### a07_cobill_with_outcome

- 질문: '같은 무대 동료' — 같은 날·같은 공연장에서 정답 받은 팀과 함께 선 적 있는 팀은, 그렇지 않은 팀보다 나중에 정답을 더 많이 받나?
- 왜 중요한가: 잘되는 팀과 자주 같은 무대에 서는 팀은 같은 씬·같은 기획자 눈에 든 팀일 가능성이 크다(네트워크 신호).
- 읽는 법: 동료_유형 3가지 — '이미 정답 팀과 같이 섬' = 공연 당시 상대가 이미 정답을 받은 상태(지금 시점에서도 쓸 수 있는 신호),
- '나중 정답 팀과만 같이 섬' = 상대가 공연 뒤에 정답을 받음(그때는 몰랐던 정보라 예측 신호로는 못 쓰고 '씬 근접도' 참고용),
- '정답 팀과 같이 선 적 없음' = 비교 기준. 정답_비율이 기준보다 높으면 동료 신호가 있다는 뜻.
- 데이터 주의: 정답이 모두 2025년 이후라 2024 공연에서는 '이미 정답' 그룹이 생길 수 없다. 그래서 2025 상반기 공연을
- 두 번째 기간으로 함께 본다(그 기간 전에 이미 정답을 받은 팀은 후보에서 뺀다). 페스티벌처럼 출연 팀이 많은 날도 그대로 센다.
- '나중 정답' 그룹에는 서로가 둘 다 나중에 정답을 받은 경우(같은 쇼케이스 출신 등)도 섞여 비율이 부풀 수 있다.

<details><summary>쿼리 보기</summary>

```sql
WITH periods AS (
    SELECT '2024 공연' AS period, DATE '2024-01-01' AS gig_from, DATE '2024-12-31' AS gig_to
    UNION ALL
    SELECT '2025 상반기 공연', DATE '2025-01-01', DATE '2025-06-30'
),
outcome_team AS (                                    -- 팀별 첫 센 정답 날짜
    SELECT team_key, first_outcome_date
    FROM core.v_outcome_team
),
gig AS (                                             -- 공연 1회 = 날짜 × 공연장, 출연 팀
    SELECT DISTINCT p.period, g.gig_date,
           TRIM(split_part(g.venue_text, ' (', 1)) AS venue,
           COALESCE(tm.team_key, g.artist_key) AS team_key   -- 팀 대표 키
    FROM raw.raw_kr_gig g
    JOIN periods p ON g.gig_date BETWEEN p.gig_from AND p.gig_to
    LEFT JOIN core.v_team_map tm ON tm.variant_key = g.artist_key
    WHERE g.artist_key IS NOT NULL AND g.artist_key <> ''
      AND TRIM(split_part(g.venue_text, ' (', 1)) NOT IN ('', '공연장 미정')
),
gig_with_outcome AS (                                -- 공연 출연 팀에 '첫 정답 날짜' 붙이기
    SELECT gg.*, ot.first_outcome_date
    FROM gig gg
    LEFT JOIN outcome_team ot ON ot.team_key = gg.team_key
),
cobill AS (                                          -- 팀 A × 같은 무대의 정답 팀 B
    SELECT a.period, a.team_key,
           MAX(CASE WHEN b.first_outcome_date <= a.gig_date THEN 1 ELSE 0 END) AS with_already,
           MAX(CASE WHEN b.first_outcome_date >  a.gig_date THEN 1 ELSE 0 END) AS with_later
    FROM gig_with_outcome a
    JOIN gig_with_outcome b
      ON b.period = a.period AND b.gig_date = a.gig_date AND b.venue = a.venue
     AND b.team_key <> a.team_key
    WHERE b.first_outcome_date IS NOT NULL
    GROUP BY a.period, a.team_key
),
candidate AS (                                       -- 기간 안 출연 팀 (기간 시작 전에 이미 정답 받은 팀 제외)
    SELECT gw.period, gw.team_key,
           MIN(gw.gig_date)            AS first_gig,
           MIN(gw.first_outcome_date)  AS own_outcome_date
    FROM gig_with_outcome gw
    JOIN periods p ON p.period = gw.period
    GROUP BY gw.period, gw.team_key, p.gig_from
    HAVING MIN(gw.first_outcome_date) IS NULL OR MIN(gw.first_outcome_date) >= p.gig_from
),
labeled AS (
    SELECT c.period, c.team_key,
           CASE WHEN cb.with_already = 1 THEN '1) 이미 정답 팀과 같이 섬'
                WHEN cb.with_later   = 1 THEN '2) 나중 정답 팀과만 같이 섬'
                ELSE                          '3) 정답 팀과 같이 선 적 없음' END AS peer_type,
           CASE WHEN c.own_outcome_date > c.first_gig
                 AND c.own_outcome_date >= DATE '2025-01-01' THEN 1 ELSE 0 END AS is_hit
    FROM candidate c
    LEFT JOIN cobill cb ON cb.period = c.period AND cb.team_key = c.team_key
)
SELECT period                                       AS 기간,
       peer_type                                    AS 동료_유형,
       COUNT(*)                                     AS 팀수,
       SUM(is_hit)                                  AS 이후_정답_팀수,
       ROUND(100.0 * SUM(is_hit) / COUNT(*), 1)     AS 정답_비율_pct
FROM labeled
GROUP BY period, peer_type
ORDER BY period, peer_type;
```

</details>

결과 5행

| 기간 | 동료_유형 | 팀수 | 이후_정답_팀수 | 정답_비율_pct |
|---|---|---|---|---|
| 2024 공연 | 2) 나중 정답 팀과만 같이 섬 | 217 | 15 | 6.9 |
| 2024 공연 | 3) 정답 팀과 같이 선 적 없음 | 1001 | 12 | 1.2 |
| 2025 상반기 공연 | 1) 이미 정답 팀과 같이 섬 | 7 | 1 | 14.3 |
| 2025 상반기 공연 | 2) 나중 정답 팀과만 같이 섬 | 121 | 10 | 8.3 |
| 2025 상반기 공연 | 3) 정답 팀과 같이 선 적 없음 | 561 | 12 | 2.1 |

### a08_platform_presence

- 질문: 같은 발매(팀 × 제목)가 몇 개 음원 플랫폼(멜론·벅스·지니·플로)에 동시에 잡혔나? 유통사 상위 10곳은 어디고,
- 각 유통사 발매는 몇 %가 여러 플랫폼에 잡혔나?
- 왜 중요한가: 여러 플랫폼 '신곡' 목록에 동시에 올라온 발매는 유통 힘이 있는(또는 주목받는) 발매다. 유통사별로 보면
- 인디 신인이 주로 어느 유통사를 거치는지, 그 유통사가 노출을 얼마나 넓게 주는지 알 수 있다.
- 읽는 법: 구분 '플랫폼 수 분포' = N개 플랫폼에 잡힌 발매 수와 전체 대비 비율. 구분 '유통사 상위10' = 그 유통사가 적힌 발매 수와
- 그중 2개 이상 플랫폼에 잡힌 비율. 발매 키 = (artist_key, title_key).
- 데이터 주의: 2026-11-23~26 며칠치 신곡 목록뿐이라 표본이 작다(약 100개 발매). 포크라노스는 제목 키가 없어 제외.
- 유통사 이름은 플랫폼마다 표기가 달라(예: Dreamus/드림어스) 같은 회사가 따로 셀 수 있다.

<details><summary>쿼리 보기</summary>

```sql
WITH release_rows AS (
    SELECT artist_key, title_key, source,
           NULLIF(TRIM(distributor_text), '') AS distributor
    FROM raw.raw_kr_release
    WHERE title_key IS NOT NULL AND title_key <> ''
      AND artist_key IS NOT NULL AND artist_key <> ''
),
release_platforms AS (                               -- 발매별 플랫폼 수
    SELECT artist_key, title_key, COUNT(DISTINCT source) AS platform_cnt
    FROM release_rows
    GROUP BY artist_key, title_key
),
platform_dist AS (
    SELECT '1) 플랫폼 수 분포'                             AS 구분,
           CAST(platform_cnt AS varchar(10)) || '개 플랫폼' AS 항목,
           COUNT(*)                                         AS 발매_수,
           ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS 비율_pct,
           platform_cnt                                     AS sort_key
    FROM release_platforms
    GROUP BY platform_cnt
),
distributor_release AS (                             -- 유통사 × 발매 (한 발매가 여러 유통사 표기를 가질 수 있음)
    SELECT DISTINCT r.distributor, r.artist_key, r.title_key, rp.platform_cnt
    FROM release_rows r
    JOIN release_platforms rp
      ON rp.artist_key = r.artist_key AND rp.title_key = r.title_key
    WHERE r.distributor IS NOT NULL
),
distributor_rank AS (
    SELECT distributor,
           COUNT(*)                                                   AS release_cnt,
           SUM(CASE WHEN platform_cnt >= 2 THEN 1 ELSE 0 END)         AS multi_cnt,
           ROW_NUMBER() OVER (ORDER BY COUNT(*) DESC, distributor)    AS rn
    FROM distributor_release
    GROUP BY distributor
),
distributor_top AS (
    SELECT '2) 유통사 상위10'                                         AS 구분,
           distributor                                                AS 항목,
           release_cnt                                                AS 발매_수,
           ROUND(100.0 * multi_cnt / release_cnt, 1)                  AS 비율_pct,   -- 다중 플랫폼 비율
           rn                                                         AS sort_key
    FROM distributor_rank
    WHERE rn <= 10
)
SELECT 구분, 항목, 발매_수, 비율_pct
FROM (
    SELECT * FROM platform_dist
    UNION ALL
    SELECT * FROM distributor_top
) x
ORDER BY 구분, sort_key;
```

</details>

결과 14행

| 구분 | 항목 | 발매_수 | 비율_pct |
|---|---|---|---|
| 1) 플랫폼 수 분포 | 1개 플랫폼 | 73 | 60.8 |
| 1) 플랫폼 수 분포 | 2개 플랫폼 | 26 | 21.7 |
| 1) 플랫폼 수 분포 | 3개 플랫폼 | 13 | 10.8 |
| 1) 플랫폼 수 분포 | 4개 플랫폼 | 8 | 6.7 |
| 2) 유통사 상위10 | 미러볼뮤직 | 12 | 16.7 |
| 2) 유통사 상위10 | 주식회사 뮤즈플랫폼 | 12 | 0.0 |
| 2) 유통사 상위10 | 사운드리퍼블리카 | 8 | 62.5 |
| 2) 유통사 상위10 | 마운드미디어 | 7 | 100.0 |
| 2) 유통사 상위10 | 지니뮤직, STONE MUSIC | 6 | 50.0 |
| 2) 유통사 상위10 | (주)지니뮤직 | 6 | 83.3 |
| 2) 유통사 상위10 | YG PLUS | 6 | 33.3 |
| 2) 유통사 상위10 | 카카오엔터테인먼트 | 5 | 20.0 |
| 2) 유통사 상위10 | 주식회사 코부코 | 5 | 0.0 |
| 2) 유통사 상위10 | 워너뮤직/ADA | 4 | 50.0 |

### a09_score_v0_backtest

- 질문: 손으로 정한 점수 v0로 '그때 기준' 상위 K팀을 뽑았다면, 그중 몇 팀이 나중에 실제로 정답(신인상·주요 신인 프로그램)을 받았나? 무작위·단순 기준보다 나은가?
- 왜 중요한가: 점수가 쓸모 있으려면 '미래를 모르는 상태'에서 뽑은 상위 목록이 무작위보다 정답을 많이 담아야 한다(백테스트).
- 읽는 법: 기준일(cutoff) 전 3년 신호만으로 점수를 매기고, 기준일 뒤 정답으로 채점한다. 적중률 = 상위 K팀 중 정답 팀 비율,
- 배수 = 적중률 ÷ 기준율(후보 전체의 정답 비율 = 무작위로 K팀 뽑았을 때 기대값). 배수가 1보다 크면 무작위보다 낫다.
- 비교 방법: '점수 v0' / '공연 수만' / '갈래 수만' / '무작위'(기준율 × K).
- 점수 v0 (가중치는 데이터에 맞춰 조정하지 않은 손 규칙 — 과적합 방지, PROJECT.md 점수 규칙 후보 그대로):
- 2 × (갈래 수 − 1) + 선정 최고 단계(STAGE_RANK 0~4) + 1 × 선정 팀과 같은 무대 + 0.5 × DMZ 출연
- + 0.5 × ln(1 + 직전 1년 공연 수) + 1 × min(큐레이션 매체 수, 3)
- 데이터 주의: 정답이 모두 2025년 이후라 '중간 정답 보유'·'이미 정답 팀과 같은 무대' 신호는 기준일 전에 생길 수 없어
- '선정(selected 이상) 팀과 같은 무대'로 대신했다. 발매 갈래는 2026-11 이후만 있어 백테스트에 안 쓴다.
- 신인 대용: 멜론 프로필이 대부분 없어서 '우리 데이터에 처음 나온 지 3년 이내' 팀만 후보로 둔다(없으면 이센스·9와숫자들 같은
- 기성 팀이 DMZ·큐레이션 덕에 상위를 차지함). DMZ 출연은 선정 단계에서 빼고 0.5 가점으로만 센다.
- 유명 팀 제외는 지금의 멜론 프로필 기준이라 약간의 미래 정보가 섞인다(프로필 없는 팀은 그대로 둔다).
- 팀 묶기: core 뷰의 team_key (아티스트 연결표 ref.artist_xref, 없으면 괄호 별칭). 유명 팀 판정도 team_key로 찾는다
- (영문 키로 저장된 프로필 — 예: xdinaryheroes — 도 한글 팀 이름에 붙도록).
- 기준일 뒤 관찰 기간이 2026-11까지로 짧아(17~23개월) 나중에 정답을 받을 팀이 '틀림'으로 세어질 수 있다.

<details><summary>쿼리 보기</summary>

```sql
WITH params AS (
    SELECT DATE '2025-01-01' AS cutoff UNION ALL
    SELECT DATE '2025-07-01'
),
sig AS (                                              -- 기준일 전 3년 신호, 팀 키 통일
    SELECT p.cutoff, s.team_key,                     -- 팀 대표 키 (core 뷰: 연결표 → 괄호 별칭)
           s.branch, s.program, s.stage_rank, s.signal_date, s.detail
    FROM core.v_signal s
    JOIN params p ON s.signal_date <  p.cutoff
                 AND s.signal_date >= p.cutoff - INTERVAL '3 years'
    WHERE s.artist_key IS NOT NULL AND s.artist_key <> ''
),
outcome AS (                                          -- 센 정답, 팀 키 통일
    SELECT o.team_key, MIN(o.announced_start) AS first_outcome
    FROM core.v_outcome o
    WHERE o.counted
    GROUP BY 1
),
selected_team AS (                                    -- 선정(selected 이상)된 팀과 그 날짜
    SELECT cutoff, team_key, MIN(signal_date) AS selected_on
    FROM sig WHERE branch = '선정·지원' AND stage_rank >= 3
    GROUP BY 1, 2
),
gig AS (
    SELECT DISTINCT cutoff, team_key, signal_date AS gig_date, detail AS venue
    FROM sig WHERE branch = '공연' AND COALESCE(detail, '') NOT IN ('', '공연장 미정')
),
peer AS (                                             -- 공연 당시 이미 선정된 다른 팀과 같은 날·같은 공연장에 섬
    SELECT DISTINCT a.cutoff, a.team_key
    FROM gig a
    JOIN gig b ON b.cutoff = a.cutoff AND b.gig_date = a.gig_date AND b.venue = a.venue AND b.team_key <> a.team_key
    JOIN selected_team st ON st.cutoff = b.cutoff AND st.team_key = b.team_key AND st.selected_on <= a.gig_date
),
feat AS (
    SELECT s.cutoff, s.team_key,
           COUNT(DISTINCT s.branch)                                                        AS n_branch,
           COALESCE(MAX(CASE WHEN s.program <> 'dmz_lineup' THEN s.stage_rank END), 0)     AS best_stage,   -- DMZ는 아래 가점으로만
           MAX(CASE WHEN s.program = 'dmz_lineup' THEN 1 ELSE 0 END)                       AS dmz,
           COUNT(DISTINCT CASE WHEN s.branch = '공연' AND s.signal_date >= s.cutoff - INTERVAL '1 year'
                               THEN s.signal_date END)                                     AS gigs_1y,
           COUNT(DISTINCT CASE WHEN s.branch = '큐레이션' THEN s.program END)               AS outlets
    FROM sig s
    GROUP BY s.cutoff, s.team_key
),
first_seen AS (                                       -- 우리 데이터 전체에서 팀이 처음 나온 날 (상상마당 공연은 2010~)
    SELECT s.team_key, MIN(s.signal_date) AS first_seen
    FROM core.v_signal s
    WHERE s.artist_key IS NOT NULL AND s.artist_key <> ''
    GROUP BY 1
),
pool AS (                                             -- 후보: 기준일 전에 정답 없음, 유명 팀 아님, 처음 나온 지 3년 이내(신인 대용)
    SELECT f.*,
           CASE WHEN pe.team_key IS NOT NULL THEN 1 ELSE 0 END AS peer_selected,
           CASE WHEN o.first_outcome >= f.cutoff THEN 1 ELSE 0 END AS is_hit
    FROM feat f
    LEFT JOIN peer pe ON pe.cutoff = f.cutoff AND pe.team_key = f.team_key
    LEFT JOIN outcome o ON o.team_key = f.team_key
    JOIN first_seen fs ON fs.team_key = f.team_key
    WHERE fs.first_seen >= f.cutoff - INTERVAL '3 years'
      AND (o.first_outcome IS NULL OR o.first_outcome >= f.cutoff)
      AND NOT EXISTS (SELECT 1 FROM core.v_artist_status st             -- 유명 팀 제외 (팀 대표 키로, 프로필 중 하나라도 유명이면)
                      WHERE st.team_key = f.team_key AND st.status = 'famous')
),
scored AS (
    SELECT p.*,
           2 * (n_branch - 1) + best_stage + peer_selected + 0.5 * dmz
           + 0.5 * LN(1 + gigs_1y) + LEAST(outlets, 3)                                     AS score_v0
    FROM pool p
),
ranked AS (                                           -- 동점은 팀 키 해시로 고정(매번 같은 결과)
    SELECT cutoff, is_hit,
           ROW_NUMBER() OVER (PARTITION BY cutoff ORDER BY score_v0 DESC, MD5(team_key)) AS r_score,
           ROW_NUMBER() OVER (PARTITION BY cutoff ORDER BY gigs_1y  DESC, MD5(team_key)) AS r_gigs,
           ROW_NUMBER() OVER (PARTITION BY cutoff ORDER BY n_branch DESC, MD5(team_key)) AS r_branch
    FROM scored
),
base AS (
    SELECT cutoff, COUNT(*) AS pool_n, SUM(is_hit) AS pool_hits, 1.0 * SUM(is_hit) / COUNT(*) AS base_rate
    FROM scored GROUP BY cutoff
),
ks AS (SELECT 20 AS k UNION ALL SELECT 50 UNION ALL SELECT 100 UNION ALL SELECT 200),
result AS (
    SELECT r.cutoff, ks.k, '점수 v0' AS method, SUM(CASE WHEN r.r_score  <= ks.k THEN r.is_hit ELSE 0 END) AS hits
    FROM ranked r CROSS JOIN ks GROUP BY 1, 2
    UNION ALL
    SELECT r.cutoff, ks.k, '공연 수만', SUM(CASE WHEN r.r_gigs   <= ks.k THEN r.is_hit ELSE 0 END)
    FROM ranked r CROSS JOIN ks GROUP BY 1, 2
    UNION ALL
    SELECT r.cutoff, ks.k, '갈래 수만', SUM(CASE WHEN r.r_branch <= ks.k THEN r.is_hit ELSE 0 END)
    FROM ranked r CROSS JOIN ks GROUP BY 1, 2
)
SELECT res.cutoff                                         AS 기준일,
       b.pool_n                                           AS 후보_팀수,
       b.pool_hits                                        AS 이후_정답_팀수,
       res.k                                              AS 상위_k,
       res.method                                         AS 방법,
       res.hits                                           AS 맞힌_팀수,
       ROUND(100.0 * res.hits / res.k, 1)                 AS 적중률_pct,
       ROUND(b.base_rate * res.k, 1)                      AS 무작위_기대_팀수,
       ROUND(res.hits / NULLIF(b.base_rate * res.k, 0), 1) AS 무작위_대비_배수
FROM result res
JOIN base b ON b.cutoff = res.cutoff
ORDER BY res.cutoff, res.k, res.method;
```

</details>

결과 24행

| 기준일 | 후보_팀수 | 이후_정답_팀수 | 상위_k | 방법 | 맞힌_팀수 | 적중률_pct | 무작위_기대_팀수 | 무작위_대비_배수 |
|---|---|---|---|---|---|---|---|---|
| 2025-01-01 | 2581 | 25 | 20 | 갈래 수만 | 1 | 5.0 | 0.2 | 5.2 |
| 2025-01-01 | 2581 | 25 | 20 | 공연 수만 | 0 | 0.0 | 0.2 | 0.0 |
| 2025-01-01 | 2581 | 25 | 20 | 점수 v0 | 2 | 10.0 | 0.2 | 10.3 |
| 2025-01-01 | 2581 | 25 | 50 | 갈래 수만 | 2 | 4.0 | 0.5 | 4.1 |
| 2025-01-01 | 2581 | 25 | 50 | 공연 수만 | 2 | 4.0 | 0.5 | 4.1 |
| 2025-01-01 | 2581 | 25 | 50 | 점수 v0 | 2 | 4.0 | 0.5 | 4.1 |
| 2025-01-01 | 2581 | 25 | 100 | 갈래 수만 | 2 | 2.0 | 1.0 | 2.1 |
| 2025-01-01 | 2581 | 25 | 100 | 공연 수만 | 3 | 3.0 | 1.0 | 3.1 |
| 2025-01-01 | 2581 | 25 | 100 | 점수 v0 | 3 | 3.0 | 1.0 | 3.1 |
| 2025-01-01 | 2581 | 25 | 200 | 갈래 수만 | 5 | 2.5 | 1.9 | 2.6 |
| 2025-01-01 | 2581 | 25 | 200 | 공연 수만 | 6 | 3.0 | 1.9 | 3.1 |
| 2025-01-01 | 2581 | 25 | 200 | 점수 v0 | 5 | 2.5 | 1.9 | 2.6 |
| 2025-07-01 | 3255 | 20 | 20 | 갈래 수만 | 1 | 5.0 | 0.1 | 8.1 |
| 2025-07-01 | 3255 | 20 | 20 | 공연 수만 | 1 | 5.0 | 0.1 | 8.1 |
| 2025-07-01 | 3255 | 20 | 20 | 점수 v0 | 1 | 5.0 | 0.1 | 8.1 |

_24행 중 15행만 표시_

## 데이터 검증 SQL

아티스트 매칭·메타데이터 검수: 수집 데이터의 문제 행 찾기

### c01_release_date_mismatch

- 무엇을 찾나: 같은 앨범(artist_key + title_key)이 2개 이상 플랫폼에 올라왔는데 발매일(released_at)이 서로 다른 경우.
- 왜 문제인가: 플랫폼마다 발매일을 다르게 적으면 "언제 처음 나왔나"가 흔들려 신호 시점·첫 발매 계산이 틀어진다.
- 결과를 보고 할 일: 날짜 차이가 큰 줄부터 원본 페이지를 확인하고, 앨범 발매일은 가장 이른 날(또는 신뢰 플랫폼)로 정한다.

<details><summary>쿼리 보기</summary>

```sql
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
```

</details>

결과 0행

_결과 없음_

### c02_name_variants

- 무엇을 찾나: 같은 artist_key인데 원문 표기(artist_text)가 2가지 이상으로 적힌 팀 (모든 raw 표 통틀어).
- 왜 문제인가: 표기가 여러 개면 매칭 규칙(괄호·공백·대소문자 제거)에 의존하게 되고, 규칙이 바뀌면 같은 팀이 둘로 갈라진다.
- 결과를 보고 할 일: 표기 수가 많은 팀부터 대표 표기를 정해 별칭 사전(ref)에 등록하고, 다른 팀이 섞였는지 눈으로 확인한다.

<details><summary>쿼리 보기</summary>

```sql
WITH all_names AS (
    SELECT 'release' AS tbl, artist_key, artist_text FROM raw.raw_kr_release
    UNION ALL SELECT 'gig',       artist_key, artist_text FROM raw.raw_kr_gig
    UNION ALL SELECT 'selection', artist_key, artist_text FROM raw.raw_kr_selection
    UNION ALL SELECT 'press',     artist_key, artist_text FROM raw.raw_press
    UNION ALL SELECT 'outcome',   artist_key, artist_text FROM raw.raw_outcome
    UNION ALL SELECT 'profile',   artist_key, artist_text FROM raw.raw_artist_profile
),
spelling AS (
    SELECT artist_key, artist_text,
           count(*) AS rows_n,
           string_agg(DISTINCT tbl, '/') AS tables
    FROM all_names
    WHERE artist_key IS NOT NULL AND artist_key <> '' AND artist_text IS NOT NULL
    GROUP BY artist_key, artist_text
),
ranked AS (
    SELECT artist_key,
           count(*)    AS variant_count,
           sum(rows_n) AS total_rows,
           string_agg(artist_text || ' [' || rows_n || ', ' || tables || ']', ' | ' ORDER BY rows_n DESC, artist_text) AS spellings
    FROM spelling
    GROUP BY artist_key
    HAVING count(*) >= 2
)
SELECT artist_key, variant_count, total_rows, spellings
FROM ranked
ORDER BY variant_count DESC, total_rows DESC, artist_key
LIMIT 30;
```

</details>

결과 30행

| artist_key | variant_count | total_rows | spellings |
|---|---|---|---|
| 컨파인드화이트 | 5 | 26 | 컨파인드화이트 [20, gig] \| 컨파인드 화이트 [3, outcome] \| 컨파인드 화이트 (Confined White) [1, press] \| 컨파인드 화이트(Confined White) [1, outcome] \| 컨파인드화이트 (Confined White) [1, press] |
| 릴리잇머신 | 4 | 18 | 릴리잇머신 [14, gig] \| 릴리 잇 머신 [2, outcome/profile] \| 릴리 잇 머신 (Lilly Eat Machine) [1, profile] \| 릴리잇머신 (Lily Eat Machine) [1, press] |
| 피치트럭하이재커스 | 4 | 17 | 피치트럭하이재커스 [12, gig/outcome/selection] \| 피치트럭하이재커스 (Peach Truck Hijackers) [3, press] \| 피치 트럭 하이재커스(Peach Truck Hijackers) [1, outcome] \| 피치트럭 하이재커스(Peach Truck Hijackers) [1, outcome] |
| 터치드 | 4 | 11 | 터치드 [6, gig/outcome] \| 터치드 (Touched) [3, press] \| 터치드(Touched) [1, selection] \| 터치드(TOUCHED) [1, profile] |
| 술탄오브더디스코 | 4 | 7 | 술탄 오브 더 디스코 [4, gig/release/selection] \| 술탄오브더디스코 [1, gig] \| 술탄 오브 더 디스코 (Sultan Of The Disco) [1, press] \| 술탄오브더디스코 (Sultan Of The Disco) [1, press] |
| 카코포니 | 4 | 7 | 카코포니 [3, gig] \| 카코포니 (cacophony) [2, press] \| 카코포니 (Cacophony) [1, press] \| 카코포니(Cacophony) [1, gig] |
| 오티스림 | 4 | 6 | 오티스림 [3, gig/outcome/selection] \| 오티스 림 [1, press] \| 오티스 림 (Otis Lim) [1, press] \| 오티스림 (Otis Lim) [1, press] |
| 유라 | 4 | 6 | 유라 [2, press] \| 유라 (Youra) [2, press] \| 유라 (youra) [1, press] \| 유라(youra) [1, press] |
| 오코예 | 4 | 5 | 오코예(O'KOYE) [2, outcome/press] \| 오코예 (O'KOYE) [1, press] \| 오코예 (O’Koye) [1, press] \| 오코예 (O’KOYE) [1, press] |
| 사비나앤드론즈 | 4 | 4 | 사비나앤드론즈 [1, gig] \| 사비나 앤 드론즈 [1, outcome] \| 사비나 앤 드론즈 (Savina & Drones) [1, press] \| 사비나앤드론즈 (Savina & Drones) [1, press] |
| 사이먼도미닉 | 4 | 4 | 사이먼 도미닉 [1, gig] \| 사이먼 도미닉 (Simon Dominic) [1, press] \| 사이먼 도미닉(Simon Dominic) [1, press] \| 사이먼도미닉 (Simon Dominic) [1, press] |
| 라이엇키즈 | 3 | 49 | 라이엇키즈 [47, gig] \| 라이엇키즈 (Riot Kidz) [1, press] \| 라이엇 키즈(RIOT KIDZ) [1, selection] |
| 더바스타즈 | 3 | 28 | 더 바스타즈 [26, gig] \| 더 바스타즈 (The Vastards) [1, profile] \| 더 바스타즈(The Vastards) [1, outcome] |
| 콘트라젤리 | 3 | 28 | 콘트라젤리 [26, gig/press] \| 콘트라젤리 (Kontrajelly) [1, press] \| 콘트라젤리 (KONTRAJELLY) [1, press] |
| 키라라 | 3 | 24 | 키라라 [19, gig/press/selection] \| 키라라 (KIRARA) [4, press] \| 키라라 (Kirara) [1, press] |

_30행 중 15행만 표시_

### c03_daily_volume_drop

- 무엇을 찾나: 표·소스·수집일(collected_at 날짜)별 행 수를 세고, 직전 수집일보다 50% 넘게 줄어든 날을 표시한다.
- 왜 문제인가: 사이트 구조가 바뀌거나 차단되면 수집기는 오류 없이 "적게" 가져온다. 행 수 급감이 가장 빠른 고장 신호다.
- 결과를 보고 할 일: is_drop = true 인 줄의 수집기를 바로 다시 돌려 보고, 원본 페이지와 파서를 점검한다. (첫 수집일은 비교 대상 없음)

<details><summary>쿼리 보기</summary>

```sql
WITH all_rows AS (
    SELECT 'raw_kr_release' AS tbl, source, collected_at FROM raw.raw_kr_release
    UNION ALL SELECT 'raw_kr_gig',         source, collected_at FROM raw.raw_kr_gig
    UNION ALL SELECT 'raw_kr_selection',   source, collected_at FROM raw.raw_kr_selection
    UNION ALL SELECT 'raw_press',          source, collected_at FROM raw.raw_press
    UNION ALL SELECT 'raw_outcome',        source, collected_at FROM raw.raw_outcome
    UNION ALL SELECT 'raw_artist_profile', source, collected_at FROM raw.raw_artist_profile
),
daily AS (
    SELECT tbl, source, CAST(collected_at AS date) AS collected_date, count(*) AS rows_n
    FROM all_rows
    GROUP BY tbl, source, CAST(collected_at AS date)
),
with_prev AS (
    SELECT d.*,
           lag(rows_n)         OVER (PARTITION BY tbl, source ORDER BY collected_date) AS prev_rows,
           lag(collected_date) OVER (PARTITION BY tbl, source ORDER BY collected_date) AS prev_date
    FROM daily d
)
SELECT tbl, source, collected_date, rows_n, prev_date, prev_rows,
       CASE WHEN prev_rows IS NULL THEN NULL
            ELSE round(100.0 * (rows_n - prev_rows) / prev_rows, 1) END AS change_pct,
       COALESCE(rows_n < prev_rows * 0.5, false)                         AS is_drop
FROM with_prev
ORDER BY is_drop DESC, tbl, source, collected_date DESC;
```

</details>

결과 27행

| tbl | source | collected_date | rows_n | prev_date | prev_rows | change_pct | is_drop |
|---|---|---|---|---|---|---|---|
| raw_artist_profile | instagram | 2026-11-27 | 19 | 2026-11-26 | 107 | -82.2 | t |
| raw_artist_profile | instagram | 2026-11-26 | 107 |  |  |  | f |
| raw_artist_profile | melon | 2026-11-26 | 83 |  |  |  | f |
| raw_artist_profile | spotify | 2026-11-26 | 43 |  |  |  | f |
| raw_kr_gig | indiego | 2026-11-26 | 427 |  |  |  | f |
| raw_kr_gig | indistreet | 2026-11-26 | 14192 |  |  |  | f |
| raw_kr_gig | sangsangmadang | 2026-11-26 | 849 |  |  |  | f |
| raw_kr_release | bugs | 2026-11-26 | 70 |  |  |  | f |
| raw_kr_release | flo | 2026-11-26 | 39 |  |  |  | f |
| raw_kr_release | genie | 2026-11-26 | 46 |  |  |  | f |
| raw_kr_release | melon | 2026-11-26 | 62 |  |  |  | f |
| raw_kr_release | poclanos | 2026-11-26 | 33 |  |  |  | f |
| raw_kr_selection | busanrock | 2026-11-26 | 13 |  |  |  | f |
| raw_kr_selection | dmz | 2026-11-26 | 152 |  |  |  | f |
| raw_kr_selection | gbsound | 2026-11-26 | 33 |  |  |  | f |

_27행 중 15행만 표시_

### c04_missing_fields

- 무엇을 찾나: 핵심 칸이 비었거나 덜 정확한 비율 — 공연(장소·시각), 발매(유통사·레이블·장르), 선정(연도만 아는 날짜), 정답(연·월만 아는 날짜).
- 왜 문제인가: 빈 칸이 많은 소스는 장소·장르 분석에서 빠지고, 날짜가 거칠면 "신호가 정답보다 먼저였나" 판정이 흐려진다.
- 결과를 보고 할 일: 비율이 높은 소스부터 수집기에서 해당 칸을 더 가져올 수 있는지 보고, 안 되면 다른 소스로 보충한다.

<details><summary>쿼리 보기</summary>

```sql
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
```

</details>

결과 46행

| tbl | source_or_program | check_name | total_rows | problem_rows | problem_pct |
|---|---|---|---|---|---|
| raw_kr_gig | sangsangmadang | gig_time 없음 | 849 | 204 | 24.0 |
| raw_kr_gig | indistreet | gig_time 없음 | 14192 | 848 | 6.0 |
| raw_kr_gig | indiego | gig_time 없음 | 427 | 0 | 0.0 |
| raw_kr_gig | indistreet | venue_text 없음 | 14192 | 848 | 6.0 |
| raw_kr_gig | indiego | venue_text 없음 | 427 | 0 | 0.0 |
| raw_kr_gig | sangsangmadang | venue_text 없음 | 849 | 0 | 0.0 |
| raw_kr_release | poclanos | distributor_text 없음 | 33 | 33 | 100.0 |
| raw_kr_release | bugs | distributor_text 없음 | 70 | 0 | 0.0 |
| raw_kr_release | flo | distributor_text 없음 | 39 | 0 | 0.0 |
| raw_kr_release | genie | distributor_text 없음 | 46 | 0 | 0.0 |
| raw_kr_release | melon | distributor_text 없음 | 62 | 0 | 0.0 |
| raw_kr_release | bugs | genre 없음 | 70 | 0 | 0.0 |
| raw_kr_release | flo | genre 없음 | 39 | 0 | 0.0 |
| raw_kr_release | genie | genre 없음 | 46 | 0 | 0.0 |
| raw_kr_release | melon | genre 없음 | 62 | 0 | 0.0 |

_46행 중 15행만 표시_

### c05_namesake_risk

- 무엇을 찾나: 동명 팀 의심 — (A) 한 artist_key가 멜론 아티스트 ID 2개 이상에 연결, (B) 2010년 이전 선정 기록과 2024년 이후 공연이 같은 키에 함께 있음.
- 왜 문제인가: 이름만으로 팀을 잇기 때문에, 다른 두 팀이 한 팀으로 합쳐지면 연차·첫 발매·적중 계산이 모두 틀어진다.
- 결과를 보고 할 일: 멜론 ID·활동 연도·장르를 비교해 다른 팀이면 별도 키(예: 이름+ID)로 나누는 수동 매핑을 만든다.

<details><summary>쿼리 보기</summary>

```sql
WITH multi_profile AS (
    SELECT artist_key,
           count(DISTINCT artist_source_id) AS melon_id_count,
           string_agg(DISTINCT artist_text || ' (id ' || artist_source_id || ', 데뷔 '
                      || COALESCE(debut_date, first_release_date, '?') || ')', ' | ') AS evidence
    FROM raw.raw_artist_profile
    WHERE artist_key IS NOT NULL
    GROUP BY artist_key
    HAVING count(DISTINCT artist_source_id) >= 2
),
old_selection AS (
    SELECT artist_key, min(announced_start) AS first_sel, min(program) AS program
    FROM raw.raw_kr_selection
    WHERE announced_end < DATE '2010-01-01'
    GROUP BY artist_key
),
recent_gig AS (
    SELECT artist_key, max(gig_date) AS last_gig, count(*) AS recent_gigs
    FROM raw.raw_kr_gig
    WHERE gig_date >= DATE '2024-01-01'
    GROUP BY artist_key
)
SELECT 'A: 멜론 ID 여러 개' AS risk_type, artist_key, melon_id_count AS strength, evidence
FROM multi_profile
UNION ALL
SELECT 'B: 2010년 전 선정 + 2024년 후 공연', s.artist_key, g.recent_gigs,
       s.program || ' ' || s.first_sel || ' 선정 / 최근 공연 ' || g.recent_gigs || '회 (마지막 ' || g.last_gig || ')'
FROM old_selection s
JOIN recent_gig g ON g.artist_key = s.artist_key
ORDER BY risk_type, strength DESC, artist_key;
```

</details>

결과 48행

| risk_type | artist_key | strength | evidence |
|---|---|---|---|
| A: 멜론 ID 여러 개 | 구구 | 3 | 구구 (GuGu) (id 2897501, 데뷔 2021-04-07) \| 구구 (id 5wpgBWnsCL8y5s5FSwY71k, 데뷔 2021-04-07) \| 구구(GuGu) (id 9u9u_01, 데뷔 ?) |
| A: 멜론 ID 여러 개 | 블낫블 | 3 | 블낫블 𝐁𝐥𝐮𝐞 𝐢𝐬 𝐍𝐨𝐭 𝐁𝐥𝐮𝐞 (id off.bnb, 데뷔 ?) \| 블낫블(Blue is Not Blue) (id 0uTWf6LJUvbPgJ67K9CVRL, 데뷔 2025-07-29) \| 블낫블(Blue is Not Blue) (id 4408798, 데뷔 2025-07-29) |
| A: 멜론 ID 여러 개 | luamel | 3 | LUAMEL (루아멜) (id 2299617, 데뷔 2018-10-05) \| LUAMEL (루아멜) (id luamel_official, 데뷔 ?) \| LUAMEL (id 0GP1FM3P7XrmSNz1Nr29Yy, 데뷔 2018-10-05) |
| A: 멜론 ID 여러 개 | 공원 | 2 | 공원 (id 3563915, 데뷔 2025-03-27) \| 공원 (id 40Gp1pozXyDoTKNkxTbZKQ, 데뷔 2025-06-03) |
| A: 멜론 ID 여러 개 | 김승주 | 2 | 김승주 (id 2877532, 데뷔 2020-06-30) \| 김승주 (id 7wV6FuZ1nuVpI7rH0jRRuj, 데뷔 2025-07-21) |
| A: 멜론 ID 여러 개 | 김시온 | 2 | 김시온 (id 6Sb6DraTcNV5zaqWDgMCoa, 데뷔 2023-07-07) \| 김시온 (Kim Sion) (id 2957454, 데뷔 2021-08-10) |
| A: 멜론 ID 여러 개 | 릴리잇머신 | 2 | 릴리 잇 머신 (id 1ogeL4SXrnpTgS0cB917ww, 데뷔 2023-10-06) \| 릴리 잇 머신 (Lilly Eat Machine) (id 3573882, 데뷔 2023-10-06) |
| A: 멜론 ID 여러 개 | 브로콜리너마저 | 2 | 브로콜리너마저 (id 1gq4XavqmZhqOzEkpFBz1j, 데뷔 2010-11-01) \| 브로콜리너마저 (id 230490, 데뷔 2007-10-31) |
| A: 멜론 ID 여러 개 | 산만한시선 | 2 | 산만한시선 (id 2aqvIa1gUFcwMDEWOsEdsm, 데뷔 ?) \| 산만한시선 (id 4011774, 데뷔 2024-10-31) |
| A: 멜론 ID 여러 개 | 산보 | 2 | 산보 (id 2rKxDvJDT1Pv93k4ohx8Cp, 데뷔 2024-09-19) \| 산보 (id 3940959, 데뷔 2024-09-19) |
| A: 멜론 ID 여러 개 | 삼산 | 2 | 삼산 (id 0Mqb4ZExEqQNOkEFSyZiql, 데뷔 2023-10-13) \| 삼산 (id 3584597, 데뷔 2023-10-13) |
| A: 멜론 ID 여러 개 | 송소희 | 2 | 송소희 (id 2CqJ2OWIZcSwKtfslMLj7W, 데뷔 ?) \| 송소희 (id 672059, 데뷔 2015-04-23) |
| A: 멜론 ID 여러 개 | 신인류 | 2 | 신인류 (id 2298840, 데뷔 2018-09-26) \| 신인류 (id 6hqKJovR688oBXggv1iCGF, 데뷔 ?) |
| A: 멜론 ID 여러 개 | 우륵과풍각쟁이들 | 2 | 우륵과 풍각쟁이들 (id 3QQr6mc2bkCf1znKo4uUUa, 데뷔 2025-09-16) \| 우륵과 풍각쟁이들 (id 4581741, 데뷔 2025-09-16) |
| A: 멜론 ID 여러 개 | 우수현 | 2 | 우수현 (id 0JjuaT60jLgBmyqcMkTDjD, 데뷔 2024-01-24) \| 우수현 (id 3458321, 데뷔 2024-01-24) |

_48행 중 15행만 표시_

### c06_multi_person_cells

- 무엇을 찾나: 한 칸(artist_text)에 여러 사람·팀이 들어간 것처럼 보이는 값 (', ' / ' 외 ' / ' x ' / '&' / '/' 포함).
- 왜 문제인가: "A, B" 가 통째로 하나의 팀 키가 되어 A·B 각각의 기록에 잡히지 않는다 (신호 누락).
- 결과를 보고 할 일: 진짜 합동 무대면 행을 팀별로 나누고, "한글 / English" 병기나 이름 자체의 &(예: ~ & the band)는 예외 목록에 넣는다.
- (HTML 엔티티 &apos; &amp; 는 먼저 풀어서 판정한다 — 엔티티 자체는 c08에서 따로 본다)

<details><summary>쿼리 보기</summary>

```sql
WITH all_names AS (
    SELECT 'release' AS tbl, artist_text FROM raw.raw_kr_release
    UNION ALL SELECT 'gig',       artist_text FROM raw.raw_kr_gig
    UNION ALL SELECT 'selection', artist_text FROM raw.raw_kr_selection
    UNION ALL SELECT 'press',     artist_text FROM raw.raw_press
    UNION ALL SELECT 'outcome',   artist_text FROM raw.raw_outcome
    UNION ALL SELECT 'profile',   artist_text FROM raw.raw_artist_profile
),
decoded AS (
    SELECT tbl, artist_text,
           replace(replace(replace(artist_text, '&apos;', ''''), '&#39;', ''''), '&amp;', '&') AS name
    FROM all_names
    WHERE artist_text IS NOT NULL
),
classified AS (
    SELECT tbl, artist_text,
           CASE
             WHEN name LIKE '% 외 %' OR name LIKE '% 외' OR name ~ ' 외 ?[0-9]+명' THEN '외 N명'
             WHEN name LIKE '% x %' OR name LIKE '% X %'                         THEN 'x 협업'
             WHEN name LIKE '%, %'                                                THEN '쉼표 나열'
             WHEN name LIKE '%&%'                                                 THEN '& 연결'
             WHEN name ~ '^[^/]*[가-힣][^/]* / [^가-힣/]+$'
               OR name ~ '^[^가-힣/]+ / [^/]*[가-힣][^/]*$'                       THEN '/ 한영 병기(대개 한 팀)'
             WHEN name LIKE '%/%'                                                 THEN '/ 나열'
           END AS pattern
    FROM decoded
),
flagged AS (
    SELECT tbl, pattern, artist_text, count(*) AS rows_n
    FROM classified
    WHERE pattern IS NOT NULL
    GROUP BY tbl, pattern, artist_text
),
ranked AS (
    SELECT f.*, row_number() OVER (PARTITION BY tbl, pattern ORDER BY rows_n DESC, artist_text) AS rn,
           count(*)    OVER (PARTITION BY tbl, pattern) AS distinct_values,
           sum(rows_n) OVER (PARTITION BY tbl, pattern) AS total_rows
    FROM flagged f
)
SELECT tbl, pattern, distinct_values, total_rows,
       string_agg(artist_text || ' (' || rows_n || ')', ' | ' ORDER BY rn) AS top_examples
FROM ranked
WHERE rn <= 5
GROUP BY tbl, pattern, distinct_values, total_rows
ORDER BY tbl, total_rows DESC;
```

</details>

결과 18행

| tbl | pattern | distinct_values | total_rows | top_examples |
|---|---|---|---|---|
| gig | / 한영 병기(대개 한 팀) | 18 | 84 | 디아틱 / The ATIC (28) \| 일가인 / ilgyne (18) \| 칩포스트갱 / Chip Post Gang (11) \| 미역수염 / Seaweedmustache (5) \| 고고학 / GOGOHAWK (3) |
| gig | & 연결 | 36 | 62 | 팻햄스터&캉뉴 (21) \| Groover Kim & Jazzup Band (3) \| 나잠수&문선 (2) \| 이지연&신설아 (2) \| 해미&승혜 (2) |
| gig | 쉼표 나열 | 4 | 4 | 저, 밴드맨이 됩니다 (1) \| 고요, 비눗방울, 우주 (1) \| Black Country, New Road (1) \| Moon, Night & Starts (1) |
| gig | x 협업 | 2 | 4 | 블랙홀 X 방수미 (2) \| Love X Stereo (2) |
| gig | / 나열 | 2 | 2 | 펜타클 (Pentacle)  서경대학교 / 더티슈 (Dirty Shoe)  경희대학교 / 울림터 (Ullimteo) 연세대학교 / 마젠타 (Magenta) 국민대학교 / 데스티니 (Destiny)  숙명여자대학교 (1) \| Sunn-Row w/ WeDaBand (1) |
| outcome | & 연결 | 2 | 2 | 정지수 & Baroque in Blue (1) \| yonglee & the DOLTANG (1) |
| press | 쉼표 나열 | 28 | 31 | SUMIN, Slom (2) \| Sun Gin, 격 (2) \| Tyler, The Creator (2) \| 데미지 없이도 끌어올린 타격감, 김도언 (1) \| 카더가든 (Car, the garden) (1) |
| press | & 연결 | 26 | 27 | Maalib & WRKMS (2) \| 슬라이 앤 더 패밀리 스톤 (Sly & The Family Stone) (1) \| 사비나 앤 드론즈 (Savina & Drones) (1) \| 재키 와이 & 방달 (1) \| 키드 밀리 & 오카시 (1) |
| press | / 나열 | 4 | 5 | Model/Actriz (2) \| 시월 (Cwar) / 반타01 (VANTA01) (1) \| 제이미 / 박지민 (Jamie) (1) \| 케이에이치씨/모리벳 (khc/moribet) (1) |
| press | x 협업 | 2 | 2 | 데이지둠 (Love X Stereo (1) \| 투모로우바이투게더 (Tomorrow X Together) (1) |
| profile | 쉼표 나열 | 2 | 2 | 클럽빵 LiveClub BBang, korea first & longest indie (1) \| 구름, cloud koh, クラウド, 고형석 (1) |
| profile | / 나열 | 2 | 2 | 뮤즈온 / MUSE ON (1) \| 坂東祐大 / Yuta Bandoh (1) |
| profile | / 한영 병기(대개 한 팀) | 2 | 2 | 대봉 / Debong (1) \| CHUDAHYE_CHAGIS / 추다혜차지스 (1) |
| profile | & 연결 | 1 | 1 | 단편선 순간들 Danpyunsun & The Moments Ensemble (1) |
| selection | 쉼표 나열 | 19 | 19 | 김수현, 임상현 (1) \| 김태균, 염정업 (1) \| 김현범, 성낙원 (1) \| 나현진, 최민규 (1) \| 박수정, 김민지 (1) |

_18행 중 15행만 표시_

### c07_duplicate_keys

- 무엇을 찾나: 표마다 업무상 같은 행(비즈니스 키)이 여러 번 들어간 경우 — 대개 같은 날 수집기를 다시 돌려 생긴 파일(_HHMMSS.csv) 때문.
- 키: 공연 gig_url+artist_text, 발매 source+source_id(없으면 url), 선정 program+round+stage+artist_text, 정답 program+round+result+artist_text,
- 기사 url+artist_text, 프로필 artist_source_id.
- 왜 문제인가: 중복을 그대로 세면 공연 횟수·신호 수가 부풀려진다. raw는 원본 보존용이므로 뷰(core.*)에서 반드시 중복을 걸러야 한다.
- 결과를 보고 할 일: 표별 중복 비율을 확인하고, 뷰에 DISTINCT ON(키) ORDER BY collected_at DESC 같은 "최신 1건" 규칙을 넣는다.

<details><summary>쿼리 보기</summary>

```sql
WITH keyed AS (
    SELECT 'raw_kr_gig' AS tbl, COALESCE(gig_url, source_id) || ' | ' || artist_text AS biz_key, source_file
    FROM raw.raw_kr_gig
    UNION ALL
    SELECT 'raw_kr_release', source || ':' || COALESCE(source_id, release_url) || ' | ' || artist_text, source_file
    FROM raw.raw_kr_release
    UNION ALL
    SELECT 'raw_kr_selection', program || ' | ' || COALESCE(round, '') || ' | ' || COALESCE(stage, '') || ' | ' || artist_text, source_file
    FROM raw.raw_kr_selection
    UNION ALL
    SELECT 'raw_outcome', program || ' | ' || COALESCE(round, '') || ' | ' || COALESCE(result, '') || ' | ' || artist_text, source_file
    FROM raw.raw_outcome
    UNION ALL
    SELECT 'raw_press', url || ' | ' || artist_text, source_file
    FROM raw.raw_press
    UNION ALL
    SELECT 'raw_artist_profile', source || ':' || artist_source_id, source_file
    FROM raw.raw_artist_profile
),
dup_keys AS (
    SELECT tbl, biz_key, count(*) AS copies,
           count(DISTINCT source_file) AS files,
           string_agg(DISTINCT source_file, ', ') AS file_list
    FROM keyed
    WHERE biz_key IS NOT NULL
    GROUP BY tbl, biz_key
    HAVING count(*) >= 2
),
totals AS (
    SELECT tbl, count(*) AS total_rows FROM keyed GROUP BY tbl
),
ranked AS (
    SELECT d.*, row_number() OVER (PARTITION BY tbl ORDER BY copies DESC, biz_key) AS rn
    FROM dup_keys d
)
SELECT t.tbl, t.total_rows,
       COALESCE(s.dup_keys, 0)    AS dup_keys,
       COALESCE(s.extra_rows, 0)  AS extra_rows,
       round(100.0 * COALESCE(s.extra_rows, 0) / t.total_rows, 1) AS extra_pct,
       COALESCE(s.cross_file_keys, 0) AS keys_in_2plus_files,
       e.examples
FROM totals t
LEFT JOIN (
    SELECT tbl, count(*) AS dup_keys, sum(copies - 1) AS extra_rows,
           sum(CASE WHEN files >= 2 THEN 1 ELSE 0 END) AS cross_file_keys
    FROM dup_keys GROUP BY tbl
) s ON s.tbl = t.tbl
LEFT JOIN (
    SELECT tbl, string_agg(biz_key || ' x' || copies || ' [' || file_list || ']', E'\n' ORDER BY rn) AS examples
    FROM ranked WHERE rn <= 3 GROUP BY tbl
) e ON e.tbl = t.tbl
ORDER BY extra_rows DESC;
```

</details>

결과 6행

| tbl | total_rows | dup_keys | extra_rows | extra_pct | keys_in_2plus_files | examples |
|---|---|---|---|---|---|---|
| raw_kr_gig | 15468 | 469 | 469 | 3.0 | 469 | https://indistreet.com/gigs/2026-11-26-%EA%B7%B8%EB%A3%A8%EB%B8%8C%EC%9E%AC%EC%A6%88%EB%8D%B0%EC%9D%B4-groove-in-november-1126-mly4qbnlzw9ligj6fmalu16i \| Groover Kim & Jazzup Band x2 [raw_kr_gig_2026-11-26_indistreet_212810.csv, raw_kr_gig_2026-11-26_indistreet.csv] https://indistreet.com/gigs/2026-11-26-%EB%85%B8%EB%9E%98%ED%95%98%EB%8A%94-%EC%8B%9C%EC%9D%B8-%EB%B0%95%EC%9D%B8%ED%9D%AC-%EC%BD%98%EC%84%9C%ED%8A%B8-%EC%84%9C%EC%9A%B8-1126-doyp4fygtwysv13gfd7maeou \| 박인희 x2 [raw_kr_gig_2026-11-26_indistreet_212810.csv, raw_kr_gig_2026-11-26_indistreet.csv] https://indistreet.com/gigs/2026-11-26-%EB%A8%BC%EB%8D%B0%EC%9D%B4%ED%94%84%EB%A1%9C%EC%A0%9D%ED%8A%B8-in-%EB%9D%BC%EC%9D%B4%EB%B8%8C%ED%81%B4%EB%9F%BD-mombrimz-%EB%8B%A8%EB%8F%85%EC%BD%98%EC%84%9C%ED%8A%B8-rungxk3vk7o4enrytviw61p8 \| MOMBRIMZ x2 [raw_kr_gig_2026-11-26_indistreet_212810.csv, raw_kr_gig_2026-11-26_indistreet.csv] |
| raw_kr_release | 250 | 36 | 36 | 14.4 | 36 | melon:12885474 \| 한올 x2 [raw_kr_release_2026-11-26_melon_214103.csv, raw_kr_release_2026-11-26_melon.csv] melon:14418214 \| 109 x2 [raw_kr_release_2026-11-26_melon_214103.csv, raw_kr_release_2026-11-26_melon.csv] melon:14965365 \| Aden (에이든) x2 [raw_kr_release_2026-11-26_melon_214103.csv, raw_kr_release_2026-11-26_melon.csv] |
| raw_press | 4150 | 0 | 0 | 0.0 | 0 |  |
| raw_artist_profile | 252 | 0 | 0 | 0.0 | 0 |  |
| raw_kr_selection | 701 | 0 | 0 | 0.0 | 0 |  |
| raw_outcome | 438 | 0 | 0 | 0.0 | 0 |  |

### c08_html_entities_and_handles

- 무엇을 찾나: (A) HTML 특수문자 코드(&amp; &#39; 등)가 그대로 남은 이름, (B) 인스타그램 계정명처럼 보이는 이름(소문자·숫자·_·. 만, 공백·한글 없음).
- 왜 문제인가: "a&amp;b" 와 "a&b", "@band_official" 과 "밴드" 는 다른 키가 되어 같은 팀인데 이어지지 않는다.
- 결과를 보고 할 일: (A)는 적재 전에 HTML 디코딩을 넣고, (B)는 계정명→팀 이름 매핑표(ref)를 만들어 키를 바꾼다.

<details><summary>쿼리 보기</summary>

```sql
WITH all_names AS (
    SELECT 'release' AS tbl, artist_text FROM raw.raw_kr_release
    UNION ALL SELECT 'gig',       artist_text FROM raw.raw_kr_gig
    UNION ALL SELECT 'selection', artist_text FROM raw.raw_kr_selection
    UNION ALL SELECT 'press',     artist_text FROM raw.raw_press
    UNION ALL SELECT 'outcome',   artist_text FROM raw.raw_outcome
    UNION ALL SELECT 'profile',   artist_text FROM raw.raw_artist_profile
),
flagged AS (
    SELECT tbl, artist_text,
           CASE WHEN artist_text ~ '&(#[0-9]+|#x[0-9a-fA-F]+|[a-zA-Z]+);' THEN 'A: HTML 엔티티'
                WHEN artist_text ~ '^@?[a-z0-9._]+$'
                     AND artist_text ~ '[._]'          -- 계정명 특징: _ 또는 . 포함
                     AND artist_text ~ '[a-z]'
                THEN 'B: 인스타 계정명 모양'
           END AS issue,
           count(*) AS rows_n
    FROM all_names
    WHERE artist_text IS NOT NULL
    GROUP BY tbl, artist_text
)
SELECT issue, tbl, artist_text, rows_n
FROM flagged
WHERE issue IS NOT NULL
ORDER BY issue, rows_n DESC, tbl, artist_text;
```

</details>

결과 59행

| issue | tbl | artist_text | rows_n |
|---|---|---|---|
| B: 인스타 계정명 모양 | press | _muse_on | 4 |
| B: 인스타 계정명 모양 | press | kocca_official | 4 |
| B: 인스타 계정명 모양 | press | shin_in_ryu | 3 |
| B: 인스타 계정명 모양 | gig | lyli. | 2 |
| B: 인스타 계정명 모양 | gig | nib.archive | 2 |
| B: 인스타 계정명 모양 | gig | quinn_ | 2 |
| B: 인스타 계정명 모양 | gig | vgtbl.pl | 2 |
| B: 인스타 계정명 모양 | press | fleet_official_ | 2 |
| B: 인스타 계정명 모양 | press | inaekkum_official | 2 |
| B: 인스타 계정명 모양 | press | lunedi_niverse | 2 |
| B: 인스타 계정명 모양 | press | omm.. | 2 |
| B: 인스타 계정명 모양 | press | oysters.999 | 2 |
| B: 인스타 계정명 모양 | press | sally_everywhere_ | 2 |
| B: 인스타 계정명 모양 | press | wemakeeachother_ | 2 |
| B: 인스타 계정명 모양 | gig | autopilot77_77 | 1 |

_59행 중 15행만 표시_

