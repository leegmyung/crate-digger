# 플랫폼별 팔로워 변화 — 데이터 점검과 설계 (2026-11-28)

> **왜:** [Chartmetric 대비 점검표](chartmetric_gap_2026-11-28.md)의 빈칸 '지표 변화 타일'(Chartmetric 은 스포티파이·인스타 팔로워 7일/30일 변화를 보여 줌). 우리 팀 개요 '변화' 칸에 **'인스타 팔로워 +n (30일)'** 같은 칸을 넣을 수 있는지 먼저 데이터를 본다.
> **결론:** **아직 못 넣는다.** 같은 팀의 팔로워 수가 두 날짜 이상 쌓인 경우가 인스타 0팀 · 스포티파이 0팀이다. 아래처럼 수집 쪽을 먼저 바꾸고, 3~4주 쌓인 뒤 칸을 켠다.

## 1. 지금 있는 것 (data/raw/, 2026-11-28 확인)

| 플랫폼 | 원본 | 팔로워 수가 있는 팀 | 기록 날짜 | 두 날짜 이상 쌓인 팀 | 값이 바뀐 팀 |
|---|---|---|---|---|---|
| 인스타그램 | `raw_artist_profile_<날짜>_instagram*.csv` 3개 (`fan_count` = 팔로워) | 126 | 11-26 · 11-27 | **0** (날짜마다 다른 팀을 봄) | 0 |
| 스포티파이 | `raw_artist_profile_<날짜>_spotify.csv` 2개 | **0** — `fan_count` 칸이 비어 있음(팔로워 수를 저장하지 않음) | 11-26 · 11-28 | 0 | 0 |
| 멜론 팬 수 (참고) | `raw_artist_profile_<날짜>_melon*.csv` 40개 · `data/raw/state/fan_history.json` | 819 | 11-26 ~ 11-28 | 52 (1~2일 간격) | 3 |

## 2. 먼저 바꿀 것 (수집)

1. **스포티파이:** 아티스트 정보를 받을 때 응답에 이미 있는 `followers.total`을 `fan_count`에 저장한다. 요청을 늘리지 않으므로 하루 예산(`scripts/spotify_budget.py`)은 그대로. (`collect_spotify.py` 는 지금 다른 작업자가 고치는 중이라 그쪽에 넘김)
2. **인스타:** 지금은 계정을 4일마다 차례로 돌아 같은 계정을 다시 보는 간격이 길다. **관찰 목록(관심 팀·후보 상위 100·정답 팀)만이라도 7일마다 다시 보며** 팔로워 수를 남긴다. 로그인 요구로 막히면 늦추는 규칙은 그대로.
3. **멜론:** 팬 수 다시 받기(`profile_refreshed.json`)를 관찰 목록에 주 1회로. 이미 52팀이 두 날짜 이상이다.

## 3. 쌓인 뒤 만들 것 (설계)

- **작은 스크립트 `scripts/followers.py` → `docs/lab/data/followers.csv`** (`export_lab_data.py` 는 건드리지 않음):
  칸 `team_key, platform(instagram|spotify|melon), latest_date, latest, base_date, base, change, change_pct`.
  `base` = `latest_date`보다 **21~35일 앞**에서 가장 가까운 기록(없으면 그 팀·플랫폼 줄을 쓰지 않음 — 짧은 간격 변화를 30일 변화처럼 보이지 않게). 팀 키는 `artist_xref.canonical_key`(팀 표와 같은 규칙). 팔로워 수는 이미 공개된 숫자라 팀 이름과 같이 내보내도 된다(인스타 계정명은 내보내지 않음).
- **`scripts/update_meta_extras.py` EXTRAS 에 `followers.csv` 등록** — 없거나 빈 파일이면 앱이 받지 않는다(404 없음).
- **앱 팀 개요 '변화' 칸**(`views/team_pulse.js` `renderChangeRowHtml` 옆): 플랫폼 줄마다 '인스타 팔로워 1.2천 → 1.5천 (+25%, 30일)'. 값이 없으면 칸을 숨긴다(0과 구별). 핵심 숫자 4칸은 그대로 두고 변화 칸에만 넣는다.
- **검증:** 팔로워 증가가 정답보다 먼저 오는지(리드타임)는 기록이 3개월 넘게 쌓인 뒤 `score_tune`처럼 따로 잰다. 그 전에는 화면 정보로만 쓰고 점수에 넣지 않는다.

## 4. 언제 다시 보나

