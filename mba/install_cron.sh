#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="$PROJECT_DIR/venv/bin/python"
LOG="$PROJECT_DIR/logs/mba-cron.log"
TAG="# mba-group-daily"
TASK="0 8 * * * cd $PROJECT_DIR && $PY scripts/mba_news_daily.py --channel zhihu --limit 1 >> $LOG 2>&1"

if [[ ! -x "$PY" ]]; then
  echo "错误：找不到 $PY" >&2
  exit 1
fi

remove_existing() {
  crontab -l 2>/dev/null | awk -v tag="$TAG" '$0 == tag {skip=1; next} skip == 1 {skip=0; next} {print}' || true
}

case "${1:-status}" in
  install)
    current="$(remove_existing)"
    { [[ -n "$current" ]] && echo "$current"; echo "$TAG"; echo "$TASK"; } | crontab -
    echo "已安装 MBA 群每日发布任务："
    echo "$TASK"
    ;;
  uninstall)
    current="$(remove_existing)"
    if [[ -n "$current" ]]; then echo "$current" | crontab -; else crontab -r 2>/dev/null || true; fi
    echo "已卸载 MBA 群每日发布任务"
    ;;
  status)
    crontab -l 2>/dev/null | grep -A1 -F "$TAG" || echo "（未安装）"
    ;;
  *) echo "用法: $0 {install|uninstall|status}" >&2; exit 2 ;;
esac
