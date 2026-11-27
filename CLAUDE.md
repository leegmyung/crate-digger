# CLAUDE.md

**Crate Digger** — Bandcamp 신인 발굴 대시보드 프로젝트. 자세한 내용은 `PROJECT.md`(방향·결정·할 일), `README.md`(실행 방법), `HISTORY.md`(진행 기록)를 먼저 읽는다.
- **세션을 시작하면 `PROJECT.md`의 '0. 재개 지점'부터 확인하고, 멈춘 작업을 이어서 한다** (사용량 한도·인터넷 끊김 대비). 큰 작업 단위가 끝날 때마다 그 칸을 갱신한다.

- GitHub 저장소: https://github.com/leegmyung/crate-digger (공개)
- 응답과 문서는 한국어로. 사용자는 개발에 익숙하지 않으니 기술 용어는 쉽게 풀어서 설명한다.

## 커밋 규칙

- 작업 단위가 끝나면 Claude가 알아서 커밋하고 `git push`까지 한다.
- 메시지 형식: `<type>: <설명>` (설명은 한국어 가능)
  - type: `feat`(기능), `fix`(버그), `refactor`, `docs`, `test`, `chore`, `perf`, `ci`
  - 예: `feat: 장르별 매출 차트 추가`, `docs: README 실행 방법 정리`
- 브랜치는 기본 `main`을 쓴다. 강제 push(`--force`)와 기록 다시 쓰기는 사용자에게 먼저 묻는다.

## 개인정보·비밀값 (공개 저장소)

- API 키, 토큰, 비밀번호는 코드나 문서에 절대 적지 않는다. 필요하면 `.env`(커밋 안 됨)나 환경변수로만 쓴다. 예: `LASTFM_API_KEY`.
- 사용자의 실제 이메일, 다른 계정 이름, 연락처, 내 컴퓨터 경로(`/Users/...`)를 파일에 넣지 않는다.
- 커밋 작성자 이메일은 GitHub noreply 주소로 설정돼 있다(`git config user.email`). 바꾸지 않는다.
- `data/`는 가상 샘플 데이터만 둔다. 실제 수집 데이터나 개인 취향 기록을 넣을 때는 커밋 전에 사용자에게 묻는다.
- 커밋 전 `git diff --cached`로 위 항목이 섞이지 않았는지 확인한다.

## 작업 방식 (2026-11-26 정함)

- **파이프라인을 그대로 따르지 않는다.** 단계마다 부족하거나 미흡한 점을 찾아 채우고, 찾은 빈틈과 보완은 `docs/data/board.json`(진행판)에 기록한다.
- 단계를 진행할 때마다 파이프라인 지도에서 **지금 위치를 다시 보여주고**, 결과물(진행판 https://leegmyung.github.io/crate-digger/ 등)을 보여준다.
- **디깅 풀은 넓게 본다.** 발매 / 공연 / 선정·지원 / 큐레이션 4갈래. 새 소스는 후보 신호(작고 이른 단계)와 정답(크고 경쟁 센 단계) 중 한쪽으로만 분류한다.
- **웹 확인·수집은 aside로.** aside 안의 AI(`aside exec`)는 사용량 한도가 있으니 브라우저 조종(`aside repl`)을 쓴다. 공개 API가 있고 robots.txt가 허용하면 스크립트로 수집한다. robots.txt가 막은 곳은 aside로 그냥 읽는다 — 일부러 쉬는 시간은 두지 않고 페이지가 뜰 때까지만 기다린다 (2026-11-26 사용자 지시). 수집은 하루 1번, 원본은 `data/raw/`(커밋 안 함). 인스타가 로그인 요구로 막히면 그때만 늦춘다.
- 새 코드는 테스트 먼저 (`python3 -m unittest discover -s tests`).

## 기록

- **매일 21:00 자동 실행** (`scripts/daily_run.sh`, launchd): 수집 → 진행판 → 일일 기록 `docs/log/<날짜>.md` → 커밋·push. 자동 커밋은 `docs/data/collect.json`, `docs/log/`, 대시보드·SQL 결과·랩 데이터(`docs/data/dashboard.json`, `docs/sql/README.md`, `docs/lab/data/`)만 올린다.
- **대화 기반 누적 기록은 엑셀** `records/crate-digger_작업기록.xlsx` (시트: 작업기록, 결정사항, 지침, 직무참고). 작업을 마칠 때 그날 대화에서 나온 한 일·결정과 이유·지침·직무 참고를 `records/entries/<날짜>.json`으로 쓰고 `python3 scripts/worklog.py records/entries/<날짜>.json`으로 붙인다.
- `records/`와 `data/raw/`는 커밋하지 않는다 (개인 기록, 실제 수집 원본). 지원하는 회사 이름 같은 구직 정보는 공개 저장소에 쓰지 않고 `records/`에만 둔다.
