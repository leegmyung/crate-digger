#!/bin/bash
# 매일 저녁 자동 실행: 수집 → 진행판 갱신 → 일일 기록 → 커밋·push
#   직접 실행: bash scripts/daily_run.sh
#   예약: ~/Library/LaunchAgents/com.crate-digger.daily.plist (scripts/install_daily.sh 로 설치)
# 공개 저장소에는 docs/data/collect.json 과 docs/log/ 만 커밋한다 (원본 data/raw/, 개인 기록 records/ 제외).
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
else
  echo "⚠️ aside 명령이 없어 공연·인스타 수집을 건너뜀"
fi
"$PY" scripts/validate_csv.py data/raw/*"$DAY"*.csv || echo "⚠️ 형식 검사에서 오류 발견 (진행판에 실패로 표시됨)"
"$PY" scripts/build_site_data.py || echo "⚠️ 진행판 데이터 갱신 실패"
"$PY" scripts/daily_note.py "$DAY" || echo "⚠️ 일일 기록 실패"

git add docs/data/collect.json "docs/log/$DAY.md"
if git diff --cached --quiet; then
  echo "바뀐 내용 없음 → 커밋 안 함"
else
  git commit -q -m "chore: $DAY 일일 수집·기록" && git push -q origin main && echo "✅ 커밋·push 완료" || echo "❌ 커밋 또는 push 실패"
fi
echo "===== 끝 $(TZ=Asia/Seoul date +%H:%M:%S)"
