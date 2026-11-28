# 데이터 사전

_자동 생성: `python3 scripts/build_data_dictionary.py` — 칸 이름은 코드(scripts/csv_schema.py, scripts/export_lab_data.py, 수집기 상수)에서 읽고, 설명은 build_data_dictionary.COLUMN_DOC 에 있습니다. 칸이 바뀌면 테스트가 알려 줍니다._

## 한눈에

| 표 | 위치 | 공개 | 갈래/쓰임 | 갱신 |
|---|---|---|---|---|
| `raw_artist_profile` | `data/raw/raw_artist_profile_<날짜>.csv` | 비공개 | 프로필 | 매일 21시 |
| `raw_kr_release` | `data/raw/raw_kr_release_<날짜>.csv` | 비공개 | 발매 | 매일 21시 |
| `raw_kr_gig` | `data/raw/raw_kr_gig_<날짜>.csv` | 비공개 | 공연 | 매일 21시 |
| `raw_press` | `data/raw/raw_press_<날짜>.csv` | 비공개 | 큐레이션 | 매일 21시 |
| `raw_kr_selection` | `data/raw/raw_kr_selection_<날짜>.csv` | 비공개 | 선정·지원 | 매일 21시 |
| `raw_outcome` | `data/raw/raw_outcome_<날짜>.csv` | 비공개 | 정답 | 매일 21시 |
| `raw_video` | `data/raw/raw_video_<날짜>.csv` | 비공개 | 보조(팀 상세 영상) | 매일 21시 |
| `raw_collab` | `data/raw/raw_collab_<날짜>.csv` | 비공개 | 협업 (검증 대기) | 매일 21시 |
| `raw_collab_partner` | `data/raw/raw_collab_partner_<날짜>.csv` | 비공개 | 협업 (검증 대기) | 매일 21시 |
| `signals` | `docs/lab/data/signals.csv` | 공개 | 신호 | 매일 21시 (export_lab_data.py) |
| `teams` | `docs/lab/data/teams.csv` | 공개 | 팀 | 매일 21시 (export_lab_data.py) |
| `outcomes` | `docs/lab/data/outcomes.csv` | 공개 | 정답 | 매일 21시 (export_lab_data.py) |
| `programs` | `docs/lab/data/programs.csv` | 공개 | 참고 | 매일 21시 (export_lab_data.py) |
| `links` | `docs/lab/data/links.csv` | 공개 | 보조 | 매일 21시 (export_lab_data.py) |
| `images` | `docs/lab/data/images.csv` | 공개 | 보조 | 매일 21시 (export_lab_data.py) |
| `players` | `docs/lab/data/players.csv` | 공개 | 보조 | 매일 21시 (export_lab_data.py) |
| `videos` | `docs/lab/data/videos.csv` | 공개 | 보조 | 매일 21시 (export_lab_data.py) |
| `collabs` | `docs/lab/data/collabs.csv` | 공개 | 협업 (검증 대기) | 매일 21시 (export_lab_data.py) |
| `snapshots` | `docs/lab/data/snapshots/<날짜>.csv` | 공개 | 점수 기록 | 매일 21시 (lab_snapshot.py, 최근 것만 보관) |

데이터 흐름: 수집기 → 원본 CSV(`data/raw/`, 비공개) → PostgreSQL(raw → core 뷰, 팀·공연장 묶기) → 랩 데이터(`docs/lab/data/`, 공개) → 앱·SQL 결과·엑셀.

## 1. 공개 랩 데이터 (`docs/lab/data/`)

### `signals`

- 위치: `docs/lab/data/signals.csv` · 공개
- 출처: PostgreSQL core.v_signal (원본 4갈래를 한 표로, 팀·공연장 묶기 적용) · 갈래/쓰임: 신호 · 갱신: 매일 21시 (export_lab_data.py)

| 칸 | 뜻·단위 | 형식 |
|---|---|---|
| `team_key` | 팀 대표 키 (아티스트 연결표로 같은 팀의 여러 표기를 하나로) | — |
| `branch` | 신호 갈래 (공연·큐레이션·선정·지원·발매) | — |
| `source` | 수집 출처 코드 | — |
| `program` | 프로그램 코드 (선정·지원 또는 정답) | — |
| `stage_rank` | 선정 단계 점수 0~4 (응모 0 … 최종 4) | — |
| `signal_date` | 신호 날짜 (일부만 아는 날짜는 기간의 마지막 날 — 시점 누수 방지) | — |
| `venue` | 공연장 대표 이름 (공연장 표기 묶기 적용) | — |
| `role` | 출처 역할 (discovery 발굴 / context 맥락 / pending 검증 대기 / excluded 제외) | — |

