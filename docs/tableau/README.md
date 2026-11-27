# Tableau 대시보드 설계서

Tableau 계정이 없어도 바로 올릴 수 있게 **추출 데이터(CSV 4개)와 시트·차트 설계**를 준비했습니다. 숫자는 앱과 같은 계산입니다(`docs/lab/sql/*.sql`을 DuckDB로 실행). 주간 엑셀(`docs/report/`)과 기준일·성적표 기간이 같습니다.

- 만들기: `.venv/bin/python scripts/export_tableau.py` → 이 폴더의 CSV 4개를 다시 씀
- 공개 데이터만 들어 있습니다: 팀 이름, 공개 출처의 숫자. 수집 원본은 넣지 않습니다.
- 모든 파일은 **긴 형식(tidy)** 입니다. 한 줄에 관측 하나라서 Tableau에서 피벗 없이 바로 끌어다 쓸 수 있습니다.

## 1. 데이터 원본 (CSV 4개)

### `candidate_score_parts.csv` — 후보 점수 구성 (후보 300팀 × 구성 10개 = 3,000줄)

| 칸 | 뜻 | Tableau 형식 |
|---|---|---|
| `as_of` | 기준일 (데이터 끝 날짜) | 날짜 |
| `rank` | 점수 순위 (1 = 가장 높음) | 정수, 차원으로도 씀 |
| `team_key` | 팀 대표 키 (다른 파일과 연결하는 열쇠) | 문자열 |
| `team_name` | 화면에 보일 팀 이름 | 문자열 |
| `genre` | 대표 장르 | 문자열 |
| `profile_status` | 팀 상태 (newcomer 신인 / unknown 프로필 없음 / established 기성) | 문자열 |
| `score` | 총점 (점수 v2) — 같은 팀의 10줄에 같은 값이 반복됨 | 소수 |
| `component` | 점수 구성 이름 (갈래 수·선정 단계·공연장 다양성·수상 팀과 같은 무대·발굴 매거진·맥락 매거진 등) | 문자열 |
| `points` | 그 구성이 준 점수 (10줄 합 = `score`) | 소수 |

### `signal_timeline.csv` — 후보 팀의 신호 타임라인 (기준일까지)

| 칸 | 뜻 | Tableau 형식 |
|---|---|---|
| `team_key` | 팀 대표 키 | 문자열 |
| `team_name` | 팀 이름 | 문자열 |
| `rank` | 그 팀의 현재 점수 순위 | 정수 |
| `signal_date` | 신호 날짜 (일부만 아는 날짜는 기간의 마지막 날) | 날짜 |
| `branch` | 갈래 (공연·큐레이션·선정·지원·발매) | 문자열 |
| `source` | 출처 코드 (indistreet·musicy 등) | 문자열 |
| `program` | 선정·지원 프로그램 또는 매체 코드 | 문자열 |
| `venue` | 공연장 대표 이름 (공연 갈래만) | 문자열 |
| `role` | 출처 역할 (discovery 발굴 / context 맥락 / pending 검증 대기 / excluded 제외) | 문자열 |

### `source_scorecard.csv` — 출처 성적표 (기준일 3개 합산, 수상 팀은 2024-01-01 이후)

| 칸 | 뜻 | Tableau 형식 |
|---|---|---|
| `src` | 출처 키 `갈래:출처` (선정·지원은 `갈래:프로그램`) | 문자열 |
| `branch` | 갈래 | 문자열 |
| `role` | 역할 코드 | 문자열 |
| `role_ko` | 역할 한글 (발굴·맥락·검증 대기·제외) | 문자열 |
| `since_date` | 기록 시작일 | 날짜 |
| `teams` | 후보 팀 수 (기준일마다 다시 셀 수 있음) | 정수 |
| `hits` | 그중 기준일 뒤 24개월 안에 정답을 받은 팀 | 정수 |
| `rate` | 적중률 % | 소수 |
| `lift` | 배수 = 적중률 ÷ 기준선 | 소수 |
| `base_rate` | 기준선 % (후보 전체 적중률) | 소수 |
| `below_baseline` | 배수 1 미만이면 true | 불리언 |
| `winners_seen` | 수상 팀 중 정답 전에 이 출처에 나온 팀 | 정수 |
| `first_to_see` | 그중 모든 출처 가운데 가장 먼저 잡은 팀 | 정수 |
| `only_source` | 그중 이 출처에만 나온 팀 (유일 기여) | 정수 |
| `median_lead_months` | 정답보다 몇 개월 먼저 잡았나 (중앙값) | 소수 |

### `backtest.csv` — 백테스트 (기준일 3개 × 상위 K 4개 × 방법 3개 = 36줄)

| 칸 | 뜻 | Tableau 형식 |
|---|---|---|
| `cutoff` | 기준일 (2024-07-01·2025-01-01·2025-07-01) | 날짜 |
| `k` | 상위 몇 팀을 뽑았나 (20·50·100·200) | 정수, 차원으로도 씀 |
| `method` | 방법 (점수 / 공연 수만 / 갈래 수만) | 문자열 |
| `hits` | 상위 K 중 기준일 뒤 정답을 받은 팀 | 정수 |
| `hit_rate` | 적중률 % | 소수 |
| `random_expected` | 무작위로 K팀 뽑았을 때 기대 적중 팀 | 소수 |
| `lift` | 무작위 대비 배수 | 소수 |
| `pool_n` | 후보 팀 수 | 정수 |
| `pool_hits` | 후보 중 정답 팀 수 | 정수 |

