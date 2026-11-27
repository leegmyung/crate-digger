# 오늘 후보 상위 50팀 표본 검증 (2026-11-27)

> 질문: **"우리 점수가 고른 상위 50팀, 판정이 맞나?"** — 한 팀씩 공개 웹(웹 검색·매체 리뷰·위키·공연 기록 공개 페이지)으로 확인했다. 브라우저 조종(aside)은 쓰지 않았다.
> 대상: `candidates.sql`(점수 v2, 기준일 2026-11-27, 정답 없는 팀만) 상위 50팀. 데이터는 그날 19:13 생성본이라 21시 자동 실행 뒤 순위가 조금 바뀔 수 있다.
> 확인 항목: ① 실제 데뷔 연도(우리 `first_release`·`first_seen`과 비교) ② 인디인가(소속 규모) ③ 활동 중인가(최근 1년) ④ 이미 유명한가 ⑤ 이름 연결 오류(다른 팀과 섞임) ⑥ 장르.
> 함께 볼 문서: `docs/candidate_audit.md`(우리 데이터만으로 상위 300팀을 자동 점검). 이 문서는 그 위에 **공개 웹으로 직접 대조**한 표본 검증이다.

---

## 1. 한눈에 — 유형별 오류율

| 유형 | 50팀 중 | 확인된 팀 중 | 해당 팀 |
|---|---|---|---|
| **신인 아님** (3년보다 오래 활동) | **10팀 (20%)** | 데뷔 연도 확인 24팀 중 **10팀 (42%)** | 클라프(2016) · 콘트라젤리(2015) · 에이틴 에이프릴(2011) · 티어드랍(2004 결성 추정) · 신스네이크(2016) · 애니멀다이버스(2018) · 놀플라워(2018) · 바림(2020 결성) · 하즈(2022-10) · 세일러 허니문(2022~) |
| **이름 연결 오류** | 1팀 (2%) | — | 성현 (공연·리뷰는 인디 싱어송라이터 성현, 멜론 프로필은 빅히트 신인 그룹 멤버 성현) |
| **이미 주목받음** | 1팀 (2%) | — | 세일러 허니문 (NME 표지, PIAS 배급, 해외 페스티벌) |
| **최근 활동 없음** (180일 신호 0) | 3팀 (6%) | — | 품바 21(마지막 2025-05) · neverandno(2025-08) · 놀플라워(2025-12) |
| **인디 아님** | 0팀 | 소속 확인 9팀 모두 작은 인디 레이블 | (성현은 연결 오류로 따로 셈) |
| **장르 틀림** | 0팀 | 장르 있는 15팀 중 대조 가능 5팀 모두 맞음 | 대신 **장르 빈칸 35팀(70%)** |
| 공개 웹으로 확인 못 함 | 데뷔 연도 미확인 26팀 (52%) | — | 4장 표의 '미확인' |

**가장 큰 문제는 '신인 판정'이다.** 특히 **멜론 프로필이 없는 팀**(상위 50 중 35팀)에서 크다:
- 프로필 없는 팀 중 데뷔 연도를 확인한 18팀 → **10팀(56%)이 신인 아님**.
- 프로필 있는 팀 중 확인한 6팀 → 5팀 맞음, 1팀은 연결 오류(성현).

### 왜 이런가 (원인)
- 신인 규칙은 `COALESCE(first_release, first_seen) >= 기준일 - 3년`(`docs/lab/sql/features.sql` 125행)이다. 프로필이 없으면 **우리 데이터에 처음 보인 날(first_seen)**로 판정한다.
- 그런데 공연 데이터의 주 출처인 **인디스트릿은 2024-01-04부터** 모았다. 그래서 2016년부터 활동한 밴드도 우리 눈엔 "2024년 2월에 처음 등장" → 기준(2023-11-27)보다 늦으니 **자동으로 신인**이 된다. (데이터 시작점에 잘린 효과)
- 실제로 first_seen이 2024-01~04인 프로필 없는 팀 중 확인된 8팀 가운데 5팀이 신인 아님(콘트라젤리·클라프·에이틴 에이프릴·티어드랍·하즈). 그 뒤 몇 달 안에 처음 보인 팀(바림·신스네이크·놀플라워·세일러 허니문·애니멀다이버스)도 마찬가지였다.

