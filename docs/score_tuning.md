# 점수 가중치 고르기 (교차 검증)

_자동 생성: `.venv/bin/python scripts/score_tune.py`_

**순위 규칙 변경 (2026-11-27)**: 동점 처리를 앱 후보 목록과 같게 바꿨다(점수 → 마지막 신호 최근 순 → md5). 전에는 AUC에서 동점을 절반으로, 상위 K에서 팀 이름 순으로 쳐서 문서 숫자가 앱 화면 순위와 달랐다. 같은 데이터(랩 데이터 2026-11-27 20:36)로 전 → 후: 고른 가중치 평균 AUC 0.786 → 0.805, v0 0.783 → 0.799, 상위 50 적중 합계 고른 것 23 → 23, v0 22 → 22.

기준일 하나를 빼고 나머지 기준일의 평균 AUC가 가장 높은 가중치를 고른 뒤, **뺀 기준일**에서 채점했다(고를 때 안 본 시점).
관찰 기간 24개월(2025-07-01은 데이터 끝 2026-11까지라 약 17개월), 신호 3년·신인 3년·유명 팀 제외. 가중치 후보 10,368가지.

AUC = 정답 팀 하나와 아닌 팀 하나를 골랐을 때 **앱 순위에서** 정답 팀이 더 위에 있을 확률(0.5 = 무작위). 순위는 앱 후보 목록과 같다 — 점수(소수 둘째 자리) 높은 순 → 마지막 신호 최근 순 → md5(team_key). 아래 AUC는 정답 등급 가중(S=3·A=2·B=1). 점수에는 '발굴 신호' 출처만 쓴다(config/source_roles.json).

| 뺀 기준일 | 후보 | 정답 | 고른 가중치(나머지로 고름) | AUC 고른 것 | AUC v0 | AUC 공연 수만 | AUC 갈래 수만 | 상위50 고른 것 | 상위50 v0 |
|---|---|---|---|---|---|---|---|---|---|
| 2023-01-01 | 125 | 8 | branch 1 · stage 1 · peer 0 · dmz 0 · gigs 0 · outlets 1 · recent 0 · venues 1 · winner 2 · context 0.5 · collab 0 | 0.759 | 0.761 | 0.406 | 0.565 | 7 | 7 |
| 2023-07-01 | 515 | 7 | branch 3 · stage 2 · peer 1 · dmz 0 · gigs 0 · outlets 2 · recent 1 · venues 1 · winner 0 · context 1 · collab 0 | 0.737 | 0.791 | 0.429 | 0.487 | 3 | 3 |
| 2024-01-01 | 794 | 5 | branch 2 · stage 1 · peer 0 · dmz 0 · gigs 0 · outlets 1 · recent 0 · venues 1 · winner 2 · context 0.5 · collab 0 | 0.884 | 0.835 | 0.425 | 0.435 | 2 | 2 |
| 2024-07-01 | 1,698 | 17 | branch 2 · stage 1 · peer 0 · dmz 0 · gigs 0 · outlets 1 · recent 0 · venues 1 · winner 2 · context 0.5 · collab 0 | 0.839 | 0.821 | 0.725 | 0.724 | 4 | 3 |
| 2025-01-01 | 2,353 | 23 | branch 2 · stage 1 · peer 0 · dmz 0 · gigs 0 · outlets 1 · recent 0 · venues 1 · winner 2 · context 0.5 · collab 0 | 0.812 | 0.814 | 0.721 | 0.754 | 4 | 4 |
| 2025-07-01 | 2,949 | 21 | branch 2 · stage 1 · peer 0 · dmz 0 · gigs 0 · outlets 1 · recent 0 · venues 1 · winner 2 · context 0.5 · collab 0 | 0.796 | 0.774 | 0.745 | 0.777 | 3 | 3 |

**평균 AUC (뺀 기준일 기준)**: 고른 가중치 0.805 · v0 0.799 · 공연 수만 0.575 · 갈래 수만 0.624
**상위 50 적중 합계**: 고른 가중치 23 · v0 22 · 고른 가중치가 v0보다 AUC가 높았던 기준일 3/6

## 추천 가중치 (기준일 전체로 고름)

`branch 1 · stage 1 · peer 0 · dmz 0 · gigs 0 · outlets 1 · recent 0 · venues 1 · winner 2 · context 0.5 · collab 0`

교차 검증에서 기준일마다 골라진 가중치의 범위(안정성 확인):

- branch: 1, 2, 3
- stage: 1, 2
- peer: 0, 1
- dmz: 0
- gigs: 0
- outlets: 1, 2
- recent: 0, 1
- venues: 1
- winner: 0, 2
- context: 0.5, 1
- collab: 0
