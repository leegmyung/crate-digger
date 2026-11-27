# 아티스트 연결표 요약 (artist_xref)

_자동 생성: `python3 scripts/artist_xref.py` · 2026-11-27 18:55_

플랫폼·소스마다 다르게 적힌 팀 이름을 **대표 이름 1개 + 표기 목록**으로 묶고, 인스타 계정·멜론/스포티파이 번호를 붙인 표예요 (업계 말로 '아티스트 매칭·메타데이터 검수'). 문제 찾기는 검증 SQL(`docs/sql/README.md` c02·c06·c08), 고친 표 만들기는 이 스크립트, 결과는 다시 PostgreSQL `ref.artist_xref`(표기 키 → 대표 키)로 넣어 SQL에서 씁니다.
원본 연결표는 실제 수집 데이터라 저장소에 올리지 않고 여기엔 숫자와 예시만 둡니다.

## 숫자

| 항목 | 값 |
|---|---|
| 대표 팀 수 | 9,240 |
| 표기 2개 이상으로 적힌 팀 | 1,526팀 (표기 3,399개) |
| 이름 키가 달라 갈라져 있던 팀 → 새로 묶음 (한영 병기·인스타 이름 근거) | 1,376팀 |
| 선정 명단에서 한 칸에 여러 명 → 팀 단위로 나눈 칸 | 22칸 |
| 인스타 계정 (아티스트로 분류된 것) | 128개 |
| └ 다른 소스의 팀과 연결 (high + mid) | 52개 (40.6%) — high 32, mid 20 |
| └ 인스타에만 있는 이름 (low) | 74개 |
| 멜론 번호 / 스포티파이 번호 붙은 팀 | 618 / 400 |
| **정답 팀 중 신호(공연·선정·발매·기사)와 이어진 팀** | 400 / 478팀 (83.7%) |
| └ 그중 연결표로 다른 표기를 묶어서 새로 이어진 팀 | 11팀 |
| 사람이 확인한 별칭 (`config/artist_aliases.json`) | 5팀 · 별칭 5개 |
| 사람 확인 필요 | 112건 (ig_unmatched 74, alias_conflict 21, cell_split 11, multiple_platform_ids 5, ig_multiple_handles 1) |

정답↔신호 연결률은 날짜를 따지지 않은 '이름이 이어지는가'만 본 숫자예요. 점수 백테스트의 정답 수는 여기에 '신호가 정답보다 먼저'·'정답 기간 2025년 이후'·'같은 프로그램 계열 제외' 조건이 더해져 줄어듭니다.

확신도: **high** = 다른 소스의 팀 이름과 맞고 계정명도 닮았거나 근거가 2가지 이상 · **mid** = 근거 1가지 · **low** = 인스타에만 있음.

자동 규칙으로 못 묶는 같은 팀의 다른 표기(철자·외래어 표기·숫자 읽기 차이)는 사람이 근거를 확인한 뒤 `config/artist_aliases.json`에 적는다. 이유·근거 링크·확인 날짜가 있어야 하고, high 연결로 들어가되 자동 연결과 같이 충돌 검사(같은 별칭이 다른 팀에 붙으면 버림)를 받는다.

## 묶인 예시 (표기가 많은 순 10개)

| 대표 이름 | 표기 | 인스타 | 소스 |
|---|---|---|---|
| 99' 네스티 키즈 | 99' 네스티 키즈 / 99 네스티 키즈 / 99' Nasty Kidz / 99’ Nasty Kidz / 99네스티키즈 | - | press |
| 제네 더 질라 | 제네 더 질라 / ZENE THE ZILLA / Zene The Zilla / Zene The Zilla) / 제네더질라 | - | gig, press |
| 캔트비블루 | 캔트비블루 / CAN'T BE BLUE / can’t be blue / can't be blue / can’tbeblue | - | gig, melon, outcome, press, profile, spotify |
| Ambid Jack | Ambid Jack / 앰비드 잭 / Ambid Jack) / 앰비드잭 | - | gig, melon, outcome, press, profile |
| BrokenTeeth | BrokenTeeth / 브로큰티스 / Broken Teeth / Brokenteeth | - | gig, press |
| Dante | Dante / DANTE / DaNTe' / 단테 | - | gig, melon, profile, release, selection, spotify |
| EK | EK / 이케이 / e.K / 도익환 | - | gig, melon, outcome, press, profile, release |
| ISAAC | ISAAC / 이삭 / Isaac / Issac | - | gig, press |
| owen oh | owen oh / Owen Oh / 오웬 오 / 오웬오 | - | gig, press |
| SEOUL SPIT | SEOUL SPIT / SEOULSPIT / 서울스핏 / Seoulspit | - | gig, melon, press, profile |

