# Crate Digger — 국내 인디 신인을 '뜨기 전에' 찾는 데이터 파이프라인

> 공연·선정·발매·매체 소개 데이터를 매일 모아, 나중에 신인상·주요 신인 프로그램(정답)을 받을 팀을 **미리** 골라낼 수 있는지 SQL로 검증하는 프로젝트입니다.

**바로 보기** · [진행판](https://leegmyung.github.io/crate-digger/) · [데이터 대시보드](https://leegmyung.github.io/crate-digger/dashboard.html) · [랩 — 설정형 분석 도구 (제작 중)](https://leegmyung.github.io/crate-digger/lab.html) · [SQL 결과 문서](docs/sql/README.md) · [방법론](docs/methods.md) · [용어집](docs/glossary.md)

---

## 무엇을 푸는가

**"국내 신인을 수상·선정 전에 먼저 찾을 수 있나? 몇 달 먼저 찾나?"**

음악 플랫폼·레이블의 발굴 담당자는 작은 공연, 지원사업 선정, 매거진 소개 같은 흩어진 신호를 사람이 직접 훑습니다. 이 프로젝트는 그 신호를 자동으로 모아 한 팀 단위로 묶고, **과거로 돌아가 '그때 알 수 있던 정보만으로' 뽑았다면 맞혔을지**(백테스트)를 숫자로 확인합니다.

## 데이터 4갈래 + 정답

모든 소스는 **후보 신호**(작고 이른 단계) 또는 **정답**(크고 경쟁이 센 단계) 중 한쪽으로만 씁니다.

| 갈래 | 무엇 | 출처 | 규모 (PostgreSQL, 2026-11-27) |
|---|---|---|---|
| 공연 | 라이브 클럽·공연장 출연 | 인디스트릿·인디고·상상마당 공연 목록, 공연장 인스타 라인업 | 14,933행 · 4,959팀 (2010~) |
| 큐레이션 | 매체가 골라 소개 | 인스타 음악 매거진, 웹진(IZM·음악취향Y·리드머·weiv·VISLA·overtone) | 4,093행 · 2,546팀 (2023~) |
| 선정·지원 | 지원사업·경연 선정 | 부산 루키즈·뮤즈 인 세종·경북 창작소·유재하 경연·밴드 디스커버리·DMZ | 701행 · 622팀 |
| 발매 | 신보 | 포크라노스·멜론·벅스·지니·FLO | 214행 · 127팀 (2026-11 수집분부터) |
| **정답** | 신인상·주요 신인 프로그램 | 한국대중음악상 신인·올해의 헬로루키·CJ 튠업 등 (최종) / 펜타 슈퍼루키·뮤즈온·인디스땅스 등 (중간) | 438행 · 295팀 (2025-01~2026-11) |

원본 수집 데이터는 공개하지 않습니다(`data/raw/`, 커밋 안 함). 저장소의 `data/`에는 가상 샘플만 있습니다.

## 파이프라인

```
 [소스]  공연 · 큐레이션 · 선정·지원 · 발매          정답(신인상·신인 프로그램)
    │        │           │           │                   │
    ▼        ▼           ▼           ▼                   ▼
 ① 수집기 11개 (매일 21:00 자동)  → 원본 CSV (수정 금지) → 형식 검사
    │
 ② PostgreSQL 적재 (raw 스키마)
    │
 ③ 아티스트 매칭·메타데이터 검수  scripts/artist_xref.py → ref.artist_xref
    │   한글/영문 표기·띄어쓰기·여러 명 칸·인스타 계정을 대표 팀 키(team_key) 하나로
    │
 ④ 기초 뷰 (core.v_signal · v_outcome …)  날짜 규칙으로 시점 누수 차단
    │
 ⑤ 분석 SQL 9개 + 검증 SQL 8개 · 거꾸로 따라가기 · 점수 v0 백테스트
    │
 ⑥ 보여주기: 진행판 · 데이터 대시보드 · 랩 · SQL 결과 문서 (매일 자동 갱신)
```

## 핵심 결과 (지금까지)

> ⚠️ **표본이 작습니다.** 정답 팀이 86팀(2025년 이후)이고, 2021~2024 정답을 더해도 기준일마다 맞혀야 할 팀은 2~21팀뿐이라 아래 숫자는 '방향'으로만 읽어 주세요. 출처: [SQL 결과](docs/sql/README.md) (2026-11-27 기준), [거꾸로 따라가기](docs/backtrace.md).

1. **정답 팀의 79%가 정답 전에 우리 레이더에 먼저 잡혔습니다.** 2025년 이후 센 정답을 받은 86팀 중 68팀이 정답 전에 공연·큐레이션·선정 신호가 있었고, 첫 신호는 정답보다 **중앙값 13.2개월** 먼저였습니다 (a02).
2. **잘될 팀들은 같은 무대에 모여 있었습니다(씬 근접도).** 2024년 공연 기준, 나중에 정답을 받을 팀과 같은 날·같은 공연장에 섰던 팀은 6.9%(217팀 중 15팀)가 이후 정답을 받았고, 그렇지 않은 팀은 1.2%(1,001팀 중 12팀)였습니다(약 5.8배, a07). 단 '나중에 정답 받을 팀'은 그때는 모르는 정보라 **예측 신호가 아니라 참고 지표**이고, 점수에는 대신 '공연 당시 이미 선정된 팀과 같은 무대'를 씁니다.
3. **점수 v1은 '처음 보는 시점'에서도 v0보다 나았습니다.** 기준일 6개(2023~2025, 반년 간격) 중 하나를 빼고 나머지로 가중치를 고른 뒤 뺀 기준일로 채점하는 교차 검증에서, 평균 AUC가 v0 0.651 → **v1 0.701**(공연 수만 0.571)로 올랐고 데이터가 충분한 2024년 이후 기준일 4개에서는 모두 v1이 앞섰습니다. 새로 넣은 신호는 **최근 6개월 활동량·서로 다른 공연장 수·이미 상 받은 팀과 같은 무대**이고, 매거진 소개 수는 그 자체로는 예측력이 거의 없었습니다(AUC 0.47). 다만 상위 50팀 적중은 6개 기준일 합계 14팀(v0 13팀)으로 아직 작습니다 ([점수 교차 검증](docs/score_tuning.md), [앱](https://leegmyung.github.io/crate-digger/dashboard.html#/backtest)에서 가중치를 바꿔 직접 확인).

> 데이터는 양보다 쓸모로 나눴습니다: 출처마다 성적표를 재서 **발굴 · 맥락 · 제외 · 검증 대기**로 분류하고, 정답도 **S·A·B 등급**으로 가중합니다. 검증 안 된 출처를 빼도 성능(등급 가중 AUC 0.742)은 그대로였습니다 → [데이터 역할과 정답 등급](docs/source_roles.md)

## 업계 용어로 보면

| 용어 | 이 프로젝트에서 |
|---|---|
| **아티스트 매칭 · 메타데이터 검수** | 플랫폼마다 다른 이름 표기('피치 트럭 하이재커스(Peach Truck Hijackers)' / 'Peach Truck Hijackers')를 한 팀으로 묶는 연결표 `artist_xref`. 1,112팀을 새로 묶고, 잘못 합쳐져 있던 팀(예: 멤버 이름 + 괄호 속 소속 팀)을 다시 나눔 → [요약](docs/artist_xref.md) |
| **백테스트** | 과거 기준일을 정해 그 전 신호만으로 점수를 매기고, 그 뒤 실제 정답으로 채점 |
| **기준선 대비 배수 (lift)** | 적중률 ÷ 무작위로 뽑았을 때의 기대 적중률. 1보다 커야 쓸모 있음 |
| **시점 누수 방지** | 날짜를 월·연도까지만 알면 신호는 기간 마지막 날, 정답은 첫날로 계산해 '미리 맞혔다'를 부풀리지 않음 |

정의·공식·한계는 [docs/methods.md](docs/methods.md)에 정리했습니다.

## AI로 자동화한 방법

수집기 11개(공연·선정·발매·인스타·웹진·플랫폼 프로필 등)는 공개 API나 페이지 구조가 허용하는 곳은 파이썬 스크립트로, 로그인 없이 보이지만 스크립트 접근이 어려운 페이지는 브라우저 자동화로 읽습니다. 맥이 **매일 21:00** `scripts/daily_run.sh`를 실행해 수집 → 형식 검사 → PostgreSQL 적재 → 대시보드·SQL 결과 문서·랩 데이터 갱신 → 일일 기록 → 커밋·push까지 사람 손 없이 돌립니다. 개발은 **여러 AI 에이전트가 분업**했습니다: 코디네이터 에이전트(Claude Code)가 계획·검토·커밋을 맡고, 작업자 에이전트들이 수집·아티스트 매칭·대시보드를 파일 단위로 나눠 동시에 만들었습니다. 새 코드는 테스트를 먼저 쓰고(현재 테스트 360개 이상), 결정과 그 이유는 [PROJECT.md](PROJECT.md)에 남겼습니다.

---

## 실행 방법

### 처음 한 번: 파이썬 환경 준비

```bash
python3 -m venv .venv                 # 프로젝트 전용 파이썬 공간 (커밋 안 됨)
source .venv/bin/activate             # 터미널을 새로 열 때마다 실행
pip install -r requirements.txt
```

이후 `python3` 명령은 `.venv` 안의 파이썬으로 실행됩니다. 확인한 환경: Python 3.9.6, numpy 2.0.2, voyager 2.2.4.

### 매일 수집 (국내)

매일 21:00에 맥이 `scripts/daily_run.sh`를 자동 실행합니다. 설치·시간 변경: `bash scripts/install_daily.sh 21 0`. 공연·인스타 수집은 브라우저 자동화 앱(aside)이 켜져 있어야 합니다.

```bash
python3 scripts/collect_poclanos.py            # 포크라노스 최근 3일 → data/raw/ (비공개)
python3 scripts/validate_csv.py data/raw/*.csv # 형식 검사
python3 scripts/collect_gigs.py                # 인디고·인디스트릿 공연 7일
python3 scripts/build_site_data.py             # 진행판 공개 데이터 docs/data/collect.json
python3 scripts/daily_note.py                  # 일일 기록 docs/log/
python3 -m unittest discover -s tests          # 테스트
```

형식은 [docs/csv_spec.md](docs/csv_spec.md).

### 분석 (PostgreSQL)

```bash
python3 scripts/load_pg.py                     # 원본 CSV → PostgreSQL raw 스키마
python3 scripts/artist_xref.py --load-pg       # 아티스트 연결표 → ref.artist_xref (+ docs/artist_xref.md)
python3 scripts/run_pg_queries.py              # 기초 뷰 → 분석·검증 SQL → docs/sql/README.md
python3 scripts/backtrace.py                   # 거꾸로 따라가기 → docs/backtrace.md
```

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
