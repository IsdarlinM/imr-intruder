#!/usr/bin/env bash
set -euo pipefail
APP_HOME="${XDG_DATA_HOME:-$HOME/.local/share}/imr-intruder"
BIN_DIR="$HOME/.local/bin"
rm -f "$BIN_DIR/imr-intruder"
rm -rf "$APP_HOME"
for rc in "$HOME/.profile" "$HOME/.bashrc" "$HOME/.zshrc"; do
  if [ -f "$rc" ]; then
    sed -i.bak '/# imr-intruder$/d' "$rc" 2>/dev/null || true
    rm -f "$rc.bak"
  fi
done
printf 'imr-intruder removed. Open a new terminal to refresh PATH.\n'