---

## 2. 고칠 규칙 제안 (config 반영은 코디네이터)

| # | 제안 | 고쳐지는 팀(이번 표본) | 크기 |
|---|---|---|---|
| R1 | **수동 데뷔 연도 덮어쓰기** 표(예: `config/debut_overrides.json`: 팀 키 → 데뷔 날짜 + 근거 링크)를 두고, 신인 판정에서 `first_release`보다 먼저 쓴다. 데뷔는 과거 사실이라 백테스트(과거 기준일)에 써도 미래 정보가 새지 않는다. 우선 아래 10팀: 클라프 2016-07-02, 콘트라젤리 2015, 에이틴 에이프릴 2011, 티어드랍 2006, 신스네이크 2016, 애니멀다이버스 2018, 놀플라워 2018, 바림 2023 이전(2020 결성), 하즈 2022-10-12, 세일러 허니문 2022 | 10팀 → 후보에서 빠짐 | 작음 |
| R2 | **프로필 없는 팀은 first_seen만으로 '신인'이라 하지 않는다.** 최소한 "출처 시작일 + 90일 안에 처음 보인 팀"(인디스트릿 2024-01-04~04-03)은 `신인 미확인`으로 두고, 순위표에 꼬리표를 달거나 '지금 후보'에서 따로 묶는다. | 상위 50 중 프로필 없음 35팀, 그중 시작일 90일 안 13팀 | 중간 (순위 많이 바뀜 — 사용자 결정 필요) |
| R3 | **멜론 프로필 보강 우선순위**: 매일 '멜론 100팀 보강' 명단에 *상위 후보인데 프로필 없는 팀*을 먼저 넣는다. 프로필의 첫 발매일이 R2 문제를 가장 싸게 줄인다. | 35팀 | 작음 (daily_run 명단) |
| R4 | **성현 멜론 프로필 연결 끊기** (연결표 보정 구역 '다른 팀'). 일반 규칙으로: 프로필 소속사가 대형 기획사(하이브·빅히트·SM·JYP·YG 등)인데 우리 신호가 인디 공연·인디 매체뿐이면 `연결 의심`으로 표시하고 프로필을 쓰지 않는다. | 성현 | 작음 |
| R5 | **이미 주목받는 팀 제외 목록**(candidate_rules)에 세일러 허니문 추가. 해외 매체(NME 등)·해외 레이블 정보는 우리가 모으지 않으므로 지금은 수동 목록이 현실적. | 세일러 허니문 | 작음 |
| R6 | **휴면 팀 표시**: 최근 180일 신호 0 + 최근 1년 공연 0이면 '지금 후보'에서 `휴면` 칸으로 내린다(지우지는 않음). 지금 1위 품바 21이 여기에 걸린다 — 1위가 1년 반 동안 활동 기록이 없다는 건 사용자에게 바로 보여야 한다. | 품바 21 · neverandno · 놀플라워 | 작음 |
| R7 | **장르 칸 채우기**: 상위 50의 70%가 장르 빈칸. 이번 표에서 웹으로 찾은 장르(아래 표 '장르' 열)를 수동으로 넣고, 장르 지도에 `메탈·하드코어` 갈래를 따로 둔다(상위 50에 메탈 계열이 7팀 이상: 하즈·에이틴 에이프릴·클라프·티어드랍·신스네이크·바림·(턴포아워)). 지금은 모두 '록·밴드'나 빈칸에 묻힌다. | 35팀 | 작음 |
| R8 | **짧은 이름 동명 주의 목록**: 성현·한이·일렁·하즈·머지·바림·아토처럼 두 글자 이름은 다른 사람과 섞이기 쉽다. 매체 리뷰에 '적바림'과 '바림'이 함께 있다(이번엔 섞이지 않음). 짧은 이름은 연결 시 영문 표기·공연장까지 맞을 때만 잇는 규칙 검토. | 예방 | 작음 |

