# 데이터 검사 (매일 자동)

_자동 생성: `.venv/bin/python scripts/data_checks.py` · 검사일 2026-11-28 · 랩 데이터 2026-11-28 17:26 기준 (데이터 끝 2026-11-28)_

**결과: 통과 22 · 경고 5 · 실패 0**

## 먼저 볼 것

- ⚠️ **전날 대비 행 수** — 급증: signals 26,534→62,079, teams 9,096→15,334, outcomes 723→1,218, links 1,100→3,864, videos 1,736→5,180, images 241→441  
  → 고치는 법: 줄었으면 그날 수집·적재 로그 확인(수집 실패·연결표 오류), 늘었으면 같은 행이 두 번 들어갔는지 확인
- ⚠️ **같은 팀 중복 의심** — 251쌍 (띄어쓰기·대소문자·the 3, 표기 흔들림 16, 같은 링크 주소 33, 로마자 표기 14, 한 글자 차이 159, 짧은 이름 표기 흔들림 26): crane = thecrane, henzclub = thehenzclub, moss = themoss, 넉살x까데호 = 넉살까데호, 더리셋터즈 = 리셋터즈, 래드클라인 = 레드클라인, 리추얼리티 = 리츄얼리티, 릴체리x골드부다 = 릴체리골드부다 외 58  
  → 고치는 법: 같은 팀이면 config/artist_aliases.json aliases에 근거와 함께 묶고, 다른 팀이면 distinct에 적는다 (목록은 아래 '자세히')
- ⚠️ **점수 상위 100팀 중 프로필 없음** — 33/100팀 (33.0%) — 상위부터: 포져군단, 천둥오리, 최춘목밴드, 직사광선, 한이 외 28  
  → 고치는 법: scripts/melon_names.py 보강 명단에 점수 상위 팀을 먼저 넣는다 (멜론 상세 페이지 차단이면 스포티파이로)
- ⚠️ **팀 표 신인 확인·장르 확신도 분포** — newcomer_check: first_seen 14,065 · verified 783 · unverified 486 / genre_confidence: (빈칸) 6,457 · inferred 3,021 · profile 2,449 · review 1,838 · inferred_low 1,385 · press 184 — 모르는 값: review  
  → 고치는 법: export_lab_data.py의 newcomer_check·genre_confidence 값 목록과 data_checks.py NEWCOMER_CHECKS·GENRE_CONFIDENCES를 맞춘다
- ⚠️ **멜론 본인 음반 첫 발매(first_release_own)** — 본인 음반 첫 발매 88/819 (10.7%) · 전체 첫 발매 810 · 본인 음반이 3년 넘게 늦은 프로필 12개 · 본인이 더 이른 오류 0개  
  → 고치는 법: collect_artists.py --refresh가 7일마다 다시 받아 채움 — '늦은 프로필'은 참여·소속 음반 때문에 첫 발매가 앞당겨졌던 팀(뷰가 본인 음반 기준으로 바로잡음)

## 전체 검사