### `teams`

- 위치: `docs/lab/data/teams.csv` · 공개
- 출처: 팀별 첫 등장 + 멜론·스포티파이 프로필 · 갈래/쓰임: 팀 · 갱신: 매일 21시 (export_lab_data.py)

| 칸 | 뜻·단위 | 형식 |
|---|---|---|
| `team_key` | 팀 대표 키 (아티스트 연결표로 같은 팀의 여러 표기를 하나로) | — |
| `display_name` | 화면에 보일 팀 이름 | — |
| `first_seen` | 우리 데이터에 처음 나온 날 | — |
| `first_release` | 프로필 첫 발매일 (없으면 빈 칸). 사람이 확인한 데뷔일(config/debut_overrides.json)이 더 이르면 그 날짜 | — |
| `fan_count` | 플랫폼 팬(좋아요) 수, 명 | — |
| `album_count` | 플랫폼에 올라온 앨범 수(싱글 포함), 개 | — |
| `profile_status` | 팀 상태 (newcomer 신인 / established 기성 / famous 유명 / unknown 프로필 없음) | — |
| `primary_genre` | 대표 장르 (사람이 확인한 장르 config/genre_overrides.json 이 있으면 그것, 빈칸은 추정으로 채움 — genre_confidence) | — |
| `agency` | 소속사 | — |
| `newcomer_check` | 신인 판정 확인 상태 — verified 첫 발매일 있음(사람 확인 데뷔일 포함) / unverified 첫 발매일 없고 그 팀을 처음 본 출처의 수집 시작 90일 안에 처음 봄(그 전부터 활동했을 수 있어 신인인지 확실치 않음) / first_seen 첫 발매일 없고 그 뒤에 처음 봄. 표시용 — 점수·후보군엔 안 씀 | — |
| `genre_confidence` | 대표 장르의 확신도 — profile 멜론·발매 장르·사람 확인 / press 확실한 출처 힌트(리드머·밴드 디스커버리) / inferred 같은 무대 다수결·공연장 성향·약한 출처 힌트로 추정 / review 매체 리뷰 장르(음악취향Y·overtone·VISLA) / inferred_low 같은 무대에 장르 아는 팀이 1팀뿐(확신 낮음) — 이 셋은 앱 필터·표시에만('추정' 꼬리표), 비교·분석엔 안 씀(docs/genre_fill.md) / 빈칸 모름 | — |

### `outcomes`

- 위치: `docs/lab/data/outcomes.csv` · 공개
- 출처: 정답 + 등급 (config/source_roles.json) · 갈래/쓰임: 정답 · 갱신: 매일 21시 (export_lab_data.py)

| 칸 | 뜻·단위 | 형식 |
|---|---|---|
| `team_key` | 팀 대표 키 (아티스트 연결표로 같은 팀의 여러 표기를 하나로) | — |
| `program` | 프로그램 코드 (선정·지원 또는 정답) | — |
| `program_label` | 프로그램 한글 이름 | — |
| `tier` | 정답 단계 (final 최종 / mid 중간) | — |
| `result` | 결과 (선정·수상·후보 등) | — |
| `announced_date` | 정답 발표일 (일부만 알면 기간의 첫날 — 보수적) | — |
| `counted` | 센 정답인지 (기성 팀 연차 규칙 통과) true/false | — |
| `grade` | 정답 등급 S·A·B | — |
| `weight` | 정답 등급 가중치 (S=3·A=2·B=1) | — |
| `same_house_sources` | 정답 발표 전에 이 팀을 실은 같은 집안 출처 (그 출처의 적중으로 안 셈) | — |
| `same_house_scored` | 같은 집안 출처가 점수에 쓰는 출처면 true — 점수 백테스트 적중에서도 뺌 | — |

### `programs`

- 위치: `docs/lab/data/programs.csv` · 공개
- 출처: 선정·지원·정답 프로그램 이름표 · 갈래/쓰임: 참고 · 갱신: 매일 21시 (export_lab_data.py)

| 칸 | 뜻·단위 | 형식 |
|---|---|---|
| `program` | 프로그램 코드 (선정·지원 또는 정답) | — |
| `label` | 프로그램 한글 이름 | — |
| `kind` | 프로그램 종류 (signal 신호 / outcome 정답) | — |

### `links`

- 위치: `docs/lab/data/links.csv` · 공개
- 출처: 플랫폼 아티스트 페이지 연결 (동명 없는 것만) · 갈래/쓰임: 보조 · 갱신: 매일 21시 (export_lab_data.py)

