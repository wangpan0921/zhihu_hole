#!/usr/bin/env bash
# 将项目内置技能安装到 Codex 和 Kiro 的技能目录。
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
SOURCE_ROOT="$PROJECT_ROOT/skills"
CODEX_HOME_DIR="${CODEX_HOME:-$HOME/.codex}"
CODEX_TARGET="${CODEX_SKILLS_DIR:-$CODEX_HOME_DIR/skills}"
KIRO_TARGET="${KIRO_SKILLS_DIR:-$PROJECT_ROOT/.kiro/skills}"

SKILLS=(
  excalidraw-lesson-images
  generate-kid-coding-video
  publish-wechat-album-to-zhihu
  pytorch-training-efficiency-course
)

MODE=copy
FORCE=0
COMMAND=install

usage() {
  cat <<'EOF'
用法：
  bash scripts/install_project_skills.sh install [--force] [--link]
  bash scripts/install_project_skills.sh check

说明：
  install  将项目 skills/ 下的四个技能复制到 Codex 和项目 Kiro 目录。
  check    检查两个目标目录是否与项目内技能一致，不修改文件。
  --force  替换目标目录中同名技能；不影响其他技能。
  --link   使用指向项目 skills/ 的符号链接，而不是复制文件。

可选环境变量：
  CODEX_HOME        Codex 根目录，默认 ~/.codex
  CODEX_SKILLS_DIR  Codex 技能目录，默认 $CODEX_HOME/skills
  KIRO_SKILLS_DIR   Kiro 技能目录，默认 <项目>/.kiro/skills
EOF
}

die() {
  echo "错误：$*" >&2
  exit 1
}

parse_args() {
  [[ $# -ge 1 ]] && COMMAND="$1" || true
  shift || true
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --force) FORCE=1 ;;
      --link) MODE=link ;;
      -h|--help) usage; exit 0 ;;
      *) die "未知参数：$1" ;;
    esac
    shift
  done
}

validate_sources() {
  [[ -d "$SOURCE_ROOT" ]] || die "找不到项目技能目录：$SOURCE_ROOT"
  local name
  for name in "${SKILLS[@]}"; do
    [[ -f "$SOURCE_ROOT/$name/SKILL.md" ]] || die "技能缺少 SKILL.md：$SOURCE_ROOT/$name"
  done
}

same_tree() {
  local source="$1" target="$2"
  [[ -d "$target" ]] || return 1
  diff -qr -- "$source" "$target" >/dev/null
}

check_target() {
  local target_root="$1" name source target
  local failed=0
  for name in "${SKILLS[@]}"; do
    source="$SOURCE_ROOT/$name"
    target="$target_root/$name"
    if [[ -L "$target" ]] && [[ "$(readlink -f -- "$target")" == "$(readlink -f -- "$source")" ]]; then
      echo "通过：$target -> $source"
    elif same_tree "$source" "$target"; then
      echo "通过：$target"
    else
      echo "不一致或缺失：$target"
      failed=1
    fi
  done
  return "$failed"
}

install_target() {
  local target_root="$1" name source target
  mkdir -p -- "$target_root"
  for name in "${SKILLS[@]}"; do
    source="$SOURCE_ROOT/$name"
    target="$target_root/$name"
    if [[ -e "$target" || -L "$target" ]]; then
      if [[ "$FORCE" -ne 1 ]]; then
        die "目标已存在：$target；如需替换请加 --force"
      fi
      [[ "$target" == "$target_root/$name" ]] || die "拒绝删除非技能目录：$target"
      rm -rf -- "$target"
    fi
    if [[ "$MODE" == link ]]; then
      ln -s -- "$source" "$target"
    else
      cp -a -- "$source" "$target"
    fi
    echo "已安装：$target"
  done
}

parse_args "$@"
validate_sources

case "$COMMAND" in
  check)
    check_target "$CODEX_TARGET"
    check_target "$KIRO_TARGET"
    ;;
  install)
    install_target "$CODEX_TARGET"
    install_target "$KIRO_TARGET"
    echo "完成：Codex=$CODEX_TARGET，Kiro=$KIRO_TARGET"
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
