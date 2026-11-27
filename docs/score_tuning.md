# 점수 가중치 고르기 (교차 검증)

_자동 생성: `.venv/bin/python scripts/score_tune.py`_

기준일 하나를 빼고 나머지 기준일의 평균 AUC가 가장 높은 가중치를 고른 뒤, **뺀 기준일**에서 채점했다(고를 때 안 본 시점).
관찰 기간 24개월(2025-07-01은 데이터 끝 2026-11까지라 약 17개월), 신호 3년·신인 3년·유명 팀 제외. 가중치 후보 10,368가지.

AUC = 정답 팀 하나와 아닌 팀 하나를 골랐을 때 정답 팀 점수가 더 높을 확률(0.5 = 무작위).

| 뺀 기준일 | 후보 | 정답 | 고른 가중치(나머지로 고름) | AUC 고른 것 | AUC v0 | AUC 공연 수만 | AUC 갈래 수만 | 상위50 고른 것 | 상위50 v0 |
|---|---|---|---|---|---|---|---|---|---|
| 2023-01-01 | 147 | 6 | branch 0 · stage 1 · peer 0 · dmz 0 · gigs 0 · outlets 0.5 · recent 1 · venues 2 · winner 0 | 0.668 | 0.685 | 0.522 | 0.660 | 4 | 4 |
| 2023-07-01 | 534 | 8 | branch 3 · stage 2 · peer 0 · dmz 0 · gigs 0 · outlets 0.5 · recent 2 · venues 1 · winner 1 | 0.553 | 0.589 | 0.522 | 0.557 | 2 | 2 |
| 2024-01-01 | 832 | 7 | branch 1 · stage 1 · peer 0 · dmz 0 · gigs 0 · outlets 0.5 · recent 1 · venues 2 · winner 0 | 0.821 | 0.640 | 0.484 | 0.487 | 1 | 1 |
| 2024-07-01 | 1,810 | 20 | branch 2 · stage 2 · peer 0 · dmz 0 · gigs 0 · outlets 0.5 · recent 1 · venues 2 · winner 0 | 0.695 | 0.602 | 0.637 | 0.550 | 3 | 2 |
| 2025-01-01 | 2,519 | 21 | branch 2 · stage 2 · peer 0 · dmz 0 · gigs 0 · outlets 0.5 · recent 1 · venues 2 · winner 1 | 0.722 | 0.671 | 0.640 | 0.567 | 3 | 2 |
| 2025-07-01 | 3,198 | 20 | branch 2 · stage 2 · peer 0 · dmz 0 · gigs 0 · outlets 0.5 · recent 1 · venues 2 · winner 2 | 0.745 | 0.717 | 0.621 | 0.570 | 1 | 2 |

**평균 AUC (뺀 기준일 기준)**: 고른 가중치 0.701 · v0 0.651 · 공연 수만 0.571 · 갈래 수만 0.565
**상위 50 적중 합계**: 고른 가중치 14 · v0 13 · 고른 가중치가 v0보다 AUC가 높았던 기준일 4/6

## 추천 가중치 (기준일 전체로 고름)

`branch 2 · stage 2 · peer 0 · dmz 0 · gigs 0 · outlets 0.5 · recent 1 · venues 2 · winner 1`

교차 검증에서 기준일마다 골라진 가중치의 범위(안정성 확인):

- branch: 0, 1, 2, 3
- stage: 1, 2
- peer: 0
- dmz: 0
- gigs: 0
- outlets: 0.5
- recent: 1, 2
- venues: 1, 2
- winner: 0, 1, 2
