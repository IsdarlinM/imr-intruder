# Installation

## Python requirement

`imr-intruder` requires Python 3.10 or newer. The installers stop before changing the system when the requirement is not met.

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

Optional source path:

```cmd
install.cmd /SOURCE C:\path\to\imr-intruder
```

The installer:

1. Detects `py -3` or `python` with Python 3.10+.
2. Creates an isolated versioned virtual environment.
3. Installs all dependencies.
4. Creates `%LOCALAPPDATA%\Programs\imr-intruder\bin\imr-intruder.cmd`.
5. Updates the user PATH through the registry without truncating it.
6. Sets `IMR_INTRUDER_HOME`, `CONFIG`, `STATE`, `DATA`, and `CACHE`.
7. Broadcasts the Windows environment update.
8. Validates the installed command with `doctor`.

No PowerShell is required.

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
