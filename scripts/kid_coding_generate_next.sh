#!/usr/bin/env bash
# 每天 07:10 由 crontab 调用：生成少儿编程连载的「下一课」草稿。
#
# 背景：此任务原先挂在本机 paseo 调度器（~/.paseo/schedules/9f370bf1.json），
# 但 paseo daemon 退出后无人看护重启，导致定时任务长期静默。现迁移到 crontab 托管。
#
# 做法：复用 paseo 当年那段生成 prompt（已导出到 scripts/kid_coding_next_prompt.txt），
# 用 codex exec 非交互执行。codex 本身会先按 prompt 判断「最新一课是否已定稿」，
# 未定稿则跳过、已定稿则生成 lesson-(NN+1) 的 article.md + 配图.md。
#
# 安装/卸载：bash scripts/install_kid_coding_cron.sh install|uninstall|status
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PROMPT_FILE="$PROJECT_DIR/scripts/kid_coding_next_prompt.txt"
LOG="$PROJECT_DIR/logs/kid_coding_cron.log"
LOCK="$PROJECT_DIR/logs/.kid_coding_cron.lock"

# crontab 的 PATH 很短，显式补上 node（codex 的 #!/usr/bin/env node 依赖）、codex 及常用 bin 路径。
# 注意：必须用稳定的 nvm node，不要用 MiCO 会话级 runtime node（路径随会话变、crontab 下不可靠）。
NODE_BIN_DIR="/home/wangpan/.nvm/versions/node/v24.18.0/bin"
export PATH="$NODE_BIN_DIR:/home/wangpan/.npm-global/bin:/home/wangpan/.local/bin:/usr/local/bin:/usr/bin:/bin"
export CODEX_HOME="${CODEX_HOME:-/home/wangpan/.codex}"

mkdir -p "$PROJECT_DIR/logs"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') [kid_coding_cron] $*" >> "$LOG"; }

# 防重入：若已有一次在跑则退出
if [[ -e "$LOCK" ]]; then
  log "已有实例在运行（锁 $LOCK 存在），本次跳过。"
  exit 0
fi
trap 'rm -f "$LOCK"' EXIT
echo "$$" > "$LOCK"

if [[ ! -f "$PROMPT_FILE" ]]; then
  log "错误：找不到生成 prompt 文件 $PROMPT_FILE"
  exit 1
fi

if ! command -v codex >/dev/null 2>&1; then
  log "错误：PATH 中找不到 codex 可执行文件"
  exit 1
fi

log "===== 开始生成下一课（工作目录 $PROJECT_DIR）====="

# 先跑本地判定脚本，把「该生成/该跳过」写进日志，便于事后排查
if [[ -x "$PROJECT_DIR/venv/bin/python" ]]; then
  JUDGE="$("$PROJECT_DIR/venv/bin/python" "$PROJECT_DIR/scripts/kid_coding_next.py" 2>&1 | head -1 || true)"
  log "判定脚本首行：$JUDGE"
fi

# 非交互执行：workspace-write 沙箱允许写工作目录内文件，无需人工审批
set +e
codex exec \
  --sandbox workspace-write \
  -C "$PROJECT_DIR" \
  --skip-git-repo-check \
  --color never \
  - < "$PROMPT_FILE" >> "$LOG" 2>&1
RC=$?
set -e

if [[ $RC -eq 0 ]]; then
  log "===== codex 执行结束，退出码 0 ====="
else
  log "===== codex 执行结束，退出码 $RC（可能失败，请查看上方输出）====="
fi
exit $RC