수집 변경이 들어간 날부터 **4주 뒤** 이 표(1절)를 다시 센다. 관찰 목록에서 '21일 이상 떨어진 두 기록이 있는 팀'이 50팀을 넘으면 3절을 만든다.

## 5. 시작한 것 (2026-11-28 오후)

- **스포티파이** `collect_spotify.py`: 검색 응답에 `followers.total` 이 있으면 `data/raw/state/followers_spotify.jsonl` 에 `{team_key, spotify_id, date, followers}` 한 줄 (추가 요청 없음). ⚠️ 두 가지 한계 — ① 2026 개발자 모드에선 팔로워가 비어 올 수 있다(수집기 설명에 그렇게 적혀 있음, 다음 실제 실행에서 확인) ② 새 이름을 **처음 찾을 때만** 검색하므로 팀마다 한 번만 남는다. 날짜별로 쌓으려면 관찰 목록을 주 1회 `/v1/artists?ids=`(50팀씩, 300팀이면 요청 6번)로 받는 단계가 따로 필요 — 하루 예산을 조금 쓰는 일이라 결정이 필요하다.
- **관찰 목록** `scripts/followers_watch.py`: 상위 300(`coverage_targets.json`) + 앱에서 내려받은 관심 팀 CSV(`data/raw/review/watchlist*.csv`) → `data/raw/state/followers_watch.json`, 멜론 추가 번호(`followers_watch_melon_extra.txt`, 상위 300 밖 관심 팀만 — 상위 팀은 `--refresh` 가 이미 7일마다), 인스타 계정(`followers_watch_instagram.txt`). 첫 실행: 300팀 · 인스타 계정 15개(links.csv 에 인스타 주소가 있는 팀이 적음).
- **인스타** `collect_ig_artists.py --handles-file`: 그 계정을 이미 봤어도 마지막으로 받은 지 7일 지났으면 다시 열어 팔로워 수를 남긴다(처음 보는 계정 먼저, 그다음 오래된 순).
- **뼈대** `scripts/followers.py` (+테스트): 지금 팀·플랫폼 기록 908개, 30일 비교 가능 0줄.

**daily_run.sh 월요일 블록에 넣을 줄 (제안 — aside 묶음 안, 인스타 매거진 수집 앞):**

```bash
if [ "$(TZ=Asia/Seoul date +%u)" = 1 ]; then
  "$PY" scripts/followers_watch.py || echo "⚠️ 팔로워 관찰 목록 실패"
  [ -s data/raw/state/followers_watch_melon_extra.txt ] && { "$PY" scripts/collect_artists.py --ids-file data/raw/state/followers_watch_melon_extra.txt || echo "⚠️ 관심 팀 멜론 팬 수 다시 받기 실패"; }
  "$PY" scripts/collect_ig_artists.py --handles-file data/raw/state/followers_watch_instagram.txt --limit 100 || echo "⚠️ 관찰 팀 인스타 팔로워 다시 보기 실패"
fi
```
`scripts/followers.py` 와 EXTRAS 등록은 4주 뒤(21일 이상 떨어진 기록이 50팀을 넘으면) 넣는다.

## 6. 스포티파이 주 1회 · 인스타 연결 보강 (2026-11-28 저녁)

- **스포티파이 주 1회** `scripts/followers_spotify_weekly.py` (+테스트 5): 관찰 팀 중 links.csv 에 스포티파이 아티스트 주소가 있는 팀을 `/v1/artists?ids=` 50팀씩. 하루 예산·429 는 `spotify_budget` 공유, 멈추면 이번 주는 끝(다음 주에 다시), 6일 안에 돌았으면 건너뜀. 팔로워가 비어 오면(개발자 모드) 기록하지 않고 상태 파일 `followers_spotify_weekly.json`의 `empty_last`에 수만 남김. **지금 대상은 300팀 중 27팀뿐**(links.csv 스포티파이 주소; `spotify_match.json` 이름 짝을 더해도 30팀) → 요청 1번/주.
- **인스타 연결 보강** — 이미 있는 원본으로는 관찰 300팀에 새로 붙는 팀이 **0**이었다: MusicBrainz 인스타 146팀 중 관찰 안 12팀(이미 links.csv), 인스타 프로필 이름·계정 정확 일치 36팀 중 관찰 안 2팀(이미 있음), 연결표(artist_xref)의 '확신 낮음' 후보 132개는 관찰 팀에 없음, 게시물 캡션+태그로 분명한 후보 1팀. 관찰 팀은 대부분 인디스트릿 공연으로 들어온 팀이고, 우리 인스타 원본은 매거진 태그라 사는 동네가 다르다.
  → 새 방법: **인디스트릿 아티스트 페이지의 구조화 데이터(JSON-LD) `sameAs`** = 팀이 직접 적은 공식 채널. `scripts/collect_indistreet_sns.py` (+테스트 4): 인디스트릿 공연 원본의 artist_url 로 팀 ↔ 페이지(페이지가 여럿인 팀 = 동명 의심 → 뺌), sameAs 안 인스타가 정확히 하나일 때만. robots.txt 허용(/artists/), 한 번에 한 페이지, 30일마다 다시.
  **결과: 관찰 팀 263페이지(1분 29초, 실패 0) → sameAs 있음 37 · 인스타 33팀(새 연결 31) → 관찰 300팀 인스타 15 → 46.** 덤으로 sameAs 에 유튜브 18 · 애플뮤직 5 · 스포티파이 4.
  `followers_watch.py` 가 이 파일로 links.csv 빈칸을 채우므로 월요일 인스타 다시 보기 대상이 바로 46개가 된다.