**관계(Relationship):** `candidate_score_parts.team_key` = `signal_timeline.team_key`로 연결합니다(둘 다 팀 기준이라 Tableau가 집계 수준을 맞춤). `source_scorecard`, `backtest`는 따로 씁니다.

## 2. 시트·차트 설계

| 시트 | 차트 | 열 | 행 | 색·크기·레이블 | 필터 |
|---|---|---|---|---|---|
| ① 이번 주 후보 TOP 20 | 가로 누적 막대 | `SUM(points)` | `team_name` (정렬: `MIN(rank)` 오름차순) | 색 = `component`, 레이블 = `MAX(score)` | [상위 N 안], `genre`, `profile_status` |
| ② 점수 구성 비중 | 100% 누적 막대 또는 트리맵 | [구성 비율] | `component` | 색 = `component` | [상위 N 안], 장르 |
| ③ 후보 신호 타임라인 | 점 그래프(간트형) | `signal_date` (연속, 월) | `team_name` (정렬: `MIN(rank)`) | 색 = `branch`, 모양 = `role` | [상위 N 안], `branch`, 날짜 범위(최근 3년) |
| ④ 출처 성적표 | 산점도 | `lift` | `winners_seen` | 색 = `role_ko`, 크기 = `teams`, 레이블 = `src`, 참조선 x = 1 | `branch`, `role_ko` |
| ⑤ 출처 성적표 표 | 텍스트 표 | — | `src` | `rate`·`lift`·`only_source`, 색 = [기준선 이하] | `role_ko` |
| ⑥ 백테스트 | 묶은 막대 | `k` | `SUM(hits)` | 색 = `method`, 참조선 = `SUM(random_expected)` (점선) | `cutoff` |
| ⑦ 무작위 대비 배수 | 선 그래프 | `k` | `AVG(lift)` | 색 = `method` | `cutoff` |

**대시보드 구성 (1,400 × 900 권장):** 위 왼쪽 ① 후보 TOP 20, 위 오른쪽 ④ 출처 성적표 산점도, 아래 왼쪽 ③ 타임라인(① 막대를 누르면 그 팀만 보이게 — 동작: 필터, 원본 ①, 대상 ③, 필드 `team_key`), 아래 오른쪽 ⑥ 백테스트. 맨 위에 KPI 띠: 기준일, 후보 수, 평균 점수.

## 3. 계산 필드

| 이름 | 식 | 쓰임 |
|---|---|---|
| [상위 N] (매개변수) | 정수, 기본 20, 범위 10~100 | 후보 수 조절 |
| [상위 N 안] | `[rank] <= [상위 N]` | ①②③ 필터 |
| [구성 비율] | `SUM([points]) / TOTAL(SUM([points]))` | ② 100% 막대 (테이블 계산: 구성 기준) |
| [기준선 이하] | `IF [below_baseline] THEN "기준선 이하" ELSE "기준선 이상" END` | ⑤ 색 |
| [배수 구간] | `IF [lift] >= 2 THEN "2배 이상" ELSEIF [lift] >= 1 THEN "1~2배" ELSE "1배 미만" END` | ④ 범례 |
| [무작위보다 나음] | `SUM([hits]) - SUM([random_expected])` | ⑥ 툴팁 |
| [최근 1년 신호] | `[signal_date] >= DATEADD('year', -1, {MAX([signal_date])})` | ③ 강조 |
| [신호 수] | `COUNT([signal_date])` (팀별) | ③ 툴팁 |
| [신인 여부] | `IF [profile_status] = "newcomer" THEN "신인(프로필)" ELSEIF [profile_status] = "unknown" THEN "프로필 없음" ELSE "기성" END` | ① 필터 |

## 4. 권장 필터와 읽는 법

- **장르·팀 상태 필터는 ①~③에 함께 적용**(필터 > 적용 대상 > 이 데이터 원본을 쓰는 모든 시트)하면 한 장르의 후보와 그 신호를 같이 볼 수 있습니다.
- ④ 산점도는 **오른쪽 위**(배수 높고, 수상 팀을 많이 먼저 잡음)가 좋은 출처입니다. x = 1 참조선 왼쪽은 기준선 이하라 점수에 약하게만 쓰거나 맥락으로 둡니다.
- ⑥ 백테스트는 **점선(무작위 기대)보다 막대가 얼마나 높은가**를 봅니다. 기준일마다 정답 팀 수(`pool_hits`)가 16~23팀으로 작아 1~2팀 차이로 크게 흔들리니, 툴팁에 `pool_hits`를 꼭 넣어 주세요.
- 정의(역할·정답 등급·AUC)는 [방법론](../methods.md), [데이터 역할과 정답 등급](../source_roles.md), 칸 정의는 [데이터 사전](../data_dictionary.md)에 있습니다.
