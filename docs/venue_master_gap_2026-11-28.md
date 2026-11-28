# 공연장 목록(venues_kr) 짝 못 찾은 곳 줄이기 (2026-11-28)

데이터 검사 '공연장 목록(venues_kr) 짝 못 찾은 곳'(scripts/data_checks_extra.py `check_venue_master`) 경고를 공연 밤 많은 순으로 정리했다.
셈: 공연 신호(docs/lab/data/signals.csv)의 공연장별 공연 밤(같은 날 같은 공연장 = 1밤) 중 config/venues_kr.json 의 이름·별칭·인스타 계정과 짝이 안 되는 몫.

## 전후 숫자

| 시점 | 짝 없는 곳 | 짝 없는 공연 밤 | 비율 |
|---|---|---|---|
| 작업 지시 때 (예전 검사 결과) | 153곳 | 1,144 / 10,957 | 10.4% |
| 이 작업 시작 때 — 지도 작업(공연장 91곳 추가, b974700)과 새 적재 뒤 | 88곳 | 352 / 11,218 | 3.1% |
| **이 작업 뒤** | **69곳** | **327 / 11,218** | **2.9%** |
| 아래 제안 1·2를 검사에 넣으면 | — | 116 / 11,007 | 1.1% |

네스트나다·고인물·언플러그드 신촌점·문화정원아트홀·복합문화공간 에무·홍대 플렉스라운지·인천노크는 지도 작업에서 이미 마스터에 들어가 짝이 생겼다.

## 이번에 고친 것 (config — 추가만)

- `config/venues_kr.json`
  - 롤링홀 별칭에 '롤링홀 홍대', 홍대 플렉스라운지에 인스타 계정 `flex.lounge`(라인업 계정 '플렉스라운지 (본점)').
  - 실제 공연장 17곳 추가: BBCB(서울, 인스타 bbcb.seoul), 반쥴 스테이지(서울 종로), 전주 야간비행, 경남음악창작소 뮤지시스(김해), 스튜디오로그·프리즘플러스(서울), 부산 지원 공연 장소 11곳(책과 아이들·어반플랜트·나유타의부엌·전람회의 그림·카페플랜트370·어반305·카멜앤오아시스·구루요가원·브로스·문달래·딥슬립커피). 주소를 못 확인한 곳은 상태 '확인 필요', 근거 링크(인스타·부산음악창작소 게시판)를 남김. 좌표는 찾은 곳만.
- `config/venue_aliases.json`: 롤링홀 홍대 → 롤링홀.

## 남은 327밤은 대부분 공연장이 아니다

| 종류 | 공연 밤 | 예 |
|---|---|---|
| 기획·레이블·행사 인스타 계정 (config/insta_accounts.json 역할 promoter·label·event_showcase) | 약 190 | @more_breaks_kr, @galactique_seoul, @vibecampus.kr, @yngandrichrecords, @younggiftedwack … |
| 공연장 계정으로 잘못 적힌 페스티벌·파티·DJ (역할 venue_showcase) | 약 95 | @seoulfootwork2025, @gorani.festival, @festival_thesub, @busanrockfest, @gotunlucky, @bulbit.seoul, @blockpartykorea, @kimchifactoryhomies, @djwegun … |
| 행사 이름·온라인 중계 | 15 | 축제 (을지로) 13, 'KT&G 상상마당 홍대 공식 유튜브 채널', 'KT&G 상상마당 부산 공식 인스타그램 LIVE' |
| 실제 공연장일 수 있으나 근거 부족 | 몇 밤 | 홍대 컨벤트라이브펍(마스터 '컨벤트'와 같은 곳인지 미확인), 해운대 이벤트광장, GBN LIVEHOUSE, 살롱노마드 |

## 제안 — '공연장 아님' 표시 (다른 담당 파일이라 바꾸지 않음)

1. **검사에서 공연장 아닌 계정·이름 빼기** — `check_venue_master` 가 공연 밤을 셀 때
   `venues_kr.non_venue_handles()`(인스타 역할이 promoter·label·event_showcase 인 '@계정')와
   `venues_kr.not_venue_names()`(config/venue_capacity.json 의 `not_venue: true`)를 분모·분자에서 뺀다.
   venues_kr.py 의 `gig_stats`·`venue_city` 가 이미 같은 목록을 쓰므로 규칙이 하나로 맞는다. → 1.1%.
2. **행사 이름·온라인 중계를 not_venue 로** — config/venue_capacity.json 에 `"축제 (을지로)": {"not_venue": true, "note": "행사 이름"}`,
   '… 공식 유튜브 채널'·'… 공식 인스타그램 LIVE' 같은 온라인 중계도 같은 표시 (add_missing_venues.py 가 이미 온라인 중계는 공연장으로 안 넣음).
3. **인스타 계정 역할 바로잡기** — config/insta_accounts.json 에서 venue_showcase 로 적힌 계정 중
   페스티벌은 `event_showcase`(@seoulfootwork2025·@gorani.festival·@festival_thesub·@busanrockfest),
   파티·크루·DJ 는 `promoter_showcase`(@gotunlucky·@bulbit.seoul·@blockpartykorea·@kimchifactoryhomies·@djwegun·@ugs_undergroundsound·@groovl1nofficial),
   학교 동아리 @yonsei_ullimteo 는 `promoter_showcase`. @junctionseoul·@fictionseoul·@stamina_375ml·@soundsupply_service·@whitelunarmusic·@gwangbok_record 는
   고정 공연장인지 계정 소개를 보고 정한다. 바로잡으면 지도·도시 통계에서도 '공연장 미상' 칸으로 제대로 빠진다.
