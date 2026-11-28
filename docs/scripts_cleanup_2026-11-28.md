# 파이썬 스크립트 미사용 파일·함수·중복 유틸 점검 보고 (2026-11-28)

- **점검 범위**: `scripts/*.py` (118개, `__init__.py` 제외) + `scripts/*.sh` (5개) = **총 123개**
- **대조 대상**: `scripts/daily_run.sh`, `scripts/build_app_extras.sh`, `scripts/refresh_analyses.sh`, `.github/workflows/*`, `README.md`('손으로 가끔 돌리는 수집기'·'손으로 다시 만들기'·'예전 단계'), `tests/**/*.py` (154개)
- **기준 시점**: 2026-11-28 17:55 (기존 파일 수정 없음, AST 정적 분석 + 비주석 셸 호출 그래프 기준)
- **요약**
  - **매일 실행(`daily_run.sh`)·CI 도달 스크립트**: **84개** / **미도달 스크립트**: **39개**
    - `README.md` 문서화된 수동 실행: **5개** (`collect_gigs_history.py` 포함; `README.md:145`의 나머지 5개 수집기는 현재 `daily_run.sh`로 편입 완료)
    - `scripts/refresh_analyses.sh` 일괄 분석 묶음 전용: **7개**
    - 예전 Bandcamp 프로토타입 (`tests/` 0건): **8개** (총 1,084줄 — 정리·아카이브 최우선 후보)
    - `daily_run.sh`·`refresh_analyses.sh`·`README.md` 모두 미등재(수동 보강/일회성 점검, `tests/` 존재): **19개**
  - **완전 미사용 최상위 함수 (내부 0 · 다른 스크립트 0 · 테스트 0)**: **1개** (`scripts/collect_regional_gigs.py:78 def _iso`)
  - **`scripts/` 미호출 · `tests/`에서만 호출되는 함수**: **8개**
  - **중복 유틸 묶음**: **11개 묶음** (`write_csv` 17곳, `_read_csv` 10곳, `load_state`/`save_state` 7곳, `KST` 20곳, `USER_AGENT` 11곳, `load_env`·`plus_months`·`years_before`·`wilson`·`to_kst` 등)

---

## 1. `daily_run.sh`·CI에서 호출되지 않는 스크립트 (39개)

### 1-1. `README.md`에 명시된 수동 실행 스크립트 (5개 — 유지 대상)

| 파일 | 줄 수 | README 근거 | 테스트 | 역할 |
|---|---:|---|---|---|
| `scripts/collect_gigs_history.py` | 402 | `README.md:145` ('손으로 가끔 돌리는 수집기') | `test_collect_gigs_history.py` | 인디스트릿 지난 공연 채우기 |
| `scripts/build_data_dictionary.py` | 254 | `README.md:158` ('손으로 다시 만들기') | `test_build_data_dictionary.py` | `docs/data_dictionary.md` 생성 |
| `scripts/check_links.py` | 65 | `README.md:159` ('손으로 다시 만들기') | `test_check_links.py` | 마크다운 상대 링크 검사 |
| `scripts/export_tableau.py` | 100 | `README.md:156` ('손으로 다시 만들기') | `test_export_tableau.py` | Tableau CSV 추출 |
| `scripts/install_daily.sh` | 36 | `README.md:129` (매일 실행 스케줄 등록) | — | launchd/cron 매일 실행 설치 |

> **README 메모**: `README.md:145` '손으로 가끔 돌리는 수집기'에 적힌 나머지 5개(`collect_webzines`·`collect_ig_artists`·`collect_ssm_shows`·`collect_trackzero`·`collect_hiphople`)는 현재 `scripts/daily_run.sh`에서 자동 호출되고 있어(`collect_hiphople --backfill` 옵션만 수동) 위 목록에서 제외했습니다.

### 1-2. `scripts/refresh_analyses.sh` 일괄 분석 묶음 전용 (7개 — 유지 대상)