## 사람 확인이 필요한 애매한 목록 (상위 20)

| 종류 | 내용 | 이유 |
|---|---|---|
| multiple_platform_ids | 나이테 melon 4722708, 5324101 | 한 팀에 플랫폼 번호가 여러 개 — 동명 팀이 섞였을 수 있음 |
| multiple_platform_ids | 루시갱 spotify 6bdK4VbII2XlfccYCeK47S, 6gXEyIkyyFcVrhY2tk8NSy | 한 팀에 플랫폼 번호가 여러 개 — 동명 팀이 섞였을 수 있음 |
| multiple_platform_ids | 밴디츠 melon 3752676, 5182442 | 한 팀에 플랫폼 번호가 여러 개 — 동명 팀이 섞였을 수 있음 |
| multiple_platform_ids | 애리 spotify 3s85ERxPcJlYlvquO4X1rT, 5wcyZGHnvGc4lhk1JZLvak | 한 팀에 플랫폼 번호가 여러 개 — 동명 팀이 섞였을 수 있음 |
| multiple_platform_ids | 호아 melon 2201264, 980733 | 한 팀에 플랫폼 번호가 여러 개 — 동명 팀이 섞였을 수 있음 |
| alias_conflict | ateez ← 민기, 에이티즈 | 같은 별칭이 여러 팀에 붙음 (동명 팀일 수 있음) |
| alias_conflict | bignaughty ← 빅나티, 서동현 | 같은 별칭이 여러 팀에 붙음 (동명 팀일 수 있음) |
| alias_conflict | cyan ← 시안, 싸이언 | 같은 별칭이 여러 팀에 붙음 (동명 팀일 수 있음) |
| alias_conflict | hathaw9y ← 보수동쿨러해서웨이, 해서웨이 | 같은 별칭이 여러 팀에 붙음 (동명 팀일 수 있음) |
| alias_conflict | kickflip ← 동화, 킥플립 | 같은 별칭이 여러 팀에 붙음 (동명 팀일 수 있음) |
| alias_conflict | mildbeats ← 마일드비츠, 정인마일드비츠 | 같은 별칭이 여러 팀에 붙음 (동명 팀일 수 있음) |
| alias_conflict | moonsun ← 나잠수문선, 문선 | 같은 별칭이 여러 팀에 붙음 (동명 팀일 수 있음) |
| alias_conflict | mrch ← 마치, 윤마치 | 같은 별칭이 여러 팀에 붙음 (동명 팀일 수 있음) |
| alias_conflict | nstthesoulsauce ← 노선택과소울소스, 소울소스 | 같은 별칭이 여러 팀에 붙음 (동명 팀일 수 있음) |
| alias_conflict | oddeyecircle ← 오드아이서클, 오드아이써클 | 같은 별칭이 여러 팀에 붙음 (동명 팀일 수 있음) |
| alias_conflict | sejin ← 세진, 윤석철세진 | 같은 별칭이 여러 팀에 붙음 (동명 팀일 수 있음) |
| alias_conflict | tuesdaybeachclub ← 투즈데이비치클럽, 튜즈데이비치클럽 | 같은 별칭이 여러 팀에 붙음 (동명 팀일 수 있음) |
| alias_conflict | twice ← 채영, 트와이스 | 같은 별칭이 여러 팀에 붙음 (동명 팀일 수 있음) |
| alias_conflict | yb ← 와이비, 윤도현밴드 | 같은 별칭이 여러 팀에 붙음 (동명 팀일 수 있음) |
| alias_conflict | ノイ ← neu, 노이 | 같은 별칭이 여러 팀에 붙음 (동명 팀일 수 있음) |

종류: cell_split = 한 칸 여러 명 중 나누지 않고 둔 것 · alias_conflict = 같은 별칭이 여러 팀에 붙음 · multiple_platform_ids = 한 팀에 플랫폼 번호 여러 개 · ig_multiple_teams = 한 계정이 여러 팀과 맞음 · ig_unmatched = 인스타에만 있는 이름 · platform_namesake = 검색 동명이인.