참고(이번 작업 범위 밖, 눈에 띈 점): 상위 50 중 47팀이 거의 같은 모양(인디스트릿 공연 + 음악취향Y 리뷰 1건 + '수상 팀과 같은 무대')이라 점수 5.61이 12팀, 5.39가 6팀처럼 **동점이 많다**. 순위 아래쪽은 사실상 구별이 안 된다.

---

## 3. 확인 방법
- 팀마다 한국어·영문 이름으로 웹 검색. 영문 이름은 음악취향Y 리뷰 제목(예: "클라프 (KlaFF)")에서 얻었다 — 그 리뷰 페이지 자체도 공개 근거로 링크했다(`musicy.kr … ix=번호`).
- '신인' 기준은 우리 규칙과 같게 **기준일 3년 전(2023-11-27) 이후 첫 발매**.
- 웹에서 아무 정보도 못 찾은 팀은 '미확인'으로 두고 추측하지 않았다. 미국 기반 검색이라 작은 국내 인디 팀은 잘 안 잡힌다 — 미확인이 많은 건 정보 부족이지 판정이 맞다는 뜻이 아니다.
- 활동 여부는 우리 데이터(최근 180일·1년 신호)로 봤다. 웹에서 최근 소식이 확인되면 함께 적었다.

---

## 4. 50팀 검증표

열: **우리** = 우리 데이터(프로필 상태 · 첫 발매 또는 첫 포착), **웹** = 공개 웹에서 확인한 것, **신인** ✅맞음 ❌아님 ⚠️연결 오류 ❔미확인, **활동** = 최근 1년 공연 수(우리 데이터), **장르** = 웹으로 확인한 장르(빈칸 = 못 찾음).

