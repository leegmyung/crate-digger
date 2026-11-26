# 대화 경과 기록 (Claude Code 세션, 2026-11-23 ~ 11-26)

> 원문 대화가 아니라, Claude가 기억하는 흐름을 단계별로 정리한 것입니다.
> 현재 방향·할 일은 [PROJECT.md](PROJECT.md), 파이프라인 그림은 `docs/pipeline.html`.
> 모든 숫자·아티스트·카탈로그는 **샘플(가상) 데이터**입니다 (좋아요 곡 목록의 곡명·아티스트만 실제 음악).

---

## 전체 흐름 한눈에
| 단계 | 날짜 | 주제 | 결과 |
|---|---|---|---|
| 1 | 11-23 | Bandcamp로 무엇을 할 수 있나 | 데이터 소스·주제 3개 제안 |
| 2 | 11-23 | 판매 대시보드 (주제 1) | SQL 스키마·쿼리 + 대시보드 *Bandcamp Sales Pulse* |
| 3 | 11-23 | 내 음원 취향 기반 추천 가능? | 가능. 청취 기록 추출 방법 조사 |
| 4 | 11-23 | Spotify·멜론·지니·FLO 좋아요 추출 | Spotify API 제한, TuneMyMusic 발견 |
| 5 | 11-23 | TuneMyMusic로 추출 | Spotify·Apple·YouTube Music → CSV 확인 |
| 6 | 11-23 | 추천 프로토타입 | 취향 벡터·세분화·추천 SQL + 대시보드 *Bandcamp Taste Match* |
| 7 | 11-23~24 | Last.fm 태그, 큐레이션, 앨범 상세, 취향 리포트 | 스크립트·대시보드 확장 |
| 8 | 11-24 | Spotify 오픈소스 | Voyager 적용 |
| 9 | 11-24 | 프로젝트 정리 / mod | 요약, 사용량 표시 mod |
| 10 | 11-24 | 파이프라인 시각화 + 피드백 | 파이프라인 페이지 v1 |
| 11 | 11-24~25 | **방향 전환**: 국내·해외 신인 발굴 + 실효성 검증 | Last.fm 보류, 새 파이프라인 |
| 12 | 11-25 | 해외 대안 소스, Pitchfork | 유료화 확인, 대안 정리 |
| 13 | 11-25 | 공증(검증) 소스, 국내 후보 풀 | 헬로루키·튠업 등 리스트, 포크라노스 |
| 14 | 11-25 | 5분 발표 | PDF 8장 |
| 15 | 11-26 | 할 일 정리, GitHub 이전 | zip·문서 정리 |

---

## 1단계 — 주제 탐색
- 요청: bandcamp.com 데이터로 SQL·AI 툴 대시보드를 만들고 싶다. 주제와 데이터 확인.
- 환경: 이 클라우드 컨테이너는 **bandcamp.com 접속이 프록시에서 차단**됨 (웹 페치도 실패). 이후 Last.fm, TuneMyMusic도 차단. → 사용자는 **aside**로 직접 크롤링 가능.
- 제안한 데이터 소스: ① 판매 데이터셋 *The Chaos Bazaar* (components.one, 2020년 판매 100만 건), ② 비공식 판매 피드 `api/salesfeed/1/get`, ③ discover 비공식 API, ④ 앨범 페이지 `data-tralbum` JSON, ⑤ Bandcamp Daily.
- 제안 주제: 1) 글로벌 인디 판매 대시보드(추천), 2) 장르 트렌드·가격 전략, 3) 편집자 선정 효과.

## 2단계 — 판매 대시보드 (주제 1 선택)
- 사용자: 데이터는 aside로 크롤링 가능. SQL·스키마로 대시보드.
- 만든 것
  - `sql/schema.sql`: `stg_salesfeed`(판매 피드 원본) → `dim_country`, `dim_currency`, `dim_artist`, `dim_item`(포맷 분류, URL+유형+설명 유니크), `item_tags`, `fact_sales`, 뷰 `v_sales`(시간·요일·채널·정가 대비 비율)
  - `sql/load.sql`: 정제, 국가 지역 매핑, 통화 환율 역산, 포맷 분류(CASE/LIKE), 태그 분리(재귀 CTE)
  - `sql/queries/01~08`: 주간 KPI, 일별 추이, 요일×시간 히트맵, 국가 Top15, 포맷 믹스, 정가 대비 결제 분포, 아티스트 Top15, 장르 매출
  - `scripts/generate_sample.py`(가상 판매 22,716건, 2026-10-26~11-22), `build_db.py`, `run_queries.py`(결과 JSON에 SQL 원문 포함)
  - 대시보드 *Bandcamp Sales Pulse*: https://claude.ai/artifact/MT4ngSezz1ppy6iJn4YHdf (`dashboard/index.html`)

