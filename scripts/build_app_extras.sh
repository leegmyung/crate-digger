#!/bin/bash
# 앱 데이터 생성 묶음 — 랩 데이터(export_lab_data) 다음에 앱 화면용 보조 데이터를 한 번에 만든다.
#   직접 실행: bash scripts/build_app_extras.sh               # 랩 데이터가 이미 최신일 때 (매일 실행: export_lab_data 다음 줄)
#              bash scripts/build_app_extras.sh --with-export # 랩 데이터부터 다시 만든 뒤 (수동으로 한 번에)
# 순서대로 돌리고, 하나가 실패해도 다음으로 넘어간다. 단계마다 걸린 시간과 성공 여부를 적는다 (refresh_analyses.sh 와 같은 형식).
# 결과(모두 앱이 읽는 데이터 — 문서는 덮지 않음):
#   docs/lab/data/venue_ladder.json (팀별 공연장 사다리·공연장 전후 흐름)  · docs/lab/data/venue_profiles.json (공연장 프로필)
#   docs/lab/data/city_profiles.json · team_cities.csv (도시 층)            · docs/data/alerts.json (오늘 새로 생긴 일)
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 1
PY="${PY:-$ROOT/.venv/bin/python}"
# "이름|스크립트 인자" — 이름은 출력용
STEPS=("venue_ladder|scripts/venue_ladder.py --json-only"
       "venue_profiles|scripts/venue_profiles.py"
       "city_profiles|scripts/city_profiles.py --data-only"
       "build_alerts|scripts/build_alerts.py")
if [ "${1:-}" = "--with-export" ]; then
  STEPS=("export_lab_data|scripts/export_lab_data.py" "${STEPS[@]}")
fi
FAILED=()
START_ALL=$(date +%s)
echo "===== 앱 데이터 생성 $(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M:%S')"
for step in "${STEPS[@]}"; do
  name="${step%%|*}"
  read -r -a cmd <<< "${step#*|}"
  t0=$(date +%s)
  if "$PY" "${cmd[@]}" > /dev/null 2> >(tail -3 >&2); then
    echo "✅ $name  $(( $(date +%s) - t0 ))초"
  else
    echo "⚠️ $name 실패 ($(( $(date +%s) - t0 ))초) — 다음으로 넘어감"
    FAILED+=("$name")
  fi
done
echo "===== 끝: 전체 $(( $(date +%s) - START_ALL ))초" "${FAILED[@]:+· 실패: ${FAILED[*]}}"
[ ${#FAILED[@]} -eq 0 ]
