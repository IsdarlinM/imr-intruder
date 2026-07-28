# Installation and lifecycle

## Supported environments

- Linux distributions with Python 3.10+ and `venv`
- Kali Linux, Debian, Ubuntu, Fedora, Arch, and similar distributions
- Windows 10 or Windows 11 with Python 3.10+

The project does not commit binaries or virtual environments. The native platform installer creates an isolated environment on the user's machine.

## Linux installer

```bash
chmod +x install.sh
./install.sh
```

Default locations:

```text
Application releases: ~/.local/share/imr-intruder/releases/<version>/
Current release:       ~/.local/share/imr-intruder/current
Command launcher:      ~/.local/bin/imr-intruder
Runtime state/logs:    ~/.local/state/imr-intruder/
```

XDG overrides are honored through `XDG_DATA_HOME`, `XDG_BIN_HOME`, and `XDG_STATE_HOME`.

The installer is idempotent. Reinstalling the same version replaces that release only after preserving a temporary backup. `doctor` and `version` must pass before installation completes.

### Missing venv support

Debian, Ubuntu, or Kali:

```bash
sudo apt update
sudo apt install python3-venv
```

Specify another Python interpreter:

```bash
PYTHON_BIN=python3.12 ./install.sh
```

### PATH

The installer adds this marked line when needed:

```bash
export PATH="${XDG_BIN_HOME:-$HOME/.local/bin}:$PATH" # imr-intruder
```

Use `--skip-path` to opt out.

## Windows CMD installer

```cmd
install.cmd
```

Default locations:

```text
Application releases: %LOCALAPPDATA%\Programs\imr-intruder\releases\<version>\
Command launcher:      %LOCALAPPDATA%\Programs\imr-intruder\bin\imr-intruder.cmd
Runtime state/logs:    %LOCALAPPDATA%\imr-intruder\state\
```

The installer uses `py -3` when available, otherwise `python`. The launcher directory is added to the current user's PATH through `HKCU\Environment`, and Windows is notified of the environment update. Existing terminals may still need to be reopened.

## Verification

```bash
imr-intruder doctor
imr-intruder version
imr-intruder request --help
imr-intruder intrude --help
imr-intruder batch --help
imr-intruder web --help
```

Start and validate the web console:

```bash
imr-intruder web start --background --no-browser
imr-intruder web status
imr-intruder web stop
```

## Updating

From an authenticated environment that can access the official repository:

```bash
imr-intruder update
```

Preview the exact update command without changing the installation:

```bash
imr-intruder update --dry-run
```

The native installers can also be rerun from a freshly downloaded or cloned release. User runtime state is stored separately from release files.

## Uninstallation

Linux:

```bash
~/.local/share/imr-intruder/uninstall.sh
~/.local/share/imr-intruder/uninstall.sh --purge
```

Windows:

```cmd
%LOCALAPPDATA%\Programs\imr-intruder\uninstall.cmd
%LOCALAPPDATA%\Programs\imr-intruder\uninstall.cmd /PURGE
```

Without purge, runtime logs and web-process state are preserved for troubleshooting.