`daily_run.sh`에서는 안 부르지만 `scripts/refresh_analyses.sh:11`의 `STEPS=(...)` 배열이 직접 실행합니다(`score_model.py`는 `daily_run.sh` 도달이라 제외).

| 파일 | 줄 수 | 호출처 / 테스트 | 역할 |
|---|---:|---|---|
| `scripts/candidate_audit.py` | 225 | `refresh_analyses.sh:11` / `test_candidate_audit.py` | 후보 상위 중 비대상 팀 점검 |
| `scripts/debut_cohort.py` | 114 | `refresh_analyses.sh:11` / `test_scorecard_debut.py` | 데뷔 코호트 성적표 (`docs/debut_cohort.md`) |
| `scripts/discovery_stage.py` | 300 | `refresh_analyses.sh:11` / `test_discovery_stage.py` | 발굴 단계·모멘텀 성적표 |
| `scripts/genre_bias.py` | 773 | `refresh_analyses.sh:11` / `test_genre_bias.py` | 장르별 편향 점검 (`docs/genre_bias.md`) |
| `scripts/missed_analysis.py` | 379 | `refresh_analyses.sh:11`, `rule_leakage.py` / `test_missed_analysis.py` | 놓친 팀 분석 (`docs/missed_analysis.md`) |
| `scripts/rule_leakage.py` | 281 | `refresh_analyses.sh:11` (`README` 본문 연결) / `test_rule_leakage.py` | 후보 규칙 시점 누수 점검 |
| `scripts/same_house.py` | 292 | `refresh_analyses.sh:11` (`README` 본문 연결) / `test_same_house.py` | 같은 집안 효과 점검 |

### 1-3. 예전 Bandcamp 프로토타입 단계 — `daily_run.sh`·`tests/` 0건 (8개, 총 1,084줄 — 정리 최우선 후보)

`README.md:170` `## 예전 단계 (참고용)`에 기록된 초기 판매 대시보드·추천 프로토타입용 스크립트로, 현행 파이프라인·CI·테스트 어디서도 호출되지 않습니다.

| 파일 | 줄 수 | 다른 스크립트 호출처 | 테스트 | 역할 |
|---|---:|---|---|---|
| `scripts/build_db.py` | 45 | 없음 | 0건 | Bandcamp 크롤 CSV → SQLite 구축 |
| `scripts/build_reco.py` | 117 | `curate.py`만 import | 0건 | Bandcamp 추천 인덱스 구축 |
| `scripts/curate.py` | 108 | 없음 | 0건 | Bandcamp 좋아요 기반 큐레이션 |
| `scripts/fetch_lastfm_tags.py` | 258 | `curate.py`만 import | 0건 | Last.fm 태그 수집 |
| `scripts/generate_reco_sample.py` | 237 | 없음 | 0건 | 추천 프로토타입 가상 샘플 생성 |
| `scripts/generate_sample.py` | 190 | 없음 | 0건 | Bandcamp 판매 피드 가상 샘플 생성 |
| `scripts/run_queries.py` | 39 | 없음 (`run_pg_queries.py` 독스트링 언급만) | 0건 | SQLite 쿼리 실행 |
| `scripts/voyager_index.py` | 90 | 없음 | 0건 | Spotify Voyager 벡터 검색 |

### 1-4. `daily_run.sh`·`refresh_analyses.sh`·`README.md` 모두 미등재 (19개, 모두 `tests/` 존재)

단위테스트가 붙어 있어 삭제 시 대응 테스트도 함께 검토해야 합니다. 성격상 **수동 운영/보강 도구(9개)**와 **일회성 점검·실험·시안(10개)**으로 나뉩니다.

**수동 운영 · 데이터 보강 도구 (9개)**