| 칸 | 뜻·단위 | 형식 |
|---|---|---|
| `team_key` | 팀 대표 키 (아티스트 연결표로 같은 팀의 여러 표기를 하나로) | — |
| `platform` | 플랫폼 (spotify·melon·instagram·youtube 등) | — |
| `url` | 아티스트 페이지 주소 | — |

### `images`

- 위치: `docs/lab/data/images.csv` · 공개
- 출처: 아티스트 사진 주소 (스포티파이 → 유튜브 공식 채널 아바타) · 갈래/쓰임: 보조 · 갱신: 매일 21시 (export_lab_data.py)

| 칸 | 뜻·단위 | 형식 |
|---|---|---|
| `team_key` | 팀 대표 키 (아티스트 연결표로 같은 팀의 여러 표기를 하나로) | — |
| `url` | 사진 주소 (i.scdn.co · yt3.ggpht.com · yt3.googleusercontent.com 의 https 만) | — |
| `source` | 사진 출처 (spotify 먼저, 없으면 youtube 공식 채널 아바타) | — |
| `page_url` | 사진 출처 페이지 (스포티파이 아티스트·유튜브 채널) — 사진 옆 출처 링크용 | — |

### `players`

- 위치: `docs/lab/data/players.csv` · 공개
- 출처: 바로 듣기: 팀마다 스포티파이·대표 유튜브 영상·확인된 iTunes 미리듣기 각 1줄 (scripts/players.py·collect_itunes.py) · 갈래/쓰임: 보조 · 갱신: 매일 21시 (export_lab_data.py)

| 칸 | 뜻·단위 | 형식 |
|---|---|---|
| `team_key` | 팀 대표 키 (아티스트 연결표로 같은 팀의 여러 표기를 하나로) | — |
| `kind` | 재생 종류 (spotify 아티스트 삽입 재생 / youtube 영상 삽입 재생 / itunes 30초 미리듣기 오디오) | — |
| `id` | 재생 번호 (spotify: 'artist:<22자>', youtube: 영상 번호 11자, itunes: https 미리듣기 주소) | — |
| `title` | 영상 제목 (spotify 는 빈칸) | — |
| `channel_title` | 영상 올린 채널 (spotify 는 빈칸) | — |
| `source` | 고른 근거 (spotify / official 팀 공식 채널 / stage 무대 채널 / search 검색 / itunes) | — |
| `published_at` | 영상 올린 날 YYYY-MM-DD (spotify 는 빈칸) | — |
| `view_count` | 가장 최근 조회수 (모르면 빈칸) | — |
| `page_url` | 원래 페이지 (스포티파이 아티스트·유튜브 영상·Apple Music 곡) — iTunes 는 약관상 링크 필수 | — |

### `videos`

- 위치: `docs/lab/data/videos.csv` · 공개
- 출처: 팀별 무대·공식 영상 (최대 6개) · 갈래/쓰임: 보조 · 갱신: 매일 21시 (export_lab_data.py)

| 칸 | 뜻·단위 | 형식 |
|---|---|---|
| `team_key` | 팀 대표 키 (아티스트 연결표로 같은 팀의 여러 표기를 하나로) | — |
| `video_id` | 유튜브 영상 번호 (11자) | — |
| `title` | 제목 | — |
| `channel_title` | 채널 이름 | — |
| `published_at` | 게시일 | — |
| `kind` | 영상 종류 (stage 무대·official_live·official·search) | — |

### `collabs`

- 위치: `docs/lab/data/collabs.csv` · 공개
- 출처: 스포티파이 협업 (기성 파트너 판정 포함) · 갈래/쓰임: 협업 (검증 대기) · 갱신: 매일 21시 (export_lab_data.py)

| 칸 | 뜻·단위 | 형식 |
|---|---|---|
| `team_key` | 팀 대표 키 (아티스트 연결표로 같은 팀의 여러 표기를 하나로) | — |
| `partner_key` | 협업 상대의 팀 대표 키 | — |
| `partner_name` | 협업 상대 이름 | — |
| `release_date` | 협업곡 발매일 (일부만 알면 기간의 마지막 날) | — |
| `role` | 협업 형태 (co_lead / feat_on_own / guest_on_partner) | — |
| `partner_established` | 협업 당시 상대가 기성 아티스트였나 true/false (첫 발매 5년 이상 앞섬·앨범 15개 이상·유명·이미 수상) | — |

### `snapshots`

