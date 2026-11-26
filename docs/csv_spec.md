# 수집 CSV 형식 정의서 (국내)

> 파이프라인 1단계 "원본 수집"의 약속. aside든 스크립트든 사람이 직접 적든, 이 형식으로 저장하면 그대로 DB에 들어갑니다.
> 기계가 읽는 기준은 `scripts/csv_schema.py`이고, 검사는 `python3 scripts/validate_csv.py <파일>`로 합니다. 칸을 바꿀 때는 두 파일을 같이 고칩니다.

## 공통 규칙

| 규칙 | 내용 |
|---|---|
| 인코딩 | UTF-8 (엑셀에서 저장한 BOM 포함 파일도 됨) |
| 구분 | 쉼표 `,`. 값에 쉼표가 있으면 큰따옴표로 감쌈: `"오후, 세 시"` |
| 첫 줄 | 칸 이름 (아래 표와 똑같이). 순서는 달라도 됨 |
| 파일 이름 | `<테이블>_<수집일>_<소스>.csv` 예: `raw_kr_release_2026-11-26_bugs.csv` |
| 저장 위치 | 실제 수집 파일은 `data/raw/` (공개 저장소에 안 올라감). `data/samples/`는 가상 예시만 |
| 모르는 값 | 빈칸으로 둠. `N/A`, `-`, `없음` 쓰지 않기 |
| 이름 | 페이지에 보이는 그대로 적기 (한/영 병기, 괄호 포함). 정리·통일은 2단계(검수)에서 함 |
| 수정 금지 | 한 번 저장한 파일은 고치지 않음. 다시 받으면 새 파일로 저장 |
| 수집 시각 `collected_at` | `2026-11-26T09:30:00+09:00` (한국 시간, 시간대까지) |
| 날짜 | `2026-11-26`. 일·월을 모르면 `2026-11`, `2026`도 됨 (발매일·발표일만) |
| 수집 방식 `collector` | `aside` / `script` / `manual` |

## 1. `raw_kr_release` — 새 발매 1건 × 참여 팀 1팀 = 1행

여러 팀이 함께 낸 앨범(콜라보)은 팀마다 한 줄씩 적어요. 같은 앨범 주소라도 팀이 다르면 중복이 아니에요.

| 칸 | 필수 | 설명 | 예 |
|---|---|---|---|
| collected_at | ✅ | 수집 시각 | 2026-11-26T09:30:00+09:00 |
| source | ✅ | 소스 코드 (아래) | bugs |
| collector | ✅ | aside / script / manual | aside |
| source_id | | 그 사이트의 앨범 번호 | 7000001 |
| released_at | ✅ | 발매일 | 2026-11-26 |
| artist_text | ✅ | 아티스트명 그대로 | Lumen Garden (루멘가든) |
| artist_source_id | | 그 사이트의 아티스트 번호 (신인 판별·이름 맞추기에 중요) | 500001 |
| title | ✅ | 앨범·곡 제목 | 첫차 |
| release_type | | single / EP / LP / OST / compilation. 미니앨범은 EP, 정규는 LP | EP |
| genre | | 장르, 여러 개면 `\|`로 구분 | shoegaze\|alternative |
| label_text | | 레이블·기획사 | |
| track_count | | 곡 수 | 5 |
| release_url | ✅ | 앨범 상세 주소 | https://music.bugs.co.kr/album/… |

소스 코드: `poclanos` 포크라노스 · `muzeplatform` 뮤즈플랫폼 · `vlending` OGQ 블렌딩 · `mirrorball` 미러볼뮤직 · `bugs` 벅스 · `flo` FLO · `genie` 지니 · `melon` 멜론 · `bandcamp_kr` Bandcamp 한국 · `manual` 직접 입력

## 2. `raw_kr_gig` — 공연 1건 × 출연 팀 1팀 = 1행

