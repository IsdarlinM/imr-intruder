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
4. Upgrades pip, setuptools, and wheel inside that environment.
5. Installs dependencies from `requirements.txt` through the isolated interpreter.
6. Installs the project without build isolation downloads.
7. Falls back to validated host dependencies only when the package index is unavailable.
8. Runs `version` and `doctor` before activation.
9. Activates the version under `releases/<version>`.
10. Creates the launcher in `~/.local/bin`.
11. Adds a managed environment block to `.profile` and existing Bash/Zsh profiles.

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
install.cmd /FORCE-PYTHON-BOOTSTRAP
install.cmd /NO-WINGET
```

When Python 3.10+ is missing, the interactive installer asks for permission before installing Python. Before discovery it clears inherited Python, pip, and virtual-environment overrides that can make a valid interpreter fail. It checks commands, launcher paths, PEP 514 `ExecutablePath` and default `InstallPath` values, standard CPython directories, and WinGet package directories. `/AUTO-INSTALL-PYTHON` accepts this step for automated deployments. `/NO-PYTHON-INSTALL` preserves fail-fast behavior. `/FORCE-PYTHON-BOOTSTRAP` ignores existing Python installations so the clean-machine path can be tested. `/NO-WINGET` forces the checksum-verified official-installer path.

The Windows bootstrap is split into three components: `install.cmd` coordinates the flow, `scripts/find_python.cmd` performs read-only interpreter discovery, and `scripts/bootstrap_python.cmd` installs a pinned runtime when discovery fails. This keeps each CMD file small and avoids command-line length growth.

The installer:

1. Detects an existing Python 3.10+ installation, including the launcher and standard per-user/system locations.
2. If Python is missing, asks whether it should be installed automatically.
3. Uses one WinGet Python 3.13 package when available and validates that the resulting interpreter is runnable.
4. Downloads the pinned official installer with built-in `curl.exe`, falling back to `certutil.exe` when curl is unavailable.
5. Verifies the official installer with a pinned SHA-256 checksum before execution.
6. Installs Python per-user with pip enabled, then re-discovers the actual runnable interpreter even when the installer enters maintenance mode or ignores the requested `TargetDir`.
7. Creates an isolated versioned virtual environment.
8. Installs and validates all project dependencies.
9. Creates `%LOCALAPPDATA%\Programs\imr-intruder\bin\imr-intruder.cmd`.
10. Adds the selected Python directory, its `Scripts` directory, and the imr-intruder launcher directory to the user PATH through the registry without truncating it.
11. Creates a managed command shim in an already-active writable user PATH directory (normally `%LOCALAPPDATA%\Microsoft\WindowsApps`, with `%LOCALAPPDATA%\Microsoft\WinGet\Links` as a fallback) and validates `imr-intruder version`. This allows the command to become immediately resolvable in existing CMD/PowerShell sessions when one of those directories is already present in the current PATH.
12. Sets `IMR_INTRUDER_HOME`, `IMR_INTRUDER_CONFIG`, `IMR_INTRUDER_STATE`, `IMR_INTRUDER_DATA`, and `IMR_INTRUDER_CACHE` persistently for the current user.
13. Broadcasts the Windows environment update.
14. Validates Python, pip, the installed command, and `doctor` before reporting success. The application launcher clears inherited `PYTHONHOME`, `PYTHONPATH`, pip, and virtual-environment overrides on every run.

The installer intentionally does **not** create persistent `PYTHONHOME` or `PYTHONPATH` variables. Those variables are not required for a normal CPython installation and commonly make Python and virtual environments unusable when they point to stale directories. Instead, the installer registers only the actual Python runtime directory and its `Scripts` directory in the user `Path`, and the application uses an isolated virtual environment.

No PowerShell script or administrator privileges are required. The direct-download path requires `certutil.exe` for SHA-256 verification and uses built-in `curl.exe` for download, with `certutil -urlcache` as a download fallback.

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