- **export_lab_data.py 에 넣을 곳 (제안, 직접 안 고침)**: `extra_refs()`에서 artist_xref 다음·musicbrainz 앞에
  ```python
  INDISTREET_SNS = ROOT / "data" / "raw" / "state" / "indistreet_sns.json"
  refs += [{"team_key": k, "platform": "instagram", "ref": v["instagram"]}
           for k, v in _read_json_dict(INDISTREET_SNS).items() if isinstance(v, dict) and v.get("instagram")]
  ```
  (팀이 직접 적은 계정이라 확신 high 와 같게 본다. sameAs 의 유튜브·스포티파이도 같은 자리에서 `link_rows` 주소 검사를 거쳐 넣을 수 있음.)
- **daily_run.sh 월요일 블록에 더할 줄 (제안)** — 5절 블록 안, `followers_watch.py` 바로 앞:
  ```bash
  "$PY" scripts/collect_indistreet_sns.py || echo "⚠️ 인디스트릿 공식 SNS 실패"          # 30일 지난 팀만 (약 1~2분)
  ```
  스포티파이 묶음 단계(다른 스포티파이 단계 뒤, 예산 공유):
  ```bash
  [ "$(TZ=Asia/Seoul date +%u)" = 1 ] && { "$PY" scripts/followers_spotify_weekly.py || echo "⚠️ 스포티파이 팔로워 주 1회 실패"; }
  ```

## 7. 인디스트릿 sameAs 넓히기 (2026-11-28 밤)

- 대상: 관찰 300팀 → **오늘 점수 상위 500 + 정답 팀 + 인디스트릿 공연 기록이 최근 2년 안에 있는 팀 전체**(페이지 하나뿐인 팀만) = 3,920팀. 첫 회는 `--limit 1000` 4번에 나눠 돌림(한 번에 한 페이지, 실패 0). 이후 매주 월요일 30일 지난 팀만.
- export_lab_data `indistreet_sns_refs`: 인스타에 더해 sameAs 의 **유튜브 채널 주소**(@이름·channel/UC…·c/…·user/…)와 **스포티파이 아티스트 주소**(번호로)도 연결 — 각각 하나뿐일 때만, 영상·앨범·유튜브 뮤직 주소는 뺌(테스트 2개).
- **결과(links.csv 대비 새로 붙는 팀): 인스타 204 · 유튜브 69 · 스포티파이 46** (sameAs 연결 줄 인스타 226 · 유튜브 83 · 스포티파이 50).
- 사진·듣기 추정(새 유튜브 채널 → collect_yt_channels 아바타·최신 영상, 새 스포티파이 → 사진·플레이어; 최대치):

| 묶음 | 새 연결 (인스타 · 유튜브 · 스포티파이) | 사진 | 바로 듣기 |
|---|---|---|---|
| 상위 300 | 31 · 10 · 4 | 36팀 (12%) → 최대 +10 (15%) | 67팀 (22%) → 최대 +7 (25%) |
| 상위 500 | 36 · 11 · 4 | 42팀 (8%) → 최대 +11 (11%) | 85팀 (17%) → 최대 +8 (19%) |
| 정답 팀 714 | 44 · 9 · 7 | 202팀 (28%) → 최대 +10 (30%) | 406팀 (57%) → 최대 +2 (57%) |

  인디스트릿 페이지 대부분(3,920 중 sameAs 를 채운 곳은 일부)이 공식 채널을 비워 두어 사진·듣기 상승은 몇 %p 수준. 적재(export → collect_yt_channels → export) 뒤 실제 숫자는 `scripts/coverage_targets.py` 로 다시 센다.
