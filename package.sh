#!/usr/bin/env bash
# Package the skill folder into a distributable ZIP archive.
set -euo pipefail

SKILL_NAME="screenshot-to-comic-slides"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="${ROOT_DIR}/${SKILL_NAME}"
DIST_DIR="${ROOT_DIR}/dist"
OUTPUT="${DIST_DIR}/${SKILL_NAME}-skill.zip"

if [[ ! -d "$SOURCE_DIR" ]]; then
  echo "找不到技能資料夾：$SOURCE_DIR" >&2
  exit 1
fi

mkdir -p "$DIST_DIR"
rm -f "$OUTPUT"

(
  cd "$ROOT_DIR"
  zip -r -9 "$OUTPUT" "$SKILL_NAME" \
    -x '*/__pycache__/*' '*.pyc' '*.DS_Store'
)

unzip -t "$OUTPUT" >/dev/null
echo "已產出：$OUTPUT"
ls -lh "$OUTPUT"
if command -v sha256sum >/dev/null 2>&1; then
  sha256sum "$OUTPUT"
fi
