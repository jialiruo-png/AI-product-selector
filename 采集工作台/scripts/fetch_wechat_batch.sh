#!/usr/bin/env bash
set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WF_BIN="$ROOT_DIR/web-fetcher/.venv/bin/wf"
URL_FILE="${1:-$ROOT_DIR/采集工作台/urls/wechat.txt}"
OUTPUT_DIR="${2:-$ROOT_DIR/采集工作台/outputs/wechat}"
LOG_DIR="$ROOT_DIR/采集工作台/logs"
DELAY_SECONDS=3
DOWNLOAD_ASSETS="${DOWNLOAD_ASSETS:-0}"

mkdir -p "$OUTPUT_DIR" "$LOG_DIR"

LOG_FILE="$LOG_DIR/wechat-fetch-$(date +%Y%m%d-%H%M%S).log"

if [ ! -x "$WF_BIN" ]; then
  echo "错误：找不到可执行 wf：$WF_BIN" | tee -a "$LOG_FILE"
  echo "请先进入 web-fetcher 并安装依赖。" | tee -a "$LOG_FILE"
  exit 1
fi

if [ ! -f "$URL_FILE" ]; then
  echo "错误：找不到 URL 文件：$URL_FILE" | tee -a "$LOG_FILE"
  exit 1
fi

total=$(grep -Ev '^\s*($|#)' "$URL_FILE" | wc -l | tr -d ' ')
echo "准备抓取 $total 篇公众号文章" | tee -a "$LOG_FILE"
echo "输出目录：$OUTPUT_DIR" | tee -a "$LOG_FILE"
echo "日志文件：$LOG_FILE" | tee -a "$LOG_FILE"
if [ "$DOWNLOAD_ASSETS" = "1" ]; then
  echo "图片模式：下载到本地 assets 目录并重写 Markdown 图片路径" | tee -a "$LOG_FILE"
else
  echo "图片模式：保留远程图片链接" | tee -a "$LOG_FILE"
fi

index=0
while IFS= read -r raw_url || [ -n "$raw_url" ]; do
  url="$(printf '%s' "$raw_url" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"

  if [ -z "$url" ] || [[ "$url" == \#* ]]; then
    continue
  fi

  index=$((index + 1))
  echo "" | tee -a "$LOG_FILE"
  echo "[$index/$total] $url" | tee -a "$LOG_FILE"

  wf_args=("$url" "-o" "$OUTPUT_DIR")
  if [ "$DOWNLOAD_ASSETS" = "1" ]; then
    wf_args+=("--download-assets")
  fi

  if "$WF_BIN" "${wf_args[@]}" 2>&1 | tee -a "$LOG_FILE"; then
    echo "完成：$url" | tee -a "$LOG_FILE"
  else
    echo "失败：$url" | tee -a "$LOG_FILE"
  fi

  if [ "$index" -lt "$total" ]; then
    sleep "$DELAY_SECONDS"
  fi
done < "$URL_FILE"

echo "" | tee -a "$LOG_FILE"
echo "批量抓取结束。Markdown 输出在：$OUTPUT_DIR" | tee -a "$LOG_FILE"