| 파일 | 줄 수 | 호출처 / 테스트 | 역할 |
|---|---:|---|---|
| `scripts/add_missing_venues.py` | 347 | 없음 / `test_add_missing_venues.py` | 미등록 공연장 마스터 항목 생성 |
| `scripts/geocode_venues.py` | 227 | `add_missing_venues.py` / `test_geocode_venues.py` | 공연장 지도 좌표(lat·lon) 부여 |
| `scripts/build_kr_map.py` | 118 | 없음 / `test_build_kr_map.py` | 시·도 경계 `kr_sido.json` 생성 |
| `scripts/collect_festival_lineups.py` | 126 | 없음 / `test_festival_lineups.py` | 국내 페스티벌 라인업 → 공연 원본 CSV |
| `scripts/collect_regional_audit.py` | 150 | 없음 / `test_collect_regional_audit.py` | 지방 공연장 최근 2년 기록 점검 |
| `scripts/followers.py` | 135 | 없음 / `test_followers.py` | 팔로워 30일 변화 뼈대 (매일 실행 편입 대기) |
| `scripts/followers_spotify_weekly.py` | 138 | 없음 / `test_followers_spotify_weekly.py` | 스포티파이 팔로워 주 1회 수집 |
| `scripts/profile_queue.py` | 143 | 없음 / `test_profile_queue.py` | 프로필 보강 대기열 생성 |
| `scripts/sql_to_bigquery.py` | 169 | 없음 / `test_sql_to_bigquery.py` | PostgreSQL → BigQuery SQL 변환 |

**일회성 분석 · 감사 · 시안 스크립트 (10개)**

| 파일 | 줄 수 | 호출처 / 테스트 | 역할 |
|---|---:|---|---|
| `scripts/backtrace.py` | 232 | 없음 / `test_backtrace.py` | 정답 팀 선행 신호 역추적 |
| `scripts/build_design_mocks.py` | 230 | 없음 / `test_build_design_mocks.py` | 초기 디자인 시안(`docs/design/mock_*.html`) 데이터 주입 |
| `scripts/dormant_check.py` | 191 | `recency_lab.py` / `test_dormant_check.py` | 휴면 의심 팀 점검 |
| `scripts/festival_outcome_test.py` | 269 | 없음 / `test_festival_outcome_test.py` | 페스티벌 메인 무대 시험용 정답 B 실험 |
| `scripts/identity_audit.py` | 346 | 없음 / `test_identity_audit.py` | 팀 신원 중복·오매칭 점검 |
| `scripts/live_sessions.py` | 411 | 없음 / `test_live_sessions.py` | 라이브 세션 채널 출연 평가 |
| `scripts/newcomer_audit.py` | 150 | 없음 / `test_newcomer_audit.py` | 데뷔 5년 초과 기성 팀 점검 |
| `scripts/recency_lab.py` | 225 | 없음 / `test_recency_lab.py` | 최근 1·2년 한정 피처 실험 |
| `scripts/score_leak_audit.py` | 283 | 없음 / `test_score_leak_audit.py` | 점수 누수 감사 |
| `scripts/similar_validate.py` | 334 | 없음 / `test_similar_teams.py`, `test_similar_validate.py` | 비슷한 팀 SQL 유사도 검증 |

---

## 2. 안 쓰는 함수 (`scripts/*.py` AST 전수 검사)

### 2-1. 완전 미사용 최상위 함수 (내부 0 · 다른 스크립트 0 · 테스트 0, 1개)

| 파일 | 줄 | 함수 | 근거 |
|---|---:|---|---|
| `scripts/collect_regional_gigs.py` | 78 | `def _iso(text: str) -> str` | 바로 아래 `parse_nurirock_list`가 직접 `"-".join(dates[0])`를 사용해 `_iso`는 선언 외 `scripts/`·`tests/` 전체 0건 |

### 2-2. `scripts/` 내부 호출 0건 · `tests/`에서만 호출되는 함수 (8개 — 테스트 유지 시 삭제 주의)

