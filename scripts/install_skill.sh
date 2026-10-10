#!/usr/bin/env bash
# 一键安装 MCD Bodywise Skill 到 WorkBuddy。
# 用法:
#   bash scripts/install_skill.sh                 # 装到用户级 ~/.workbuddy/skills/mcd-bodywise
#   bash scripts/install_skill.sh /path/to/proj   # 装到项目级 <proj>/.workbuddy/skills/mcd-bodywise
set -euo pipefail

SRC="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${1:-$HOME/.workbuddy/skills/mcd-bodywise}"

mkdir -p "$DEST/src"
cp "$SRC/SKILL.md"          "$DEST/"
cp "$SRC/requirements.txt"  "$DEST/"
cp -r "$SRC/src/."          "$DEST/src/"

echo "✅ 已安装 MCD Bodywise Skill 到: $DEST"
echo "⚠️ 使用前请确认："
echo "   1) 已申请麦当劳 MCP Token: https://open.mcd.cn/mcp"
echo "   2) Token 已配置: 环境变量 MCD_MCP_TOKEN 或文件 ~/.config/mcd/mcp_token"
echo "   3) 已安装依赖: pip install -r $DEST/requirements.txt"
