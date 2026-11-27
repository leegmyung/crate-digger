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
RUN_MARK="$(mktemp)"   # 이 실행이 만든 원본 파일 표시 (자정을 넘겨 파일 날짜가 바뀌어도 형식 검사에 포함)
mkdir -p records
LOG="$ROOT/records/daily_run.log"
exec >>"$LOG" 2>&1
echo "===== $DAY $(TZ=Asia/Seoul date +%H:%M:%S) 시작"

"$PY" scripts/collect_poclanos.py --days 3 || echo "⚠️ 포크라노스 수집 실패"
"$PY" scripts/collect_selection.py --site all || echo "⚠️ 선정 명단(부산 루키즈·세종·경북) 수집 실패"
"$PY" scripts/collect_superrookie.py || echo "⚠️ 슈퍼루키챌린지 수집 실패"
"$PY" scripts/collect_trackzero.py || echo "⚠️ 멜론 트랙제로 수집 실패"   # 새 글만, 공개 페이지(aside 안 씀)
if command -v aside >/dev/null 2>&1; then
  "$PY" scripts/collect_gigs.py --site all --days 7 || echo "⚠️ 공연 수집 일부 실패 (aside 앱이 꺼져 있으면 실패해요)"
  "$PY" scripts/collect_platforms.py --days 3 || echo "⚠️ 음원 플랫폼 신보 수집 전부 실패 (일부 실패는 위 로그에 ⚠️로 표시)"
  "$PY" scripts/collect_artists.py || echo "⚠️ 아티스트 프로필(멜론) 수집 실패"
  "$PY" scripts/collect_hiphople.py --no-time-guard || echo "⚠️ 힙합엘이 국내 뉴스 수집 실패"
  "$PY" scripts/melon_names.py || echo "⚠️ 멜론 보강 명단 만들기 실패"
  NAMES="$(ls -t data/raw/review/melon_names_*.txt 2>/dev/null | head -1)"   # 후보·수상 팀 프로필 보강 (한도 없이 명단 전체)
  [ -n "$NAMES" ] && { "$PY" scripts/collect_artists.py --names-file "$NAMES" || echo "⚠️ 후보 팀 멜론 프로필 보강 실패"; }
  "$PY" scripts/collect_artists.py --refresh || echo "⚠️ 멜론 팬 수 다시 받기 실패"   # 관찰 팀 팬 수 7일마다 (팬 수 날짜별 기록용)
  "$PY" scripts/collect_insta.py || echo "⚠️ 인스타 매거진 수집 실패"   # 가장 오래 걸려서 aside 묶음 맨 뒤 (길어져도 다른 수집이 안 밀리게)
else
  echo "⚠️ aside 명령이 없어 공연·인스타·음원 플랫폼 수집을 건너뜀"
