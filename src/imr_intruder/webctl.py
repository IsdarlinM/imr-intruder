from __future__ import annotations

import json
import os
import secrets
import signal
import subprocess
import sys
import time
import urllib.request
import webbrowser
from typing import Any
from urllib.parse import urlsplit

from .paths import ensure_paths
from .storage import atomic_json_write, read_json

_BACKGROUND_PROCESSES: dict[int, subprocess.Popen[Any]] = {}


def _is_loopback(host: str) -> bool:
    return host in {"127.0.0.1", "localhost", "::1"}


def _url(host: str, port: int) -> str:
    formatted = f"[{host}]" if ":" in host and not host.startswith("[") else host
    return f"http://{formatted}:{port}"


def _state() -> dict[str, Any] | None:
    return read_json(ensure_paths().web_state)


def _alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes

            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if not handle:
                return False
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        except (AttributeError, OSError):
            return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, SystemError):
        return False


def _health(url: str, timeout: float = 1.0) -> bool:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    try:
        with urllib.request.urlopen(  # nosec B310
            url.rstrip("/") + "/health", timeout=timeout
        ) as response:
            if response.status != 200:
                return False
            payload = json.loads(response.read().decode("utf-8"))
            return payload.get("status") == "ok" and bool(payload.get("version"))
    except Exception:
        return False


def status() -> dict[str, Any]:
    state = _state()
    if not state:
        return {"running": False}
    running = _alive(int(state.get("pid", 0))) and _health(state.get("url", ""))
    if not running and ensure_paths().web_state.exists():
        ensure_paths().web_state.unlink(missing_ok=True)
    # Older versions stored the bootstrap token in web.json. Never echo legacy
    # secrets (including a token-bearing bootstrap URL) from the status command.
    public_state = {
        key: value for key, value in state.items() if key not in {"token", "bootstrap_url"}
    }
    return {**public_state, "running": running}


def serve(
    host: str,
    port: int,
    token: str,
    allow_remote: bool,
    multiuser: bool,
    open_browser: bool,
    allowed_hosts: list[str] | None = None,
) -> int:
    if not _is_loopback(host) and not allow_remote:
        raise ValueError("Non-loopback binding requires --allow-remote.")
    if not _is_loopback(host) and not allowed_hosts:
        raise ValueError("Remote binding requires at least one --scope target host or CIDR.")
    import uvicorn

    from .web import create_app

    url = _url(host, port)
    if open_browser:
        webbrowser.open(url + (f"/?token={token}" if allow_remote else ""))
    uvicorn.run(
        create_app(
            token,
            require_page_token=allow_remote,
            multiuser=multiuser,
            allowed_hosts=allowed_hosts,
        ),
        host=host,
        port=port,
        log_level="info",
    )
    return 0


def start_background(
    host: str,
    port: int,
    token: str | None,
    allow_remote: bool,
    multiuser: bool,
    allowed_hosts: list[str] | None = None,
) -> dict[str, Any]:
    if not _is_loopback(host) and not allow_remote:
        raise ValueError("Non-loopback binding requires --allow-remote.")
    if not _is_loopback(host) and not allowed_hosts:
        raise ValueError("Remote binding requires at least one --scope target host or CIDR.")
    existing = status()
    if existing.get("running"):
        if existing.get("host") != host or int(existing.get("port", 0)) != port:
            raise RuntimeError(
                f"Web console is already running at {existing.get('url')}; stop it before changing the listener."
            )
        return existing
    token = token or secrets.token_urlsafe(32)
    paths = ensure_paths()
    command = [
        sys.executable,
        "-m",
        "imr_intruder.command",
        "_web-serve",
        f"--host={host}",
        f"--port={port}",
        f"--pid-file={paths.web_pid}",
    ]
    paths.web_pid.unlink(missing_ok=True)
    if allow_remote:
        command.append("--allow-remote")
    if multiuser:
        command.append("--multiuser")
    for allowed_host in allowed_hosts or []:
        command.extend(["--scope", allowed_host])
    log = paths.web_log.open("a", encoding="utf-8")
    kwargs: dict[str, Any] = {
        "stdout": log,
        "stderr": subprocess.STDOUT,
        "stdin": subprocess.DEVNULL,
        "close_fds": True,
        "env": {**os.environ, "IMR_INTRUDER_WEB_RUNTIME_TOKEN": token},
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True
    try:
        process = subprocess.Popen(command, **kwargs)
        _BACKGROUND_PROCESSES[process.pid] = process
    finally:
        log.close()
    url = _url(host, port)
    state_data = {
        "pid": process.pid,
        "host": host,
        "port": port,
        "url": url,
        "multiuser": multiuser,
        "scope": allowed_hosts or [],
        "log": str(paths.web_log),
    }
    atomic_json_write(paths.web_token, {"token": token})
    atomic_json_write(paths.web_state, state_data)
    for attempt in range(100):
        child_state = read_json(paths.web_pid, default={}) or {}
        child_pid = int(child_state.get("pid", 0)) if isinstance(child_state, dict) else 0
        if _health(url):
            if child_pid > 0:
                state_data["pid"] = child_pid
                _BACKGROUND_PROCESSES[child_pid] = process
            atomic_json_write(paths.web_state, state_data)
            result = {**state_data, "running": True}
            if allow_remote:
                result["bootstrap_url"] = f"{url}/?token={token}"
            return result
        if process.poll() is not None and attempt >= 20 and child_pid <= 0:
            break
        time.sleep(0.1)
    tail = (
        paths.web_log.read_text(encoding="utf-8", errors="replace")[-2000:]
        if paths.web_log.exists()
        else ""
    )
    stop()
    raise RuntimeError(f"Web server did not become healthy. Log:\n{tail}")


def stop() -> dict[str, Any]:
    state = _state()
    if not state:
        return {"stopped": False, "reason": "not running"}
    pid = int(state.get("pid", 0))
    tracked = _BACKGROUND_PROCESSES.get(pid)
    verified = _alive(pid) and _health(str(state.get("url", "")))
    if not verified and tracked is None:
        paths = ensure_paths()
        paths.web_state.unlink(missing_ok=True)
        paths.web_pid.unlink(missing_ok=True)
        paths.web_token.unlink(missing_ok=True)
        return {"stopped": False, "reason": "stale state removed", "pid": pid}
    if _alive(pid):
        try:
            os.kill(pid, signal.SIGTERM)
        except (OSError, SystemError):
            pass
        for _ in range(50):
            if not _alive(pid):
                break
            time.sleep(0.1)
        if _alive(pid):
            try:
                os.kill(pid, getattr(signal, "SIGKILL", signal.SIGTERM))
            except (OSError, SystemError, AttributeError):
                pass
    tracked = _BACKGROUND_PROCESSES.pop(pid, tracked)
    if tracked is not None:
        try:
            tracked.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass
    paths = ensure_paths()
    paths.web_state.unlink(missing_ok=True)
    paths.web_pid.unlink(missing_ok=True)
    paths.web_token.unlink(missing_ok=True)
    return {"stopped": True, "pid": pid}


def open_ui() -> str:
    state = status()
    if not state.get("running"):
        raise RuntimeError("Web console is not running.")
    url = state["url"]
    if not _is_loopback(state.get("host", "")):
        token_data = read_json(ensure_paths().web_token, default={}) or {}
        token = str(token_data.get("token", "")) if isinstance(token_data, dict) else ""
        if not token:
            raise RuntimeError("Web bootstrap token is unavailable; restart the console.")
        url += f"/?token={token}"
    webbrowser.open(url)
    return url
