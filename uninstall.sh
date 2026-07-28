#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/imr-intruder"
BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/imr-intruder"
PURGE=0

case "${1:-}" in
  --purge) PURGE=1 ;;
  "") ;;
  -h|--help)
    echo "Usage: uninstall.sh [--purge]"
    echo "--purge also removes logs and runtime state."
    exit 0
    ;;
  *) echo "[ERROR] Unknown option: $1" >&2; exit 2 ;;
esac

if [ -x "$BIN_DIR/imr-intruder" ]; then
  "$BIN_DIR/imr-intruder" web stop >/dev/null 2>&1 || true
fi

rm -f "$BIN_DIR/imr-intruder"
rm -rf "$APP_ROOT"

for rc in "$HOME/.profile" "$HOME/.bashrc" "$HOME/.zshrc"; do
  if [ -f "$rc" ]; then
    sed -i.bak '/# imr-intruder$/d' "$rc" 2>/dev/null || true
    rm -f "$rc.bak"
  fi
done

if [ "$PURGE" -eq 1 ]; then
  rm -rf "$STATE_DIR"
fi

printf 'imr-intruder removed. Open a new terminal to refresh PATH.\n'
if [ "$PURGE" -eq 0 ]; then
  printf 'Runtime logs/state were preserved in: %s\n' "$STATE_DIR"
fi