fi
"$PY" scripts/fan_history.py || echo "⚠️ 팬 수 기록 실패"
"$PY" scripts/collect_spotify.py || echo "⚠️ 스포티파이 발매 이력 수집 일부 실패 (하루 한도에 걸리면 다음 날 이어서)"
"$PY" scripts/collect_spotify_collabs.py --max-requests 1500 || echo "⚠️ 스포티파이 협업 수집 일부 실패 (한도에 걸리면 다음 날 이어서)"
NEW_RAW="$(find data/raw -maxdepth 1 -name "*.csv" -newer "$RUN_MARK" | sort)"
[ -n "$NEW_RAW" ] && { "$PY" scripts/validate_csv.py $NEW_RAW || echo "⚠️ 형식 검사에서 오류 발견 (진행판에 실패로 표시됨)"; }
"$PY" scripts/collect_videos.py || echo "⚠️ 유튜브 무대 영상 수집 일부 실패 (하루 한도에 걸리면 다음 날 이어서)"
"$PY" scripts/build_site_data.py || echo "⚠️ 진행판 데이터 갱신 실패"
"$PY" scripts/load_pg.py || echo "⚠️ PostgreSQL 적재 실패 (brew services start postgresql@17 확인)"
"$PY" scripts/artist_xref.py --load-pg || echo "⚠️ 아티스트 연결표(같은 팀 다른 표기) 갱신 실패"
"$PY" scripts/venue_xref.py --load-pg || echo "⚠️ 공연장 연결표 갱신 실패"
"$PY" scripts/build_dashboard_data.py || echo "⚠️ 데이터 대시보드 갱신 일부 실패"
"$PY" scripts/run_pg_queries.py || echo "⚠️ SQL 결과 문서 일부 실패"
"$PY" scripts/collect_artist_images.py || echo "⚠️ 아티스트 사진 수집 일부 실패"
"$PY" scripts/export_lab_data.py || echo "⚠️ 랩(설정형 분석 도구) 데이터 갱신 실패"
[ "$(TZ=Asia/Seoul date +%u)" = 1 ] && { "$PY" scripts/source_roles_doc.py || echo "⚠️ 출처 분류 문서 갱신 실패"; }   # 월요일: 출처 성적표 표 자동 갱신
"$PY" scripts/source_review.py || echo "⚠️ 출처 재분류 제안 실패"
if [ "$(TZ=Asia/Seoul date +%u)" = 1 ]; then "$PY" scripts/score_review.py || echo "⚠️ 점수 재검토 실패"; fi   # 월요일만 (약 3분)
if [ "$(TZ=Asia/Seoul date +%u)" = 1 ]; then bash scripts/refresh_analyses.sh || echo "⚠️ 분석 문서 일부 다시 만들기 실패"; fi   # 월요일만 (약 2분, 부하 높으면 더)
"$PY" scripts/collect_video_stats.py || echo "⚠️ 유튜브 지표 수집 실패"
"$PY" scripts/export_video_momentum.py || echo "⚠️ 유튜브 7일 증가량 실패"
if [ "$(TZ=Asia/Seoul date +%u)" = 1 ]; then "$PY" scripts/export_excel.py || echo "⚠️ 주간 엑셀 실패"; fi   # 월요일만
"$PY" scripts/lab_snapshot.py || echo "⚠️ 점수 스냅샷 실패 (.venv에 duckdb 필요)"
bash scripts/build_app_extras.sh || echo "⚠️ 앱 보조 데이터(공연장·도시·페스티벌·라인업·사건·알림) 일부 실패"   # 스냅샷 뒤(알림의 순위 비교에 씀)
"$PY" scripts/build_scene_map.py || echo "⚠️ 사운드 지도 실패"
"$PY" scripts/daily_note.py "$DAY" || echo "⚠️ 일일 기록 실패"
"$PY" scripts/data_checks.py || echo "⚠️ 데이터 검사에서 실패 항목 발견 (docs/data_checks.md)"
if [ "$(TZ=Asia/Seoul date +%u)" = 1 ]; then bash scripts/e2e_check.sh > records/e2e_check.log 2>&1 || echo "⚠️ 앱 화면 점검 실패 (records/e2e_check.log)"; fi   # 월요일만 (약 5분, 크롬 필요)
"$PY" scripts/build_status_report.py || echo "⚠️ 진행 점검표 실패"   # 일일 기록까지 끝난 뒤 (최근 기록 링크 포함)

git add docs/data/collect.json "docs/log/$DAY.md" docs/data/dashboard.json docs/sql/README.md docs/lab/data docs/data/source_review.json docs/report docs/status_report.html docs/data/score_review.json docs/score_tuning.md docs/source_roles.md docs/fan_history.md docs/debut_cohort.md docs/missed_analysis.md docs/rule_leakage.md docs/same_house.md docs/genre_bias.md docs/score_model.md docs/candidate_audit.md docs/discovery_stage.md docs/data/alerts.json docs/data_checks.md docs/data/data_checks.json docs/venues_kr.md
if git diff --cached --quiet; then
  echo "바뀐 내용 없음 → 커밋 안 함"
else
  git commit -q -m "chore: $DAY 일일 수집·기록" && git push -q origin main && echo "✅ 커밋·push 완료" || echo "❌ 커밋 또는 push 실패"
fi
echo "===== 끝 $(TZ=Asia/Seoul date +%H:%M:%S)"