## 3~5단계 — 취향 기반 추천 아이디어
- 질문: 기존 음원 플랫폼 알고리즘 기반으로 Bandcamp 앨범 추천 가능?
  - 답: 플랫폼 알고리즘 자체는 못 쓰지만 **내 청취 기록**을 가져와 직접 추천 로직을 만들 수 있음.
- 질문: Spotify·멜론·지니·FLO 좋아요로 세분화·추천 서비스? Spotify 좋아요는 공유가 안 됨.
  - Spotify: 개인정보 다운로드(Your Library JSON) 또는 Web API `GET /me/tracks`. 단 2026년 2월부터 개발 모드 Premium 필요·앱당 5명. 확장 승인 기준 높음(2025-05).
  - 멜론·지니·FLO: 공식 API·내보내기 미확인 → 캡처+AI 추출, 웹 복사, 개인정보 열람 청구.
- TuneMyMusic 확인: Spotify·Apple Music·YouTube Music의 **좋아요 곡을 CSV/TXT로 내보내기** 가능, 무료 500곡. 멜론·지니·FLO 지원은 미확인. 자유 텍스트 → 파일 기능 있음.

## 6단계 — 추천 프로토타입 (현재 보류)
- 샘플: 가상 사용자 3명(Spotify 27곡 / Apple Music 25곡 / YouTube Music 22곡, 실제 곡), 손으로 지정한 아티스트 태그, 가상 팬 3,000명 컬렉션.
- `sql/reco/schema_reco.sql`: `raw_tmm_export`, `user_likes`, `ext_artist_tags`, `tag_family`(12개 취향군 매핑), `bc_fan_collection`, `bc_album_detail`
- `sql/reco/reco.sql` 로직
  1. 좋아요 → 주 아티스트·매칭 키 (`load_likes.sql`)
  2. 취향 벡터 = Σ(좋아요 곡 수 × 아티스트 태그), 취향군 가상 태그 `fam:`를 0.5배로 추가, 정규화
  3. 세분화: 12개 취향군 비중, 12% 이상 = 세그먼트. 1위 60% 이상 한 우물형 / 세그먼트 3개 이상 탐험형 / 그 외 두 갈래형
  4. Bandcamp 아티스트 벡터(상품 태그 빈도, 대표 장르 1.0·서브 0.6)
  5. 점수 = **0.55 태그 유사도(코사인) + 0.25 팬 공동구매 + 0.10 상승세 + 0.10 발굴 가치**
  6. 다양성: 취향군당 최대 4팀, 사용자당 12팀. 이유: 가장 닮은 좋아요 아티스트 + 겹치는 태그 2개
- 대시보드 *Bandcamp Taste Match*: https://claude.ai/artifact/JYtChoYG6BGRXQGD6yGexW (`dashboard/reco.html`)

## 7단계 — 확장
- `scripts/fetch_lastfm_tags.py`: Last.fm `artist.getTopTags`, 잡음 태그 제거, 표기 통일, 별칭 파일, 캐시, 초당 4회. 가짜 서버로만 테스트 (Last.fm 접속 차단).
- `scripts/curate.py`: CSV 넣으면 태그 수집 → 추천 → 큐레이션 md를 한 번에.
- 앨범 상세: 커버(생성형), 발매일, 곡 수·재생 시간, 레이블, 지역, 포맷, 서포터 수, 소개문 (`bc_album_detail`).
- 나의 취향 리포트 (`r5_taste_report.sql`): 최애 아티스트, 시그니처 태그, 다양성 지수(엔트로피), 의외의 취향, 닮은 팬 수, 발굴 지수, 알고리즘 기여도.
- Last.fm 설명: 사용자 청취 기록·태그 서비스, 무료 API. 이름 → 태그 "번역기" 역할.

## 8단계 — Spotify 오픈소스
- PyPI 확인: Voyager 2.2.4, Annoy 1.17.3, Pedalboard 0.9.26, Basic Pitch 0.4.0, Luigi 3.8.1, Chartify 5.0.1.
- `scripts/voyager_index.py`: 아티스트 벡터 HNSW 인덱스, SQL 정확 결과 대비 recall@50 96~100%, 검색 0.1~1ms. 최종 추천은 순위가 바뀌므로 후보 K는 200 이상 필요. `bc_similar`(비슷한 아티스트) 생성.
- 확장 후보: Pedalboard(소리 분석, 약관 검토 필요), Luigi(자동화).

## 9단계 — 정리와 mod
- 프로젝트 요약 정리. 채팅창 위 요약 mod(`bandcamp-brief`) → 사용자 요청으로 삭제 → **사용량 표시 mod**(`tools/usage-band`: 컨텍스트 %, 5시간·주간 한도, 비용).

