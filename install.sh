#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
APP_ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/imr-intruder"
BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/imr-intruder"
SKIP_PATH=0

usage() {
  cat <<'EOF'
Usage: ./install.sh [--skip-path]

Installs imr-intruder for the current Linux user in an isolated virtual environment.
No root privileges are required.

Options:
  --skip-path  Do not modify shell startup files.
  -h, --help   Show this help.
EOF
}

for arg in "$@"; do
  case "$arg" in
    --skip-path) SKIP_PATH=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "[ERROR] Unknown option: $arg" >&2; usage >&2; exit 2 ;;
  esac
done

command -v "$PYTHON_BIN" >/dev/null 2>&1 || {
  echo "[ERROR] Python 3.10 or newer is required." >&2
  exit 1
}

"$PYTHON_BIN" - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit("[ERROR] Python 3.10 or newer is required.")
PY

VERSION="$($PYTHON_BIN - <<PY
import re
from pathlib import Path
text = Path(r"$ROOT/src/imr_intruder/__init__.py").read_text(encoding="utf-8")
match = re.search(r'__version__\s*=\s*["\']([^"\']+)', text)
if not match:
    raise SystemExit("Unable to determine package version")
print(match.group(1))
PY
)"

RELEASES_DIR="$APP_ROOT/releases"
RELEASE_DIR="$RELEASES_DIR/$VERSION"
BACKUP_DIR="$RELEASE_DIR.backup.$$"
CURRENT_LINK="$APP_ROOT/current"
LAUNCHER="$BIN_DIR/imr-intruder"

mkdir -p "$RELEASES_DIR" "$BIN_DIR" "$STATE_DIR"
chmod 700 "$APP_ROOT" "$RELEASES_DIR" "$STATE_DIR" 2>/dev/null || true

restore_on_error() {
  code=$?
  if [ "$code" -ne 0 ]; then
    echo "[ERROR] Installation failed; restoring the previous release." >&2
    rm -rf "$RELEASE_DIR"
    if [ -d "$BACKUP_DIR" ]; then
      mv "$BACKUP_DIR" "$RELEASE_DIR"
    fi
  fi
  exit "$code"
}
trap restore_on_error ERR

if [ -d "$RELEASE_DIR" ]; then
  rm -rf "$BACKUP_DIR"
  mv "$RELEASE_DIR" "$BACKUP_DIR"
fi

if [ "${IMR_INSTALL_TEST_MODE:-0}" = "1" ]; then
  "$PYTHON_BIN" -m venv "$RELEASE_DIR/venv" || {
    echo "[ERROR] Python venv is unavailable. On Debian/Kali install: sudo apt install python3-venv" >&2
    false
  }
  PARENT_SITE="$($PYTHON_BIN -c 'import site; print(site.getsitepackages()[0])')"
  VENV_SITE="$($RELEASE_DIR/venv/bin/python -c 'import site; print(site.getsitepackages()[0])')"
  printf '%s\n' "$PARENT_SITE" > "$VENV_SITE/imr-installer-test.pth"
  "$RELEASE_DIR/venv/bin/python" -m pip install --disable-pip-version-check --no-build-isolation --no-deps "$ROOT"
else
  "$PYTHON_BIN" -m venv "$RELEASE_DIR/venv" || {
    echo "[ERROR] Python venv is unavailable. On Debian/Kali install: sudo apt install python3-venv" >&2
    false
  }
  "$RELEASE_DIR/venv/bin/python" -m pip install --disable-pip-version-check --upgrade pip
  "$RELEASE_DIR/venv/bin/python" -m pip install --disable-pip-version-check --upgrade "$ROOT"
fi
"$RELEASE_DIR/venv/bin/imr-intruder" doctor --json >/dev/null
"$RELEASE_DIR/venv/bin/imr-intruder" version >/dev/null

ln -sfn "$RELEASE_DIR" "$CURRENT_LINK"
cat > "$LAUNCHER" <<EOF
#!/usr/bin/env bash
exec "$CURRENT_LINK/venv/bin/imr-intruder" "\$@"
EOF
chmod 755 "$LAUNCHER"

cp "$ROOT/uninstall.sh" "$APP_ROOT/uninstall.sh"
chmod 700 "$APP_ROOT/uninstall.sh"
printf '%s\n' "$VERSION" > "$APP_ROOT/VERSION"
rm -rf "$BACKUP_DIR"
trap - ERR

if [ "$SKIP_PATH" -eq 0 ]; then
  PATH_LINE='export PATH="${XDG_BIN_HOME:-$HOME/.local/bin}:$PATH" # imr-intruder'
  for rc in "$HOME/.profile" "$HOME/.bashrc"; do
    touch "$rc"
    if ! grep -Fq '# imr-intruder' "$rc"; then
      printf '\n%s\n' "$PATH_LINE" >> "$rc"
    fi
  done
  if [ -f "$HOME/.zshrc" ] || [ "${SHELL##*/}" = "zsh" ]; then
    touch "$HOME/.zshrc"
    if ! grep -Fq '# imr-intruder' "$HOME/.zshrc"; then
      printf '\n%s\n' "$PATH_LINE" >> "$HOME/.zshrc"
    fi
  fi
fi

export PATH="$BIN_DIR:$PATH"
printf '\nimr-intruder v%s installed successfully.\n' "$VERSION"
printf 'Launcher: %s\n' "$LAUNCHER"
printf 'Run now: imr-intruder doctor\n'
printf 'Web UI:  imr-intruder web start --background\n'
printf 'Uninstall: %s\n' "$APP_ROOT/uninstall.sh"
