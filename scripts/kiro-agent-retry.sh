#!/usr/bin/env bash
# 监控 custom-agent：非交互式运行，输出中出现 dispatch failed 等错误就自动重试。
#
# 用法:
#   scripts/kiro-agent-retry.sh <agent_name> "<prompt>"
#
# 说明:
#   - 用 `kiro-cli chat --no-interactive` 一次性跑完返回，捕获全部输出做错误匹配。
#   - 命中 ERROR_PATTERNS 中任一模式即视为失败 → 重试，最多 MAX_RETRY 次。
#   - 后续遇到新的典型错误日志，往 ERROR_PATTERNS 里加一行即可。
set -uo pipefail

MAX_RETRY=10
COOLDOWN=5   # 每次重试前等待秒数（退避）

# 典型错误日志（按需新增）。匹配为不区分大小写、按子串。
ERROR_PATTERNS=(
  "dispatch failure"
  "dispatch failed"
  "Failed to send the request"
  "error sending request for url"
  "Kiro is having trouble responding"
)

AGENT="${1:?用法: $0 <agent_name> \"<prompt>\"}"
PROMPT="${2:?用法: $0 <agent_name> \"<prompt>\"}"

build_regex() { local IFS="|"; echo "${ERROR_PATTERNS[*]}"; }
REGEX="$(build_regex)"

attempt=0
while (( attempt < MAX_RETRY )); do
  attempt=$((attempt+1))
  echo "[retry] 第 $attempt/$MAX_RETRY 次运行 agent=$AGENT"

  # 首次带 prompt；重试用 --resume 续跑同一会话，避免从头重做
  if (( attempt == 1 )); then
    out="$(kiro-cli chat --no-interactive -a --agent "$AGENT" "$PROMPT" 2>&1)"
  else
    out="$(kiro-cli chat --no-interactive -a --agent "$AGENT" --resume "继续" 2>&1)"
  fi
  ec=$?
  printf '%s\n' "$out"

  if grep -qiE "$REGEX" <<<"$out"; then
    echo "[retry] 检测到错误，$COOLDOWN 秒后重试…"
    sleep "$COOLDOWN"
    continue
  fi

  echo "[retry] 未检测到错误（退出码 $ec），结束。"
  exit "$ec"
done

echo "[retry] 已达最大重试 $MAX_RETRY 次仍报错，停手，请人工介入。" >&2
exit 1
