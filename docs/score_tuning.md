# 점수 가중치 고르기 (교차 검증)

_자동 생성: `.venv/bin/python scripts/score_tune.py`_

기준일 하나를 빼고 나머지 기준일의 평균 AUC가 가장 높은 가중치를 고른 뒤, **뺀 기준일**에서 채점했다(고를 때 안 본 시점).
관찰 기간 24개월(2025-07-01은 데이터 끝 2026-11까지라 약 17개월), 신호 3년·신인 3년·유명 팀 제외. 가중치 후보 10,368가지.

AUC = 정답 팀 하나와 아닌 팀 하나를 골랐을 때 정답 팀 점수가 더 높을 확률(0.5 = 무작위). 아래 AUC는 정답 등급 가중(S=3·A=2·B=1). 점수에는 '발굴 신호' 출처만 쓴다(config/source_roles.json).

| 뺀 기준일 | 후보 | 정답 | 고른 가중치(나머지로 고름) | AUC 고른 것 | AUC v0 | AUC 공연 수만 | AUC 갈래 수만 | 상위50 고른 것 | 상위50 v0 |
|---|---|---|---|---|---|---|---|---|---|
| 2023-01-01 | 121 | 5 | branch 0 · stage 2 · peer 1 · dmz 0 · gigs 0 · outlets 1 · recent 1 · venues 1 · winner 0 · context 1 · collab 0 | 0.593 | 0.657 | 0.545 | 0.708 | 3 | 3 |
| 2023-07-01 | 510 | 7 | branch 3 · stage 2 · peer 1 · dmz 0 · gigs 0 · outlets 2 · recent 1 · venues 1 · winner 0 · context 1 · collab 0 | 0.651 | 0.662 | 0.527 | 0.566 | 3 | 2 |
| 2024-01-01 | 789 | 6 | branch 1 · stage 1 · peer 0 · dmz 0 · gigs 0 · outlets 1 · recent 0 · venues 1 · winner 2 · context 0.5 · collab 0 | 0.732 | 0.672 | 0.483 | 0.497 | 1 | 1 |
| 2024-07-01 | 1,736 | 16 | branch 3 · stage 1 · peer 1 · dmz 0 · gigs 0 · outlets 0.5 · recent 2 · venues 0 · winner 1 · context 1 · collab 0 | 0.731 | 0.807 | 0.697 | 0.582 | 3 | 3 |
| 2025-01-01 | 2,440 | 23 | branch 3 · stage 2 · peer 1 · dmz 0 · gigs 0 · outlets 1 · recent 1 · venues 1 · winner 0 · context 1 · collab 0 | 0.819 | 0.802 | 0.676 | 0.603 | 3 | 4 |
| 2025-07-01 | 3,102 | 23 | branch 3 · stage 2 · peer 1 · dmz 0 · gigs 0 · outlets 2 · recent 1 · venues 1 · winner 0 · context 0.5 · collab 0 | 0.737 | 0.670 | 0.604 | 0.550 | 4 | 3 |

**평균 AUC (뺀 기준일 기준)**: 고른 가중치 0.711 · v0 0.712 · 공연 수만 0.589 · 갈래 수만 0.584
**상위 50 적중 합계**: 고른 가중치 17 · v0 16 · 고른 가중치가 v0보다 AUC가 높았던 기준일 3/6

## 추천 가중치 (기준일 전체로 고름)

`branch 3 · stage 2 · peer 1 · dmz 0 · gigs 0 · outlets 1 · recent 1 · venues 1 · winner 0 · context 1 · collab 0`

교차 검증에서 기준일마다 골라진 가중치의 범위(안정성 확인):

- branch: 0, 1, 3
- stage: 1, 2
- peer: 0, 1
- dmz: 0
- gigs: 0
- outlets: 0.5, 1, 2
- recent: 0, 1, 2
- venues: 0, 1
- winner: 0, 1, 2
- context: 0.5, 1
- collab: 0
