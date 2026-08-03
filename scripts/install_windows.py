from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

MINIMUM_PYTHON = (3, 10)
ENV_NAMES = (
    "IMR_INTRUDER_HOME",
    "IMR_INTRUDER_CONFIG",
    "IMR_INTRUDER_STATE",
    "IMR_INTRUDER_DATA",
    "IMR_INTRUDER_CACHE",
)


class InstallationError(RuntimeError):
    """Raised when the Windows installation cannot be completed safely."""


def log(message: str) -> None:
    print(message, flush=True)


def run(
    command: list[str],
    *,
    env: dict[str, str],
    check: bool = True,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        env=env,
        text=True,
        capture_output=capture,
        check=False,
    )
    if check and completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        suffix = f": {detail}" if detail else ""
        raise InstallationError(f"Command failed ({completed.returncode}): {' '.join(command)}{suffix}")
    return completed


def project_version(source: Path) -> str:
    init_file = source / "src" / "imr_intruder" / "__init__.py"
    match = re.search(
        r'__version__\s*=\s*["\']([^"\']+)',
        init_file.read_text(encoding="utf-8"),
    )
    if not match:
        raise InstallationError("Unable to determine the project version.")
    return match.group(1)


def clean_python_environment() -> dict[str, str]:
    env = dict(os.environ)
    for name in ("PYTHONPATH", "PYTHONHOME", "PIP_TARGET", "PIP_PREFIX"):
        env.pop(name, None)
    env.setdefault("PIP_DISABLE_PIP_VERSION_CHECK", "1")
    return env


def runtime_paths() -> dict[str, Path]:
    local = os.environ.get("LOCALAPPDATA")
    roaming = os.environ.get("APPDATA")
    if not local or not roaming:
        raise InstallationError("LOCALAPPDATA and APPDATA must be defined.")
    app_home = Path(local) / "Programs" / "imr-intruder"
    return {
        "app_home": app_home,
        "config": Path(roaming) / "imr-intruder",
        "state": Path(local) / "imr-intruder" / "state",
        "data": Path(local) / "imr-intruder" / "data",
        "cache": Path(local) / "imr-intruder" / "cache",
        "bin": app_home / "bin",
    }


def venv_python(venv: Path) -> Path:
    return venv / "Scripts" / "python.exe"


def site_packages(python: Path, env: dict[str, str]) -> Path:
    completed = run(
        [str(python), "-c", "import json,site; print(json.dumps(site.getsitepackages()))"],
        env=env,
        capture=True,
    )
    candidates = json.loads(completed.stdout.strip())
    if not candidates:
        raise InstallationError("Unable to determine virtualenv site-packages.")
    return Path(candidates[0])


def create_venv(venv: Path, env: dict[str, str]) -> None:
    if venv.exists():
        shutil.rmtree(venv)
    run([sys.executable, "-m", "venv", str(venv)], env=env)
    python = venv_python(venv)
    run([str(python), "-m", "ensurepip", "--upgrade"], env=env, check=False)
    run([str(python), "-m", "pip", "--version"], env=env)


def install_from_index(source: Path, venv: Path, env: dict[str, str]) -> None:
    python = venv_python(venv)
    run(
        [str(python), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"],
        env=env,
    )
    run(
        [str(python), "-m", "pip", "install", "-r", str(source / "requirements.txt")],
        env=env,
    )
    run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--no-build-isolation",
            str(source),
        ],
        env=env,
    )


def install_from_host(source: Path, venv: Path, env: dict[str, str]) -> None:
    """Offline fallback: reuse validated host dependencies and copy the package."""
    python = venv_python(venv)
    run(
        [sys.executable, str(source / "scripts" / "link_host_paths.py"), str(python)],
        env=env,
    )
    run([str(python), str(source / "scripts" / "check_dependencies.py")], env=env)
    destination = site_packages(python, env) / "imr_intruder"
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source / "src" / "imr_intruder", destination)


def install_package(source: Path, release_dir: Path, env: dict[str, str]) -> Path:
    venv = release_dir / "venv"
    create_venv(venv, env)
    try:
        log("[+] Installing Python dependencies and imr-intruder")
        install_from_index(source, venv, env)
    except InstallationError as exc:
        log(f"[!] Online package installation failed: {exc}")
        log("[!] Trying validated dependencies from the host Python runtime")
        create_venv(venv, env)
        install_from_host(source, venv, env)
    python = venv_python(venv)
    run([str(python), "-m", "imr_intruder", "version"], env=env)
    return python


