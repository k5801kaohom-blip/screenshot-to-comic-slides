#!/usr/bin/env bash
# Install the screenshot-to-comic-slides skill into a local skills directory.
set -euo pipefail

SKILL_NAME="screenshot-to-comic-slides"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/${SKILL_NAME}"
TARGET_ROOT="${SKILLS_DIR:-$HOME/skills}"
TARGET_DIR="${TARGET_ROOT}/${SKILL_NAME}"

if [[ ! -d "$SOURCE_DIR" ]]; then
  echo "找不到技能資料夾：$SOURCE_DIR" >&2
  exit 1
fi

mkdir -p "$TARGET_ROOT"

if [[ -e "$TARGET_DIR" ]]; then
  BACKUP="${TARGET_DIR}.backup.$(date +%Y%m%d%H%M%S)"
  echo "偵測到既有安裝，備份至：$BACKUP"
  mv "$TARGET_DIR" "$BACKUP"
fi

cp -R "$SOURCE_DIR" "$TARGET_DIR"
find "$TARGET_DIR" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
find "$TARGET_DIR" -name '*.pyc' -delete 2>/dev/null || true

echo "已安裝技能至：$TARGET_DIR"
echo
echo "建議套件："
echo "  pip install pillow python-pptx openai pyyaml"
echo
echo "驗證指令："
echo "  python ${TARGET_DIR}/scripts/make_contact_sheet.py --help"
