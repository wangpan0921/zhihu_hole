#!/usr/bin/env bash
# 监控 kiro-cli chat agent：非交互式运行，**实时**显示 agent 执行进度，
# 输出中出现 dispatch failed 等错误就自动重试。
#
# 用法:
#   scripts/kiro-agent-retry.sh [--agent <agent_name>] "<prompt>"
#   scripts/kiro-agent-retry.sh <agent_name> "<prompt>"   # 兼容旧用法
#   scripts/kiro-agent-retry.sh "<prompt>"                # 使用 kiro-cli 默认 agent
#
# 说明:
#   - 不传 agent 时，省略 --agent 参数，由 kiro-cli 使用其配置的默认 agent。
#   - 用 `kiro-cli chat --no-interactive` 跑 agent，stdout/stderr 通过 `tee`
#     同时输出到终端和临时文件，做到「边跑边看」。
#   - 命中 ERROR_PATTERNS 中任一模式即视为失败 → 重试，最多 MAX_RETRY 次。
#   - 重试策略：
#       * 第 1 次：用原 prompt 启动。
#       * 第 2 次（即首次失败后的重试）：仍用原 prompt 重新开始，避免首次
#         未建立会话时 `--resume` 续到不相关的旧会话。
#       * 第 3 次及以后：用 `--resume "继续"` 续跑当前会话，避免从头重做。
#   - 退出码使用 ${PIPESTATUS[0]}，保留 kiro-cli 自身的退出码。
#   - 如系统提供 `stdbuf`，会启用行缓冲减少 CLI 输出缓冲延迟。
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

usage() {
  cat >&2 <<EOF
用法:
  $0 [--agent <agent_name>] "<prompt>"
  $0 <agent_name> "<prompt>"        # 兼容旧用法
  $0 "<prompt>"                     # 使用 kiro-cli 默认 agent
EOF
}

# ---------- 参数解析 ----------
AGENT=""
# 先解析 --agent / -a / --agent=xxx 等 flag 形式
while [[ $# -gt 0 ]]; do
  case "$1" in
    -a|--agent)
      if [[ $# -lt 2 ]]; then
        echo "[retry] 错误：$1 需要一个参数" >&2
        usage
        exit 2
      fi
      AGENT="$2"
      shift 2
      ;;
    --agent=*)
      AGENT="${1#--agent=}"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      break
      ;;
    -*)
      echo "[retry] 错误：未知参数 $1" >&2
      usage
      exit 2
      ;;
    *)
      break
      ;;
  esac
done

# 再处理位置参数：
#   1 个 → prompt
#   2 个 → agent_name prompt（兼容旧用法；与 --agent 互斥）
case $# in
  1)
    PROMPT="$1"
    ;;
  2)
    if [[ -n "$AGENT" ]]; then
      echo "[retry] 错误：已通过 --agent 指定 agent，不要再传位置参数 agent_name。" >&2
      usage
      exit 2
    fi
    AGENT="$1"
    PROMPT="$2"
    ;;
  *)
    usage
    exit 2
    ;;
esac

# ---------- 构造命令 ----------
build_regex() { local IFS="|"; echo "${ERROR_PATTERNS[*]}"; }
REGEX="$(build_regex)"

# 未指定 agent 时跳过 --agent，让 kiro-cli 走默认配置。
KIRO_BASE=(kiro-cli chat --no-interactive -a)
if [[ -n "$AGENT" ]]; then
  KIRO_BASE+=(--agent "$AGENT")
  AGENT_DESC="$AGENT"
else
  AGENT_DESC="<kiro-cli 默认 agent>"
fi

# 临时文件用来在实时输出的同时镜像一份完整日志，方便 grep 错误模式
TMP_OUT="$(mktemp -t kiro-agent-retry.XXXXXX)"
cleanup() { rm -f "$TMP_OUT"; }
trap cleanup EXIT INT TERM

# 若系统有 stdbuf，则用行缓冲减小输出延迟（无则原样调用）
if command -v stdbuf >/dev/null 2>&1; then
  RUNNER=(stdbuf -oL -eL)
else
  RUNNER=()
fi

# ---------- 重试循环 ----------
attempt=0
while (( attempt < MAX_RETRY )); do
  attempt=$((attempt+1))
  echo "[retry] 第 $attempt/$MAX_RETRY 次运行 agent=$AGENT_DESC"
  echo "[retry] ----- agent 输出开始 -----"

  # 清空上次的镜像日志
  : > "$TMP_OUT"

  # 重试策略：
  #   - attempt == 1: 用原 prompt 启动。
  #   - attempt == 2: 首次失败的重试，仍用原 prompt 重新开始；
  #     这样可避免「首次 dispatch 失败、未建立会话」时 --resume 续到无关旧会话。
  #   - attempt >= 3: 用 --resume "继续" 续跑当前会话，避免从头重做。
  # 关键：用管道把 stdout+stderr 实时 tee 到终端 & 临时文件，
  # 再用 PIPESTATUS[0] 取回 kiro-cli 的真实退出码。
  if (( attempt <= 2 )); then
    "${RUNNER[@]}" "${KIRO_BASE[@]}" "$PROMPT" 2>&1 \
      | tee "$TMP_OUT"
  else
    "${RUNNER[@]}" "${KIRO_BASE[@]}" --resume "继续" 2>&1 \
      | tee "$TMP_OUT"
  fi
  ec=${PIPESTATUS[0]}

  echo "[retry] ----- agent 输出结束 (exit=$ec) -----"

  if grep -qiE "$REGEX" "$TMP_OUT"; then
    echo "[retry] 检测到错误，$COOLDOWN 秒后重试…"
    sleep "$COOLDOWN"
    continue
  fi

  echo "[retry] 未检测到错误（退出码 $ec），结束。"
  exit "$ec"
done

echo "[retry] 已达最大重试 $MAX_RETRY 次仍报错，停手，请人工介入。" >&2
exit 1