- 위치: `docs/lab/data/snapshots/<날짜>.csv` · 공개
- 출처: 날짜별 점수 상위 300팀 (snapshots/<날짜>.csv) · 갈래/쓰임: 점수 기록 · 갱신: 매일 21시 (lab_snapshot.py, 최근 것만 보관)

| 칸 | 뜻·단위 | 형식 |
|---|---|---|
| `team_key` | 팀 대표 키 (아티스트 연결표로 같은 팀의 여러 표기를 하나로) | — |
| `score` | 그날 점수 (점수 v2) | — |
| `rank` | 그날 순위 | — |

## 2. 원본 수집 표 (비공개)

실제 수집 원본은 공개 저장소에 올리지 않습니다. 형식 규칙은 `scripts/csv_schema.py`·[csv_spec.md](csv_spec.md).

### `raw_artist_profile`

- 위치: `data/raw/raw_artist_profile_<날짜>.csv` · **비공개** (실제 수집 원본, 저장소에 안 올림 — 이름·칸만)
- 출처: 멜론·스포티파이·인스타 아티스트 페이지 · 갈래/쓰임: 프로필 · 갱신: 매일 21시
- 같은 행 판단 칸: `source`, `artist_source_id`

| 칸 | 뜻·단위 | 형식 |
|---|---|---|
| `collected_at` | 수집한 시각 | 날짜시각(시간대 포함) |
| `source` | 수집 출처 코드 | 코드(정해진 값) |
| `collector` | 수집 방법 (script=스크립트, aside=브라우저 자동화, manual=손으로) | 코드(정해진 값) |
| `artist_source_id` | 출처 안의 아티스트 번호 | 글자 |
| `artist_text` | 출처에 적힌 아티스트 이름 그대로 | 글자 |
| `debut_date` | 데뷔일 | 날짜(연·월만도 가능) |
| `debut_title` | 데뷔 곡·앨범 | 글자 |
| `activity_type` | 활동 유형 (솔로·그룹 등) | 글자 |
| `agency_text` | 소속사 | 글자 |
| `genre` | 장르 (여러 개면 |) | 글자 |
| `nationality` | 국적 | 글자 |
| `fan_count` | 플랫폼 팬(좋아요) 수, 명 | 정수(0 이상) |
| `album_count` | 플랫폼에 올라온 앨범 수(싱글 포함), 개 | 정수(0 이상) |
| `first_release_date` | 가장 오래된 발매일 (앨범 목록 전체 — 참여·소속 밴드 음반 포함) | 날짜(연·월만도 가능) |
| `first_release_own` | 본인 음반만의 가장 오래된 발매일 (앨범 아티스트에 이 팀 번호가 있는 음반, 2026-11-28부터, 없으면 빈칸) | 날짜(연·월만도 가능) |
| `youtube_url` | 아티스트 페이지에 걸린 유튜브 채널 주소 | 주소(URL) |
| `url` | 원문 주소 | 주소(URL) |
| `artist_key` | 정규화한 이름 키 (공백·기호 제거, 소문자) | 글자 |

### `raw_kr_release`

- 위치: `data/raw/raw_kr_release_<날짜>.csv` · **비공개** (실제 수집 원본, 저장소에 안 올림 — 이름·칸만)
- 출처: 포크라노스·멜론·벅스·지니·FLO 신보 · 갈래/쓰임: 발매 · 갱신: 매일 21시
- 같은 행 판단 칸: `source`, `release_url`, `artist_text`

| 칸 | 뜻·단위 | 형식 |
|---|---|---|
| `collected_at` | 수집한 시각 | 날짜시각(시간대 포함) |
| `source` | 수집 출처 코드 | 코드(정해진 값) |
| `collector` | 수집 방법 (script=스크립트, aside=브라우저 자동화, manual=손으로) | 코드(정해진 값) |
| `source_id` | 출처 안의 번호 | 글자 |
| `released_at` | 발매일 | 날짜(연·월만도 가능) |
| `artist_text` | 출처에 적힌 아티스트 이름 그대로 | 글자 |
| `artist_source_id` | 출처 안의 아티스트 번호 | 글자 |
| `title` | 제목 | 글자 |
| `release_type` | 발매 형태 (single·EP·LP 등) | 코드(정해진 값) |
| `genre` | 장르 (여러 개면 |) | 글자 |
| `label_text` | 기획사·레이블 | 글자 |
| `track_count` | 수록곡 수, 곡 | 정수(1 이상) |
| `release_url` | 발매 페이지 주소 | 주소(URL) |
| `distributor_text` | 유통사 | 글자 |
| `artist_key` | 정규화한 이름 키 (공백·기호 제거, 소문자) | 글자 |
| `title_key` | 정규화한 제목 키 (여러 플랫폼 동시 발매 묶기) | 글자 |

