#!/bin/bash
# 매일 저녁 자동 실행 예약을 이 맥에 설치한다 (기본 21:00, 맥이 잠자고 있었으면 깨어날 때 실행).
#   bash scripts/install_daily.sh          # 21:00
#   bash scripts/install_daily.sh 22 30    # 22:30
#   해제: launchctl unload ~/Library/LaunchAgents/com.crate-digger.daily.plist && rm 그 파일
set -eu
HOUR="${1:-21}"
MINUTE="${2:-0}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
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
