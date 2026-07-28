from __future__ import annotations

import json
import os
import secrets
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7415
START_TIMEOUT_SECONDS = 12.0
STOP_TIMEOUT_SECONDS = 8.0
_BACKGROUND_HANDLES: dict[int, subprocess.Popen[bytes]] = {}


def state_directory() -> Path:
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return root / "imr-intruder" / "state"
    root = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return root / "imr-intruder"


def state_file() -> Path:
    return state_directory() / "web.json"


def default_log_file() -> Path:
    return state_directory() / "web.log"


def _write_state(data: dict[str, Any]) -> None:
    directory = state_directory()
    directory.mkdir(parents=True, exist_ok=True)
    path = state_file()
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    if os.name != "nt":
        temporary.chmod(0o600)
    temporary.replace(path)


def read_state() -> dict[str, Any] | None:
    try:
        data = json.loads(state_file().read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def clear_state() -> None:
    try:
        state_file().unlink()
    except FileNotFoundError:
        pass


def _health_url(host: str, port: int) -> str:
    display_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    if ":" in display_host and not display_host.startswith("["):
        display_host = f"[{display_host}]"
    return f"http://{display_host}:{port}/health"


def _url_reachable(url: str, timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
            return response.status == 200
    except (OSError, urllib.error.URLError, ValueError):
        return False


def _pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        completed = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return completed.returncode == 0 and f'"{pid}"' in completed.stdout
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def web_status() -> dict[str, Any]:
    state = read_state()
    if not state:
        return {"running": False, "reason": "no-state"}

    try:
        pid = int(state.get("pid", 0))
        host = str(state["host"])
        port = int(state["port"])
    except (KeyError, TypeError, ValueError):
        clear_state()
        return {"running": False, "reason": "invalid-state"}

    process_alive = _pid_exists(pid)
    health_url = _health_url(host, port)
    healthy = _url_reachable(health_url)
    if not process_alive and not healthy:
        clear_state()
        return {"running": False, "reason": "stale-state"}

    return {
        **state,
        "running": process_alive and healthy,
        "process_alive": process_alive,
        "healthy": healthy,
        "health_url": health_url,
    }


def start_background(
    *,
    host: str,
    port: int,
    open_browser: bool,
    allow_remote: bool,
    token: str | None,
    log_file: Path | None = None,
) -> dict[str, Any]:
    current = web_status()
    if current.get("running"):
        raise ValueError(
            f"La consola web ya está activa en {current.get('access_url', current.get('url', ''))}."
        )

    log_path = (log_file or default_log_file()).expanduser().resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    effective_token = token or (secrets.token_urlsafe(32) if allow_remote else None)

    command = [
        sys.executable,
        "-m",
        "imr_intruder",
        "web",
        "start",
        "--foreground",
        "--host",
        host,
        "--port",
        str(port),
        "--no-browser",
    ]
    if allow_remote:
        command.append("--allow-remote")
    if effective_token:
        command.extend(["--token", effective_token])

    creationflags = 0
    popen_kwargs: dict[str, Any] = {}
    if os.name == "nt":
        creationflags = (
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
    else:
        popen_kwargs["start_new_session"] = True

    with log_path.open("ab", buffering=0) as log_handle:
        process = subprocess.Popen(  # noqa: S603
            command,
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            close_fds=os.name != "nt",
            creationflags=creationflags,
            **popen_kwargs,
        )

    display_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    if ":" in display_host and not display_host.startswith("["):
        display_host = f"[{display_host}]"
    url = f"http://{display_host}:{port}"
    access_url = (
        f"{url}/?token={effective_token}"
        if allow_remote and effective_token
        else url
    )
    _BACKGROUND_HANDLES[process.pid] = process
    state = {
        "pid": process.pid,
        "host": host,
        "port": port,
        "url": url,
        "access_url": access_url,
        "log_file": str(log_path),
        "started_at": time.time(),
    }
    _write_state(state)

    deadline = time.monotonic() + START_TIMEOUT_SECONDS
    health_url = _health_url(host, port)
    while time.monotonic() < deadline:
        if process.poll() is not None:
            clear_state()
            raise RuntimeError(
                f"La consola web terminó durante el arranque. Revisa {log_path}."
            )
        if _url_reachable(health_url):
            if open_browser:
                webbrowser.open(access_url)
            return {**state, "running": True, "healthy": True}
        time.sleep(0.2)

    stop_background(force=True)
    raise RuntimeError(f"La consola web no respondió a tiempo. Revisa {log_path}.")


def stop_background(*, force: bool = False) -> bool:
    state = read_state()
    if not state:
        return False
    try:
        pid = int(state.get("pid", 0))
    except (TypeError, ValueError):
        clear_state()
        return False

    if not _pid_exists(pid):
        clear_state()
        return False

    local_handle = _BACKGROUND_HANDLES.pop(pid, None)
    if local_handle is not None:
        if force:
            local_handle.kill()
        else:
            local_handle.terminate()
    elif os.name == "nt":
        command = ["taskkill", "/PID", str(pid), "/T"]
        if force:
            command.append("/F")
        subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            clear_state()
            return False

    deadline = time.monotonic() + STOP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if local_handle is not None:
            if local_handle.poll() is not None:
                local_handle.wait(timeout=0)
                clear_state()
                return True
        elif not _pid_exists(pid):
            clear_state()
            return True
        time.sleep(0.15)

    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    else:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    clear_state()
    return True


def open_background_web() -> str:
    status = web_status()
    if not status.get("running"):
        raise ValueError("La consola web no está activa. Usa: imr-intruder web start --background")
    access_url = str(status.get("access_url") or status.get("url"))
    webbrowser.open(access_url)
    return access_url