| 파일 | 줄 | 함수 | 참조 테스트 |
|---|---:|---|---|
| `scripts/collect_artists.py` | 142 | `melon_id_from_href()` | `test_collect_artists.py` |
| `scripts/collect_moonlight_walk.py` | 137 | `parse_title()` | `test_collect_moonlight_walk.py` |
| `scripts/fan_history.py` | 67 | `fans_at()` | `test_fan_history.py` |
| `scripts/genre_fill.py` | 177 | `evaluate()` | `test_genre_fill.py` |
| `scripts/normalize.py` | 79 | `platforms_seen()` | `test_normalize.py` |
| `scripts/preview_match.py` | 64 | `deezer_pick()` | `test_preview_match.py` |
| `scripts/score_tune.py` | 78 | `weighted_auc()` | `test_score_tune.py` |
| `scripts/score_tune.py` | 154 | `hits_at_k()` | `test_score_tune.py` |

---

## 3. 같은 일을 하는 중복 유틸 (11개 묶음)

| # | 역할 | 중복 위치 (파일:줄) | 현황 및 통합 제안 |
|---:|---|---|---|
| 1 | **CSV 쓰기 (`write_csv` / `_write_csv`)** | **17개 파일**: `collect_artists.py:169`, `collect_festival_lineups.py:99`, `collect_gigs.py:217`, `collect_ig_artists.py:218`, `collect_insta.py:193`, `collect_platforms.py:226`, `collect_poclanos.py:122`, `collect_regional_gigs.py:183`, `collect_selection.py:197`, `collect_spotify.py:295`, `collect_ssm_shows.py:276`, `collect_webzines.py:392`, `event_stars.py:265`, `export_lab_data.py:750`, `export_video_momentum.py:67`, `lineup_roles.py:179`, `newcomer.py:209` | UTF-8 `csv.DictWriter` + `parent.mkdir` 패턴이 17곳에 복붙됨. 공용 `scripts/io_utils.py` 등에 `write_csv(path, rows, fields)` 1개로 통합 가능 |
| 2 | **CSV 읽기 (`_read_csv` / `read_csv` / `load_csv`)** | **10개 파일**: `artist_xref.py:888`, `build_alerts.py:531`, `build_design_mocks.py:117`, `collect_videos.py:520`, `data_checks.py:646`, `event_stars.py:292`, `export_excel.py:120`, `genre_seen.py:202` (`_read_csvs`), `score_model.py:725`, `venue_profiles.py:89` | `utf-8-sig` / `utf-8` `csv.DictReader` + 파일 부재 시 `[]` 반환 패턴 반복 |
| 3 | **수집 상태 JSON 읽기·쓰기 (`load_state` / `save_state`)** | **7개 수집기(14함수)**: `collect_gigs_history.py:209,217`, `collect_hiphople.py:217,225`, `collect_musicbrainz.py:183,191`, `collect_spotify_collabs.py:214,221`, `collect_superrookie.py:178,186`, `collect_trackzero.py:118,136`, `collect_videos.py:110,117` | `data/raw/state/*.json` 읽기/쓰기(없으면 기본 dict, 저장 시 `mkdir` + `ensure_ascii=False`) 패턴이 동일 |
| 4 | **KST 시간대 상수 (`timezone(timedelta(hours=9))`)** | **20개 파일**: `build_dashboard_data.py:32`, `build_site_data.py:30`, `collect_artists.py:58`, `collect_festival_lineups.py:32`, `collect_gigs.py:32`, `collect_ig_artists.py:41`, `collect_indistreet_sns.py:38`, `collect_insta.py:31`, `collect_moonlight_walk.py:44`, `collect_platforms.py:36`, `collect_poclanos.py:29`, `collect_regional_gigs.py:44`, `collect_selection.py:32`, `collect_spotify.py:41`, `collect_ssm_shows.py:34`, `collect_videos.py:52`, `collect_webzines.py:45`, `daily_note.py:25`, `newcomer.py:33`, `run_pg_queries.py:23` | `KST = timezone(timedelta(hours=9))` 공용 상수 1곳으로 통합 가능 |
| 5 | **날짜 계산·변환 헬퍼 (3소묶음)** | • **UTC `...Z` → KST**: `collect_gigs.py:134` (`_to_kst`), `collect_gigs_history.py:161` (`to_kst`), `collect_webzines.py:73` (`to_kst_date`)<br>• **월 더하기 (`min(d.day, 28)`)**: `same_house.py:62` (`plus_months`), `source_roles_doc.py:70` (`_plus_months`)<br>• **연도 빼기 (윤년 처리)**: `recency_lab.py:48` (`years_before`), `rule_leakage.py:39` (`years_before`) | 세 소묶음 모두 정규식·구현이 줄 단위로 동일 |
| 6 | **`USER_AGENT` / `UA` 상수** | **11개 파일**: `collect_poclanos.py:28`, `collect_regional_gigs.py:45`, `collect_selection.py:33`, `collect_ssm_shows.py:35`, `collect_webzines.py:44` (`gigle-research/0.1 ...`), `collect_itunes.py:47`, `collect_musicbrainz.py:40` (`indie-scene-research/0.1`), `collect_gigs.py:301`, `collect_indistreet_sns.py:42`, `geocode_venues.py:38`, `fetch_lastfm_tags.py:46` (`UA`) | 동일한 프로젝트 수집기인데 UA 문자열이 4~5종으로 흩어져 있음. 공용 상수 1곳(+외부 API용 1종)으로 통일 가능 |
| 7 | **HTTP `urllib` GET 헬퍼** | **8개 파일**: `collect_gigs.py:322` (`http_get`), `collect_poclanos.py:134` (`http_get`), `collect_webzines.py:413` (`http_get`), `collect_indistreet_sns.py:113` (`fetch`), `collect_regional_gigs.py:195` (`fetch`), `collect_selection.py:209` (`fetch`), `collect_spotify.py:93` (`urllib_http`), `collect_videos.py:141` (`urllib_http`) | `urllib.request.Request(url, headers={"User-Agent": ...})` + `urlopen(timeout=...)` 패턴 반복 |
| 8 | **`.env` 로더 (`load_env`)** | **2개 파일**: `collect_spotify.py:74`, `collect_videos.py:93` | 독스트링(`".env 의 KEY=VALUE 를 읽는다..."`)과 구현이 완전히 동일 |
| 9 | **이름·키 정규화** | 공용 `normalize.py` + `artist_xref.py:125` (`canonical_key`) 외 별도 구현:<br>`collect_gigs.py:146` (`_norm_name`), `collect_moonlight_walk.py:79,98` (`clean_name`, `norm_key`), `genre.py:32` (`_norm`), `lineup_roles.py:115` (`_norm`), `collect_ssm_shows.py:103` (`_normalize_title`) | `normalize.py`의 `clean_name`·`canonical_key`와 중복되는 공백·소문자·괄호 정리 로직이 일부 수집기·분석기에 따로 있음 |
| 10 | **통계·도메인 소형 유틸 (2소묶음)** | • **윌슨 95% 신뢰구간**: `discovery_stage.py:46` (`wilson`, `%` 반환), `similar_validate.py:96` (`wilson`, `0~1` 반환)<br>• **멜론 ID 유효성**: `candidate_audit.py:43` (`valid_melon_id`), `collect_artists.py:137` (`valid_melon_id`) | `candidate_audit.py` 쪽에는 `INVALID_IDS` 제외가 빠져 있어 공용화 시 일관성 개선 가능 |
| 11 | **경로(`ROOT`)·`aside` 브라우저 호출** | • `ROOT = Path(__file__).resolve().parent.parent`: **80개 파일**<br>• `aside` 브라우저 서브프로세스/평가 호출: **5개 파일** (`collect_artists.py:320`, `collect_gigs.py:111`, `collect_gigs_history.py:257`, `collect_hiphople.py:277`, `collect_platforms.py:240`) | `ROOT`는 우선순위 낮음; `aside` 호출 래퍼는 5개 수집기 공통화 후보 |
