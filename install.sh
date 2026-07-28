#!/usr/bin/env bash
set -Eeuo pipefail

APP="imr-intruder"
SOURCE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
APP_HOME="${IMR_INTRUDER_HOME:-$HOME/.local/share/$APP}"
CONFIG_HOME="${IMR_INTRUDER_CONFIG:-$HOME/.config/$APP}"
STATE_HOME="${IMR_INTRUDER_STATE:-$HOME/.local/state/$APP}"
DATA_HOME="${IMR_INTRUDER_DATA:-$APP_HOME/data}"
CACHE_HOME="${IMR_INTRUDER_CACHE:-$HOME/.cache/$APP}"
BIN_DIR="${IMR_INTRUDER_BIN:-$HOME/.local/bin}"
PYTHON=""

usage() {
  cat <<USAGE
Usage: ./install.sh [--source PATH] [--python PATH] [--app-home PATH] [--bin-dir PATH]

Installs imr-intruder and all Python dependencies into an isolated user release.
USAGE
}

while (($#)); do
  case "$1" in
    --source) SOURCE="$(cd -- "$2" && pwd)"; shift 2 ;;
    --python) PYTHON="$2"; shift 2 ;;
    --app-home) APP_HOME="$2"; shift 2 ;;
    --bin-dir) BIN_DIR="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$PYTHON" ]]; then
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3,10))'; then
      PYTHON="$(command -v "$candidate")"; break
    fi
  done
fi
[[ -n "$PYTHON" ]] || { echo "Python 3.10 or newer is required." >&2; exit 1; }
"$PYTHON" -c 'import sys; print(f"[+] Python {sys.version.split()[0]}"); raise SystemExit(sys.version_info < (3,10))'
[[ -f "$SOURCE/pyproject.toml" ]] || { echo "pyproject.toml not found in $SOURCE" >&2; exit 1; }

VERSION="$($PYTHON - "$SOURCE/src/imr_intruder/__init__.py" <<'PY'
import re, sys
text=open(sys.argv[1],encoding='utf-8').read()
match=re.search(r'__version__\s*=\s*["\']([^"\']+)', text)
if not match: raise SystemExit('Unable to determine version')
print(match.group(1))
PY
)"
RELEASE_DIR="$APP_HOME/releases/$VERSION"
VENV="$RELEASE_DIR/venv"
BACKUP="$APP_HOME/releases/.backup-$VERSION-$$"
OLD_VERSION=""
[[ -f "$APP_HOME/current-version" ]] && OLD_VERSION="$(cat "$APP_HOME/current-version")"
SUCCESS=0
PROFILE_BEGIN="# >>> imr-intruder >>>"
PROFILE_END="# <<< imr-intruder <<<"

cleanup() {
  if ((SUCCESS == 0)); then
    rm -rf "$RELEASE_DIR"
    if [[ -d "$BACKUP" ]]; then mv "$BACKUP" "$RELEASE_DIR"; fi
    if [[ -n "$OLD_VERSION" ]]; then
      printf '%s\n' "$OLD_VERSION" > "$APP_HOME/current-version"
    else
      rm -f "$APP_HOME/current-version" "$BIN_DIR/imr-intruder"
    fi
  fi
}
trap cleanup EXIT
mkdir -p "$APP_HOME/releases" "$CONFIG_HOME" "$STATE_HOME" "$DATA_HOME" "$CACHE_HOME" "$BIN_DIR"
rm -rf "$BACKUP"
if [[ -d "$RELEASE_DIR" ]]; then mv "$RELEASE_DIR" "$BACKUP"; fi
mkdir -p "$RELEASE_DIR"
chmod 700 "$APP_HOME" "$CONFIG_HOME" "$STATE_HOME" "$DATA_HOME" "$CACHE_HOME" 2>/dev/null || true

install_into_venv() {
  local venv="$1"
  local python="$venv/bin/python"
  env -u PYTHONPATH -u PYTHONHOME -u PIP_TARGET -u PIP_PREFIX "$PYTHON" -m pip install --disable-pip-version-check -r "$SOURCE/requirements.txt" &&
  env -u PYTHONPATH -u PYTHONHOME -u PIP_TARGET -u PIP_PREFIX "$PYTHON" -m pip install --disable-pip-version-check --no-deps --no-build-isolation "$SOURCE"
}