| 상태 | 검사 | 기준 | 오늘 값 | 고치는 법 |
|---|---|---|---|---|
| ✅ 통과 | 랩 데이터 갱신 시각 | 1일 넘게 안 바뀌면 실패 | 2026-11-28 17:26 (0일 전) | daily_run.sh의 export_lab_data.py 줄이 실패했는지 records/daily_run.log 확인 |
| ✅ 통과 | meta.json 행 수 = 실제 CSV 행 수 | 다르면 실패 (내보내기가 중간에 끊긴 것) | 표 8개 모두 일치 | .venv/bin/python scripts/export_lab_data.py 를 다시 돌린다 |
| ⚠️ 경고 | 전날 대비 행 수 | 어제 20행 이상인 표가 30% 넘게 줄면 실패, 50% 넘게 늘면 경고 | 급증: signals 26,534→62,079, teams 9,096→15,334, outcomes 723→1,218, links 1,100→3,864, videos 1,736→5,180, images 241→441 | 줄었으면 그날 수집·적재 로그 확인(수집 실패·연결표 오류), 늘었으면 같은 행이 두 번 들어갔는지 확인 |
| ✅ 통과 | 출처별 마지막 수집 | 성공 수집이 2일 넘으면 경고, 7일 넘으면 실패 | 출처 28개 중 오래된 것 0개 | records/daily_run.log에서 그 출처 줄의 ⚠️를 찾아 수집기를 직접 다시 돌려 본다 |
| ✅ 통과 | 출처별 가장 최근 신호 | 공연·발매·큐레이션 출처의 오늘 이전 마지막 신호가 14일 넘으면 경고, 45일 넘거나 없으면 실패 (선정·지원은 제외) | 출처 19개 중 오래된 것 0개 | 그 출처 수집기가 새 글을 못 읽는지(사이트 구조 변경) 확인한다 — 원래 드물게 올리는 곳이면 기준에서 뺀다 |
| ✅ 통과 | 미래 날짜 신호 | 공연이 아닌 신호가 미래 날짜면 경고, 공연도 365일 넘게 뒤면 경고 | 0건 | 그 출처 수집기의 날짜 읽기(연도 추정·발표일 대신 행사일)를 확인한다 |
| ✅ 통과 | 신호의 팀이 팀 표에 있나 | 제외 목록 팀 말고 팀 표에 없는 신호가 있으면 실패 | 없는 팀 신호 0건 / 62,079건 (제외 목록 팀 신호 371건은 정상) | export_lab_data.py의 signals·teams 쿼리가 같은 sig 조건을 쓰는지 확인 (한쪽만 거르면 생김) |
| ✅ 통과 | 링크·사진·영상의 팀이 팀 표에 있나 | 표마다 팀 표에 없는 팀 비율이 15% 넘으면 경고 | links 108/3,864 (2.8%) · images 18/441 (4.1%) · videos 193/5,180 (3.7%) | 신호 없이 프로필만 받은 팀(멜론 보강 명단)인지, 팀 키 표기가 달라 못 이은 것인지 몇 개 열어 본다 |
| ⚠️ 경고 | 같은 팀 중복 의심 | 띄어쓰기·대소문자·the, 표기 흔들림(쓰/스·애/에·챠/차·즈/스·앞의 더), 같은 링크 주소(높음), 한글 로마자 표기(중간)가 있으면 경고 — 한 글자 차이(낮음)는 목록만 | 251쌍 (띄어쓰기·대소문자·the 3, 표기 흔들림 16, 같은 링크 주소 33, 로마자 표기 14, 한 글자 차이 159, 짧은 이름 표기 흔들림 26): crane = thecrane, henzclub = thehenzclub, moss = themoss, 넉살x까데호 = 넉살까데호, 더리셋터즈 = 리셋터즈, 래드클라인 = 레드클라인, 리추얼리티 = 리츄얼리티, 릴체리x골드부다 = 릴체리골드부다 외 58 | 같은 팀이면 config/artist_aliases.json aliases에 근거와 함께 묶고, 다른 팀이면 distinct에 적는다 (목록은 아래 '자세히') |
| ✅ 통과 | 정답 '셈' 판정 일관성 | 기성 팀이 섞인 정답(burock_main, hello_rookie, kma_genre, mucon)은 첫 발매 5년 이내만 셈, 나머지는 모두 셈 — 다르면 실패 | 불일치 0건 · 확인 못 함 83건(팀 표에 없음) / 정답 1218행 | sql/kr/00_core_views.sql의 v_outcome·v_team_profile과 export_lab_data.py의 팀 표 첫 발매 규칙이 같은지 확인 |
| ✅ 통과 | B등급 정답의 5년 규칙 | source_roles.json에서 B등급('첫 발매 5년 이내 팀만 셈')인 정답이 실제 5년 규칙 목록에 없으면 경고 | B등급 4개 중 규칙 밖 0개 | 그 정답을 csv_schema.CAREER_FILTERED·ref.outcome_tier에 넣거나, 설명에서 5년 규칙 예외라고 적는다 |
| ✅ 통과 | '같은 집안' 표시 | 점수 출처 표시(same_house_scored)는 집안 출처가 있을 때만 — 어긋나면 실패, 규칙이 켜졌는데 표시 0건이면 경고 | 표시 50건 (점수 출처 포함 9건) · 켜진 짝 3개 | export_lab_data.same_house_flags와 config same_house(apply=true) 짝을 확인 |
| ✅ 통과 | 장르 미분류 | 프로필 있는 팀 중 장르 빈칸이 20% 넘으면 경고, 60% 넘으면 실패 | 프로필 팀 59/799 (7.4%) · 전체 팀 42.1% | build_dashboard_data._infer_genres의 장르 이름표에 새 표기(멜론·스포티파이 장르)를 추가한다 |
| ✅ 통과 | 첫 발매일 보유율 | 프로필 있는 팀 중 첫 발매일이 있는 비율이 90% 밑이면 경고, 70% 밑이면 실패 | 프로필 팀 779/799 (97.5%) · 전체 팀 5.1% | 멜론·스포티파이 프로필 수집기가 발매일을 못 읽는지(페이지 구조 변경) 확인한다 |
| ✅ 통과 | 링크·사진 주소 모양 | https가 아니거나 플랫폼 주소가 아니면 이상 — 하나라도 있으면 경고, 2% 넘으면 실패 (주소를 실제로 열어 보지는 않음) | 이상 0건 / 4,305건 (0.0%) | export_lab_data._link_url·image_rows의 주소 규칙(URL_TEMPLATES·IMAGE_CACHE_HOSTS)을 확인 |
| ⚠️ 경고 | 점수 상위 100팀 중 프로필 없음 | 프로필(멜론·스포티파이)이 없는 팀 비율이 30% 넘으면 경고, 80% 넘으면 실패 — 프로필이 없으면 신인인지 기성인지 모름 | 33/100팀 (33.0%) — 상위부터: 포져군단, 천둥오리, 최춘목밴드, 직사광선, 한이 외 28 | scripts/melon_names.py 보강 명단에 점수 상위 팀을 먼저 넣는다 (멜론 상세 페이지 차단이면 스포티파이로) |
| ✅ 통과 | 점수 스냅샷 | 오늘 스냅샷이 있어야 하고, 제외 목록 팀이나 팀 표에 없는 팀이 들어 있으면 경고 | 2026-11-28 · 300팀 | export_lab_data.py → lab_snapshot.py 순서로 다시 돌린다 (스냅샷이 옛 팀 표로 계산된 것) |
| ✅ 통과 | 앱 보조 데이터 8개 | meta.json extras 목록에 다 있고, 파일이 있고 비어 있지 않아야 함 — 하나라도 빠지면 실패 | 모두 있음 (갱신 2026-11-28 17:26) | daily_run.sh의 앱 보조 데이터 묶음(build_app_extras.sh)이 실패했는지 records/daily_run.log 확인 후 다시 돌린다 |
| ⚠️ 경고 | 팀 표 신인 확인·장르 확신도 분포 | newcomer_check·genre_confidence 칸에 정해진 값만 — 모르는 값이 있으면 경고 (분포는 참고) | newcomer_check: first_seen 14,065 · verified 783 · unverified 486 / genre_confidence: (빈칸) 6,457 · inferred 3,021 · profile 2,449 · review 1,838 · inferred_low 1,385 · press 184 — 모르는 값: review | export_lab_data.py의 newcomer_check·genre_confidence 값 목록과 data_checks.py NEWCOMER_CHECKS·GENRE_CONFIDENCES를 맞춘다 |
| ✅ 통과 | 알림 날짜·중복 | 공연·선정 기반 알림 말고는 미래 날짜면 경고, 어떤 알림도 365일 넘게 뒤면 경고, 같은 종류·팀·날짜가 두 번이면 경고 | 알림 430건 · 이상한 미래 날짜 0건 · 중복 0건 | 미래 날짜는 build_alerts.py의 날짜 고르기, 중복은 공연장 표기 차이('대구 제임스레코드'/'제임스레코드' 등)를 config/venue_aliases.json에 묶는다 |
| ✅ 통과 | 공연장 좌표·체급 보유율 (공연 밤 기준) | 좌표 85% 밑 경고·60% 밑 실패, 체급 70% 밑 경고·40% 밑 실패 ('공연장 미정' 제외) | 좌표 10,455/11,218 (93.2%) · 체급 8,911/11,218 (79.4%) — 체급 빠진 곳(밤 많은 순): 펫사운즈 339, 카페 아이다호 189, Hukez 128, 고인물 125, 서브라이엇 해방촌 85, 세종 음악창작소 누리락 55, KT&G 상상마당 춘천 55, 꼬뮨 52 외 361 | 공연 많은 공연장부터 config/venue_capacity.json(체급)·좌표 캐시를 채운다 — 아래 값의 '빠진 곳'부터 |
| ✅ 통과 | 공연장 목록(venues_kr) 짝 못 찾은 곳 | 짝 없는 공연장의 공연 밤이 10% 넘으면 경고 ('공연장 미정'·기획/레이블/행사 인스타 계정·not_venue 이름 제외) | 13곳 · 공연 밤 57/10,948 (0.5%) · 공연장 아님 270밤 뺌 — 축제 (을지로) 13, @junctionseoul 8, @fictionseoul 7, @stamina_375ml 7, @soundsupply_service 6, @whitelunarmusic 6, @gwangbok_record 4, GBN LIVEHOUSE 1 외 5 | config/venues_kr.json에 공연장(aliases 포함)을 추가하거나, 인스타 계정명(@…)이면 공연장 연결표에 대표 이름으로 묶는다 |
| ✅ 통과 | DB 신호 수 = 랩 신호 수 | 차이가 1% 넘으면 경고 | DB 62,079행 · 랩 62,079행 | 적재(load_pg.py) 뒤 export_lab_data.py가 안 돌았거나 실패한 것 — 다시 돌린다 |
| ✅ 통과 | 등록 안 된 정답 프로그램 | ref.outcome_tier에 없는 정답 프로그램이 있으면 실패 (조용히 빠짐) | 0개 | csv_schema.OUTCOME_TIER에 등급(mid·final)을 추가하고 다시 적재 |
| ✅ 통과 | 팀 이름·날짜 없는 신호 | 합쳐서 1% 넘으면 경고 (랩에서 빠짐) | 팀 없음 21건 · 날짜 없음 0건 / 62,135건 (0.0%) | 그 출처 수집기의 이름·날짜 읽기를 확인 |
| ✅ 통과 | 5년 규칙 목록 DB = 코드 | ref.outcome_tier.career_filtered와 csv_schema.CAREER_FILTERED가 다르면 실패 | 같음 (burock_main, hello_rookie, kma_genre, mucon) | load_pg.py를 다시 돌려 ref 표를 코드 값으로 맞춘다 |
| ⚠️ 경고 | 멜론 본인 음반 첫 발매(first_release_own) | 최신 멜론 프로필 중 보유율 50% 밑이면 경고, 본인 음반이 전체보다 이르면(계산 오류) 경고 | 본인 음반 첫 발매 88/819 (10.7%) · 전체 첫 발매 810 · 본인 음반이 3년 넘게 늦은 프로필 12개 · 본인이 더 이른 오류 0개 | collect_artists.py --refresh가 7일마다 다시 받아 채움 — '늦은 프로필'은 참여·소속 음반 때문에 첫 발매가 앞당겨졌던 팀(뷰가 본인 음반 기준으로 바로잡음) |

