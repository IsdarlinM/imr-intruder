#!/usr/bin/env bash
set -Eeuo pipefail
APP="imr-intruder"
APP_HOME="${IMR_INTRUDER_HOME:-$HOME/.local/share/$APP}"
BIN_DIR="${IMR_INTRUDER_BIN:-$HOME/.local/bin}"
PURGE=0
[[ "${1:-}" == "--purge" ]] && PURGE=1

if [[ -x "$BIN_DIR/imr-intruder" ]]; then "$BIN_DIR/imr-intruder" web stop >/dev/null 2>&1 || true; fi
rm -f "$BIN_DIR/imr-intruder"
rm -rf "$APP_HOME/releases"
rm -f "$APP_HOME/current-version" "$APP_HOME/uninstall.sh"

python_cmd="$(command -v python3 || command -v python || true)"
for profile in "$HOME/.profile" "$HOME/.bashrc" "$HOME/.zshrc"; do
  [[ -f "$profile" && -n "$python_cmd" ]] || continue
  "$python_cmd" - "$profile" <<'PY'
from pathlib import Path
import sys
path=Path(sys.argv[1]); text=path.read_text(encoding='utf-8'); begin='# >>> imr-intruder >>>'; end='# <<< imr-intruder <<<'
while begin in text and end in text:
    before, rest=text.split(begin,1); _, after=rest.split(end,1); text=before+after.lstrip('\n')
path.write_text(text.rstrip()+"\n",encoding='utf-8')
PY
done

if ((PURGE)); then
  rm -rf "$APP_HOME" "${IMR_INTRUDER_CONFIG:-$HOME/.config/$APP}" "${IMR_INTRUDER_STATE:-$HOME/.local/state/$APP}" "${IMR_INTRUDER_CACHE:-$HOME/.cache/$APP}"
fi
echo "imr-intruder uninstalled."
exit 0
