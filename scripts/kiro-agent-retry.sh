#!/usr/bin/env bash
# 监控 kiro-cli chat agent：非交互式运行，**实时**显示 agent 执行进度，
# 输出中出现 dispatch failed 等错误就自动重试。
#
# 用法:
#   scripts/kiro-agent-retry.sh [选项] "<prompt>"
#
# 常用选项:
#   -a, --agent <agent>     指定 agent；不传则用 kiro-cli 默认 agent
#   -r, --resume            首次调用就续上"当前目录下最近的那次会话"（无需输入 session id）
#       --continue          同 -r，习惯打 --continue 的人也能用
#       --pick              交互式从最近若干个会话里选一个续跑（输一个数字即可）
#       --pick-n <N>        --pick 模式下展示最近多少个会话（默认 10）
#   -h, --help              查看帮助
#
# 兼容旧用法:
#   scripts/kiro-agent-retry.sh <agent_name> "<prompt>"
#   scripts/kiro-agent-retry.sh "<prompt>"
#
# 说明:
#   - 用 `kiro-cli chat --no-interactive` 跑 agent，stdout/stderr 通过 `tee`
#     同时输出到终端和临时文件，做到「边跑边看」。
#   - 命中 ERROR_PATTERNS 中任一模式即视为失败 → 重试，最多 MAX_RETRY 次。
#   - 重试策略：
#       * 默认（不带 -r/--pick）：
#           第 1 次：原 prompt 启动新会话。
#           第 2 次：仍用原 prompt 重新开始，避免首次未建立会话时
#                    `--resume` 续到不相关的旧会话。
#           第 3 次起：`--resume "继续"` 续跑当前会话，避免从头重做。
#       * 续跑模式（-r 或 --pick）：
#           启动时锁定一个 SESSION_ID，全程用 `--resume-id` 续跑该会话；
#           第 1、2 次发原 prompt，第 3 次起发 "继续"，避免重复消耗 token。
#   - 退出码使用 ${PIPESTATUS[0]}，保留 kiro-cli 自身的退出码。
#   - 如系统提供 `stdbuf`，会启用行缓冲减少 CLI 输出缓冲延迟。
#   - 后续遇到新的典型错误日志，往 ERROR_PATTERNS 里加一行即可。
set -uo pipefail

MAX_RETRY=10
COOLDOWN=5         # 每次重试前等待秒数（退避）
DEFAULT_PICK_N=10  # --pick 默认展示最近 N 个会话

# 终端颜色：仅在 stdout 是 tty 时启用，避免污染日志/管道。
if [[ -t 1 ]]; then
  C_YELLOW=$'\033[1;33m'
  C_RESET=$'\033[0m'
else
  C_YELLOW=""
  C_RESET=""
fi

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
  $0 [选项] "<prompt>"

选项:
  -a, --agent <agent>     指定 agent；不传则用 kiro-cli 默认 agent
  -r, --resume            首次调用就续上"当前目录下最近的那次会话"（无需输入 session id）
      --continue          同 -r
      --pick              交互式从最近若干个会话里选一个续跑（输一个数字即可）
      --pick-n <N>        --pick 模式下展示最近多少个会话（默认 ${DEFAULT_PICK_N}）
  -h, --help              查看帮助

兼容旧用法:
  $0 <agent_name> "<prompt>"
  $0 "<prompt>"
EOF
}

