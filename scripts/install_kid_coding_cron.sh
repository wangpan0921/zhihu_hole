#!/usr/bin/env bash
# 安装 / 卸载 kid coding 少儿编程「每日生成下一课」的 crontab 任务。
#
# 独立于 # zhihu-treehole-auto 块，用自己的标记 # kid-coding-auto，互不干扰。
# 时间表：每天 07:10 调用 scripts/kid_coding_generate_next.sh。
#
# 用法：
#   bash scripts/install_kid_coding_cron.sh install     # 安装/更新
#   bash scripts/install_kid_coding_cron.sh uninstall   # 卸载
#   bash scripts/install_kid_coding_cron.sh status      # 查看
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUNNER="$PROJECT_DIR/scripts/kid_coding_generate_next.sh"
LOG="$PROJECT_DIR/logs/kid_coding_cron.log"
TAG="# kid-coding-auto"

if [[ ! -x "$RUNNER" ]]; then
  echo "错误：找不到或不可执行：$RUNNER" >&2
  exit 1
fi

# 07:10 每天一次（与原 paseo cron 表达式 "10 7 * * *" 一致，本机时区为 Asia/Shanghai）
read -r -d '' BLOCK <<EOF || true
$TAG
10 7 * * *   $RUNNER >> $LOG 2>&1
EOF

current="$(crontab -l 2>/dev/null || true)"

strip_block() {
  # 删除以 $TAG 开头的那一行及其后紧跟的 1 行任务
  awk -v tag="$TAG" '
    $0==tag {skip=1; next}
    skip==1 {skip=0; next}
    {print}
  ' <<<"$1"
}

case "${1:-}" in
  install)
    cleaned="$(strip_block "$current")"
    # 去掉可能的尾部空行后拼接
    cleaned="$(printf '%s\n' "$cleaned" | sed -e '/^$/N;/^\n$/D')"
    if [[ -n "$cleaned" ]]; then
      printf '%s\n%s\n' "$cleaned" "$BLOCK" | crontab -
    else
      printf '%s\n' "$BLOCK" | crontab -
    fi
    echo "已安装 kid-coding-auto 任务（每天 07:10）。当前相关条目："
    crontab -l | grep -A1 "$TAG" || true
    ;;
  uninstall)
    strip_block "$current" | crontab -
    echo "已卸载 kid-coding-auto 任务。"
    ;;
  status)
    echo "当前 kid-coding-auto 相关条目："
    crontab -l 2>/dev/null | grep -A1 "$TAG" || echo "(未安装)"
    ;;
  *)
    echo "用法: $0 install|uninstall|status" >&2
    exit 2
    ;;
esac