## 10단계 — 파이프라인 시각화 v1과 피드백
- 피드백(당시 추천 구조 기준): ① 추천 평가 지표 없음(팬 컬렉션 hit rate@12 제안), ② 팬 컬렉션 의존도, ③ 태그 어휘 불일치(임베딩), ④ K-pop 사용자 뭉툭함(TF-IDF, 한국 인디 가점), ⑤ 취향 유형 변별력 없음, ⑥ 이름 기반 식별, ⑦ 수동 단계.

## 11단계 — 방향 전환 (현재 방향)
- 사용자 결정
  - **국내/해외 두 갈래**. 해외 = Bandcamp, 국내 기점 미정.
  - **Last.fm 보류**.
  - bandcamp.com/discover 차트 **매일 수집** (Claude Code에서 불가하면 aside).
  - Bandcamp API 연결 가능성 확인.
  - **실효성 검증**: 앨범 YouTube 반응 지표, 타 플랫폼 청취·반응 통계, 타 플랫폼 입점 여부 → 뽑은 데이터를 **단기·중기·장기로 추적**해 결과 분석.
  - 메타데이터 검수, SQL 저장(실무 역량), **Tableau** 시각화.
- 확인한 사실: Bandcamp API는 자기 계정 데이터만 / Bandcamp 약관상 스크래핑 금지 가능성(2차 보도) / YouTube Data API 기본 10,000단위, `videos.list` 1단위.
- 피드백: 비교 그룹 필수, 과거 지표 소급 불가 → 수집 먼저, 아티스트 매칭이 가장 어려움, 국내 기점 후보, 무료 입점 확인 API(Apple·Deezer), Tableau Public은 DB 직접 연결 불가 → PostgreSQL 권장.

## 12단계 — 해외 대안 소스
- Pitchfork: 월 5달러 구독제(비구독자 월 4개 리뷰). 2024년 대규모 해고·GQ 통합. 전직 작가 5명의 **Hearing Things**는 유료. "무료로 새로 만든 곳"은 찾지 못함.
- 대안: MusicBrainz/ListenBrainz(오픈), Hype Machine(API 없음, 순환 구조 비판), 매체 RSS, RateYourMusic·Reddit 제외.

## 13단계 — 공증 소스와 국내 후보 풀
- 사용자 아이디어: **OPCD·헬로루키 같은 공증 프로그램을 검증 요소로** — 미리 발굴한 대상이 나중에 선정되면 대시보드 실효성 검증.
  - 반영: 공증 소스는 후보로 쓰지 않고 정답으로만. 지표 = 적중률·선행 기간·재현율. 백테스트 가능.
- 조사 결과: 헬로루키(월간→연간, 2026 대상 녹이녹), CJ 튠업 27기, 펜타 슈퍼루키(대상 우륵과 풍각쟁이들), 한대음 올해의 신인 우희준, OPCD(도봉구 청년 음악 사업단, 심사 기준 미확인), BBC Sound of 2026(1위 Skye Newman), NPR Tiny Desk Contest 2026(Cure For Paranoia), KEXP 공개 API.
- 사용자: Bandcamp는 https://bandcamp.com/discover/all/vinyl 에 랭킹이 있어 리스트업 가능. 국내는 후보군 기점을 아직 못 찾음.
  - 제안: **포크라노스 장르별 발매 카탈로그**(국내 인디 유통사), Bandcamp 한국 지역 필터, 멜론·벅스 인디 최신(보조).

## 14단계 — 발표
- `docs/slides/신인발굴_대시보드_발표.pdf` (8장, 5분): 표지 / 문제·목표 / 데이터 소스 / 파이프라인 / 검수·SQL / 검증 설계 / 공증 소스·사례 / 다음 단계·위험.

## 15단계 — 할 일과 이전
- 할 일 4단계 정리 → PROJECT.md 7장.
- GitHub: 이전 세션에서는 저장소 연결이 안 돼 업로드하지 못함 → 이후 본인 계정 저장소로 이전.

---

## 환경 메모
- 작업 위치: 클라우드 컨테이너 `/home/user/bandcamp-dashboard` (임시, 사라질 수 있음).
- 프록시 차단 호스트: bandcamp.com, ws.audioscrobbler.com(Last.fm), tunemymusic.com. Google Fonts, PyPI, GitHub API(일부)는 가능.
- claude.ai 페이지(본인만 열람): 파이프라인 https://claude.ai/artifact/WqEbWwkDEH3zqup52SGASN
- DB(`bandcamp.db`)는 제외됨 → PROJECT.md 9장 명령으로 재생성. 추천 DB는 `python3 scripts/generate_reco_sample.py && python3 scripts/build_reco.py`.
