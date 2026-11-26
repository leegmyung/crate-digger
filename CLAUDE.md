# CLAUDE.md

**Crate Digger** — Bandcamp 신인 발굴 대시보드 프로젝트. 자세한 내용은 `PROJECT.md`(방향·결정·할 일), `README.md`(실행 방법), `HISTORY.md`(진행 기록)를 먼저 읽는다.

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