def launcher_text(paths: dict[str, Path]) -> str:
    app_home = paths["app_home"]
    return "\r\n".join(
        [
            "@echo off",
            "setlocal",
            f'set "IMR_INTRUDER_HOME={app_home}"',
            f'set "IMR_INTRUDER_CONFIG={paths["config"]}"',
            f'set "IMR_INTRUDER_STATE={paths["state"]}"',
            f'set "IMR_INTRUDER_DATA={paths["data"]}"',
            f'set "IMR_INTRUDER_CACHE={paths["cache"]}"',
            f'set /p VERSION=<"{app_home / "current-version"}"',
            f'call "{app_home}\\releases\\%VERSION%\\venv\\Scripts\\python.exe" -m imr_intruder %*',
            "",
        ]
    )


def application_environment(paths: dict[str, Path], base: dict[str, str]) -> dict[str, str]:
    env = dict(base)
    values = {
        "IMR_INTRUDER_HOME": paths["app_home"],
        "IMR_INTRUDER_CONFIG": paths["config"],
        "IMR_INTRUDER_STATE": paths["state"],
        "IMR_INTRUDER_DATA": paths["data"],
        "IMR_INTRUDER_CACHE": paths["cache"],
    }
    env.update({name: str(value) for name, value in values.items()})
    env["PATH"] = str(paths["bin"]) + os.pathsep + env.get("PATH", "")
    return env


def configure_user_environment(source: Path, paths: dict[str, Path], env: dict[str, str]) -> None:
    run(
        [
            sys.executable,
            str(source / "scripts" / "windows_path.py"),
            "install",
            str(paths["bin"]),
            str(paths["app_home"]),
            str(paths["config"]),
            str(paths["state"]),
            str(paths["data"]),
            str(paths["cache"]),
        ],
        env=env,
    )


def install(source: Path) -> str:
    if sys.version_info < MINIMUM_PYTHON:
        raise InstallationError("Python 3.10 or newer is required.")
    source = source.resolve()
    if not (source / "pyproject.toml").is_file():
        raise InstallationError(f"Invalid source directory: {source}")

    version = project_version(source)
    paths = runtime_paths()
    app_home = paths["app_home"]
    releases = app_home / "releases"
    release_dir = releases / version
    backup = releases / f".backup-{version}-{uuid.uuid4().hex}"
    current_file = app_home / "current-version"
    launcher = paths["bin"] / "imr-intruder.cmd"
    old_current = current_file.read_text(encoding="utf-8").strip() if current_file.exists() else None
    old_launcher = launcher.read_bytes() if launcher.exists() else None
    env = clean_python_environment()

    for path in (*paths.values(), releases):
        path.mkdir(parents=True, exist_ok=True)

    if backup.exists():
        shutil.rmtree(backup)
    if release_dir.exists():
        shutil.move(str(release_dir), str(backup))
    release_dir.mkdir(parents=True)

    try:
        log(f"[+] Creating isolated release v{version}")
        python = install_package(source, release_dir, env)
        app_env = application_environment(paths, env)
        run([str(python), "-m", "imr_intruder", "doctor", "--json"], env=app_env)

        shutil.copy2(source / "uninstall.cmd", app_home / "uninstall.cmd")
        shutil.copy2(source / "scripts" / "windows_path.py", app_home / "windows_path.py")
        launcher.write_text(launcher_text(paths), encoding="utf-8", newline="")
        current_file.write_text(version + "\n", encoding="utf-8")

        run(
            ["cmd.exe", "/d", "/c", str(launcher), "doctor", "--json"],
            env=app_env,
        )
        configure_user_environment(source, paths, app_env)
    except Exception:
        if release_dir.exists():
            shutil.rmtree(release_dir, ignore_errors=True)
        if backup.exists():
            shutil.move(str(backup), str(release_dir))
        if old_current is None:
            current_file.unlink(missing_ok=True)
        else:
            current_file.write_text(old_current + "\n", encoding="utf-8")
        if old_launcher is None:
            launcher.unlink(missing_ok=True)
        else:
            launcher.write_bytes(old_launcher)
        raise
    else:
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)

    log("")
    log(f"[+] imr-intruder v{version} installed successfully.")
    log(f"[+] Python runtime: {sys.executable}")
    log("[+] Open a new CMD window and run: imr-intruder --help")
    return version


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install imr-intruder on Windows.")
    parser.add_argument("--source", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        install(args.source)
    except (InstallationError, OSError, subprocess.SubprocessError, ValueError) as exc:
        print(f"[ERROR] Installation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
