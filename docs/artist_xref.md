# 아티스트 연결표 요약 (artist_xref)

_자동 생성: `python3 scripts/artist_xref.py` · 2026-11-28 01:06_

플랫폼·소스마다 다르게 적힌 팀 이름을 **대표 이름 1개 + 표기 목록**으로 묶고, 인스타 계정·멜론/스포티파이 번호를 붙인 표예요 (업계 말로 '아티스트 매칭·메타데이터 검수'). 문제 찾기는 검증 SQL(`docs/sql/README.md` c02·c06·c08), 고친 표 만들기는 이 스크립트, 결과는 다시 PostgreSQL `ref.artist_xref`(표기 키 → 대표 키)로 넣어 SQL에서 씁니다.
원본 연결표는 실제 수집 데이터라 저장소에 올리지 않고 여기엔 숫자와 예시만 둡니다.

## 숫자

| 항목 | 값 |
|---|---|
| 대표 팀 수 | 9,846 |
| 표기 2개 이상으로 적힌 팀 | 1,675팀 (표기 3,764개) |
| 이름 키가 달라 갈라져 있던 팀 → 새로 묶음 (한영 병기·인스타 이름 근거) | 1,463팀 |
| 선정 명단에서 한 칸에 여러 명 → 팀 단위로 나눈 칸 | 22칸 |
| 인스타 계정 (아티스트로 분류된 것) | 1,156개 |
| └ 다른 소스의 팀과 연결 (high + mid) | 64개 (5.5%) — high 40, mid 24 |
| └ 인스타에만 있는 이름 (low) | 132개 |
| 멜론 번호 / 스포티파이 번호 붙은 팀 | 813 / 400 |
| **정답 팀 중 신호(공연·선정·발매·기사)와 이어진 팀** | 601 / 725팀 (82.9%) |
| └ 그중 연결표로 다른 표기를 묶어서 새로 이어진 팀 | 37팀 |
| 사람이 확인한 별칭 (`config/artist_aliases.json`) | 67팀 · 별칭 80개 |
| 사람이 확인한 다른 팀 / 플랫폼 번호 고정 / 팀 아닌 인스타 계정 (같은 파일) | 6쌍 / 5팀 / 36개 |
| 별칭 충돌 자동 해결 (긴 이름이 짧은 이름을 품는 합동 표기 → 별칭은 짧은 쪽) | 16건 |
| 사람 확인 필요 | 153건 (ig_unmatched 132, cell_split 11, major_agency_indie 7, multiple_platform_ids 1, alias_conflict 1, ig_multiple_handles 1) |

정답↔신호 연결률은 날짜를 따지지 않은 '이름이 이어지는가'만 본 숫자예요. 점수 백테스트의 정답 수는 여기에 '신호가 정답보다 먼저'·'정답 기간 2025년 이후'·'같은 프로그램 계열 제외' 조건이 더해져 줄어듭니다.

확신도: **high** = 다른 소스의 팀 이름과 맞고 계정명도 닮았거나 근거가 2가지 이상 · **mid** = 근거 1가지 · **low** = 인스타에만 있음.

자동 규칙으로 못 묶는 같은 팀의 다른 표기(철자·외래어 표기·숫자 읽기 차이)는 사람이 근거를 확인한 뒤 `config/artist_aliases.json`에 적는다. 이유·근거 링크·확인 날짜가 있어야 하고, high 연결로 들어가되 자동 연결과 같이 충돌 검사(같은 별칭이 다른 팀에 붙으면 버림)를 받는다.

## 묶인 예시 (표기가 많은 순 10개)

| 대표 이름 | 표기 | 인스타 | 소스 |
|---|---|---|---|
| 99' 네스티 키즈 | 99' 네스티 키즈 / 99 네스티 키즈 / 99' Nasty Kidz / 99’ Nasty Kidz / 99네스티키즈 | - | press |
| 램넌츠 오브 더 폴른 | 램넌츠 오브 더 폴른 / 램넌츠오브더폴른 / Remnants Of The Fallen / 렘넌츠 오브 더 폴른 / 램넌츠 오브 폴른 | - | gig, outcome, press, selection |
| 제네 더 질라 | 제네 더 질라 / ZENE THE ZILLA / Zene The Zilla / Zene The Zilla) / 제네더질라 | - | gig, melon, press, profile |
| 캔트비블루 | 캔트비블루 / CAN'T BE BLUE / can’t be blue / can't be blue / can’tbeblue | - | gig, melon, outcome, press, profile, spotify |
| 플라시보정키스 | PLACEBO JUNKIES / Placebo Junkies / 플라시보 정키스 / 플라시보정키스 / 플라시보정키즈 | - | gig, press |
| Ambid Jack | Ambid Jack / 앰비드 잭 / Ambid Jack) / 앰비드잭 | - | gig, melon, outcome, press, profile |
| BrokenTeeth | BrokenTeeth / 브로큰티스 / Broken Teeth / Brokenteeth | - | gig, press |
| DANTE | DANTE / Dante / DaNTe' / 단테 | - | gig, melon, profile, release, selection, spotify |
| EK | EK / 이케이 / e.K / 도익환 | - | gig, melon, outcome, press, profile, release |
| ISAAC | ISAAC / 이삭 / Isaac / Issac | - | gig, press |