### `raw_kr_gig`

- 위치: `data/raw/raw_kr_gig_<날짜>.csv` · **비공개** (실제 수집 원본, 저장소에 안 올림 — 이름·칸만)
- 출처: 인디스트릿·인디고·상상마당 공연 목록 · 갈래/쓰임: 공연 · 갱신: 매일 21시
- 같은 행 판단 칸: `source`, `gig_url`, `artist_text`

| 칸 | 뜻·단위 | 형식 |
|---|---|---|
| `collected_at` | 수집한 시각 | 날짜시각(시간대 포함) |
| `source` | 수집 출처 코드 | 코드(정해진 값) |
| `collector` | 수집 방법 (script=스크립트, aside=브라우저 자동화, manual=손으로) | 코드(정해진 값) |
| `source_id` | 출처 안의 번호 | 글자 |
| `gig_date` | 공연 날짜 | 날짜 YYYY-MM-DD |
| `gig_time` | 공연 시작 시각 | 시각 HH:MM |
| `title` | 제목 | 글자 |
| `venue_text` | 공연장 (괄호 안 주소 포함) | 글자 |
| `artist_text` | 출처에 적힌 아티스트 이름 그대로 | 글자 |
| `artist_source_id` | 출처 안의 아티스트 번호 | 글자 |
| `gig_url` | 공연 페이지 주소 | 주소(URL) |
| `artist_url` | 출처의 아티스트 페이지 주소 | 주소(URL) |
| `lineup_order` | 실제 출연 순서 (1 = 첫 무대, 공연 설명의 타임테이블에서만 — 없으면 빈 칸) | 정수(1 이상) |
| `lineup_time` | 그 팀 무대 시작 시각 (타임테이블) | 시각 HH:MM |
| `lineup_size` | 그 공연 페이지의 출연 팀 수 | 정수(1 이상) |

### `raw_press`

- 위치: `data/raw/raw_press_<날짜>.csv` · **비공개** (실제 수집 원본, 저장소에 안 올림 — 이름·칸만)
- 출처: 웹진(음악취향Y·IZM·리드머·weiv·VISLA·overtone)·인스타 매거진·공연장 라인업 공지 · 갈래/쓰임: 큐레이션 · 갱신: 매일 21시
- 같은 행 판단 칸: `url`, `artist_text`

| 칸 | 뜻·단위 | 형식 |
|---|---|---|
| `collected_at` | 수집한 시각 | 날짜시각(시간대 포함) |
| `source` | 수집 출처 코드 | 코드(정해진 값) |
| `collector` | 수집 방법 (script=스크립트, aside=브라우저 자동화, manual=손으로) | 코드(정해진 값) |
| `outlet` | 매체·계정 이름 | 글자 |
| `published_at` | 게시일 | 날짜 또는 날짜시각 |
| `title` | 제목 | 글자 |
| `url` | 원문 주소 | 주소(URL) |
| `artist_text` | 출처에 적힌 아티스트 이름 그대로 | 글자 |
| `release_title` | 다룬 곡·앨범 제목 | 글자 |
| `is_pick` | 추천·선정 글이면 1 | 0/1 |
| `pick_label` | 추천 꼭지 이름 (venue_lineup = 공연장 라인업 공지 → 공연 갈래로 셈) | 글자 |
| `artist_handle` | 태그된 아티스트 인스타 계정 | 인스타 계정명 |
| `is_sponsored` | 협찬·광고 글이면 1 (신호에서 뺌) | 0/1 |
| `genre` | 장르 (여러 개면 |) | 글자 |

### `raw_kr_selection`

- 위치: `data/raw/raw_kr_selection_<날짜>.csv` · **비공개** (실제 수집 원본, 저장소에 안 올림 — 이름·칸만)
- 출처: 부산 루키즈·뮤즈 인 세종·경북 창작소·유재하 경연·밴드 디스커버리·DMZ · 갈래/쓰임: 선정·지원 · 갱신: 매일 21시
- 같은 행 판단 칸: `program`, `round`, `stage`, `artist_text`

