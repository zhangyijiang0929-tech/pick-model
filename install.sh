#!/usr/bin/env bash
# 把 pick-model 装到 Agent 的 skills 目录。
#
# 三种用法：
#   ./install.sh                      # 从当前仓库安装到 ~/.workbuddy/skills
#   ./install.sh /path/to/skills      # 指定 skills 根目录
#   curl -fsSL https://raw.githubusercontent.com/zhangyijiang0929-tech/pick-model/main/install.sh | bash
#                                     # 一行安装（自动 clone）
#
# 环境变量：
#   PICK_MODEL_REPO  覆盖 clone 源，默认本仓库的 GitHub 地址
#   PICK_MODEL_DEST  覆盖安装位置，默认 ~/.workbuddy/skills
set -eo pipefail

REPO_URL="${PICK_MODEL_REPO:-https://github.com/zhangyijiang0929-tech/pick-model.git}"
DEST_ROOT="${1:-${PICK_MODEL_DEST:-$HOME/.workbuddy/skills}}"
DEST="$DEST_ROOT/pick-model"

SELF="${BASH_SOURCE[0]:-}"
TMP_DIR=""

cleanup() {
  [ -n "$TMP_DIR" ] && [ -d "$TMP_DIR" ] && rm -rf "$TMP_DIR"
  return 0
}
trap cleanup EXIT

# 判断是"本地仓库运行"还是"管道运行"
if [ -n "$SELF" ] && [ -f "$SELF" ]; then
  SRC="$(cd "$(dirname "$SELF")" && pwd)"
  MODE="local"
else
  MODE="piped"
fi

if [ "$MODE" = "piped" ] || [ ! -f "${SRC:-}/SKILL.md" ]; then
  MODE="piped"
  if ! command -v git >/dev/null 2>&1; then
    echo "需要 git 才能安装。" >&2
    exit 1
  fi
  TMP_DIR="$(mktemp -d)"
  echo "→ 正在拉取 $REPO_URL"
  if ! git clone --depth 1 -q "$REPO_URL" "$TMP_DIR/src"; then
    echo "拉取失败。请检查网络，或改用 git clone 手动安装：" >&2
    echo "  git clone $REPO_URL $DEST" >&2
    exit 1
  fi
  SRC="$TMP_DIR/src"
fi

if [ ! -f "$SRC/SKILL.md" ]; then
  echo "在 $SRC 找不到 SKILL.md，不是有效的 skill 目录。" >&2
  exit 1
fi

mkdir -p "$DEST_ROOT"

if [ -e "$DEST" ]; then
  if [ -t 0 ]; then
    echo "$DEST 已存在。"
    read -r -p "覆盖安装？[y/N] " ans
    case "$ans" in
      [yY]*) ;;
      *) echo "已取消。"; exit 0 ;;
    esac
  else
    # 非交互（curl | bash）：先备份再覆盖，绝不静默删除用户数据
    BAK="$DEST.bak.$(date +%Y%m%d%H%M%S)"
    mv "$DEST" "$BAK"
    echo "已存在，旧版本备份到 $BAK"
  fi
  rm -rf "$DEST"
fi

cp -R "$SRC" "$DEST"
rm -rf "$DEST/.git" "$DEST/.github"

echo "✓ 已安装到 $DEST"

if command -v python3 >/dev/null 2>&1; then
  echo ""
  python3 "$DEST/scripts/estimate.py" --check
else
  echo "提示：未找到 python3，成本估算脚本不可用（skill 仍可基于价目表工作）。"
fi

echo ""
echo "装好了。在你的 Agent 里试：/pick-model 从 500 张收据里抽商户名、金额，输出 JSON"
