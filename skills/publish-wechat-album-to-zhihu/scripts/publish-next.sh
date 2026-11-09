#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${ZHIHU_HOLE_PROJECT_DIR:-${WECHAT_ZHIHU_PROJECT_DIR:-}}"
if [[ -z "$PROJECT_DIR" ]]; then
  PROJECT_DIR="$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null || true)"
fi
if [[ -z "$PROJECT_DIR" ]]; then
  echo "错误：请从项目 Git 目录运行，或设置 ZHIHU_HOLE_PROJECT_DIR" >&2
  exit 1
fi
PYTHON_BIN="$PROJECT_DIR/venv/bin/python"
PUBLISH_SCRIPT="$PROJECT_DIR/scripts/publish_wechat_album_to_zhihu.py"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "错误：找不到 Python 虚拟环境：$PYTHON_BIN" >&2
  exit 1
fi

if [[ ! -f "$PUBLISH_SCRIPT" ]]; then
  echo "错误：找不到合集发布脚本：$PUBLISH_SCRIPT" >&2
  exit 1
fi

cd "$PROJECT_DIR"
exec "$PYTHON_BIN" "$PUBLISH_SCRIPT" "$@"