| 칸 | 뜻·단위 | 형식 |
|---|---|---|
| `collected_at` | 수집한 시각 | 날짜시각(시간대 포함) |
| `source` | 수집 출처 코드 | 코드(정해진 값) |
| `collector` | 수집 방법 (script=스크립트, aside=브라우저 자동화, manual=손으로) | 코드(정해진 값) |
| `program` | 프로그램 코드 (선정·지원 또는 정답) | 코드(정해진 값) |
| `round` | 회차 | 글자 |
| `stage` | 단계 (응모·서류·선정·최종 등) | 코드(정해진 값) |
| `announced_at` | 발표일 | 날짜(연·월만도 가능) |
| `artist_text` | 출처에 적힌 아티스트 이름 그대로 | 글자 |
| `url` | 원문 주소 | 주소(URL) |
| `note` | 메모 | 글자 |

### `raw_outcome`

- 위치: `data/raw/raw_outcome_<날짜>.csv` · **비공개** (실제 수집 원본, 저장소에 안 올림 — 이름·칸만)
- 출처: 신인상·주요 신인 프로그램 발표 (손으로 확인한 것 포함) · 갈래/쓰임: 정답 · 갱신: 매일 21시
- 같은 행 판단 칸: `program`, `round`, `artist_text`, `result`

| 칸 | 뜻·단위 | 형식 |
|---|---|---|
| `collected_at` | 수집한 시각 | 날짜시각(시간대 포함) |
| `source` | 수집 출처 코드 | 코드(정해진 값) |
| `collector` | 수집 방법 (script=스크립트, aside=브라우저 자동화, manual=손으로) | 코드(정해진 값) |
| `program` | 프로그램 코드 (선정·지원 또는 정답) | 코드(정해진 값) |
| `round` | 회차 | 글자 |
| `announced_at` | 발표일 | 날짜(연·월만도 가능) |
| `result` | 결과 (선정·수상·후보 등) | 코드(정해진 값) |
| `artist_text` | 출처에 적힌 아티스트 이름 그대로 | 글자 |
| `url` | 원문 주소 | 주소(URL) |
| `note` | 메모 | 글자 |

### `raw_video`

- 위치: `data/raw/raw_video_<날짜>.csv` · **비공개** (실제 수집 원본, 저장소에 안 올림 — 이름·칸만)
- 출처: 유튜브 Data API (공식 채널·무대 채널) · 갈래/쓰임: 보조(팀 상세 영상) · 갱신: 매일 21시

| 칸 | 뜻·단위 | 형식 |
|---|---|---|
| `collected_at` | 수집한 시각 | — |
| `team_key` | 팀 대표 키 (아티스트 연결표로 같은 팀의 여러 표기를 하나로) | — |
| `display_name` | 화면에 보일 팀 이름 | — |
| `video_id` | 유튜브 영상 번호 (11자) | — |
| `title` | 제목 | — |
| `channel_title` | 채널 이름 | — |
| `channel_id` | 채널 번호 | — |
| `published_at` | 게시일 | — |
| `kind` | 영상 종류 (stage 무대·official_live·official·search) | — |
| `source_channel_handle` | 찾은 채널 계정 (@…) | — |

### `raw_collab`

- 위치: `data/raw/raw_collab_<날짜>.csv` · **비공개** (실제 수집 원본, 저장소에 안 올림 — 이름·칸만)
- 출처: 스포티파이 Web API (피처링·공동 참여 곡) · 갈래/쓰임: 협업 (검증 대기) · 갱신: 매일 21시

| 칸 | 뜻·단위 | 형식 |
|---|---|---|
| `collected_at` | 수집한 시각 | — |
| `artist_name` | 우리 팀 이름 (스포티파이 표기) | — |
| `artist_spotify_id` | 우리 팀 스포티파이 번호 | — |
| `partner_spotify_id` | 상대 스포티파이 번호 | — |
| `partner_name` | 협업 상대 이름 | — |
| `track_id` | 곡 번호 | — |
| `track_name` | 곡 이름 | — |
| `album_id` | 앨범 번호 | — |
| `album_name` | 앨범 이름 | — |
| `release_date` | 협업곡 발매일 (일부만 알면 기간의 마지막 날) | — |
| `release_date_precision` | 발매일 정밀도 (year·month·day) | — |
| `role` | 협업 형태 (co_lead 공동 주인 / feat_on_own 우리 곡에 피처링 / guest_on_partner 상대 곡에 참여) | — |
| `album_group` | 앨범 구분 (album·single·appears_on 등) | — |

### `raw_collab_partner`

- 위치: `data/raw/raw_collab_partner_<날짜>.csv` · **비공개** (실제 수집 원본, 저장소에 안 올림 — 이름·칸만)
- 출처: 스포티파이 Web API (협업 상대 프로필) · 갈래/쓰임: 협업 (검증 대기) · 갱신: 매일 21시

