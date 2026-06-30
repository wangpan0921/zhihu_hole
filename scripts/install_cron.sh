#!/usr/bin/env bash
# 安装 / 卸载 当前用户的 crontab 任务
#
# 默认时间表：
#   19:00  预生成「明天」的 morning + evening 两条想法草稿到 data/pending/
#   08:00  扫 docs/pending/ 发布一篇文章到微信公众号
#   19:00  扫 docs/pending/ 发布一篇文章到知乎专栏（同一时刻，两条任务并行跑互不影响）
#   07:00  发布 morning slot 想法（data/pending 没有则现生现发）
#   18:00  发布 evening slot 想法
#
# 用法：
#   bash scripts/install_cron.sh install     # 安装
#   bash scripts/install_cron.sh uninstall   # 卸载
#   bash scripts/install_cron.sh status      # 查看当前任务
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="$PROJECT_DIR/venv/bin/python"
LOG="$PROJECT_DIR/logs/cron.log"

if [[ ! -x "$PY" ]]; then
  echo "错误：找不到 $PY ，请先创建 venv 并安装依赖" >&2
  exit 1
fi

# 唯一标记，便于查询/卸载
TAG="# zhihu-treehole-auto"

# 关键：crontab 默认 PATH 很短，且不读 .env。我们用 cd 到项目目录 + dotenv 加载 .env
# 这里直接显式 cd，并依赖 src/utils.py 里的 load_dotenv() 读 .env
RUN_GEN="cd $PROJECT_DIR && $PY scripts/generate_drafts.py --for tomorrow >> $LOG 2>&1"
RUN_PUB_M="cd $PROJECT_DIR && $PY scripts/publish_slot.py morning >> $LOG 2>&1"
RUN_PUB_E="cd $PROJECT_DIR && $PY scripts/publish_slot.py evening >> $LOG 2>&1"
RUN_PUB_ARTICLE="cd $PROJECT_DIR && $PY scripts/publish_articles.py >> $LOG 2>&1"
RUN_PUB_WECHAT="cd $PROJECT_DIR && $PY scripts/publish_wechat_articles.py >> $LOG 2>&1"

# 6 行任务（含一行注释 tag）
read -r -d '' BLOCK <<EOF || true
$TAG
0  8 * * *   $RUN_PUB_WECHAT
0 19 * * *   $RUN_GEN
0 19 * * *   $RUN_PUB_ARTICLE
0  7 * * *   $RUN_PUB_M
0 18 * * *   $RUN_PUB_E
EOF

# tag 后面跟着的任务行数（用于 install/uninstall 时整块替换）
TASK_LINES=5

cmd="${1:-status}"

case "$cmd" in
  install)
    # 先剥掉旧的同 tag 块（tag 行 + 后面 N 行任务）再插入
    current=$(crontab -l 2>/dev/null || true)
    cleaned=$(echo "$current" | awk -v tag="$TAG" -v n="$TASK_LINES" '
      $0==tag {skip=n; next}
      skip>0  {skip--; next}
      {print}
    ')
    {
      [[ -n "$cleaned" ]] && echo "$cleaned"
      echo "$BLOCK"
    } | crontab -
    echo "已安装 cron 任务："
    echo "$BLOCK"
    ;;
  uninstall)
    current=$(crontab -l 2>/dev/null || true)
    cleaned=$(echo "$current" | awk -v tag="$TAG" -v n="$TASK_LINES" '
      $0==tag {skip=n; next}
      skip>0  {skip--; next}
      {print}
    ')
    if [[ -z "$cleaned" ]]; then
      crontab -r 2>/dev/null || true
    else
      echo "$cleaned" | crontab -
    fi
    echo "已卸载 zhihu-treehole 相关 cron 任务"
    ;;
  status)
    crontab -l 2>/dev/null | grep -A"$TASK_LINES" "$TAG" || echo "（未安装）"
    ;;
  *)
    echo "用法: $0 {install|uninstall|status}" >&2
    exit 2
    ;;
esac
