#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_HOME="${XDG_DATA_HOME:-$HOME/.local/share}/imr-intruder"
BIN_DIR="$HOME/.local/bin"
VENV="$APP_HOME/venv"

command -v python3 >/dev/null 2>&1 || {
  echo "[ERROR] Python 3 is required." >&2
  exit 1
}

python3 - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit("[ERROR] Python 3.10 or newer is required.")
PY

mkdir -p "$APP_HOME" "$BIN_DIR"
python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install --upgrade "$ROOT"

cat > "$BIN_DIR/imr-intruder" <<EOF
#!/usr/bin/env bash
exec "$VENV/bin/imr-intruder" "\$@"
EOF
chmod +x "$BIN_DIR/imr-intruder"
cp "$ROOT/uninstall.sh" "$APP_HOME/uninstall.sh"
chmod +x "$APP_HOME/uninstall.sh"

PATH_LINE='export PATH="$HOME/.local/bin:$PATH" # imr-intruder'
for rc in "$HOME/.profile" "$HOME/.bashrc"; do
  touch "$rc"
  if ! grep -Fq '# imr-intruder' "$rc"; then
    printf '\n%s\n' "$PATH_LINE" >> "$rc"
  fi
done
if [ -n "${ZSH_VERSION:-}" ] || [ -f "$HOME/.zshrc" ]; then
  touch "$HOME/.zshrc"
  if ! grep -Fq '# imr-intruder' "$HOME/.zshrc"; then
    printf '\n%s\n' "$PATH_LINE" >> "$HOME/.zshrc"
  fi
fi

printf '\nimr-intruder installed successfully.\n'
printf 'Launcher: %s\n' "$BIN_DIR/imr-intruder"
printf 'Run now: %s version\n' "$BIN_DIR/imr-intruder"
printf 'New terminals can use: imr-intruder web\n'
