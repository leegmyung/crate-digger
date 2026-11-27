#!/bin/bash
# 앱 화면 점검 (수동·선택 실행): 로컬 서버 띄우기 → tests/e2e/route_check.mjs → 서버 끄기. 실패하면 종료 코드 1.
#   bash scripts/e2e_check.sh                       # 기본: 서버·크롬 디버깅 포트 모두 비어 있는 포트를 자동으로 고름
#   bash scripts/e2e_check.sh --chrome <크롬 경로> --port 8800 --debug-port 9444 --limit-ms 20000
# 필요한 것: node 22 이상(내장 WebSocket), 크롬 또는 크로미움. 크롬 경로는 --chrome 이나 환경변수 CHROME_PATH.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT=0   # 0 = 비어 있는 포트 자동 선택
PASS_ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --port) PORT="$2"; shift 2 ;;
    --chrome|--debug-port|--limit-ms|--out) PASS_ARGS+=("$1" "$2"); shift 2 ;;
    *) echo "모르는 인자: $1" >&2; exit 1 ;;
  esac
done

if ! command -v node >/dev/null 2>&1; then
  echo "node 가 없습니다" >&2
  exit 1
fi
if [ "$PORT" = "0" ]; then
  PORT="$(node -e "const s = require('net').createServer(); s.listen(0, '127.0.0.1', () => { console.log(s.address().port); s.close(); });")"
fi
if curl -s -o /dev/null "http://127.0.0.1:$PORT/"; then
  echo "포트 $PORT 를 이미 누가 쓰고 있습니다 — --port 로 다른 포트를 고르세요" >&2
  exit 1
fi

node "$ROOT/tests/e2e/static_server.mjs" "$ROOT/docs" "$PORT" >/dev/null 2>&1 &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null' EXIT

for _ in $(seq 1 50); do
  curl -s -o /dev/null "http://127.0.0.1:$PORT/dashboard.html" && break
  sleep 0.1
done
if ! curl -s -o /dev/null "http://127.0.0.1:$PORT/dashboard.html"; then
  echo "로컬 서버가 뜨지 않았습니다 (포트 $PORT)" >&2
  exit 1
fi

echo "앱 서버: http://127.0.0.1:$PORT/dashboard.html"
node "$ROOT/tests/e2e/route_check.mjs" --base "http://127.0.0.1:$PORT/dashboard.html" ${PASS_ARGS[@]+"${PASS_ARGS[@]}"}
