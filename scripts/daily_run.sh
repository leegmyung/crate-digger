#!/bin/bash
# 매일 저녁 자동 실행: 수집 → 진행판 갱신 → 일일 기록 → 커밋·push
#   직접 실행: bash scripts/daily_run.sh
#   예약: ~/Library/LaunchAgents/com.crate-digger.daily.plist (scripts/install_daily.sh 로 설치)
# 공개 저장소에는 진행판·일일 기록·대시보드·SQL 결과·랩 데이터만 커밋한다 (원본 data/raw/, 개인 기록 records/ 제외).
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 1
export PATH="$HOME/.local/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH"
PY="$ROOT/.venv/bin/python"
DAY="$(TZ=Asia/Seoul date +%Y-%m-%d)"
mkdir -p records
LOG="$ROOT/records/daily_run.log"
exec >>"$LOG" 2>&1
echo "===== $DAY $(TZ=Asia/Seoul date +%H:%M:%S) 시작"

"$PY" scripts/collect_poclanos.py --days 3 || echo "⚠️ 포크라노스 수집 실패"
"$PY" scripts/collect_selection.py --site all || echo "⚠️ 선정 명단(부산 루키즈·세종·경북) 수집 실패"
if command -v aside >/dev/null 2>&1; then
  "$PY" scripts/collect_gigs.py --site all --days 7 || echo "⚠️ 공연 수집 일부 실패 (aside 앱이 꺼져 있으면 실패해요)"
  "$PY" scripts/collect_insta.py || echo "⚠️ 인스타 매거진 수집 실패"
  "$PY" scripts/collect_platforms.py --days 3 || echo "⚠️ 음원 플랫폼 신보 수집 전부 실패 (일부 실패는 위 로그에 ⚠️로 표시)"
  "$PY" scripts/collect_artists.py || echo "⚠️ 아티스트 프로필(멜론) 수집 실패"
  NAMES="$(ls -t data/raw/review/melon_names_*.txt 2>/dev/null | head -1)"   # 후보·수상 팀 프로필 보강 (하루 최대 100팀, 멜론 일시 차단 피하려고 나눠 받음)
  [ -n "$NAMES" ] && { "$PY" scripts/collect_artists.py --names-file "$NAMES" || echo "⚠️ 후보 팀 멜론 프로필 보강 실패"; }
else
  echo "⚠️ aside 명령이 없어 공연·인스타·음원 플랫폼 수집을 건너뜀"
fi
"$PY" scripts/collect_spotify.py || echo "⚠️ 스포티파이 발매 이력 수집 일부 실패 (하루 한도에 걸리면 다음 날 이어서)"
"$PY" scripts/collect_spotify_collabs.py --max-requests 1500 || echo "⚠️ 스포티파이 협업 수집 일부 실패 (한도에 걸리면 다음 날 이어서)"
"$PY" scripts/validate_csv.py data/raw/*"$DAY"*.csv || echo "⚠️ 형식 검사에서 오류 발견 (진행판에 실패로 표시됨)"
"$PY" scripts/collect_videos.py || echo "⚠️ 유튜브 무대 영상 수집 일부 실패 (하루 한도에 걸리면 다음 날 이어서)"
"$PY" scripts/build_site_data.py || echo "⚠️ 진행판 데이터 갱신 실패"
"$PY" scripts/load_pg.py || echo "⚠️ PostgreSQL 적재 실패 (brew services start postgresql@17 확인)"
"$PY" scripts/artist_xref.py --load-pg || echo "⚠️ 아티스트 연결표(같은 팀 다른 표기) 갱신 실패"
"$PY" scripts/venue_xref.py --load-pg || echo "⚠️ 공연장 연결표 갱신 실패"
"$PY" scripts/build_dashboard_data.py || echo "⚠️ 데이터 대시보드 갱신 일부 실패"
"$PY" scripts/run_pg_queries.py || echo "⚠️ SQL 결과 문서 일부 실패"
"$PY" scripts/collect_artist_images.py || echo "⚠️ 아티스트 사진 수집 일부 실패"
"$PY" scripts/export_lab_data.py || echo "⚠️ 랩(설정형 분석 도구) 데이터 갱신 실패"
"$PY" scripts/source_review.py || echo "⚠️ 출처 재분류 제안 실패"
"$PY" scripts/lab_snapshot.py || echo "⚠️ 점수 스냅샷 실패 (.venv에 duckdb 필요)"
"$PY" scripts/daily_note.py "$DAY" || echo "⚠️ 일일 기록 실패"

git add docs/data/collect.json "docs/log/$DAY.md" docs/data/dashboard.json docs/sql/README.md docs/lab/data docs/data/source_review.json
if git diff --cached --quiet; then
  echo "바뀐 내용 없음 → 커밋 안 함"
else
  git commit -q -m "chore: $DAY 일일 수집·기록" && git push -q origin main && echo "✅ 커밋·push 완료" || echo "❌ 커밋 또는 push 실패"
fi
echo "===== 끝 $(TZ=Asia/Seoul date +%H:%M:%S)"
