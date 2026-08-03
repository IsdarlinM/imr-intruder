# Installation

## Python requirement

`imr-intruder` requires Python 3.10 or newer. On Windows, `install.cmd` offers to install a supported Python runtime automatically when none is available. On Linux, install Python 3.10+ through the operating system package manager before running the installer.

## Linux native installer

```bash
chmod +x install.sh
./install.sh
```

Optional parameters:

```bash
./install.sh --source /path/to/source
./install.sh --python /usr/bin/python3.12
./install.sh --app-home "$HOME/.local/share/imr-intruder"
./install.sh --bin-dir "$HOME/.local/bin"
```

The installer:

1. Detects Python 3.10+.
2. Reads the application version from the package.
3. Creates a staging virtual environment.
4. Installs dependencies from `requirements.txt`.
5. Installs the project without build isolation downloads.
6. Falls back to validated host dependencies only when the package index is unavailable.
7. Runs `version` and `doctor` before activation.
8. Activates the version under `releases/<version>`.
9. Creates the launcher in `~/.local/bin`.
10. Adds a managed environment block to `.profile` and existing Bash/Zsh profiles.

The installer never requires root.

## Windows CMD installer

Run from Command Prompt:

```cmd
install.cmd
```

Optional parameters:

```cmd
install.cmd /SOURCE C:\path\to\imr-intruder
install.cmd /PYTHON C:\Path\To\python.exe
install.cmd /AUTO-INSTALL-PYTHON
install.cmd /NO-PYTHON-INSTALL
```

When Python 3.10+ is missing, the interactive installer asks for permission before installing Python. `/AUTO-INSTALL-PYTHON` accepts this step for automated deployments. `/NO-PYTHON-INSTALL` preserves fail-fast behavior.

The installer:

1. Detects an existing Python 3.10+ installation, including the launcher and standard per-user/system locations.
2. If Python is missing, asks whether it should be installed automatically.
3. Uses WinGet first; if unavailable, downloads the pinned official Python installer from `python.org`.
4. Verifies the fallback installer with a pinned SHA-256 checksum before execution.
5. Installs Python per-user with pip, the launcher, and PATH integration enabled.
6. Creates an isolated versioned virtual environment.
7. Installs and validates all project dependencies.
8. Creates `%LOCALAPPDATA%\Programs\imr-intruder\bin\imr-intruder.cmd`.
9. Updates the user PATH through the registry without truncating it.
10. Sets `IMR_INTRUDER_HOME`, `CONFIG`, `STATE`, `DATA`, and `CACHE`.
11. Broadcasts the Windows environment update.
12. Validates Python, pip, the installed command, and `doctor` before reporting success.

No PowerShell script or administrator privileges are required. The direct-download fallback requires `curl.exe` and `certutil.exe`, both included in supported Windows 10/11 installations.

## Environment variables

| Variable | Linux default | Windows default |
|---|---|---|
| `IMR_INTRUDER_HOME` | `~/.local/share/imr-intruder` | `%LOCALAPPDATA%\Programs\imr-intruder` |
| `IMR_INTRUDER_CONFIG` | `~/.config/imr-intruder` | `%APPDATA%\imr-intruder` |
| `IMR_INTRUDER_STATE` | `~/.local/state/imr-intruder` | `%LOCALAPPDATA%\imr-intruder\state` |
| `IMR_INTRUDER_DATA` | `$IMR_INTRUDER_HOME/data` | `%LOCALAPPDATA%\imr-intruder\data` |
| `IMR_INTRUDER_CACHE` | `~/.cache/imr-intruder` | `%LOCALAPPDATA%\imr-intruder\cache` |
| `IMR_INTRUDER_GITHUB_TOKEN` | optional update token | optional update token |

## Updating

```bash
imr-intruder check-update
imr-intruder update
```

No new clone is required. The updater downloads and validates a GitHub archive and invokes the native installer from the extracted source.

## Uninstalling

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

Without purge, user data/configuration may be preserved. Purge removes application data, state, cache, and configuration.