## 자세히: 같은 팀 중복 의심

- 높음 · 띄어쓰기·대소문자·the · crane ↔ thecrane
- 높음 · 띄어쓰기·대소문자·the · henzclub ↔ thehenzclub
- 높음 · 띄어쓰기·대소문자·the · moss ↔ themoss
- 높음 · 표기 흔들림 · 넉살x까데호 ↔ 넉살까데호
- 높음 · 표기 흔들림 · 더리셋터즈 ↔ 리셋터즈
- 높음 · 표기 흔들림 · 래드클라인 ↔ 레드클라인
- 높음 · 표기 흔들림 · 리추얼리티 ↔ 리츄얼리티
- 높음 · 표기 흔들림 · 릴체리x골드부다 ↔ 릴체리골드부다
- 높음 · 표기 흔들림 · 마인드애틱 ↔ 마인드에틱
- 높음 · 표기 흔들림 · 매디엑스피 ↔ 메디엑스피
- 높음 · 표기 흔들림 · 모사이코 ↔ 모싸이코
- 높음 · 표기 흔들림 · 스태리웨이브 ↔ 스테리웨이브
- 높음 · 표기 흔들림 · 앨리워드 ↔ 엘리워드
- 높음 · 표기 흔들림 · 워크맨쉽maalib ↔ 워크맨십maalib
- 높음 · 표기 흔들림 · 코스모스 ↔ 코즈모스
- 높음 · 표기 흔들림 · 킬카이저 ↔ 킬카이져
- 높음 · 표기 흔들림 · 포보틀스 ↔ 포보틀즈
- 높음 · 표기 흔들림 · 플랫폼스테레오 ↔ 플렛폼스테레오
- 높음 · 표기 흔들림 · 플레이버대쉬 ↔ 플레이버대시
- 높음 · 같은 링크 주소 · 01 ↔ 정용찬 (www.instagram.com)
- 높음 · 같은 링크 주소 · 13children ↔ 서틴칠드런 (www.instagram.com)
- 높음 · 같은 링크 주소 · 30 ↔ 요이 (www.instagram.com)
- 높음 · 같은 링크 주소 · baan ↔ 반 (www.instagram.com)
- 높음 · 같은 링크 주소 · deny ↔ 디나이 (www.instagram.com)
- 높음 · 같은 링크 주소 · eddieandthebricks ↔ 에디앤더브릭스 (open.spotify.com)
- 높음 · 같은 링크 주소 · fleet플릿 ↔ 플릿 (www.instagram.com)
- 높음 · 같은 링크 주소 · frnk ↔ 프랭크 (www.instagram.com)
- 높음 · 같은 링크 주소 · giok ↔ 지옥 (www.instagram.com)
- 높음 · 같은 링크 주소 · himinn ↔ 히민 (www.instagram.com)
- 높음 · 같은 링크 주소 · howcani ↔ 하우캔아이 (www.instagram.com)
- 높음 · 같은 링크 주소 · izoko ↔ 이조코 (www.instagram.com)
- 높음 · 같은 링크 주소 · lucyvalentine ↔ 루시발렌타인 (www.instagram.com)
- 높음 · 같은 링크 주소 · menandthem ↔ 맨앤뎀 (www.instagram.com)
- 높음 · 같은 링크 주소 · mhd ↔ 메리헤이데이 (www.instagram.com)
- 높음 · 같은 링크 주소 · mischiefers ↔ 미스치퍼스 (www.instagram.com)
- 높음 · 같은 링크 주소 · myveryend ↔ 마이베리엔드 (www.instagram.com)
- 높음 · 같은 링크 주소 · omilgop ↔ 오미일곱 (www.instagram.com)
- 높음 · 같은 링크 주소 · pnr ↔ 피스앤로맨스 (www.instagram.com)
- 높음 · 같은 링크 주소 · redc ↔ 레드씨 (www.instagram.com)
- 높음 · 같은 링크 주소 · revesenrebirth ↔ 리버스앤리버스 (www.instagram.com)
- 높음 · 같은 링크 주소 · roon ↔ 룬 (www.instagram.com)
- 높음 · 같은 링크 주소 · sabbaha ↔ 사바하 (www.instagram.com)
- 높음 · 같은 링크 주소 · sallyeverywhere샐리에브리웨어 ↔ 샐리에브리웨어 (www.instagram.com)
- 높음 · 같은 링크 주소 · scarletkimband ↔ 스칼렛킴밴드 (www.instagram.com)
- 높음 · 같은 링크 주소 · sosoyon ↔ 소소욘 (www.instagram.com)
- 높음 · 같은 링크 주소 · thejoyfools ↔ 조이풀스 (www.instagram.com)
- 높음 · 같은 링크 주소 · underflow언더플로우 ↔ 언더플로우 (www.instagram.com)
- 높음 · 같은 링크 주소 · wakingsuns ↔ 웨이킹선스 (www.instagram.com)
- 높음 · 같은 링크 주소 · 나르샤 ↔ 나르샤browneyedgirls (www.melon.com)
- 높음 · 같은 링크 주소 · 변하은 ↔ 변하은과하이에나 (www.instagram.com)
- 높음 · 같은 링크 주소 · 송남현 ↔ 준비왕송남현 (www.instagram.com)
- 높음 · 같은 링크 주소 · 윤석철 ↔ 윤석철트리오 (www.instagram.com)
- 중간 · 로마자 표기 · 가경 ↔ gagyeong
- 중간 · 로마자 표기 · 나미카이 ↔ namikai
- 중간 · 로마자 표기 · 디디한 ↔ didihan
- 중간 · 로마자 표기 · 로얄44 ↔ royal44
- 중간 · 로마자 표기 · 모하니 ↔ mohani
- 중간 · 로마자 표기 · 바바바 ↔ bababa
- 중간 · 로마자 표기 · 사케비 ↔ sakebi
- 중간 · 로마자 표기 · 송요다 ↔ songyoda
- 중간 · 로마자 표기 · 수련 ↔ suryeon
- 중간 · 로마자 표기 · 연준 ↔ yeonjun
- 중간 · 로마자 표기 · 욘욘 ↔ yonyon
- 중간 · 로마자 표기 · 한강 ↔ hangang
- 중간 · 로마자 표기 · 한결 ↔ hangyeol
- 중간 · 로마자 표기 · 해로이키 ↔ haeroiki
- 낮음 · 한 글자 차이 · 100kgold ↔ 100kgoldx
- 낮음 · 한 글자 차이 · aaprocky ↔ asaprocky
- 낮음 · 한 글자 차이 · ableakre ↔ bleakre
- 낮음 · 한 글자 차이 · advance ↔ advanced
- 낮음 · 한 글자 차이 · allica ↔ ellica
- 낮음 · 한 글자 차이 · altruisiticdrum ↔ altruisticdrum
- 낮음 · 한 글자 차이 · amyiee ↔ amyiie
- 낮음 · 한 글자 차이 · badwimps ↔ radwimps
- 낮음 · 한 글자 차이 · bbbbomb ↔ bbbomb
- 낮음 · 한 글자 차이 · blight ↔ bright
- 낮음 · 한 글자 차이 · bugokhawaii ↔ bukokhawaii
- 낮음 · 한 글자 차이 · cifika ↔ cifikas
- 낮음 · 한 글자 차이 · codeine ↔ codemine
- 낮음 · 한 글자 차이 · darkmirrorovtragedy ↔ darkmirrorovtregedy
- 낮음 · 한 글자 차이 · dayoung ↔ hayoung
- 낮음 · 한 글자 차이 · forest ↔ norest
- 낮음 · 한 글자 차이 · freaks ↔ treaks
- 낮음 · 한 글자 차이 · gori2lla ↔ gori2llaa
- 낮음 · 한 글자 차이 · jaezae ↔ jaezze
- 낮음 · 한 글자 차이 · jaezze ↔ zaezze
- 낮음 · 한 글자 차이 · jasminekelly ↔ jasminkelly
- 낮음 · 한 글자 차이 · jinmoo ↔ jinwoo
- 낮음 · 한 글자 차이 · jungin ↔ sungin
- 낮음 · 한 글자 차이 · jy밴드 ↔ ky밴드
- 낮음 · 한 글자 차이 · leekyungminn ↔ leekyungminnn
- 낮음 · 한 글자 차이 · loosendoor ↔ loosendoors
- 낮음 · 한 글자 차이 · lushroom ↔ nushroom
- 낮음 · 한 글자 차이 · lyumin ↔ lyumln
- 낮음 · 한 글자 차이 · maalib ↔ madlib
- 낮음 · 한 글자 차이 · marviista ↔ marvista
- 낮음 · 한 글자 차이 · mokhzolla ↔ mokzolla
- 낮음 · 한 글자 차이 · moreen ↔ morten
- 낮음 · 한 글자 차이 · mountxir ↔ mountxlr
- 낮음 · 한 글자 차이 · nevermind ↔ theneverminds
- 낮음 · 한 글자 차이 · noname ↔ nonamer
- 낮음 · 한 글자 차이 · perila ↔ perilla
- 낮음 · 한 글자 차이 · pupura ↔ purpura
- 낮음 · 한 글자 차이 · reversenrebirth ↔ revesenrebirth
- 낮음 · 한 글자 차이 · royal44 ↔ royal44k
- 낮음 · 한 글자 차이 · santiagonicolas ↔ santiagonicols
- 낮음 · 한 글자 차이 · shallowleve ↔ shallowlevee
- 낮음 · 한 글자 차이 · shanghaiqiutian ↔ shanhaiqiutian
- 낮음 · 한 글자 차이 · slosolo ↔ slosxlo
- 낮음 · 한 글자 차이 · stravinsukiyak ↔ stravinsukiyaki
- 낮음 · 한 글자 차이 · yln포린 ↔ yln포린등
- 낮음 · 한 글자 차이 · yunili ↔ yunini
- 낮음 · 한 글자 차이 · 강다니엘 ↔ 김다니엘
- 낮음 · 한 글자 차이 · 강다니엘 ↔ 허다니엘
- 낮음 · 한 글자 차이 · 걸어프라이드 ↔ 걸어프레이드
- 낮음 · 한 글자 차이 · 고니밴드 ↔ 수니밴드
- 낮음 · 한 글자 차이 · 김다니엘 ↔ 허다니엘
- 낮음 · 한 글자 차이 · 김현정밴드 ↔ 김현철밴드
- 낮음 · 한 글자 차이 · 나르디스 ↔ 나르키스
- 낮음 · 한 글자 차이 · 네메시스 ↔ 네미시스
- 낮음 · 한 글자 차이 · 네모난구 ↔ 네모지구
- 낮음 · 한 글자 차이 · 다섯번째 ↔ 여섯번째
- 낮음 · 한 글자 차이 · 더블랭크샵 ↔ 더블랭크숍
- 낮음 · 한 글자 차이 · 더사운드 ↔ 웜사운드
- 낮음 · 한 글자 차이 · 더스미스 ↔ 더스미어
- 낮음 · 한 글자 차이 · 듀포인트 ↔ 원포인트
- 낮음 · 한 글자 차이 · 디비아디 ↔ 디비아이디
- 낮음 · 한 글자 차이 · 디스맨즈 ↔ 홀스맨즈
- 낮음 · 한 글자 차이 · 디에이드 ↔ 디에이팝
- 낮음 · 한 글자 차이 · 라이프라디 ↔ 라이프라디오
- 낮음 · 한 글자 차이 · 랑그에빠롤 ↔ 랑그에파롤
- 낮음 · 한 글자 차이 · 러버사이즈 ↔ 오버사이즈
- 낮음 · 한 글자 차이 · 러브x스테레오 ↔ 러브엑스테레오
- 낮음 · 한 글자 차이 · 레드브릭스 ↔ 레이브릭스
- 낮음 · 한 글자 차이 · 레오파드 ↔ 베오파드
- 낮음 · 한 글자 차이 · 레인폴띠어리 ↔ 레인폴씨어리
- 낮음 · 한 글자 차이 · 론울프엘러지클럽 ↔ 론울프엘리지클럽
- 낮음 · 한 글자 차이 · 롱아일랜드 ↔ 심아일랜드
- 낮음 · 한 글자 차이 · 루시드림 ↔ 루시드폴
- 낮음 · 한 글자 차이 · 리마이더스 ↔ 리마인더스
- 낮음 · 한 글자 차이 · 리브포레버 ↔ 리브포에버
- 낮음 · 한 글자 차이 · 마이호미타 ↔ 마이호미타르
- 낮음 · 한 글자 차이 · 머쉬베놈 ↔ 머쉬베놈과
- 낮음 · 한 글자 차이 · 메이릴리 ↔ 메이트리
- 낮음 · 한 글자 차이 · 모노플로 ↔ 주노플로
- 낮음 · 한 글자 차이 · 모사이코 ↔ 모텔사이코
- 낮음 · 한 글자 차이 · 미스피츠 ↔ 코스피츠
- 낮음 · 한 글자 차이 · 바비돌스 ↔ 바비핀스
- 낮음 · 한 글자 차이 · 반디시티 ↔ 윈디시티
- 낮음 · 한 글자 차이 · 배드큐피드 ↔ 배드큐피트
- 낮음 · 한 글자 차이 · 밴드그린 ↔ 밴드기린
- 낮음 · 한 글자 차이 · 버스터즈 ↔ 토스터즈
- 낮음 · 한 글자 차이 · 베더블루 ↔ 베티블루
- 낮음 · 한 글자 차이 · 보이콜드 ↔ 보이후드
- 낮음 · 한 글자 차이 · 불나방단 ↔ 불나방들
- 낮음 · 한 글자 차이 · 블랙스완 ↔ 블랙스톤
- 낮음 · 한 글자 차이 · 블루블루 ↔ 블루앤블루
- 낮음 · 한 글자 차이 · 비더보이스 ↔ 비치보이스
- 낮음 · 한 글자 차이 · 비웨이브 ↔ 영웨이브
- 낮음 · 한 글자 차이 · 사운드마켓 ↔ 사운드포켓
- 낮음 · 한 글자 차이 · 상현밴드 ↔ 상흠밴드
- 낮음 · 한 글자 차이 · 상흠밴드 ↔ 정흠밴드
- 낮음 · 한 글자 차이 · 서나밴드 ↔ 서도밴드
- 낮음 · 한 글자 차이 · 소매밴드 ↔ 소호밴드
- 낮음 · 한 글자 차이 · 소호밴드 ↔ 팡호밴드
- 낮음 · 한 글자 차이 · 스위밍돌 ↔ 스위밍풀
- 낮음 · 한 글자 차이 · 스트레이 ↔ 스프레이
- 낮음 · 한 글자 차이 · 스파게티 ↔ 스파게티즈
- 낮음 · 한 글자 차이 · 슬레이터 ↔ 트레이터
- 낮음 · 한 글자 차이 · 슬로우빌 ↔ 슬로우쥰
- 낮음 · 한 글자 차이 · 슬로우빌 ↔ 슬로우진
- 낮음 · 한 글자 차이 · 슬로우쥰 ↔ 슬로우진
- 낮음 · 한 글자 차이 · 신스네이크 ↔ 앤스네이크
- 낮음 · 한 글자 차이 · 심아일랜드 ↔ 심아일밴드
- 낮음 · 한 글자 차이 · 쎄미블루 ↔ 이미블루
- 낮음 · 한 글자 차이 · 씨없는수박김대중 ↔ 씨없는수박김태중
- 낮음 · 한 글자 차이 · 아이리스킴 ↔ 아이리스트
- 낮음 · 한 글자 차이 · 아이브이 ↔ 아이아이
- 낮음 · 한 글자 차이 · 아이브이 ↔ 아이타이
- 낮음 · 한 글자 차이 · 아이아이 ↔ 아이오아이
- 낮음 · 한 글자 차이 · 아이아이 ↔ 아이타이
- 낮음 · 한 글자 차이 · 아이오아 ↔ 아이오아이
- 낮음 · 한 글자 차이 · 아이오아 ↔ 아이오와
- 낮음 · 한 글자 차이 · 안경잽이 ↔ 안경쟁이
- 낮음 · 한 글자 차이 · 양지밴드 ↔ 하지밴드
- 낮음 · 한 글자 차이 · 어라이브펑크 ↔ 얼라이브펑크
- 낮음 · 한 글자 차이 · 얼라이브펑크 ↔ 얼라이브훵크
- 낮음 · 한 글자 차이 · 에이머스 ↔ 에이체스
- 낮음 · 한 글자 차이 · 에이티즈 ↔ 에이퍼즈
- 낮음 · 한 글자 차이 · 여리밴드 ↔ 토리밴드
- 낮음 · 한 글자 차이 · 오렌지맨 ↔ 오렌지섬
- 낮음 · 한 글자 차이 · 오아시스 ↔ 오아시아
- 낮음 · 한 글자 차이 · 오아시스 ↔ 오이시스
- 낮음 · 한 글자 차이 · 오윤밴드 ↔ 오주밴드
- 낮음 · 한 글자 차이 · 오이스터 ↔ 오이스터즈
- 낮음 · 한 글자 차이 · 올시스템그린 ↔ 올시스템즈그린
- 낮음 · 한 글자 차이 · 우주소녀 ↔ 우주소요
- 낮음 · 한 글자 차이 · 유어마인 ↔ 유얼마인
- 낮음 · 한 글자 차이 · 이지구밴드 ↔ 이지두밴드
- 낮음 · 한 글자 차이 · 이지구밴드 ↔ 이지선밴드

기준값은 `scripts/data_checks.py` 맨 위 상수에 있어요. 주소는 모양만 보고 실제로 열어 보지는 않아요.
