# 국내·해외 신인 발굴 대시보드 — 프로젝트 노트

> 매일 후보를 모으고, 오래 지켜보고, 우리 선택이 맞았는지 데이터로 확인한다.
>
> 대화 흐름 전체는 [HISTORY.md](HISTORY.md). 이 문서는 Claude Code 세션(2026-11-23 ~ 11-26)에서 정리한 방향, 결정 사항, 조사 결과, 할 일을 모은 것입니다.
> 대화 원문은 포함되지 않았습니다. 2026-11-26 기준.

## 1. 목표
| 목표 | 내용 |
|---|---|
| 발굴 | 아직 작지만 신호가 있는 신인을 매일 자동으로 찾기 |
| 검수 | 플랫폼마다 다른 이름·표기·메타데이터를 하나로 맞추기 (메타데이터 검수) |
| 검증 | 선정한 아티스트가 실제로 컸는지 단기·중기·장기로 추적해 실효성 검증 |
| 역량 | PostgreSQL 저장, SQL 분석, Tableau 지표 시각화 |

핵심 질문: **"우리가 먼저 찾은 신인이, 나중에 정말 떴는가? 몇 달 먼저 찾았는가?"**

## 2. 파이프라인 (자세한 그림: `docs/pipeline.html`, 발표: `docs/slides/`)
```
해외  Bandcamp discover 랭킹 (매일) + KEXP API + MusicBrainz + 매체 RSS(평론 신호)  ─┐
국내  인디 신보 풀: 유통사 카탈로그(포크라노스) + Bandcamp 한국 + 멜론·벅스 + 웹진   ─┤
                                                                                     ▼
공통  1 원본 저장 (수집일별, 수정 금지)
      2 메타데이터 검수·매칭 (MusicBrainz 연결, 한/영 표기, 중복·누락, 수동 검수 대기열)
      3 반응·입점 지표 매일 스냅샷 (YouTube 조회수·좋아요·댓글·구독자 / Spotify·Apple·Deezer·멜론 입점)
      4 발굴 선정 (점수 규칙) + 비교 그룹 무작위 추출 → 관찰 목록, T0 기록
      5 추적: T+14 / T+90 / T+180 / T+365
      6 검증: 성장 배수, 공증 적중률, 선행 기간, 재현율 (선정 vs 비교)
      7 Tableau 4개 보드: 발굴 / 관찰 목록 / 검증 결과 / 데이터 품질
```

### 검증 설계
- **비교 그룹**: 같은 시기·같은 후보 풀에서 선정되지 않은 아티스트를 무작위 추출. 없으면 실효성 주장 불가.
- **성공 기준은 추적 시작 전에 문서로 고정** (예: 90일 조회수 증가 중앙값이 비교 그룹의 1.5배 이상).
- **공증(정답) 소스는 후보·점수에 쓰지 않는다.** 선정일 이후 발표된 결과만 적중으로 집계.
- 지표: 성장 배수(T0 대비), 적중률(선정 중 나중에 공증된 비율), 선행 기간(선정일 → 공증 발표일), 재현율(공증 선정자 중 미리 찾은 비율).
- **과거 반응 지표는 소급 불가** → 수집을 먼저, 지금부터 매일 쌓기.
- **백테스트**: 과거 공증 회차 목록 + 과거에 남는 신호(발매일, 큐레이션 언급, 평론)로 규칙을 미리 검증 가능.

## 3. 소스 목록

