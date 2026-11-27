# 점수 가중치 고르기 (교차 검증)

_자동 생성: `.venv/bin/python scripts/score_tune.py`_

**데이터 갱신 (2026-11-28)**: 2021~25 정답 보강 적재(outcomes.csv 723 → 1,272행). 전 → 후: 후보 8,434 → 8,091행, 정답 81 → 84행, 고른 가중치 평균 AUC 0.805 → 0.809, v0 0.799 → 0.819, 상위 50 적중 합계 고른 것 23 → 30, v0 22 → 24.

**순위 규칙 변경 (2026-11-27)**: 동점 처리를 앱 후보 목록과 같게 바꿨다(점수 → 마지막 신호 최근 순 → md5). 전에는 AUC에서 동점을 절반으로, 상위 K에서 팀 이름 순으로 쳐서 문서 숫자가 앱 화면 순위와 달랐다. 같은 데이터(랩 데이터 2026-11-27 20:36)로 전 → 후: 고른 가중치 평균 AUC 0.786 → 0.805, v0 0.783 → 0.799, 상위 50 적중 합계 고른 것 23 → 23, v0 22 → 22.

기준일 하나를 빼고 나머지 기준일의 평균 AUC가 가장 높은 가중치를 고른 뒤, **뺀 기준일**에서 채점했다(고를 때 안 본 시점).
관찰 기간 24개월(2025-07-01은 데이터 끝 2026-11까지라 약 17개월), 신호 3년·신인 3년·유명 팀 제외, 공연장 수는 최근 2년(2026-11-28 사용자 결정, docs/methods.md). 가중치 후보 10,368가지.

AUC = 정답 팀 하나와 아닌 팀 하나를 골랐을 때 **앱 순위에서** 정답 팀이 더 위에 있을 확률(0.5 = 무작위). 순위는 앱 후보 목록과 같다 — 점수(소수 둘째 자리) 높은 순 → 마지막 신호 최근 순 → md5(team_key). 아래 AUC는 정답 등급 가중(S=3·A=2·B=1). 점수에는 '발굴 신호' 출처만 쓴다(config/source_roles.json).

| 뺀 기준일 | 후보 | 정답 | 고른 가중치(나머지로 고름) | AUC 고른 것 | AUC v0 | AUC 공연 수만 | AUC 갈래 수만 | 상위50 고른 것 | 상위50 v0 |
|---|---|---|---|---|---|---|---|---|---|
| 2023-01-01 | 121 | 7 | branch 0 · stage 2 · peer 1 · dmz 0 · gigs 0 · outlets 2 · recent 2 · venues 1 · winner 1 · context 0 · collab 0 | 0.720 | 0.742 | 0.495 | 0.606 | 6 | 6 |
| 2023-07-01 | 498 | 6 | branch 3 · stage 2 · peer 1 · dmz 0 · gigs 0 · outlets 0.5 · recent 3 · venues 0 · winner 2 · context 0 · collab 0 | 0.746 | 0.835 | 0.426 | 0.298 | 3 | 3 |
| 2024-01-01 | 769 | 7 | branch 2 · stage 2 · peer 1 · dmz 0 · gigs 0 · outlets 1 · recent 3 · venues 1 · winner 2 · context 0.5 · collab 0 | 0.839 | 0.833 | 0.421 | 0.425 | 2 | 2 |
| 2024-07-01 | 1,622 | 21 | branch 2 · stage 2 · peer 1 · dmz 0 · gigs 0 · outlets 1 · recent 3 · venues 1 · winner 2 · context 0.25 · collab 0 | 0.828 | 0.812 | 0.769 | 0.763 | 5 | 3 |
| 2025-01-01 | 2,246 | 21 | branch 2 · stage 2 · peer 1 · dmz 0 · gigs 0 · outlets 1 · recent 3 · venues 1 · winner 2 · context 0 · collab 0 | 0.870 | 0.861 | 0.762 | 0.779 | 7 | 5 |
| 2025-07-01 | 2,835 | 22 | branch 2 · stage 2 · peer 1 · dmz 0 · gigs 0 · outlets 1 · recent 3 · venues 1 · winner 2 · context 0 · collab 0 | 0.849 | 0.832 | 0.788 | 0.787 | 7 | 5 |

**평균 AUC (뺀 기준일 기준)**: 고른 가중치 0.809 · v0 0.819 · 공연 수만 0.610 · 갈래 수만 0.610
**상위 50 적중 합계**: 고른 가중치 30 · v0 24 · 고른 가중치가 v0보다 AUC가 높았던 기준일 4/6

## 추천 가중치 (기준일 전체로 고름)

`branch 2 · stage 2 · peer 1 · dmz 0 · gigs 0 · outlets 1 · recent 3 · venues 1 · winner 2 · context 0 · collab 0`

교차 검증에서 기준일마다 골라진 가중치의 범위(안정성 확인):

- branch: 0, 2, 3
- stage: 2
- peer: 1
- dmz: 0
- gigs: 0
- outlets: 0.5, 1, 2
- recent: 2, 3
- venues: 0, 1
- winner: 1, 2
- context: 0, 0.25, 0.5
- collab: 0