printf '[+] Creating isolated environment for v%s\n' "$VERSION"
"$PYTHON" -m venv "$VENV"
if ! install_into_venv "$VENV"; then
  echo "[!] Package index installation failed; checking host-provided dependencies."
  rm -rf "$VENV"
  "$PYTHON" -m venv "$VENV"
  "$PYTHON" "$SOURCE/scripts/link_host_paths.py" "$VENV/bin/python" >/dev/null
  "$VENV/bin/python" "$SOURCE/scripts/check_dependencies.py"
  env -u PYTHONPATH -u PYTHONHOME -u PIP_TARGET -u PIP_PREFIX "$VENV/bin/python" -m pip install --disable-pip-version-check --no-deps --no-build-isolation "$SOURCE"
fi

"$VENV/bin/imr-intruder" version >/dev/null
printf '%s\n' "$VERSION" > "$APP_HOME/current-version"

cp "$SOURCE/uninstall.sh" "$APP_HOME/uninstall.sh"
chmod 700 "$APP_HOME/uninstall.sh"

cat > "$BIN_DIR/imr-intruder" <<LAUNCHER
#!/usr/bin/env bash
set -e
export IMR_INTRUDER_HOME="${APP_HOME}"
export IMR_INTRUDER_CONFIG="${CONFIG_HOME}"
export IMR_INTRUDER_STATE="${STATE_HOME}"
export IMR_INTRUDER_DATA="${DATA_HOME}"
export IMR_INTRUDER_CACHE="${CACHE_HOME}"
VERSION=\$(cat "${APP_HOME}/current-version")
exec "${APP_HOME}/releases/\${VERSION}/venv/bin/imr-intruder" "\$@"
LAUNCHER
chmod 755 "$BIN_DIR/imr-intruder"

PROFILE_BLOCK="$PROFILE_BEGIN
export PATH=\"$BIN_DIR:\$PATH\"
export IMR_INTRUDER_HOME=\"$APP_HOME\"
export IMR_INTRUDER_CONFIG=\"$CONFIG_HOME\"
export IMR_INTRUDER_STATE=\"$STATE_HOME\"
export IMR_INTRUDER_DATA=\"$DATA_HOME\"
export IMR_INTRUDER_CACHE=\"$CACHE_HOME\"
$PROFILE_END"

update_profile() {
  local file="$1"
  touch "$file"
  "$PYTHON" - "$file" "$PROFILE_BEGIN" "$PROFILE_END" "$PROFILE_BLOCK" <<'PY'
from pathlib import Path
import sys
path=Path(sys.argv[1]); begin=sys.argv[2]; end=sys.argv[3]; block=sys.argv[4]
text=path.read_text(encoding='utf-8')
while begin in text and end in text:
    before, rest=text.split(begin,1); _, after=rest.split(end,1); text=before+after.lstrip('\n')
text=text.rstrip()+"\n\n"+block+"\n"
path.write_text(text,encoding='utf-8')
PY
}
update_profile "$HOME/.profile"
[[ -f "$HOME/.bashrc" ]] && update_profile "$HOME/.bashrc"
[[ -f "$HOME/.zshrc" ]] && update_profile "$HOME/.zshrc"

export PATH="$BIN_DIR:$PATH"
export IMR_INTRUDER_HOME="$APP_HOME" IMR_INTRUDER_CONFIG="$CONFIG_HOME" IMR_INTRUDER_STATE="$STATE_HOME" IMR_INTRUDER_DATA="$DATA_HOME" IMR_INTRUDER_CACHE="$CACHE_HOME"
"$BIN_DIR/imr-intruder" doctor --json >/dev/null
rm -rf "$BACKUP"
SUCCESS=1
trap - EXIT
printf '\n[+] imr-intruder v%s installed successfully.\n' "$VERSION"
printf '[+] Command: %s\n' "$BIN_DIR/imr-intruder"
printf '[+] Open a new terminal or run: source ~/.profile\n'