### 후보 풀 (공증 전)
| 갈래 | 소스 | 방법 | 비고 |
|---|---|---|---|
| 해외 | Bandcamp discover 랭킹 (예: https://bandcamp.com/discover/all/vinyl, 포맷·장르·지역 필터) | aside 크롤링, 매일 | 메인. 약관 확인 필요 (아래 4) |
| 해외 | KEXP 공개 API (https://api.kexp.org/v2/plays/) | API | 편성 곡·레이블·발매일·DJ 코멘트. 이용 조건 확인 |
| 해외 | MusicBrainz / ListenBrainz | 오픈 API | 신보 목록, 정제·매칭 기준 |
| 해외 | 매체 RSS (Pitchfork, Stereogum, Bandcamp Daily 등) | RSS | 평론 신호. 선정 여부만 기록 |
| 해외 | Hype Machine | 크롤링 (API 없음) | 보조 |
| 국내 | 포크라노스 장르별 발매 목록 (예: https://poclanos.com/genre/alternative/) | aside | **메인 후보 (미확정)**. 다른 유통사 추가 검토 |
| 국내 | Bandcamp 한국 아티스트 (지역 필터) | 해외 수집기 재사용 | 보조 |
| 국내 | 멜론·벅스 인디 장르 최신 | aside | API 없음, 약관 확인 |
| 국내 | YouTube 인디 라이브 채널 | YouTube Data API | 반응 지표 겸용 |
| 국내 | 킨디라운지(한국음악레이블산업협회) 주간 신보, 웹진 | aside/수동 | 평론·큐레이션 신호 |

### 공증(검증) 소스
| 갈래 | 등급 | 소스 | 2026 확인 내용 |
|---|---|---|---|
| 국내 | 1 | 헬로루키 (EBS 스페이스 공감) | 월간 선정 → 연말 올해의 헬로루키. 2026 대상 녹이녹, 2,028팀 지원 |
| 국내 | 1 | CJ 튠업 (CJ문화재단) | 27기 6팀, 148:1 (4월 발표) |
| 국내 | 1 | 펜타 슈퍼루키 (인천펜타포트) | TOP6, 대상 우륵과 풍각쟁이들 (5월) |
| 국내 | 1 | 한국대중음악상 올해의 신인 | 2026 수상 우희준 |
| 국내 | 2 | OPCD (도봉구 청년 음악 사업단) | 심사 기준 미확인 |
| 국내 | 2 | 킨디라운지, 원 콘쿨(민트페이퍼), 웹진 이달의 앨범 | 큐레이션 |
| 해외 | 1 | BBC Radio 1 Sound of | 업계 패널 170명+, 2026 1위 Skye Newman |
| 해외 | 1 | NPR Tiny Desk Contest | 2026 우승 Cure For Paranoia |
| 해외 | 2 | Pitchfork Best New Music (유료화), KEXP 편성 | |
| 해외 | 확인 필요 | NME 100, FADER Gen F, Stereogum Band to Watch, SXSW, 페스티벌 신인 무대 | |

실제 사례 (공증 흐름 근거):
- 녹이녹: 2026년 5월 헬로루키 → 11월 올해의 헬로루키 대상
- 피치트럭 하이재커스: CJ 튠업(4월) + 펜타 슈퍼루키 TOP6(5월) 중복 선정

## 4. 조사 결과 (확인한 사실)
- **Bandcamp API** (https://bandcamp.com/developer): 신청제, 본인이 관리하는 밴드·레이블 계정 데이터만(계정, 판매 리포트, 굿즈 주문). discover·카탈로그 데이터 없음 → 크롤링 필요.
- **Bandcamp 약관**: Acceptable Use 정책이 스크래핑·데이터 마이닝을 금지한다는 2차 보도 있음 (원문 미확인). 봇 차단도 있음. → 원문 확인 후 공개 차트만, 하루 1회, 소량, 원본 비공개로 범위 제한.
- **YouTube Data API**: 기본 하루 10,000 단위. `videos.list`는 호출당 1단위(영상 50개까지). `search.list`는 비쌈(호출당 100단위로 알려짐, 공식 표 확인). → 채널·영상 ID는 처음 한 번만 검색, 이후 ID로 통계 조회.
- **Spotify Web API**: 2026년 2월부터 개발 모드는 Premium 필요, Client ID당 사용자 5명, 엔드포인트 축소. 확장 승인 기준 높음. → 보조로만.
- **Pitchfork**: 월 5달러 구독제, 비구독자 월 4개 리뷰. 전직 에디터들의 Hearing Things도 유료.
- **TuneMyMusic**: Spotify·Apple Music·YouTube Music 좋아요를 CSV로 내보내기 가능 (무료 500곡). 취향 추천 기능용 — 현재 보류.
- **Tableau Public은 DB 직접 연결 불가** → CSV/Google Sheets 내보내기. DB 직접 연결은 Desktop (학생 라이선스 확인).
- **Last.fm**: 보류.

## 5. 결정 사항
- 국내·해외 두 갈래로 진행
- 해외 메인 = Bandcamp discover 랭킹 (aside로 매일 수집)
- 공증 프로그램을 검증 지표로 사용 (헬로루키, OPCD 등)
- Last.fm, 취향 기반 추천(Taste Match) 보류
- 저장소 PostgreSQL 권장 (현재 코드는 SQLite)
- **국내부터 진행** (2026-11-26)
- 관찰용 웹 화면 = **GitHub Pages(공개)**, `docs/index.html` 진행판. 원본 수집 파일은 비공개, 공개 페이지에는 이름·제목·발매일·링크·공개 숫자·계산 결과만
- 추적 = 관찰 목록 전부 하루 1번 지표 저장, T+14/90/180/365는 저장값으로 계산 (GA 같은 방문자 분석은 불필요)
- 파이프라인에 **1.5단계 '신인 판별'** 추가 (어느 목록에도 데뷔작 표시가 없음)
- 국내 후보 풀 = **가능한 곳 전부** (포크라노스, 뮤즈플랫폼, OGQ, 미러볼, 벅스, FLO, 지니, 멜론, Bandcamp 한국, 인디고, 인디스트릿, 킨디라운지 등). robots.txt 차단 4곳(벅스·FLO·지니·인디스트릿)은 하루 1번 aside로 천천히, 원본 비공개
- 신인 기준 = 첫 발매 2년 이내 & 발매 5개 이하, 또는 발매 없이 공연만 있는 팀
- 웹진은 후보 풀이 아니라 평론 신호(가점)로만
- 국내 후보 소스 22곳 조사 결과(하루 건수, 신인 비중, robots 허용 여부)는 `docs/data/board.json` / 진행판 '국내 후보 소스 비교'

## 6. 아직 정할 것
1. 국내 후보 메인 소스: 포크라노스 카탈로그로 할지, 다른 유통사 추가할지
2. 헬로루키 월간 선정 위치: 검증 쪽(추천) vs 후보 쪽
3. 공증 소스 목록·등급 확정 (OPCD 2등급 여부)
4. Tableau Public vs Desktop
5. Bandcamp 약관 원문 확인 후 수집 범위

## 7. 할 일
### 1단계 — 수집 시작 (가장 급함)
- [ ] Bandcamp 약관 원문 확인 → 수집 범위 결정 (사용자)
- [ ] aside: Bandcamp discover 랭킹 매일 (바이닐·디지털·카세트, 한국 지역 포함) (사용자)
- [ ] aside: 포크라노스 장르별 신보 (사용자)
- [ ] aside용 CSV 형식 정의서
- [ ] PostgreSQL 스키마 (raw_gl_chart, raw_kr_release, raw_press, raw_outcome, artist, release, artist_xref, qa_issue, metric_snapshot, watchlist, outcome_event)
- [ ] CSV → DB 적재 스크립트
- [ ] YouTube Data API 키 발급 (사용자) → 매일 지표 수집 스크립트
- [ ] KEXP API 수집 스크립트

### 2단계 — 검수·공증 데이터
- [ ] MusicBrainz 연결 + 아티스트 매칭 (신뢰도, 한/영 표기)
- [ ] 검수 규칙 SQL + 수동 검수 대기열
- [ ] 공증 소스 과거 회차 목록 수집 (헬로루키 월간·연간, CJ 튠업, 펜타 슈퍼루키, 한대음 신인, BBC Sound of, Tiny Desk)
- [ ] 타 플랫폼 입점 확인 (Apple Music, Deezer 공개 검색)

### 3단계 — 선정 규칙·백테스트
- [ ] 발굴 점수 규칙 (신규성, 차트 상승, 평론 신호, 아직 작은 규모)
- [ ] 성공 기준 문서 고정 (사용자)
- [ ] 비교 그룹 추출 SQL, 관찰 목록 등록
- [ ] 백테스트 (과거 공증 회차)

### 4단계 — 추적·검증·Tableau
- [ ] v_cohort_growth (T0, T+14, T+90, T+180)
- [ ] v_validation (적중률, 선행 기간, 재현율)
- [ ] Tableau용 내보내기
- [ ] Tableau 4개 보드 (발굴, 관찰 목록, 검증, 데이터 품질)

## 8. 저장소 구성
| 경로 | 내용 | 상태 |
|---|---|---|
| `PROJECT.md` | 이 문서 (방향·결정·할 일) | 현재 |
| `docs/index.html`, `docs/data/board.json` | 진행판 (GitHub Pages): 단계 상태, 빈틈, 후보 소스 비교 | 현재 |
| `docs/pipeline.html` | 파이프라인 시각화 페이지 | 현재 |
| `docs/slides/` | 5분 발표 슬라이드 (HTML, PDF 8장) | 현재 |
| `sql/schema.sql`, `sql/load.sql`, `sql/queries/` | Bandcamp 판매 스타 스키마·적재·집계 쿼리 (SQLite) | 재사용 예정 |
| `scripts/build_db.py`, `run_queries.py`, `generate_sample.py` | 판매 데이터 파이프라인, 가상 샘플 생성 | 재사용 예정 |
| `dashboard/index.html` | 판매 대시보드 페이지 원본 | 참고 |
| `sql/reco/`, `scripts/*reco*`, `curate.py`, `fetch_lastfm_tags.py`, `dashboard/reco.html` | 취향 기반 추천 프로토타입, Last.fm 수집 | **보류** |
| `scripts/voyager_index.py` | Spotify Voyager 유사도 검색 | 보류 (확장용) |
| `data/` | 가상 샘플 데이터 (실제 데이터 아님) | 샘플 |
| `out/` | 대시보드용 쿼리 결과 JSON | 샘플 |
| `tools/usage-band/` | Claude Code 사용량 표시 mod | 개발 도구 |
| `README.md` | 예전 단계(판매 대시보드·취향 추천) 사용법 | 참고 |

claude.ai 대시보드 링크 (본인만 열람 가능):
- 파이프라인: https://claude.ai/artifact/WqEbWwkDEH3zqup52SGASN
- Bandcamp Sales Pulse: https://claude.ai/artifact/MT4ngSezz1ppy6iJn4YHdf
- Bandcamp Taste Match (보류): https://claude.ai/artifact/JYtChoYG6BGRXQGD6yGexW

## 9. 매일 수집 (국내)
```bash
source .venv/bin/activate
python3 scripts/collect_poclanos.py            # 포크라노스 최근 3일 → data/raw/ (비공개)
python3 scripts/validate_csv.py data/raw/*.csv # 형식 검사 (aside로 받은 파일도)
python3 scripts/build_site_data.py             # 진행판 공개 데이터 docs/data/collect.json
python3 -m unittest discover -s tests          # 테스트
```
형식은 `docs/csv_spec.md`. 진행판: https://leegmyung.github.io/crate-digger/

## 10. 다시 만들기 (예전 판매 대시보드)
```bash
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt   # 처음 한 번
python3 scripts/generate_sample.py data/sample_salesfeed.csv   # 가상 판매 샘플 (선택)
python3 scripts/build_db.py data/sample_salesfeed.csv           # bandcamp.db 생성
python3 scripts/run_queries.py                                  # out/*.json
```
