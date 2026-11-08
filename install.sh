#!/usr/bin/env bash
# 把 pick-model 装到 Agent 的 skills 目录。
# 用法：./install.sh [目标目录]
#   默认：~/.workbuddy/skills
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST_ROOT="${1:-$HOME/.workbuddy/skills}"
DEST="$DEST_ROOT/pick-model"

if [ ! -f "$SRC/SKILL.md" ]; then
  echo "找不到 SKILL.md，请在仓库根目录运行。" >&2
  exit 1
fi

mkdir -p "$DEST_ROOT"

if [ -e "$DEST" ]; then
  echo "$DEST 已存在。"
  read -r -p "覆盖安装？[y/N] " ans
  case "$ans" in
    [yY]*) rm -rf "$DEST" ;;
    *) echo "已取消。"; exit 0 ;;
  esac
fi

cp -R "$SRC" "$DEST"
rm -rf "$DEST/.git"

echo "✓ 已安装到 $DEST"
if command -v python3 >/dev/null 2>&1; then
  python3 "$DEST/scripts/estimate.py" --check
else
  echo "提示：未找到 python3，成本估算脚本不可用（skill 仍可基于价目表工作）。"
fi
