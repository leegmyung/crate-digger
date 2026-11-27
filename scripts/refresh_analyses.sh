#!/bin/bash
# 분석 문서 한 번에 다시 만들기 (데이터가 바뀐 뒤 — 예: 21시 매일 실행이 끝난 뒤, 멜론 프로필을 많이 받은 뒤)
#   직접 실행: bash scripts/refresh_analyses.sh
# 순서대로 돌리고, 하나가 실패해도 다음으로 넘어간다. 단계마다 걸린 시간과 성공 여부를 적는다.
# 결과: docs/debut_cohort.md · missed_analysis.md · rule_leakage.md · same_house.md · genre_bias.md · score_model.md · candidate_audit.md
#       (candidate_audit 은 data/raw/review/candidate_audit_<날짜>.csv 도 만든다 — 비공개)
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 1
PY="$ROOT/.venv/bin/python"
STEPS=(debut_cohort missed_analysis rule_leakage same_house genre_bias score_model candidate_audit)
FAILED=()
START_ALL=$(date +%s)
echo "===== 분석 다시 만들기 $(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M:%S')"
for s in "${STEPS[@]}"; do
  t0=$(date +%s)
  if "$PY" "scripts/$s.py" > /dev/null 2> >(tail -3 >&2); then
    echo "✅ $s  $(( $(date +%s) - t0 ))초"
  else
    echo "⚠️ $s 실패 ($(( $(date +%s) - t0 ))초) — 다음으로 넘어감"
    FAILED+=("$s")
  fi
done
echo "===== 끝: 전체 $(( $(date +%s) - START_ALL ))초" "${FAILED[@]:+· 실패: ${FAILED[*]}}"
[ ${#FAILED[@]} -eq 0 ]
