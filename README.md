# Gigle Research (기글 리서치) — 국내 인디 신인을 '뜨기 전에' 찾는 데이터 파이프라인

> 공연·선정·발매·매체 소개 데이터를 매일 모아, 나중에 신인상·주요 신인 프로그램(정답)을 받을 팀을 **미리** 골라낼 수 있는지 SQL로 검증하는 프로젝트입니다.

**바로 보기** · [진행판](https://leegmyung.github.io/crate-digger/) · [앱(대시보드)](https://leegmyung.github.io/crate-digger/dashboard.html) · [SQL 결과](docs/sql/README.md) · [방법론](docs/methods.md) · [용어집](docs/glossary.md)

---

## 무엇을 푸는가

**"국내 신인을 수상·선정 전에 먼저 찾을 수 있나? 몇 달 먼저 찾나?"**

음악 플랫폼·레이블의 발굴 담당자는 작은 공연, 지원사업 선정, 매거진 소개 같은 흩어진 신호를 사람이 직접 훑습니다. 이 프로젝트는 그 신호를 자동으로 모아 한 팀 단위로 묶고, **과거로 돌아가 '그때 알 수 있던 정보만으로' 뽑았다면 맞혔을지**(백테스트)를 숫자로 확인합니다.

## 결과물 한눈에

| 결과물 | 무엇 | 바로 가기 |
|---|---|---|
| 앱 (대시보드) | 메뉴 홈 / 찾기(발굴·차트·공연장·도시·페스티벌) / 내 것(알림·내 목록) / 검증. 위쪽 검색(`/`)으로 팀·공연장·도시·페스티벌을 바로 찾고, 팀 페이지는 탭 7개(개요·점수·사건·공연·관계·영상·선례), 모든 탭 아래 '근거' 줄이 검증 화면으로 이어짐 (브라우저 안 DuckDB로 가중치를 바꿔 직접 확인). 아래 '앱 화면' 절 참고 | [열기](https://leegmyung.github.io/crate-digger/dashboard.html) · [사용 안내](https://leegmyung.github.io/crate-digger/dashboard.html#/help) |
| 주간 엑셀 | 요약·후보 TOP100·이번 주 변화·다가오는 공연·출처 성적표·점수 검증·정의 7시트 (앱과 같은 숫자) | [docs/report/crate-digger_weekly.xlsx](docs/report/crate-digger_weekly.xlsx) |
| Tableau 추출 | 바로 올릴 긴 형식 CSV 4개 + 시트·계산 필드 설계서 | [docs/tableau/](docs/tableau/README.md) |
| 사운드 지도 | 같은 무대 공동 출연으로 나눈 씬 묶음 244개, 묶음별 대표 공연장·상위 후보 | [docs/scene_map.md](docs/scene_map.md) |
| 서비스 기획 | 음악 스트리밍 서비스에 적용하는 3가지 안, A/B 실험 설계(지표·표본 크기·가드레일) | [docs/service_plan.md](docs/service_plan.md) |
| SQL (PostgreSQL · BigQuery) | 분석 9개·검증 8개 쿼리와 결과, 같은 쿼리의 BigQuery 문법판 | [결과](docs/sql/README.md) · [sql/kr/](sql/kr/) · [sql/bigquery/](sql/bigquery/) |
| 데이터 사전 | 모든 표의 칸·단위·출처·갱신 주기 (코드에서 자동 생성) | [docs/data_dictionary.md](docs/data_dictionary.md) |
| 방법론 | 정의·시점 누수 방지·점수 공식·백테스트·한계 | [docs/methods.md](docs/methods.md) |
| 화면 정보 분석 (점수 미반영) | 발굴 단계·공연장 체급과 사다리·공연장 프로필·도시·라인업 역할·알림·새 특징 실험·신원 점검 — 한 줄 정의와 점수에 안 넣은 이유(교차 검증 숫자) | [방법론 마지막 절](docs/methods.md) |
| 출처 분류 | 출처별 성적표와 역할(발굴·맥락·제외·검증 대기), 정답 등급 S·A·B | [docs/source_roles.md](docs/source_roles.md) |
| 점수 교차 검증 | 기준일을 하나씩 빼고 가중치를 고른 결과 | [docs/score_tuning.md](docs/score_tuning.md) |

### 앱 화면 (2026-11-28 새 구조)

경쟁 서비스(Chartmetric·Viberate)의 **정보 구조**(메뉴 나눔·검색 중심·팀 페이지 탭)를 가져와 우리 데이터에 맞게 바꿨습니다 — [화면 구조 설계](docs/app_structure_v2.md). 주소는 모두 `dashboard.html#/…` 형식이고, 예전 주소(`#/today`·`#/candidates` 등)도 새 주소로 자동으로 넘어갑니다.

| 메뉴 | 주소 예시 | 무엇을 보나 |
|---|---|---|
| 홈 | `#/home` | 이번 주 브리핑 — 알림 요약(새 정답·새 선정·백지 신인 첫 언급·언급 급증), 저장 필터에 새로 들어온 팀 |
| 발굴 | `#/discover` · `#/discover?preset=rising` | 조건(장르·지역·첫 발매 N개월·발굴 단계·신호)으로 후보 거르기, 표 ↔ 색 지도, 조건 저장 |
| 차트 | `#/charts/debut` | 정의가 정해진 순위표 — 갓 데뷔(첫 발매 뒤 언급). 전체·장르·도시·떠오르는은 준비 중 |
| 공연장 | `#/venues` · `#/venue/롤링홀/flow` | 공연장 목록(체급·종류), 공연장 페이지(출연 팀·공연·전후 흐름) |
| 도시 · 페스티벌 | `#/city/부산` · `#/festivals` | 도시별 공연장·첫 무대 신인, 페스티벌 라인업과 그 뒤 정답 |
| 알림 · 내 목록 | `#/alerts` · `#/mine` | 받은 알림(준비 중), 관심 팀·구독 공연장·저장한 필터 |
| 검증 (고급) | `#/verify/backtest` · `#/verify/scorecard` | 백테스트·출처 성적표·신호 원본·데이터 품질·SQL — 우리가 앞선 부분 |
| 팀 페이지 | `#/team/<팀 이름>/score` | 탭 7개: 개요·점수·사건·공연·관계·영상·선례 (탭마다 '근거' 줄 → 검증) |
| 검색 결과 | `#/search?q=부산` | 팀·공연장·도시·페스티벌을 종류별로 |
| 사용 안내 | `#/help` | 메뉴 설명·자주 쓰는 흐름·단축키(`/`·↑↓·Enter·Esc)·꼬리표 뜻 |

## 데이터 4갈래 + 정답

모든 소스는 **후보 신호**(작고 이른 단계) 또는 **정답**(크고 경쟁이 센 단계) 중 한쪽으로만 씁니다.

| 갈래 | 무엇 | 출처 | 규모 (PostgreSQL, 2026-11-27) |
|---|---|---|---|
| 공연 | 라이브 클럽·공연장 출연 | 인디스트릿·인디고·상상마당 공연 목록, 공연장 인스타 라인업 | 14,925행 · 4,947팀 (2010~) |
| 큐레이션 | 매체가 골라 소개 | 인스타 음악 매거진, 웹진(IZM·음악취향Y·리드머·weiv·VISLA·overtone) | 4,139행 · 2,550팀 (2023~) |
| 선정·지원 | 지원사업·경연 선정 | 부산 루키즈·뮤즈 인 세종·경북 창작소·유재하 경연·밴드 디스커버리·DMZ | 701행 · 622팀 |
| 발매 | 신보 | 포크라노스·멜론·벅스·지니·FLO | 214행 · 127팀 (2026-11 수집분부터) |
| **정답** | 신인상·주요 신인 프로그램 | 한국대중음악상 신인·올해의 헬로루키·CJ 튠업 등 (S·A·B 등급) | 745행 · 479팀 (2021-02~2026-11), 센 정답 222팀 |

이 밖에 보조 데이터로 스포티파이 협업(피처링)·유튜브 무대 영상 조회수를 매일 모읍니다(기록이 짧아 '검증 대기'). 원본 수집 데이터는 공개하지 않습니다(`data/raw/`, 커밋 안 함). 저장소의 `data/`에는 가상 샘플만 있습니다.

## 파이프라인

```
 [소스]  공연 · 큐레이션 · 선정·지원 · 발매 · (협업·영상)     정답(신인상·신인 프로그램)
    │                                                          │
    ▼                                                          ▼
 ① 수집기 18개 (13개는 매일 21:00 자동)  → 원본 CSV (수정 금지) → 형식 검사
    │   └ 관찰 팀 멜론 팬 수 7일마다 다시 받기 → 팬 수 날짜별 기록 (기준일 시점 유명 판정 준비)
    │
 ② PostgreSQL 적재 (raw 스키마)
    │
 ③ 아티스트 매칭·메타데이터 검수  팀 표기 묶기(artist_xref) · 공연장 표기 묶기(venue_xref)
    │
 ④ 기초 뷰 (core.v_signal · v_outcome …)  날짜 규칙으로 시점 누수 차단
    │
 ⑤ 출처 성적표 → 역할 분류(발굴·맥락·제외·검증 대기) · 정답 등급(S·A·B) · 같은 집안 규칙 (월요일 문서 자동 갱신)
    │
 ⑥ 점수 v2 · 백테스트 · 교차 검증(과거 기준일엔 '지금 팬 수' 유명 판정 안 씀) · 분석/검증 SQL
    │
 ⑦ 화면 정보(점수 미반영): 발굴 단계 · 공연장 체급·사다리·프로필 · 도시 · 라인업 역할 · 오늘 알림
    │   (단계·체급·도시·라인업은 점수 v2에 더해 교차 검증 — 채택 기준 미달이라 설명·탐색용으로만)
    │
 ⑧ 결과물: 앱 · 주간 엑셀 · Tableau 추출 · 사운드 지도 · SQL 결과 (매일 자동 갱신)
```

## 핵심 결과 (지금까지)

> ⚠️ **표본이 작습니다.** 기준일마다 맞혀야 할 정답 팀이 6~22팀뿐이라 아래 숫자는 '방향'으로만 읽어 주세요. 출처: [SQL 결과](docs/sql/README.md)(1·2번)·[점수 교차 검증](docs/score_tuning.md)·[방법론](docs/methods.md)(3·5번). 모두 2026-11-28 정답 보강(정답 표 1,272행)과 같은 날 새벽의 멜론 프로필 보강·본인 음반 첫 발매·공연장 수 최근 2년 반영 후 숫자입니다.

1. **정답 팀의 79%가 정답 전에 우리 레이더에 먼저 잡혔습니다.** 2025년 이후 센 정답을 받은 91팀 중 72팀이 정답 전에 공연·큐레이션·선정 신호가 있었고, 첫 신호는 정답보다 **중앙값 14.3개월** 먼저였습니다. 먼저 잡힌 팀의 81%는 6개월 이상, 57%는 12개월 이상 먼저였습니다 (a02).
2. **이미 상 받은 팀과 같은 무대에 선 신인이 더 많이 떴습니다.** 2024년 공연 기준, 공연 당시 이미 정답을 받은 팀과 같은 날·같은 공연장에 섰던 팀은 5.0%(343팀 중 17팀)가 이후 정답을 받았고, 정답 팀과 같이 선 적 없는 팀은 0.8%(726팀 중 6팀)였습니다(약 6배, 2025년 상반기 공연은 11.7% 대 1.0%). 공연 당시에도 알 수 있는 정보라 점수 v2에 가장 큰 가중치(2)로 들어갑니다 (a07).
   - _1·2번이 바뀐 이유: 빠져 있던 2021~2025년 정답(부산록페·인디스땅스·한대음 장르)을 채워 정답 표가 723 → 1,272행이 됐습니다. 보강 전 숫자는 74%(92팀 중 68팀)·중앙값 12.9개월, 같은 무대 5.0% 대 1.3%(약 3.8배)였습니다. 2021~24년 정답이 늘어 '공연 당시 이미 정답 팀'이 더 많이 확인됐고, 그 팀과 같이 서지 않은 팀의 비율은 더 낮아졌습니다._
3. **정답을 정리·보강하고 미래 정보를 걷어내자 점수 v2는 v0와 비슷하고, 담당자가 보는 상위 50에서는 앞섭니다.** 기획사 아이돌 10팀을 정답에서 빼고 상 후보는 수상보다 한 등급 낮게 센 뒤([정답 정리](docs/methods.md)), 출처와 정답을 같은 곳이 만드는 '같은 집안' 짝(예: 힙합엘이↔한국힙합어워즈)을 적중에서 빼고([같은 집안 점검](docs/same_house.md)), '지금 팬 수'로 정하는 유명 팀 제외를 과거 기준일에는 쓰지 않도록 고쳤습니다([규칙 시점 점검](docs/rule_leakage.md) — 이 판정으로 빠지던 후보 23행 중 10행이 나중에 상을 받은 팀이었음). 빠져 있던 2021~2025년 정답(부산록페·인디스땅스·한대음 장르)도 채웠습니다([정답 보강](docs/methods.md), 정답 표 723 → 1,272행). 그 결과 기준일 6개 중 하나씩 빼고 가중치를 고른 교차 검증에서 정답 등급 가중 AUC는 교차 검증으로 고른 가중치 **0.809** · v0 0.819 · 공연 수만 0.610이었고(고른 가중치가 앞선 기준일 4/6), **담당자가 실제로 보는 상위 50 적중은 30팀 대 24팀**이었습니다. 순위는 앱 화면과 같은 규칙(동점은 최근 신호 순)으로 잽니다. 평균 AUC는 v0가 0.010 높지만 기준일마다 정답이 6~22팀뿐이라 흔들리는 범위이고, 실제로 보는 상위 50은 v2 쪽이 더 많이 맞힙니다. 학습 모델(로지스틱 회귀, 0.814)과 손 공식(교차 0.809)은 사실상 같습니다(차이 +0.005, 95% 구간 −0.019~+0.045). 데이터로 다시 고른 추천 가중치(선정 단계 2·선정 팀과 같은 무대 1·최근 180일 신호 3·맥락 매체 0)는 평균 0.833으로 v2 기본값 0.827보다 0.006 높지만 변경 제안 기준(+0.01)에 못 미쳐 v2를 그대로 씁니다. v2의 장점은 검증된 출처만 쓰고 큰 상을 더 중시하는 구조입니다. _숫자가 바뀐 이유(11-28 새벽): 멜론 프로필 보강으로 첫 발매일이 채워져 기성 팀이 신인 후보군에서 빠졌고(기준일 6개 정답 92 → 84행), 첫 발매일을 본인 음반 기준으로·공연장 수를 최근 2년으로 바꿨습니다([방법론](docs/methods.md))._ ([점수 교차 검증](docs/score_tuning.md), [점수 모델 비교](docs/score_model.md)).
4. **검증 안 된 출처를 빼도 성능은 그대로였습니다.** (정답 정리 전, 기준일 전체로 채점한 같은 조건끼리 비교) 검증 대기·제외 출처를 빼도 등급 가중 AUC는 0.742로 같았고(그동안 점수에 기여하지 않았다는 뜻), 기준선 수준인 맥락 매체를 완전히 빼면 0.710으로 떨어져 약하게(가중치 0.5) 남겼습니다 ([출처 분류](docs/source_roles.md)).
5. **앱에 보이는 v2 AUC 0.827은 부풀려진 숫자입니다.** 'v2 고정' AUC는 기준일 6개를 모두 보고 고른 가중치를 같은 기준일로 채점한 값이라, 처음 보는 시점(0.809)보다 약 0.018 높습니다. 관찰 기간을 12·18·24·36개월로 바꾼 비교(11-28 정답 보강 직후, 새벽 보강 전 숫자)에서도 v2 고정(0.798·0.811·0.813·0.818)이 v0(0.782·0.792·0.793·0.805)보다 높고 상위 50 적중도 같거나 1~3팀 많지만, v2에 유리한 비교입니다. 실제 기대 성능은 0.80~0.81 안팎으로 읽어 주세요.

## 업계 용어로 보면

| 용어 | 이 프로젝트에서 |
|---|---|
| **아티스트 매칭 · 메타데이터 검수** | 플랫폼마다 다른 이름 표기('피치 트럭 하이재커스(Peach Truck Hijackers)' / 'Peach Truck Hijackers')를 한 팀으로 묶는 연결표 `artist_xref`(1,112팀 새로 묶음), 공연장 표기를 묶는 `venue_xref`(237개 표기 → 205곳) → [요약](docs/artist_xref.md) |
| **백테스트** | 과거 기준일을 정해 그 전 신호만으로 점수를 매기고, 그 뒤 실제 정답으로 채점 |
| **교차 검증** | 기준일 하나를 빼고 나머지로 가중치를 고른 뒤, 뺀 기준일로 채점 (고를 때 안 본 시점) |
| **기준선 대비 배수 (lift)** | 적중률 ÷ 무작위로 뽑았을 때의 기대 적중률. 1보다 커야 쓸모 있음 |
| **시점 누수 방지** | 날짜를 월·연도까지만 알면 신호는 기간 마지막 날, 정답은 첫날로 계산해 '미리 맞혔다'를 부풀리지 않음 |

## AI로 자동화한 방법

수집기 15개(공연·선정·발매·인스타·웹진·플랫폼 프로필·협업·영상 등)는 공개 API나 페이지 구조가 허용하는 곳은 파이썬 스크립트로, 로그인 없이 보이지만 스크립트 접근이 어려운 페이지는 브라우저 자동화로 읽습니다. 맥이 **매일 21:00** `scripts/daily_run.sh`를 실행해 수집부터 결과물 갱신, 커밋·push까지 사람 손 없이 돌립니다. 출처 분류가 성적과 어긋나면 일일 기록에 재분류 제안이 자동으로 붙습니다. 개발은 **여러 AI 에이전트가 분업**했습니다: 코디네이터 에이전트(Claude Code)가 계획·검토·커밋을 맡고, 작업자 에이전트들이 수집·아티스트 매칭·대시보드·결과물을 파일 단위로 나눠 동시에 만들었습니다. 새 코드는 테스트를 먼저 쓰고(현재 테스트 600개 이상, CI 설정 준비됨: `.github/workflows/tests.yml`), 결정과 그 이유는 [PROJECT.md](PROJECT.md)에 남겼습니다.

---

## 실행 방법

### 처음 한 번: 파이썬 환경 준비

```bash
python3 -m venv .venv                 # 프로젝트 전용 파이썬 공간 (커밋 안 됨)
source .venv/bin/activate             # 터미널을 새로 열 때마다 실행
pip install -r requirements.txt       # numpy·duckdb·sqlglot·openpyxl 등
python -m unittest discover -s tests  # 테스트 (비공개 원본 없이도 통과)
```

PostgreSQL(17)과 `.env`(유튜브·스포티파이 키, 커밋 안 됨)는 수집·적재에만 필요합니다. 공연·인스타 수집은 브라우저 자동화 앱(aside)이 켜져 있어야 합니다.

### 매일 21:00 자동 실행 (`scripts/daily_run.sh`)

설치·시간 변경: `bash scripts/install_daily.sh 21 0`. 단계는 순서대로:

| 단계 | 스크립트 | 결과 |
|---|---|---|
| 1. 수집 (스크립트) | `collect_poclanos` · `collect_selection` · `collect_superrookie`(슈퍼루키챌린지, 새 글만) | `data/raw/*.csv` (비공개) |
| 1. 수집 (aside 브라우저) | `collect_gigs` · `collect_insta` · `collect_platforms` · `collect_artists`(새 아티스트) · `collect_hiphople`(힙합엘이 국내 뉴스) · `melon_names` → `collect_artists --names-file`(후보·정답 팀 프로필 보강) · `collect_artists --refresh`(관찰 팀 팬 수, 마지막으로 받은 지 7일 지난 것만) | 〃 |
| 1. 수집 (API) | `fan_history`(팬 수 날짜별 기록) · `collect_spotify` · `collect_spotify_collabs` · `collect_videos` | 〃, `data/raw/state/fan_history.json` + [팬 수 기록 요약](docs/fan_history.md) |
| 2. 검사 | `validate_csv` | 형식 오류 표시 |
| 3. 적재·묶기 | `build_site_data` · `load_pg` · `artist_xref --load-pg` · `venue_xref --load-pg` | 진행판 데이터, PostgreSQL |
| 4. 분석 | `build_dashboard_data` · `run_pg_queries` | 대시보드 숫자, [SQL 결과](docs/sql/README.md) |
| 5. 랩·결과물 | `collect_artist_images` · `export_lab_data` · `source_roles_doc`(월요일, [출처 분류](docs/source_roles.md) 성적표 표) · `source_review` · `score_review`(월요일) · `collect_video_stats` · `export_video_momentum` · `export_excel`(월요일) · `lab_snapshot` · `build_scene_map` | `docs/lab/data/`, 주간 엑셀, 사운드 지도 |
| 6. 기록 | `daily_note` · `build_status_report` → 커밋·push | `docs/log/<날짜>.md`, 진행 점검표 |

사진·바로 듣기 보강 ([규칙](docs/media_coverage.md)): `coverage_targets`(후보 상위 500 → 정답 팀 대상·커버리지, .venv) · `collect_musicbrainz`(공식 유튜브·스포티파이·인스타 링크) · `collect_yt_channels`(공식 채널 아바타·최신 영상) → `export_lab_data`가 `images.csv`(스포티파이 → 유튜브 아바타)·`players.csv`(팀별 스포티파이 + 대표 유튜브 영상)를 만든다.

손으로 가끔 돌리는 수집기: `collect_gigs_history`(인디스트릿 지난 공연) · `collect_webzines`(웹진 과거 기록) · `collect_ig_artists` · `collect_ssm_shows` · `collect_trackzero`(멜론 트랙제로) · `collect_hiphople --backfill`(과거 기록, 21~23시 제외).

### 손으로 다시 만들기

```bash
python3 scripts/load_pg.py                     # 원본 CSV → PostgreSQL raw 스키마
python3 scripts/artist_xref.py --load-pg       # 팀 표기 연결표 → ref.artist_xref
python3 scripts/venue_xref.py --load-pg        # 공연장 표기 연결표 → ref.venue_xref
python3 scripts/run_pg_queries.py              # 기초 뷰 → 분석·검증 SQL → docs/sql/README.md
python3 scripts/export_lab_data.py             # 랩 데이터 → docs/lab/data/
.venv/bin/python scripts/export_excel.py       # 주간 엑셀 (duckdb·openpyxl)
.venv/bin/python scripts/export_tableau.py     # Tableau 추출
.venv/bin/python scripts/score_tune.py         # 점수 교차 검증 → docs/score_tuning.md
python3 scripts/build_data_dictionary.py       # 데이터 사전
python3 scripts/check_links.py                 # 문서 링크 검사
```

형식 규칙은 [docs/csv_spec.md](docs/csv_spec.md).

### 앱 화면 점검 (선택, 손으로)

앱(`docs/dashboard.html`)을 고친 뒤 `bash scripts/e2e_check.sh`를 돌린다. 내부적으로는 세 단계다. 먼저 로컬 서버(`tests/e2e/static_server.mjs`)를 띄운다. 다음으로 헤드리스 크롬으로 메뉴 16곳 × 화이트·블랙 × 1280·1920·375px = 96칸을 본다(`tests/e2e/route_check.mjs`). 마지막으로 서버를 끈다. 칸마다 콘솔 오류 0, 가로 넘침 0, 빈 화면 없음, 제한 시간(기본 20초, `--limit-ms`) 안에 그려짐을 확인한다. 하나라도 어기면 종료 코드 1이다. node 22 이상과 크롬(또는 크로미움)이 필요하다. 크롬 위치가 기본 설치 경로가 아니면 `--chrome <실행 파일>`이나 환경변수 `CHROME_PATH`로 알려 준다. 앱 서버 포트(`--port`)와 크롬 디버깅 포트(`--debug-port`)는 기본값이 0이고, 0이면 비어 있는 포트를 자동으로 고른다. 그래서 여러 작업자가 동시에 돌려도 겹치지 않는다. 결과를 파일로 남기려면 `--out 결과.json`을 붙인다. 파이썬 테스트(`unittest`)에는 들어 있지 않다.

---

## 예전 단계 (참고용)

프로젝트 초기에 만든 판매 대시보드와 취향 추천 프로토타입입니다. 지금 방향은 위의 국내 신인 발굴이고, 아래는 다시 만들 때를 위한 사용법입니다.

### Bandcamp Sales Pulse (판매 대시보드)

Bandcamp 판매 피드 데이터를 SQL로 집계하는 글로벌 인디 음악 판매 대시보드.

```
├─ sql/
│  ├─ schema.sql          # 스테이징 + 스타 스키마 (dim_* / fact_sales / item_tags) + v_sales 뷰
│  ├─ load.sql            # stg_salesfeed → 정규화 (정제, 포맷 분류, 환율 역산, 태그 분리)
│  └─ queries/            # 대시보드 패널 1개 = SQL 1개
│     ├─ 01_kpi_weekly.sql      최근 7일 vs 직전 7일 KPI
│     ├─ 02_daily_trend.sql     일별 디지털/실물 매출
│     ├─ 03_hourly_heatmap.sql  요일 × 시간대(UTC) 판매
│     ├─ 04_country_top.sql     국가별 매출 Top 15 (RANK, 점유율)
│     ├─ 05_format_mix.sql      포맷별 매출/평균가/정가초과율
│     ├─ 06_pay_ratio.sql       정가 대비 결제 비율 분포
│     ├─ 07_top_artists.sql     아티스트 Top 15 (ROW_NUMBER로 최대 구매국)
│     └─ 08_genre_revenue.sql   대표 장르별 매출 (태그 크롤 필요)
├─ scripts/
│  ├─ generate_sample.py  # 가상 샘플 CSV 생성 (실제 데이터 아님)
│  ├─ build_db.py         # CSV → SQLite (schema + load)
│  └─ run_queries.py      # queries/*.sql 실행 → out/*.json (SQL 원문 포함)
├─ dashboard/index.html   # 대시보드 페이지 원본
├─ data/sample_salesfeed.csv
└─ out/*.json             # 대시보드에 올리는 쿼리 결과
```

스키마:

```
stg_salesfeed (크롤 원본 그대로)
        │ load.sql
        ▼
dim_country ─┐
dim_currency ┤
dim_artist ──┼─ dim_item ── fact_sales (판매 1건 = 1행)
             │      └── item_tags (장르/태그, 선택)
             ▼
          v_sales (분석용 뷰: 시간·요일·채널·정가대비 비율 파생)
```

크롤링 CSV에 필요한 컬럼 (`stg_salesfeed`와 같은 이름으로 저장하면 그대로 들어가고, 없는 컬럼은 NULL):

| 컬럼 | 필수 | 설명 |
|---|---|---|
| utc_date | ✅ | 판매 시각 (UTC), `YYYY-MM-DD HH:MM:SS` |
| artist_name | ✅ | 아티스트명 |
| album_title | | 앨범명 |
| item_type | ✅ | `a` 디지털 앨범 / `t` 트랙 / `p` 실물 |
| item_description | | 포맷 분류용 (예: `Vinyl LP`, `Cassette`, `T-Shirt`) |
| url | ✅ | 상품 URL (`https://<아티스트>.bandcamp.com/...`) |
| item_price | ✅ | 정가 (판매 통화) |
| amount_paid | ✅ | 실제 결제액 (판매 통화) |
| amount_paid_usd | 권장 | USD 환산 결제액. 없으면 통화별 평균 환율로 보정 |
| currency | ✅ | `USD`, `GBP`, `EUR` ... |
| country / country_code | ✅ | 구매자 국가 |
| tags | | 앨범 페이지 태그, `|` 구분. 첫 번째 태그가 대표 장르 |

판매 피드 JSON의 실제 키 이름은 크롤링 후 꼭 확인하고, 다르면 CSV 저장 단계에서 위 이름으로 바꿔 주세요.

```bash
python3 scripts/generate_sample.py data/sample_salesfeed.csv   # 가상 판매 샘플 (선택)
python3 scripts/build_db.py data/my_crawl.csv
python3 scripts/run_queries.py bandcamp.db data/my_crawl.csv
```

그 뒤 `out/*.json` 8개를 대시보드 Sources에서 파일 교체하면 됩니다.
PostgreSQL에서 쓰려면 `schema.sql` 상단 주석대로 타입과 `strftime`/`date()` 함수를 바꾸면 됩니다.

### Bandcamp Taste Match (추천 프로토타입, 보류)

TuneMyMusic으로 내보낸 좋아요 CSV(Spotify / Apple Music / YouTube Music)를 취향 벡터로 바꾸고,
Bandcamp 카탈로그에서 인디 아티스트를 추천합니다.

```
data/likes/<user_id>.csv  ─▶ raw_tmm_export ─▶ user_likes ─▶ user_artist
data/ext_artist_tags.csv  ─▶ ext_artist_tags (실서비스: Last.fm/MusicBrainz) ─▶ liked_artist_vec ─▶ user_taste ─▶ user_segment
bandcamp.db (item_tags)   ─▶ bc_artist_vec ─┐
data/fan_collections.csv  ─▶ bc_fan_collection ─▶ reco_cofan ─┤
bandcamp.db (fact_sales)  ─▶ bc_artist_stats ───────────────┴▶ reco_score ─▶ reco_final
```

- `sql/reco/schema_reco.sql` 테이블, 태그 → 취향군 매핑
- `sql/reco/load_likes.sql` CSV 정규화 (주 아티스트 추출, 매칭 키)
- `sql/reco/reco.sql` 취향 벡터, 세분화, 코사인 유사도, 팬 공동구매, 점수, 다양성, 추천 이유
- `sql/reco/queries/r1~r4` 대시보드용 결과

점수 = 0.55·태그 유사도 + 0.25·팬 공동구매 + 0.10·상승세 + 0.10·발굴 (취향군당 최대 4팀, 사용자당 12팀)

```bash
python3 scripts/generate_reco_sample.py   # 샘플 생성 (실제 데이터가 있으면 생략)
python3 scripts/build_reco.py             # 계산 → out/reco/*.json
```

실제 데이터로 바꾸기: `data/likes/`에 TuneMyMusic CSV를 `<user_id>.csv`로 넣고,
`ext_artist_tags.csv`를 Last.fm 태그로, `fan_collections.csv`를 크롤링한 팬 컬렉션으로 교체합니다.
CSV 컬럼명이 달라도 `build_reco.py`의 ALIASES에 추가하면 됩니다.

내 데이터로 큐레이션 받기 (명령 한 번):

```bash
export LASTFM_API_KEY=발급받은키          # https://www.last.fm/api/account/create (무료)
python3 scripts/curate.py <내보낸_좋아요.csv> --user me
```

여러 플랫폼 CSV를 한꺼번에 넣어도 됩니다. 키가 없으면 기존 `data/ext_artist_tags.csv`를 씁니다.
결과는 터미널과 `out/curation_<user>.md`에 나오고, `out/reco/*.json`은 대시보드에 올리는 파일입니다.

Last.fm 태그 수집만 따로:

```bash
python3 scripts/fetch_lastfm_tags.py            # data/likes/*.csv 의 모든 아티스트
```

- 의미 없는 태그(seen live, 연도, 국적 등) 제거, 표기 통일(Hip Hop → hip-hop), 점수 10 미만 제외
- 못 찾은 아티스트는 `data/artist_aliases.csv`(artist_name,lastfm_name)로 보정 (예: 혁오,HYUKOH)
- `data/lastfm_report.csv` 아티스트별 결과, `data/lastfm_unmapped_tags.csv` 취향군 매핑이 없는 태그
- 응답은 `data/cache/lastfm/`에 캐시, 초당 4회 이하로 호출

앨범 상세 (`data/album_details.csv`): 앨범 페이지 크롤 결과 url, art_id, art_url, release_date, track_count, duration_sec, label, location, about.
대시보드에는 외부 이미지가 바로 안 뜨므로 실제 커버는 업로드한 파일 주소로 넣어야 하고, 없으면 생성형 커버를 그립니다.

Spotify Voyager로 후보 검색 (선택):

```bash
pip install voyager
python3 scripts/voyager_index.py --k 200
```

Bandcamp 아티스트 태그 벡터로 근사 최근접 이웃 인덱스(`data/bc_artist.voy`)를 만들고,
사용자 취향 벡터로 후보를 빠르게 찾습니다(`reco_ann`). 아티스트끼리 비슷한 팀도 저장합니다(`bc_similar`).
카탈로그가 수십만 팀 이상으로 커지면 "Voyager로 후보 수백 팀 → reco.sql로 정밀 점수" 2단계로 바꿉니다.
최종 추천은 팬 공동구매·발굴 점수로 순위가 바뀌므로, 후보 수(K)는 최종 추천 수보다 넉넉히(수백) 잡아야 합니다.
