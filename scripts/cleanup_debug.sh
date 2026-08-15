#!/usr/bin/env bash
# 删除 debug 目录中超过指定保留期限的顶层普通文件。
#
# 用法：
#   bash scripts/cleanup_debug.sh             # 删除 7 天以前的文件
#   DRY_RUN=1 bash scripts/cleanup_debug.sh   # 只列出待删除文件
#   RETENTION_DAYS=14 bash scripts/cleanup_debug.sh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DEBUG_DIR="${DEBUG_DIR:-$PROJECT_DIR/debug}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
DRY_RUN="${DRY_RUN:-0}"

if [[ "$DRY_RUN" != "0" && "$DRY_RUN" != "1" ]]; then
  echo "错误：DRY_RUN 必须是 0 或 1" >&2
  exit 2
fi

if [[ ! "$RETENTION_DAYS" =~ ^[1-9][0-9]*$ ]]; then
  echo "错误：RETENTION_DAYS 必须是正整数" >&2
  exit 2
fi

if [[ ! -d "$DEBUG_DIR" ]]; then
  echo "错误：debug 目录不存在：$DEBUG_DIR" >&2
  exit 1
fi

MINUTES=$((RETENTION_DAYS * 24 * 60))
FIND_ARGS=("$DEBUG_DIR" -mindepth 1 -maxdepth 1 -type f -mmin "+$MINUTES")

if [[ "$DRY_RUN" == "1" ]]; then
  find "${FIND_ARGS[@]}" -print
else
  find "${FIND_ARGS[@]}" -print -delete
fi
