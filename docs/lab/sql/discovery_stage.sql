-- 발굴 단계 + 단계 안 모멘텀 (기준일 {{as_of}} 시점). 경쟁 서비스(Chartmetric)의 '경력 단계·경력 성장'을 우리 데이터로 옮긴 것.
-- 점수(lab_scored)가 아니라 '어떤 팀부터 볼지' 고르는 화면 칸·필터용이다(점수 새 특징 실험에서 가속도·단계 상승은 효과 없음).
-- 문서: docs/discovery_stage.md (scripts/discovery_stage.py 가 과거 기준일 6개로 단계별 정답률을 잰다).
--
-- 단계 (위 단계가 우선, 기준일 '전' 정보만):
--   4 졸업        기준일 전 S·A등급 센 정답, 또는 유명 팀(지금 팬 수라 fame_known_from() 이후 기준일에만 — features.sql)
--   3 선정·중간 정답  기준일 전 선정 단계 3(선정) 이상(DMZ 제외), 또는 B등급 센 정답
--   2 여러 갈래    남의 언급이 2갈래 이상(공연·큐레이션·선정·지원 중)
--   1 첫 신호      남의 언급 1갈래
--   0 백지        첫 발매(또는 자기 발매 신호)만 있고 남의 언급 없음
-- '남의 언급' = 발매 갈래(자기 발매)가 아닌 신호, 제외 출처(role = excluded)·DMZ 라인업은 뺀다. 검증 대기(pending)·맥락 출처는 센다
--   (점수와 달리 '누가 다뤘나'라는 사실만 보기 때문). 데뷔 코호트(source_scorecard_debut.sql)의 '언급'과 같은 정의.
-- 후보: 신인(프로필 첫 발매일 우선, 없으면 첫 등장이 기준일 전 {{newcomer_years}}년 안)이고 기준일에 이미 알려진 팀
--   (기준일 전 신호가 있거나 첫 발매일이 기준일 전).
-- 모멘텀: 최근 90일 남의 언급 수(recent_n) 대 그 전 90일(prev_n). momentum = ln(1+recent_n) − ln(1+prev_n).
--   momentum_pct = 같은 단계 안 백분위(0~1, PERCENT_RANK). 백지(0단계)는 언급이 없어 NULL.
--   momentum_label = 상승(recent > prev) · 보합(같음) · 하락(recent < prev).
-- 채점(검증용, 오늘 기준일이면 모두 0): is_hit = 기준일 뒤 {{horizon_months}}개월 안 센 정답(같은 집안 정답 제외 — features.sql outcome_ok),
--   hit_sa = 그중 S·A등급, hit_weight = 가장 높은 등급 가중치(S=3·A=2·B=1).
WITH params AS (SELECT DATE {{as_of}} AS d, 90 AS mdays),
mention AS (                                    -- 기준일 전 '남의 언급'
    SELECT s.* FROM signals s, params p
    WHERE s.signal_date < p.d
      AND s.branch <> '발매'
      AND COALESCE(s.role, '') <> 'excluded'
      AND COALESCE(s.program, '') <> 'dmz_lineup'
),
known AS (                                      -- 기준일에 알려진 신인 팀
    SELECT t.team_key, COALESCE(t.display_name, t.team_key) AS display_name, t.primary_genre,
           t.first_release, t.profile_status
    FROM teams t, params p
    WHERE COALESCE(t.first_release, t.first_seen) >= p.d - to_years(CAST({{newcomer_years}} AS INTEGER))
      AND (t.first_release <= p.d
           OR EXISTS (SELECT 1 FROM signals s WHERE s.team_key = t.team_key AND s.signal_date < p.d
                                                 AND COALESCE(s.role, '') <> 'excluded'))
),
ment AS (
    SELECT m.team_key,
           COUNT(DISTINCT m.branch)                                                        AS n_mention_branches,
           COALESCE(MAX(CASE WHEN m.branch = '선정·지원' THEN m.stage_rank END), 0)          AS best_selection,
           COUNT(CASE WHEN m.signal_date >= p.d - p.mdays THEN 1 END)                       AS recent_n,
           COUNT(CASE WHEN m.signal_date <  p.d - p.mdays
                       AND m.signal_date >= p.d - 2 * p.mdays THEN 1 END)                   AS prev_n,
           MAX(m.signal_date)                                                               AS last_mention
    FROM mention m, params p
    GROUP BY m.team_key
),
past_out AS (                                   -- 기준일 전 센 정답 중 가장 높은 등급
    SELECT o.team_key,
           MAX(CASE o.grade WHEN 'S' THEN 3 WHEN 'A' THEN 2 WHEN 'B' THEN 1 ELSE 0 END)    AS best_grade_rank
    FROM outcomes o, params p
    WHERE o.counted AND o.announced_date < p.d
    GROUP BY o.team_key
),
future_out AS (                                 -- 기준일 뒤 관찰 기간 안 센 정답 (채점용)
    SELECT o.team_key, MAX(o.weight) AS hit_weight,
           MAX(CASE WHEN o.grade IN ('S', 'A') THEN 1 ELSE 0 END) AS hit_sa
    FROM outcomes o, params p
    WHERE o.counted
      AND NOT COALESCE(CAST(o.same_house_scored AS BOOLEAN), false)
      AND o.announced_date >= p.d
      AND o.announced_date < p.d + to_months(CAST({{horizon_months}} AS INTEGER))
    GROUP BY o.team_key
),
staged AS (
    SELECT k.*,
           COALESCE(m.n_mention_branches, 0) AS n_mention_branches,
           COALESCE(m.best_selection, 0)     AS best_selection,
           COALESCE(m.recent_n, 0)           AS recent_n,
           COALESCE(m.prev_n, 0)             AS prev_n,
           m.last_mention,
           CASE COALESCE(po.best_grade_rank, 0) WHEN 3 THEN 'S' WHEN 2 THEN 'A' WHEN 1 THEN 'B' END AS best_grade_before,
           CASE
               WHEN COALESCE(po.best_grade_rank, 0) >= 2
                 OR (p.d >= fame_known_from() AND COALESCE(k.profile_status, '') = 'famous') THEN 4
               WHEN COALESCE(po.best_grade_rank, 0) = 1 OR COALESCE(m.best_selection, 0) >= 3 THEN 3
               WHEN COALESCE(m.n_mention_branches, 0) >= 2 THEN 2
               WHEN COALESCE(m.n_mention_branches, 0) = 1 THEN 1
               ELSE 0
           END AS stage,
           CASE WHEN fo.team_key IS NOT NULL THEN 1 ELSE 0 END AS is_hit,
           COALESCE(fo.hit_sa, 0)     AS hit_sa,
           COALESCE(fo.hit_weight, 0) AS hit_weight
    FROM known k
    CROSS JOIN params p
    LEFT JOIN ment m USING (team_key)
    LEFT JOIN past_out po USING (team_key)
    LEFT JOIN future_out fo USING (team_key)
),
with_m AS (
    SELECT *,
           CASE WHEN stage = 0 THEN NULL ELSE LN(1 + recent_n) - LN(1 + prev_n) END AS momentum
    FROM staged
)
SELECT team_key, display_name, primary_genre, first_release, profile_status,
       stage,
       CASE stage WHEN 0 THEN '백지' WHEN 1 THEN '첫 신호' WHEN 2 THEN '여러 갈래'
                  WHEN 3 THEN '선정·중간 정답' ELSE '졸업' END AS stage_label,
       n_mention_branches, best_selection, best_grade_before, last_mention,
       recent_n, prev_n, ROUND(momentum, 3) AS momentum,
       CASE WHEN momentum IS NULL THEN NULL
            ELSE ROUND(PERCENT_RANK() OVER (PARTITION BY stage, momentum IS NULL ORDER BY momentum), 3) END AS momentum_pct,
       CASE WHEN momentum IS NULL THEN '—'
            WHEN recent_n > prev_n THEN '상승' WHEN recent_n < prev_n THEN '하락' ELSE '보합' END AS momentum_label,
       is_hit, hit_sa, hit_weight
FROM with_m
ORDER BY stage DESC, momentum_pct DESC NULLS LAST, recent_n DESC, team_key;