# ---------- 参数解析 ----------
AGENT=""
RESUME_MODE=""        # ""(新会话) | "latest"(自动选最近一次) | "pick"(交互式选)
PICK_N="$DEFAULT_PICK_N"

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
    -r|--resume|--continue)
      RESUME_MODE="latest"
      shift
      ;;
    --pick)
      RESUME_MODE="pick"
      shift
      ;;
    --pick-n)
      if [[ $# -lt 2 ]]; then
        echo "[retry] 错误：$1 需要一个参数" >&2
        usage
        exit 2
      fi
      PICK_N="$2"
      shift 2
      ;;
    --pick-n=*)
      PICK_N="${1#--pick-n=}"
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

# ---------- 工具函数 ----------
# 把 kiro-cli chat --list-sessions 的输出（带 ANSI 颜色，写到 stderr）
# 解析成 "session_id\tlabel" 的若干行，按时间从新到旧。
list_sessions_parsed() {
  kiro-cli chat --list-sessions 2>&1 \
    | sed -E $'s/\x1B\\[[0-9;]*[a-zA-Z]//g' \
    | awk '
        /^Chat SessionId:/ {
          id = $3
          if ((getline line) > 0) {
            sub(/^[ \t]+/, "", line)
            print id "\t" line
          }
        }
      '
}

# 截断字符串到最多 N 个"宽度近似单位"，纯粹给 picker 显示用，避免一行拉太长。
# 这里直接按字符数粗暴截断，中文偏宽就稍微多占点位置，不影响功能。
truncate_label() {
  local s="$1" n="${2:-100}"
  if (( ${#s} > n )); then
    printf '%s…' "${s:0:n}"
  else
    printf '%s' "$s"
  fi
}

# ---------- 锁定续跑的会话 ID（如果用户要求续跑）----------
TARGET_SESSION_ID=""

if [[ "$RESUME_MODE" == "latest" ]]; then
  TARGET_SESSION_ID="$(list_sessions_parsed | awk -F'\t' 'NR==1{print $1; exit}')"
  if [[ -z "$TARGET_SESSION_ID" ]]; then
    echo "[retry] 错误：当前目录下没有可续跑的会话。" >&2
    exit 2
  fi
  preview="$(list_sessions_parsed | awk -F'\t' 'NR==1{print $2; exit}')"
  echo "[retry] 续跑最近一次会话: $TARGET_SESSION_ID"
  echo "[retry]   $(truncate_label "$preview" 120)"
fi

if [[ "$RESUME_MODE" == "pick" ]]; then
  if ! [[ "$PICK_N" =~ ^[0-9]+$ ]] || (( PICK_N <= 0 )); then
    echo "[retry] 错误：--pick-n 需要正整数，得到: $PICK_N" >&2
    exit 2
  fi

  mapfile -t SESSIONS < <(list_sessions_parsed | head -n "$PICK_N")
  if (( ${#SESSIONS[@]} == 0 )); then
    echo "[retry] 错误：当前目录下没有可续跑的会话。" >&2
    exit 2
  fi

  echo "[retry] 最近的会话（最多展示 $PICK_N 个）："
  for i in "${!SESSIONS[@]}"; do
    idx=$((i + 1))
    line="${SESSIONS[$i]}"
    id="${line%%$'\t'*}"
    label="${line#*$'\t'}"
    printf '  [%2d] %s  %s\n' "$idx" "$id" "$(truncate_label "$label" 100)"
  done

  # 交互式读一个数字。从 /dev/tty 读，避免被管道/重定向干扰。
  if [[ ! -t 0 ]] && [[ ! -r /dev/tty ]]; then
    echo "[retry] 错误：--pick 需要终端交互，但当前没有可用的 tty。" >&2
    exit 2
  fi
  while true; do
    if [[ -r /dev/tty ]]; then
      read -r -p "[retry] 选择编号 [1-${#SESSIONS[@]}], 直接回车=1, q 取消: " choice </dev/tty || choice=""
    else
      read -r -p "[retry] 选择编号 [1-${#SESSIONS[@]}], 直接回车=1, q 取消: " choice || choice=""
    fi
    [[ -z "$choice" ]] && choice=1
    if [[ "$choice" == "q" || "$choice" == "Q" ]]; then
      echo "[retry] 已取消。" >&2
      exit 130
    fi
    if [[ "$choice" =~ ^[0-9]+$ ]] && (( choice >= 1 && choice <= ${#SESSIONS[@]} )); then
      sel="${SESSIONS[$((choice - 1))]}"
      TARGET_SESSION_ID="${sel%%$'\t'*}"
      sel_label="${sel#*$'\t'}"
      echo "[retry] 选中: $TARGET_SESSION_ID"
      echo "[retry]   $(truncate_label "$sel_label" 120)"
      break
    fi
    echo "[retry] 无效输入，请重试。" >&2
  done
fi

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

# 根据当前 attempt + 是否已锁定 SESSION_ID，组装一次完整的 kiro-cli 调用。
run_kiro_once() {
  local attempt="$1"
  if [[ -n "$TARGET_SESSION_ID" ]]; then
    # 续跑模式：始终续指定会话；前两次发原 prompt，后续发 "继续"。
    if (( attempt <= 2 )); then
      "${RUNNER[@]}" "${KIRO_BASE[@]}" --resume-id "$TARGET_SESSION_ID" "$PROMPT" 2>&1 | tee "$TMP_OUT"
    else
      "${RUNNER[@]}" "${KIRO_BASE[@]}" --resume-id "$TARGET_SESSION_ID" "继续" 2>&1 | tee "$TMP_OUT"
    fi
  else
    # 默认模式：前两次新会话发原 prompt，第 3 次起 --resume 续当前会话。
    if (( attempt <= 2 )); then
      "${RUNNER[@]}" "${KIRO_BASE[@]}" "$PROMPT" 2>&1 | tee "$TMP_OUT"
    else
      "${RUNNER[@]}" "${KIRO_BASE[@]}" --resume "继续" 2>&1 | tee "$TMP_OUT"
    fi
  fi
  return "${PIPESTATUS[0]}"
}

# ---------- 重试循环 ----------
attempt=0
while (( attempt < MAX_RETRY )); do
  attempt=$((attempt+1))
  if [[ -n "$TARGET_SESSION_ID" ]]; then
    echo "${C_YELLOW}[retry] 第 $attempt/$MAX_RETRY 次运行 agent=$AGENT_DESC (续跑 $TARGET_SESSION_ID)${C_RESET}"
  else
    echo "${C_YELLOW}[retry] 第 $attempt/$MAX_RETRY 次运行 agent=$AGENT_DESC${C_RESET}"
  fi
  echo "[retry] ----- agent 输出开始 -----"

  # 清空上次的镜像日志
  : > "$TMP_OUT"

  run_kiro_once "$attempt"
  ec=$?

  echo "[retry] ----- agent 输出结束 (exit=$ec) -----"

  if grep -qiE "$REGEX" "$TMP_OUT"; then
    echo "[retry] 检测到错误，$COOLDOWN 秒后重试…"
    sleep "$COOLDOWN"
    continue
  fi

  echo "[retry] 未检测到错误（退出码 $ec），结束。"
  retries=$((attempt - 1))
  if (( retries == 0 )); then
    echo "[retry] 一次成功，无需重试。"
  else
    echo "[retry] 共运行 $attempt 次（重试了 $retries 次）后成功。"
  fi
  exit "$ec"
done

echo "[retry] 已达最大重试 $MAX_RETRY 次仍报错，停手，请人工介入。（共运行 $attempt 次，重试了 $((attempt - 1)) 次）" >&2
exit 1