| # | 팀 | 우리 | 웹 | 신인 | 활동 | 장르 | 근거 |
|---|---|---|---|---|---|---|---|
| 1 | 품바 21 | 프로필 없음 · 첫 포착 2024-02 | 2023-04 EP로 데뷔(2019 결성), LOCALHIGH RECORDS | ✅ (3년 안) | **0 — 마지막 2025-05 (휴면)** | 록('조선 락') | [부산록페](https://busanrockfestival.com/?p=8628) · [kprofiles](https://kprofiles.com/?p=465288) · [음악취향Y](http://musicy.kr/?c=review&s=1&gbn=view&ix=8599) |
| 2 | 칩포스트갱 | 없음 · 2025-07 | 2025-10 EP 'CAVEQUAKE', 2026-09 정규 1집, 패치룸 페스티벌 운영 | ✅ | 7 | 노이즈 록 | [Debaser](https://debasermagazine.com/music/chip-post-gang-interview) · [참 매거진](https://brunch.co.kr/@chammag/18) · [음악취향Y](http://musicy.kr/?c=review&s=1&gbn=view&ix=9107) |
| 3 | 포져군단 | 없음 · 2024-09 | 공연 라인업만 확인(스페이스 한강) | ❔ | 22 | | [공연 신청 폼](https://docs.google.com/forms/d/e/1FAIpQLSd05x9_J6uXKgDUingTX-YLYoPAyiFDmDMv9RHVWitXDjov8Q/viewform) |
| 4 | PCR | 신인 · 2025-01 | 서울 아트 펑크 집단 (데뷔 날짜 미확인) | ✅ (프로필 기준) | 10 | 아트 펑크 | [Rolling Stone India](https://rollingstoneindia.com/alternative-korean-bands-to-add-to-your-playlist) · [음악취향Y](http://musicy.kr/?c=review&s=1&gbn=view&ix=9490) |
| 5 | 행간소음 | 없음 · 2024-01 | 데뷔 앨범 '독백적 집단'(2025)으로 소개된 신인 | ✅ | 5 | | [Debaser](https://debasermagazine.com/music/noise-between-the-lines-interview) · [음악취향Y](http://musicy.kr/?c=review&s=1&gbn=view&ix=8885) |
| 6 | 세일러 허니문 | 없음 · 2024-05 | 2022년부터 활동, 2026 NME 표지, 정규 1집 PIAS 배급 | ❌ (2022~) + **이미 주목** | 5 | 펑크 록 | [Wikipedia](https://en.wikipedia.org/wiki/Sailor_Honeymoon) · [NME](https://www.nme.com/the-cover/sailor-honeymoon-03-08-2026-3960368) · [스포츠경향](https://sports.khan.co.kr/article/202606300157003) |
| 7 | 콘트라젤리 | 없음 · 2024-01 | 2015 EP 'Sequence'로 데뷔 | ❌ (2015) | 10 | 신스·일렉트로닉 | [The K-Meal](https://thekmeal.com/indie-pick-kontrajelly/) · [음악취향Y](http://musicy.kr/?c=review&s=1&gbn=view&ix=8598) |
| 8 | 폴리아모리 | 없음 · 2024-06 | 서울 포스트록 듀오, 2026 정규 1집 '균의 만연' (데뷔 날짜 미확인) | ❔ | 9 | 포스트록 | [Bandcamp](https://polyamoryband.bandcamp.com/track/current) · [공연 안내](https://popga.co.kr/popup/9951) · [음악취향Y](http://musicy.kr/?c=review&s=1&gbn=view&ix=8816) |
| 9 | 하즈 | 없음 · 2024-03 | 대구 인디 메탈 HASE, 2022-10-12 데뷔, 노머시 컴퍼니 | ❌ (2022-10) | 9 | 메탈 | [나무위키](https://namu.moe/w/HASE(%EB%B0%B4%EB%93%9C)) · [Qobuz](https://www.qobuz.com/us-en/interpreter/hase/1309575) · [음악취향Y](http://musicy.kr/?c=review&s=1&gbn=view&ix=8696) |
| 10 | 몽키 갱 워 | 없음 · 2024-05 | 매체 리뷰만(2025-03 셀프 타이틀) | ❔ | 12 | | [음악취향Y](http://musicy.kr/?c=review&s=1&gbn=view&ix=8925) |
| 11 | 도그 라스트 페이지 | 없음 · 2024-02 | 매체 리뷰만(2025-06) | ❔ | 8 | | [음악취향Y](http://musicy.kr/?c=review&s=1&gbn=view&ix=8996) |
| 12 | 클라프 | 없음 · 2024-02 | 부산 록·메탈 KlaFF, 2016-07-02 첫 싱글, 불가마싸운드 | ❌ (2016) | 5 | 록·메탈 | [나무위키](https://namu.moe/w/KlaFF) · [불가마 뉴스레터](https://maily.so/bullgamasound/posts/n3jrk8e6r51) · [음악취향Y](http://musicy.kr/?c=review&s=1&gbn=view&ix=8963) |
| 13 | 비제로 | 신인 · 2025-04 | 매체 리뷰만(영문 BASEMENTZEROFLOOR) | ❔ | 12 | | [음악취향Y](http://musicy.kr/?c=review&s=1&gbn=view&ix=9221) |
| 14 | 포스트이너서클 | 없음 · 2025-02 | 서울 5인조, 데뷔 EP '인공태양'(2025) | ✅ | 6 | | [a-indie 인터뷰](https://a-indie.com/?p=3091) · [음악취향Y](http://musicy.kr/?c=review&s=1&gbn=view&ix=9119) |
| 15 | 모우들 | 신인 · 2025-06 | 매체 리뷰만(2026-04) | ❔ | 21 | | [음악취향Y](http://musicy.kr/?c=review&s=1&gbn=view&ix=9295) |
| 16 | 천둥오리 | 없음 · 2024-03 | 매체 리뷰만(2025-11) | ❔ | 9 | | [음악취향Y](http://musicy.kr/?c=review&s=1&gbn=view&ix=9126) |
| 17 | 데킬라올드패션드 | 신인 · 2024-12 | 2024-11 결성 하드록, 첫 싱글 'Look Forward' | ✅ | 13 | 하드 록 | [Discomfort Wings](https://www.discomfort-wings.com/2024/12/12/tequila-old-fashioned-look-forward-single-release) · [음악취향Y](http://musicy.kr/?c=review&s=1&gbn=view&ix=8815) |
| 18 | 에이틴 에이프릴 | 없음 · 2024-01 | 2011년부터 활동한 메탈 밴드(1804) | ❌ (2011) | 4 | 메탈 | [kprofiles](https://kprofiles.com/?p=339753) · [음악취향Y](http://musicy.kr/?c=review&s=1&gbn=view&ix=8900) |
| 19 | 모노폴리 | 없음 · 2024-01 | MONO4OLY, 2023년 말 결성, 2024-12 정규 1집 | ✅ | 6 | 블루스·하드 록 | [Discomfort Wings](https://discomfort-wings.com/2024/12/11/mono4oly-ordinary-chaos-album-release) · [음악취향Y](http://musicy.kr/?c=review&s=1&gbn=view&ix=8784) |
| 20 | JULYWANTSMORE | 신인 · 2026-06 | 못 찾음 | ❔ | 14 | | — |
| 21 | 아토 | 신인 · 2024-02-21 | 2024-02-21 싱글 '낮술'로 데뷔 — **우리 날짜와 정확히 일치** | ✅ | 8 | 록 | [kprofiles](https://kprofiles.com/ato-members-profile/) · [음악취향Y](http://musicy.kr/?c=review&s=1&gbn=view&ix=9273) |
| 22 | 최춘목밴드 | 없음 · 2025-12 | 매체 리뷰만(2026-10) | ❔ | 10 | | [음악취향Y](http://musicy.kr/?c=review&s=1&gbn=view&ix=9452) |
| 23 | 티어드랍 | 없음 · 2024-02 | 2004 결성 뉴메탈 '티어드랍', 2006 첫 EP (리뷰된 'Beastology'와 같은 팀일 가능성 높음) | ❌ (2006, 추정) | 3 | 뉴메탈 | [Discomfort Wings](https://www.discomfort-wings.com/2019/11/10/it-s-time-to-make-your-plan-z-티어드랍/) · [음악취향Y](http://musicy.kr/?c=review&s=1&gbn=view&ix=8576) |
| 24 | 유령서점 | 신인 · 2024-04 | 못 찾음(Last.fm 'Ghost Bookstore'만) | ❔ | 5 | | [음악취향Y](http://musicy.kr/?c=review&s=1&gbn=view&ix=8760) |
| 25 | neverandno | 신인 · 2025-04 | 못 찾음 | ❔ | **0 — 마지막 2025-08 (휴면)** | | — |
| 26 | 팬텀루나틱스 | 없음 · 2024-03 | 매체 리뷰만(2024-05 'Downfall') | ❔ | 2 | | [음악취향Y](http://musicy.kr/?c=review&s=1&gbn=view&ix=8642) |
| 27 | 한이 | 없음 · 2023-12 | 제34회 유재하 음악경연대회 동상 | ✅ | 2 | 싱어송라이터 | [CJ뉴스룸](https://cjnews.cj.net/%ec%a0%9c34%ed%9a%8c-cj%ec%99%80-%ed%95%a8%ea%bb%98%ed%95%98%eb%8a%94-%ec%9c%a0%ec%9e%ac%ed%95%98-%ec%9d%8c%ec%95%85%ea%b2%bd%ec%97%b0%eb%8c%80%ed%9a%8c-%ec%84%b1%eb%a3%8c/) |
| 28 | 일렁 | 없음 · 2023-12 | 제34회 유재하 음악경연대회 장려상 | ✅ | 4 | 싱어송라이터 | [CJ뉴스룸](https://cjnews.cj.net/%ec%a0%9c34%ed%9a%8c-cj%ec%99%80-%ed%95%a8%ea%bb%98%ed%95%98%eb%8a%94-%ec%9c%a0%ec%9e%ac%ed%95%98-%ec%9d%8c%ec%95%85%ea%b2%bd%ec%97%b0%eb%8c%80%ed%9a%8c-%ec%84%b1%eb%a3%8c/) |
| 29 | 퓨처피어클럽 | 없음 · 2026-01 | 매체 리뷰만(2026-11) | ❔ | 6 | | [음악취향Y](http://musicy.kr/?c=review&s=1&gbn=view&ix=9478) |
| 30 | 페이퍼라이프 | 없음 · 2025-03 | 매체 리뷰만(2026-08) | ❔ | 4 | | [음악취향Y](http://musicy.kr/?c=review&s=1&gbn=view&ix=9406) |
| 31 | 애니멀다이버스 | 없음 · 2024-09 | 2018 'Horizon Noir'로 시작, 2019 정규 1집 | ❌ (2018) | 4 | 일렉트로닉·월드 | [The K-Meal](https://thekmeal.com/b-and-9-the-striking-debut-of-a-unique-presence-electronic-duo-band-animal-divers/) · [음악취향Y](http://musicy.kr/?c=review&s=1&gbn=view&ix=8743) |
| 32 | 머지 | 없음 · 2024-02 | 매체 리뷰만(2024-02 'Horizon') | ❔ | 10 | | [음악취향Y](http://musicy.kr/?c=review&s=1&gbn=view&ix=8561) |
| 33 | 직사광선 | 없음 · 2024-12 | 못 찾음(우리 데이터: 유재하 본선) | ❔ | 5 | | — |
| 34 | 바림 | 없음 · 2024-04 | VARIM, 2020 결성 둠·스토너 메탈, 2023-07 이전 발매 다수 | ❌ (2023 이전) | 1 | 둠 메탈 | [Korea Times](https://www.koreatimes.co.kr/southkorea/globalcommunity/20230815/metal-band-varim-brings-doom-to-koreas-scene) · [Bandcamp](https://varim.bandcamp.com/album/die-or) · [음악취향Y](http://musicy.kr/?c=review&s=1&gbn=view&ix=8836) |
| 35 | 플라잉독 | 없음 · 2024-02 | 매체 리뷰만(2024-06 '오마주') | ❔ | 3 | | [음악취향Y](http://musicy.kr/?c=review&s=1&gbn=view&ix=8666) |
| 36 | 성현 | 신인 · 2025-09 · **소속 빅히트 · 팬 3,071** | 공연·리뷰('상실의 결실')는 인디 싱어송라이터 성현, 멜론 프로필은 빅히트 신인 5인조 멤버 성현 | ⚠️ **연결 오류** | 4 | | [뉴시스(빅히트 신인 그룹)](https://mobile.newsis.com/view/NISX20250714_0003250159) · [음악취향Y(인디 성현)](http://musicy.kr/?c=review&s=1&gbn=view&ix=9111) |
| 37 | 스위머스 | 없음 · 2024-05 | 매체 리뷰만(2025-11) | ❔ | 4 | | [음악취향Y](http://musicy.kr/?c=review&s=1&gbn=view&ix=9113) |
| 38 | Leaveourtears | 신인 · 2024-10 | 2024-11부터 공연 기록(상상마당·부산·대구) | ✅ | 1 | | [setlist.fm](https://www.setlist.fm/setlists/leaveourtears-7b9422b4.html) |
| 39 | SØHJ | 없음 · 2026-05 | 3호선 버터플라이 전 드러머 서현정의 새 프로젝트, 2026-06 정규 1집(튜나레코드) | ✅ (새 프로젝트 — 멤버는 경력자) | 4 | 일렉트로닉·밴드 | [헤럴드경제](https://biz.heraldcorp.com/article/10783489) |
| 40 | 이토마토 | 없음 · 2024-12 | 못 찾음(우리 데이터: 유재하 본선) | ❔ | 2 | | — |
| 41 | 체인리액션 | 없음 · 2025-03 | 매체 리뷰만(2025-03) | ❔ | 4 | | [음악취향Y](http://musicy.kr/?c=review&s=1&gbn=view&ix=8933) |
| 42 | 턴포아워 | 없음 · 2024-02 | 한국 하드코어 'Turn For Our' 데뷔 정규 기사 있음(날짜·같은 팀 여부 미확인) | ❔ | 2 | 하드코어(추정) | [Unite Asia](https://uniteasia.org/korean-hardcore-band-turn-release-debut-full-length-launch-full-stream) · [음악취향Y](http://musicy.kr/?c=review&s=1&gbn=view&ix=8635) |
| 43 | 캐주얼리커넥티드 | 없음 · 2025-07 | 매체 리뷰만(2025-07) | ❔ | 4 | | [음악취향Y](http://musicy.kr/?c=review&s=1&gbn=view&ix=9034) |
| 44 | 신스네이크 | 없음 · 2024-04 | Synsnake, 2016 데모·EP, 2021 정규 1집, 2025 정규 2집 | ❌ (2016) | 4 | 메탈코어 | [나무위키](https://namu.moe/w/Synsnake) · [Metal Kingdom](https://www.metalkingdom.net/band/synsnake-27305) · [음악취향Y](http://musicy.kr/?c=review&s=1&gbn=view&ix=9117) |
| 45 | 놀플라워 | 없음 · 2024-04 | 2018 EP '비익련리'로 데뷔 | ❌ (2018) | **1 — 180일 신호 0 (휴면)** | 오리엔탈 얼터너티브 | [kprofiles](https://kprofiles.com/?p=457317) · [음악취향Y](http://musicy.kr/?c=review&s=1&gbn=view&ix=8609) |
| 46 | 세기말 | 신인 · 2025-05 | SEKIMAL, 새 록 밴드, 데뷔 싱글 'Break it' | ✅ | 4 | 인디 록 | [The K-Meal](https://thekmeal.com/indie-pick-sekimal/) · [음악취향Y](http://musicy.kr/?c=review&s=1&gbn=view&ix=9360) |
| 47 | 닙아카이브 | 신인 · 2026-03 | 매체 리뷰만(2026-11) | ❔ | 2 | | [음악취향Y](http://musicy.kr/?c=review&s=1&gbn=view&ix=9481) |
| 48 | 이예신 | 신인 · 2025-12 | 못 찾음(우리 데이터: 유재하 본선) | ❔ | 2 | | — |
| 49 | 윤형준 | 없음 · 2024-12 | 못 찾음(우리 데이터: 유재하 본선) | ❔ | 4 | | — |
| 50 | Phase Shifter | 신인 · 2026-03 | 못 찾음 | ❔ | 2 | | — |

집계: 신인 ✅ 13팀 · ❌ 10팀 · ⚠️ 1팀 · ❔ 26팀. 인디 여부는 소속을 찾은 9팀(LOCALHIGH RECORDS·노머시 컴퍼니·불가마싸운드·자체 레이블+PIAS·튜나레코드·Watch Out! Records 등)이 모두 작은 인디 레이블이라 '인디 아님'은 연결 오류인 성현뿐이다.

---

## 5. 남은 일
- '미확인' 26팀은 공개 웹 검색으로는 정보가 없었다. 멜론 프로필 보강(R3)이나 인스타그램 공개 계정(aside로, 23시 이후)으로 2차 확인하면 신인 오류율이 더 정확해진다. 지금 비율(확인된 팀 중 42%)은 **찾기 쉬운 팀(오래 활동해 기록이 쌓인 팀)이 더 잘 확인되는 쪽으로 기울어 있을 수 있다** — 그래서 50팀 전체 기준 '최소 20%'로 읽는 게 안전하다.
- R1을 넣은 뒤 같은 표본으로 다시 상위 50을 뽑아, 새로 들어온 팀을 같은 방법으로 확인하면 규칙 효과를 볼 수 있다.