| 칸 | 뜻·단위 | 형식 |
|---|---|---|
| `collected_at` | 수집한 시각 | — |
| `partner_spotify_id` | 상대 스포티파이 번호 | — |
| `partner_name` | 협업 상대 이름 | — |
| `first_release_date` | 가장 오래된 발매일 (앨범 목록 전체 — 참여·소속 밴드 음반 포함) | — |
| `album_count` | 플랫폼에 올라온 앨범 수(싱글 포함), 개 | — |
| `edge_count` | 우리 팀들과의 협업 곡 수 | — |

## 3. 공개 JSON 파일

### `docs/lab/data/meta.json`

| 칸 | 뜻 |
|---|---|
| `prev_rows` | 직전 날짜의 표별 행 수 (앱의 '새로 붙은 수') |
| `generated_at` | 만든 시각 |
| `data_end` | 데이터 끝 날짜 (기준일) |
| `uses_artist_xref` | 아티스트 연결표를 썼는지 |
| `rows` | 표별 행 수 |
| `scene_communities` | 씬 묶음 수 (scripts/build_scene_map.py가 적음) |
| `extras` | 있는 보조 데이터 파일 이름 목록 (scripts/update_meta_extras.py) |
| `extras_rows` | 보조 데이터 파일별 행 수(JSON은 true) |
| `extras_updated_at` | 보조 데이터 목록을 적은 시각 |

### `docs/lab/data/source_roles.json`

| 칸 | 뜻 |
|---|---|
| `_설명` | 분류 기준 설명 |
| `default_role` | 분류표에 없는 출처의 임시 역할 |
| `signals` | 출처별 역할·근거 |
| `outcomes` | 정답 등급·가중치 |
| `outcome_rules` | 정답 정리 규칙 (후보는 한 등급 아래, 제외 팀과 이유) |
| `same_house` | 같은 집안 짝 (출처 ↔ 정답 프로그램, 적용 여부·이유) |
| `candidate_rules` | 후보 제외 목록 (팀이 아닌 이름·확인된 기성 팀과 이유) |

### `docs/data/board.json`

| 칸 | 뜻 |
|---|---|
| `updated` | 갱신 날짜 |
| `focus` | 지금 집중하는 일 |
| `steps` | 파이프라인 단계 상태 |
| `gaps` | 찾은 빈틈과 보완 |
| `sources` | 검토한 소스 목록 |
| `pending_research` | 조사할 것 |
| `decisions` | 결정 사항 |

### `docs/data/collect.json`

| 칸 | 뜻 |
|---|---|
| `generated` | 만든 시각 |
| `runs` | 날짜·소스별 수집 행 수와 형식 검사 결과 |
| `recent_releases` | 최근 발매 |
| `upcoming_gigs` | 다가오는 공연 |
| `selections` | 선정 명단 |
| `cross_branch` | 여러 갈래에 나온 팀 |

### `docs/data/dashboard.json`

| 칸 | 뜻 |
|---|---|
| `generated` | 만든 시각 |
| `window_from` | 집계 시작일 |
| `lookback_from` | 신호 보는 시작일 |
| `xref_active` | 아티스트 연결표 사용 여부 |
| `deltas` | 직전 대비 변화 |
| `errors` | 계산 실패한 칸 |
| `sections` | 대시보드 구역별 숫자 |

### `docs/data/source_review.json`

| 칸 | 뜻 |
|---|---|
| `generated_at` | 만든 시각 |
| `data_end` | 데이터 끝 날짜 |
| `cutoffs` | 성적표 기준일 |
| `since` | 수상 팀 셈 시작일 |
| `horizon_months` | 관찰 기간(개월) |
| `rules` | 제안 규칙 |
| `suggestions_changed_on` | 제안 목록이 바뀐 날 |
| `suggestions` | 출처 재분류 제안 |
| `sources` | 출처별 성적 숫자 |

## 4. 출처 역할 (`config/source_roles.json`)

신호 출처마다 역할을 정해 점수에 쓸지 정합니다: **발굴**(점수에 씀) · **맥락**(약하게만) · **검증 대기**(모으기만) · **제외**(효과 없음). 기준은 [source_roles.md](source_roles.md).

