> **현재 방향과 할 일은 [PROJECT.md](PROJECT.md)를 먼저 보세요.** 이 README는 예전 단계(판매 대시보드, 취향 추천 프로토타입)의 사용법입니다.

# Bandcamp Sales Pulse

Bandcamp 판매 피드 데이터를 SQL로 집계하는 글로벌 인디 음악 판매 대시보드.

```
bandcamp-dashboard/
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

## 스키마

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

## 크롤링 CSV에 필요한 컬럼

`stg_salesfeed`와 같은 이름으로 저장하면 그대로 들어갑니다. 없는 컬럼은 NULL이 됩니다.

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

## 처음 한 번: 파이썬 환경 준비

```bash
python3 -m venv .venv                 # 프로젝트 전용 파이썬 공간 (커밋 안 됨)
source .venv/bin/activate             # 터미널을 새로 열 때마다 실행
pip install -r requirements.txt
```

이후 `python3` 명령은 `.venv` 안의 파이썬으로 실행됩니다. 확인한 환경: Python 3.9.6, numpy 2.0.2, voyager 2.2.4.

## 실행

```bash
python3 scripts/build_db.py data/my_crawl.csv
python3 scripts/run_queries.py bandcamp.db data/my_crawl.csv
```

그 뒤 `out/*.json` 8개를 대시보드 Sources에서 파일 교체하면 됩니다.
PostgreSQL에서 쓰려면 `schema.sql` 상단 주석대로 타입과 `strftime`/`date()` 함수를 바꾸면 됩니다.

---

# Bandcamp Taste Match (추천 프로토타입)

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

## 내 데이터로 큐레이션 받기 (명령 한 번)

```bash
export LASTFM_API_KEY=발급받은키          # https://www.last.fm/api/account/create (무료)
python3 scripts/curate.py ~/Downloads/spotify_liked.csv --user me
```
여러 플랫폼 CSV를 한꺼번에 넣어도 됩니다. 키가 없으면 기존 `data/ext_artist_tags.csv`를 씁니다.
결과는 터미널과 `out/curation_<user>.md`에 나오고, `out/reco/*.json`은 대시보드에 올리는 파일입니다.

## Last.fm 태그 수집만 따로

```bash
python3 scripts/fetch_lastfm_tags.py            # data/likes/*.csv 의 모든 아티스트
```
- 의미 없는 태그(seen live, 연도, 국적 등) 제거, 표기 통일(Hip Hop → hip-hop), 점수 10 미만 제외
- 못 찾은 아티스트는 `data/artist_aliases.csv`(artist_name,lastfm_name)로 보정 (예: 혁오,HYUKOH)
- `data/lastfm_report.csv` 아티스트별 결과, `data/lastfm_unmapped_tags.csv` 취향군 매핑이 없는 태그
- 응답은 `data/cache/lastfm/`에 캐시, 초당 4회 이하로 호출

## 앨범 상세 (`data/album_details.csv`)
앨범 페이지 크롤 결과: url, art_id, art_url, release_date, track_count, duration_sec, label, location, about.
대시보드에는 외부 이미지가 바로 안 뜨므로 실제 커버는 업로드한 파일 주소로 넣어야 하고, 없으면 생성형 커버를 그립니다.

## Spotify Voyager로 후보 검색 (선택)

```bash
pip install voyager
python3 scripts/voyager_index.py --k 200
```
Bandcamp 아티스트 태그 벡터로 근사 최근접 이웃 인덱스(`data/bc_artist.voy`)를 만들고,
사용자 취향 벡터로 후보를 빠르게 찾습니다(`reco_ann`). 아티스트끼리 비슷한 팀도 저장합니다(`bc_similar`).
카탈로그가 수십만 팀 이상으로 커지면 "Voyager로 후보 수백 팀 → reco.sql로 정밀 점수" 2단계로 바꿉니다.
최종 추천은 팬 공동구매·발굴 점수로 순위가 바뀌므로, 후보 수(K)는 최종 추천 수보다 넉넉히(수백) 잡아야 합니다.
