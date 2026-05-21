#!/usr/bin/env bash
set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GUI="$ROOT_DIR/采集工作台/scripts/material_collector_gui.py"
RUN_LOG="$(mktemp -t ai-material-gui)"
export PATH="$ROOT_DIR/.venv/bin:$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

if [ ! -f "$GUI" ]; then
  osascript -e 'display alert "采集工具不可用" message "没有找到 material_collector_gui.py，请确认项目目录没有移动。" as critical'
  exit 1
fi

python3 "$GUI" > "$RUN_LOG" 2>&1
STATUS=$?

if [ "$STATUS" -ne 0 ]; then
  SUMMARY="$(tail -n 20 "$RUN_LOG")"
  osascript <<APPLESCRIPT
display alert "AI 素材采集启动失败" message "$(printf '%s' "$SUMMARY" | sed 's/\/\\/g; s/"/\"/g')" as warning
APPLESCRIPT
fi

rm -f "$RUN_LOG"
exit "$STATUS"