| 출처 (갈래:출처) | 역할 | 근거 |
|---|---|---|
| `공연:indistreet` | 발굴 | 수상 팀 56팀을 먼저 잡음(가장 먼저 34, 이 출처만 24), 적중률 1.38% |
| `공연:sangsangmadang` | 발굴 | 적중률 2.93%, 평균 30개월 먼저 |
| `공연:indiego` | 검증 대기 | 2026-11부터 수집 — 아직 성적 없음 |
| `공연:regional` | 검증 대기 | 지역 음악창작소·지역 페스티벌 라인업(세종 누리락·보헤미안), 2026-11부터 수집 — 아직 성적 없음 |
| `공연:instagram` | 검증 대기 | 공연장 인스타 라인업, 2026-11부터 수집 — 아직 성적 없음 |
| `큐레이션:musicy` | 발굴 | 적중률 1.75%, 수상 팀 32팀을 먼저 잡음(가장 먼저 19) |
| `큐레이션:izm` | 맥락 | 적중률 0.55% — 기준선 이하, 이미 알려진 팀을 많이 다룸 |
| `큐레이션:visla` | 맥락 | 적중률 0.33% — 기준선 이하 |
| `큐레이션:overtone` | 맥락 | 적중률 0.91% — 기준선 수준 |
| `큐레이션:rhythmer` | 맥락 | 적중률 0.91% — 기준선 수준 |
| `큐레이션:weiv` | 맥락 | 표본 16건뿐 — 판단 불가, 맥락으로만 |
| `큐레이션:instagram` | 검증 대기 | 인스타 매거진 499계정, 2026-11부터 수집 — 아직 성적 없음 |
| `발매:melon` | 검증 대기 | 신보 목록은 2026-11부터만 — 과거 기록 없음 |
| `발매:genie` | 검증 대기 | 신보 목록은 2026-11부터만 |
| `발매:bugs` | 검증 대기 | 신보 목록은 2026-11부터만 |
| `발매:flo` | 검증 대기 | 신보 목록은 2026-11부터만 |
| `발매:poclanos` | 검증 대기 | 신보 목록은 2026-11부터만 |
| `선정·지원:band_discovery` | 발굴 | 적중률 9.09% — 가장 정확 |
| `선정·지원:yoojaeha_finalist` | 발굴 | 적중률 3.7%, 평균 30개월 먼저 |
| `선정·지원:muse_sejong` | 발굴 | 적중률 4.35% |
| `선정·지원:burock_rookies` | 검증 대기 | 2026년 명단만 — 아직 성적 없음 |
| `선정·지원:dmz_lineup` | 제외 | 적중 0/103팀 — 이미 알려진 팀이 많은 페스티벌 라인업 |
| `선정·지원:gb_creation` | 제외 | 적중 0/58팀 |
| `협업:spotify` | 검증 대기 | 스포티파이 협업(피처링), 2026-11-27부터 수집 — 아직 성적 없음. 점수에는 w_collab(기본 0)로 따로 연결 |
| `반응:youtube` | 검증 대기 | 무대 영상 조회수 7일 증가량(scripts/collect_video_stats.py) — 2026-11-27부터 기록, 아직 성적 없음 |
| `큐레이션:hiphople` | 검증 대기 | 힙합엘이 국내 뉴스(발매 소식, 2021~ 3,530건). 한국힙합어워즈 신인 30팀 중 22팀을 시상 전에 실었지만(중앙값 12.4개월) 힙합엘이가 그 시상식 공동 주최사라 '같은 집안' 효과 — 한국힙합어워즈를 빼면 적중 18→2팀. 같은 집안 적중을 빼는 규칙을 정하기 전까지 점수에 안 씀 (조사: docs/research_2026-11-27_hiphop_rnb_sources.md 5절) |
| `선정·지원:superrookie` | 검증 대기 | 루트노트 슈퍼루키챌린지 라운드 선정(시즌 14~17·보컬 시즌, 85명). 아직 정답 0팀(첫 정답 시즌 전)이지만 다른 출처와 겹치는 21팀 중 13팀에서 19.1개월 먼저 나왔고 61팀은 다른 출처에 없음 — 성적이 쌓일 때까지 검증 대기 |
| `큐레이션:trackzero` | 검증 대기 | 멜론 트랙제로(이달의 아티스트·추천 신곡·기획 플레이리스트, 2022-04~ 글 262개·1,472팀). 출처 성적표는 좋지만(후보 2,133팀·적중 41·배수 2.2) 점수에 넣으면 교차 검증이 떨어짐(그대로 0.786 → 발굴로 0.752, 맥락으로 0.734 — 너무 많은 팀을 실어 점수 구분력이 흐려짐, 2026-11-27 시험). 점수에는 안 쓰고 팀 상세·갓 데뷔 화면의 '언급 출처'로만 보여 줌. 추천 신곡만 따로 떼어 다시 재 볼 것 |
