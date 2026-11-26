#!/bin/bash
# 매일 저녁 자동 실행 예약을 이 맥에 설치한다 (기본 21:00, 맥이 잠자고 있었으면 깨어날 때 실행).
#   bash scripts/install_daily.sh          # 21:00
#   bash scripts/install_daily.sh 22 30    # 22:30
#   해제: launchctl unload ~/Library/LaunchAgents/com.crate-digger.daily.plist && rm 그 파일
set -eu
HOUR="${1:-21}"
MINUTE="${2:-0}"
# 바로가기(심볼릭 링크) 경로가 아니라 진짜 경로로 등록한다. macOS는 백그라운드 작업이 데스크탑·문서·다운로드
# 폴더에 접근하는 걸 막아서, 프로젝트는 그 밖(예: ~/Projects)에 있어야 한다.
ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
case "$ROOT" in
  "$HOME/Desktop"*|"$HOME/Documents"*|"$HOME/Downloads"*)
    echo "⚠️ 프로젝트가 $ROOT 에 있어요. macOS 보안 때문에 자동 실행이 'Operation not permitted'로 실패해요. ~/Projects 같은 곳으로 옮긴 뒤 다시 실행하세요." >&2
    exit 1 ;;
esac
PLIST="$HOME/Library/LaunchAgents/com.crate-digger.daily.plist"
mkdir -p "$HOME/Library/LaunchAgents" "$ROOT/records"
cat >"$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.crate-digger.daily</string>
  <key>ProgramArguments</key>
  <array><string>/bin/bash</string><string>$ROOT/scripts/daily_run.sh</string></array>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>$HOUR</integer><key>Minute</key><integer>$MINUTE</integer></dict>
  <key>StandardOutPath</key><string>$ROOT/records/launchd.out.log</string>
  <key>StandardErrorPath</key><string>$ROOT/records/launchd.err.log</string>
</dict>
</plist>
EOF
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "✅ 매일 $(printf '%02d:%02d' "$HOUR" "$MINUTE")에 실행되도록 예약했어요: $PLIST"
