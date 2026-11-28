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