## 사람 확인이 필요한 애매한 목록 (상위 20)

| 종류 | 내용 | 이유 |
|---|---|---|
| cell_split | Eddie and the Bricks → Eddie and the Bricks | '&'·'+'·'and'는 팀 이름 안에도 나와 그대로 둠 |
| multiple_platform_ids | 애리 spotify 3s85ERxPcJlYlvquO4X1rT, 5wcyZGHnvGc4lhk1JZLvak | 한 팀에 플랫폼 번호가 여러 개 — 동명 팀이 섞였을 수 있음 |
| alias_conflict | cyan ← 시안, 싸이언 | 같은 별칭이 여러 팀에 붙음 (동명 팀일 수 있음) |
| ig_multiple_handles | 노이 ← @neu_hause, @no2yeyo | 한 팀에 인스타 계정이 여러 개 — 동명 팀이거나 개인·팀 계정 |
| major_agency_indie | AxMxP melon:4276045 (FNC엔터테인먼트) | 대형 기획사 소속 프로필인데 인디 공연 신호가 있음 — 동명이인 연결 의심, 확인 후 platform_ids not |
| major_agency_indie | CNBLUE melon:450801 (FNC엔터테인먼트) | 대형 기획사 소속 프로필인데 인디 공연 신호가 있음 — 동명이인 연결 의심, 확인 후 platform_ids not |
| major_agency_indie | Xdinary Heroes melon:3056747 ((주)JYP엔터테인먼트) | 대형 기획사 소속 프로필인데 인디 공연 신호가 있음 — 동명이인 연결 의심, 확인 후 platform_ids not |
| major_agency_indie | 동화 melon:4093552 ((주)JYP엔터테인먼트) | 대형 기획사 소속 프로필인데 인디 공연 신호가 있음 — 동명이인 연결 의심, 확인 후 platform_ids not |
| major_agency_indie | 시온 melon:3574242 ((주)SM엔터테인먼트) | 대형 기획사 소속 프로필인데 인디 공연 신호가 있음 — 동명이인 연결 의심, 확인 후 platform_ids not |
| major_agency_indie | 엔플라잉 melon:861430 (FNC엔터테인먼트) | 대형 기획사 소속 프로필인데 인디 공연 신호가 있음 — 동명이인 연결 의심, 확인 후 platform_ids not |
| major_agency_indie | 하츠웨이브 melon:4839714 (카카오엔터테인먼트) | 대형 기획사 소속 프로필인데 인디 공연 신호가 있음 — 동명이인 연결 의심, 확인 후 platform_ids not |
| cell_split | J Kim & Holidayhvre → J Kim & Holidayhvre | '&'·'+'·'and'는 팀 이름 안에도 나와 그대로 둠 |
| cell_split | Sweet & light → Sweet & light | '&'·'+'·'and'는 팀 이름 안에도 나와 그대로 둠 |
| cell_split | 김민규(델리스파이스, 스위트피) → 김민규 | 괄호 속은 멤버·소속으로 보고 팀만 남김 |
| cell_split | 메킷레인(루피·나플라·오왼 오바도즈·블루·영웨스트) → 메킷레인 | 괄호 속은 멤버·소속으로 보고 팀만 남김 |
| cell_split | 문근영(해파, 시옷과 바람) → 문근영 | 괄호 속은 멤버·소속으로 보고 팀만 남김 |
| cell_split | 박혜리(정원영밴드, 바드) → 박혜리 | 괄호 속은 멤버·소속으로 보고 팀만 남김 |
| cell_split | 뱃사공(수림, 백찬영) → 뱃사공 | 괄호 속은 멤버·소속으로 보고 팀만 남김 |
| cell_split | 이미지 외 4명 → 이미지 | '외 N명' — 나머지 이름은 원문에 없음 |
| cell_split | 이차형 외 2명 → 이차형 | '외 N명' — 나머지 이름은 원문에 없음 |

종류: cell_split = 한 칸 여러 명 중 나누지 않고 둔 것 · alias_conflict = 같은 별칭이 여러 팀에 붙음 · multiple_platform_ids = 한 팀에 플랫폼 번호 여러 개 · ig_multiple_teams = 한 계정이 여러 팀과 맞음 · ig_unmatched = 인스타에만 있는 이름 · platform_namesake = 검색 동명이인 · major_agency_indie = 대형 기획사 소속 프로필인데 인디 공연 신호(동명이인 연결 의심). 자동 해결(alias_auto)은 확인 목록 파일에만 기록하고 이 표·건수에서는 뺀다.