한 공연에 3팀이 나오면 3줄. 이름 맞추기를 팀 단위로 하기 위해서예요.

| 칸 | 필수 | 설명 | 예 |
|---|---|---|---|
| collected_at, source, collector | ✅ | 공통 | indiego |
| source_id | | 공연 번호 | e-1001 |
| gig_date | ✅ | 공연 날짜 | 2026-11-28 |
| gig_time | | 시작 시간 (24시간) | 19:30 |
| title | | 공연명 | |
| venue_text | | 공연장 (보이는 그대로, 지역 포함) | 가상홀 (서울 마포) |
| artist_text | ✅ | 출연 팀 1팀 | |
| artist_source_id | | 그 사이트의 아티스트 번호 | a-301 |
| gig_url | ✅ | 공연 상세 주소 | |
| artist_url | | 아티스트 페이지 주소 | |

소스 코드: `indiego` 인디고 · `indistreet` 인디스트릿 · `manual`

## 3. `raw_press` — 기사·큐레이션 1건 × 언급 팀 1팀 = 1행

후보 풀이 아니라 **평론 신호**(점수 가점)로 씁니다.

| 칸 | 필수 | 설명 |
|---|---|---|
| collected_at, source, collector | ✅ | 공통 |
| outlet | ✅ | 매체 이름 (음악취향Y, 킨디라운지 …) |
| published_at | ✅ | 게시일 (날짜 또는 날짜·시간) |
| title | ✅ | 글 제목 |
| url | ✅ | 글 주소 |
| artist_text | ✅ | 언급된 팀 1팀 |
| release_title | | 언급된 앨범·곡 |
| is_pick | ✅ | 추천·선정이면 1, 단순 언급이면 0 |
| pick_label | | 추천 코너 이름 (Single Out, 주간 신보 …) |
| artist_handle | | 태그된 아티스트 인스타 계정 `@abc_123`. 같은 이름의 다른 팀을 구별하는 핵심 열쇠라 보이면 꼭 적기 |
| is_sponsored | | 협찬·광고 글(#제작지원, 유료 홍보 업체)이면 1. 신호에서 빠져요 |

소스 코드: `musicy` 음악취향Y · `rhythmer` 리드머 · `liak` 킨디라운지 · `izm` 이즘 · `weiv` · `visla` · `overtone` · `instagram` (인스타 음악 매거진, outlet에 @계정) · `youtube` · `rss` · `manual`

## 4. `raw_kr_selection` — 지원사업·경연·큐레이션 선정 1건 × 팀 1팀 = 1행 (후보 신호)

작고 이른 단계의 선정 명단이에요. 큰 프로그램의 수상은 여기가 아니라 5번 `raw_outcome`(정답)에 적어요. 두 테이블은 일부러 나눠 뒀어요.

| 칸 | 필수 | 설명 | 예 |
|---|---|---|---|
| collected_at, source, collector | ✅ | 공통 | mapoindie |
| program | ✅ | 후보 프로그램 코드 (아래) | indiscovery |
| round | ✅ | 회차 | 2026 |
| stage | ✅ | applied 응모 / document 서류통과 / challenger / lineup / showcase / selected / final | challenger |
| announced_at | ✅ | 발표일 (월까지만 알아도 됨) | 2026-06 |
| artist_text | ✅ | 팀 이름 | |
| url | ✅ | 근거 주소 | |
| note | | 메모 | 챌린저 24팀 |

소스 코드: `mapoindie` · `kocca` · `gwmf` 강원음악창작소 · `seoulbusking` · `gcon` 경기콘텐츠진흥원 · `ebs` · `contest` 지역 경연 · `rollinghall` · `senggi` · `liveclubday` · `tumblbug` · `manual`

프로그램 코드: `indiscovery` 마포 인디스커버리 · `museon_document` 뮤즈온 서류통과 · `our_musician` 우리 음악인 축제 · `gw_creation` 강원음악창작소 · `seoul_busking` 구석구석라이브 · `regional_contest` 지역 밴드 경연 · `hello_rookie_applicant` 헬로루키 응모 · `indiestance_prelim` 인디스땅스 예선 · `cmyk` 롤링홀 CMYK · `senggi_curation` 생기 큐레이션 · `liveclubday` 라이브클럽데이 · `tumblbug_debut` 텀블벅 첫 음반 펀딩

**같은 프로그램 규칙:** 앞 단계를 후보로 쓴 팀은 같은 프로그램의 정답 결과를 적중으로 세지 않아요. 연결표는 `scripts/csv_schema.py`의 `SAME_PROGRAM`에 있어요.
- `hello_rookie_applicant` → `hello_rookie`, `hello_rookie_year` 제외
- `museon_document` → `museon_final` 제외
- `indiestance_prelim` → `indiestance` 제외

## 5. `raw_outcome` — 공증(정답) 발표 1건 × 팀 1팀 = 1행

**후보를 고르거나 점수를 매길 때 절대 쓰지 않습니다.** 우리가 먼저 찾았는지 맞춰 보는 정답지예요.

| 칸 | 필수 | 설명 | 예 |
|---|---|---|---|
| collected_at, source, collector | ✅ | 공통 (source는 manual / aside) | |
| program | ✅ | 프로그램 코드 (아래) | hello_rookie |
| round | ✅ | 회차 | 2026-05, 27기 |
| announced_at | ✅ | 발표일 (월까지만 알아도 됨) | 2026-05-28 |
| result | ✅ | selected / winner / finalist / shortlist / longlist / nominee / featured(매체 소개) | selected |
| artist_text | ✅ | 팀 이름 | |
| url | ✅ | 근거 주소 | |
| note | | 메모 | 월간 선정 |

프로그램 코드: `hello_rookie` 헬로루키 월간 · `hello_rookie_year` 올해의 헬로루키 · `cj_tuneup` CJ 튠업 · `penta_superrookie` 펜타 슈퍼루키 · `kma_rookie` 한국대중음악상 신인 · `opcd` OPCD · `izm_rookie` 이즘 올해의 신인 · `musicy_rookie` 음악취향Y 올해의 신인 · `rhythmer_award` 리드머 어워드 · `gg_indiestance` 경기 인디스땅스 · `bbc_sound_of` · `tiny_desk` · `museon_final` 뮤즈온 최종 · `indiestance` 인디스땅스 결선 · `yoojaeha` 유재하 음악경연대회 · 매체 소개(정답 2등급, 협찬 제외): `media_izm` · `media_bandwagon` · `media_nme` · `media_esquire`

## aside에 붙여 넣는 작업 지시문 (예: 벅스)

```
https://music.bugs.co.kr/newest/album/nindie 를 열어 첫 페이지만 읽어 줘.
로그인·구매·좋아요 등 계정 상태를 바꾸는 행동은 하지 마. 페이지를 빠르게 여러 번 넘기지 마.
각 앨범을 아래 칸으로 CSV 한 줄씩 만들어 줘. 첫 줄은 칸 이름 그대로.
collected_at,source,collector,source_id,released_at,artist_text,artist_source_id,title,release_type,genre,label_text,track_count,release_url
- collected_at: 지금 시각, 2026-11-26T09:30:00+09:00 형식
- source: bugs / collector: aside
- source_id, artist_source_id: 앨범·아티스트 링크 주소의 숫자
- release_type: 싱글=single, 미니·EP=EP, 정규=LP (모르면 빈칸)
- 모르는 값은 빈칸, 이름은 보이는 그대로. 값에 쉼표가 있으면 큰따옴표로 감싸기
파일 이름: raw_kr_release_<오늘 날짜>_bugs.csv
```

받은 파일은 `data/raw/`에 넣고 `python3 scripts/validate_csv.py data/raw/<파일>`로 검사해요.
