from __future__ import annotations

import json
import os
import secrets
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any

from .paths import ensure_paths
from .storage import atomic_json_write, read_json


def _is_loopback(host: str) -> bool:
    return host in {"127.0.0.1", "localhost", "::1"}


def _state() -> dict[str, Any] | None:
    return read_json(ensure_paths().web_state)


def _alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _health(url: str, timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/health", timeout=timeout) as response:
            return response.status == 200
    except Exception:
        return False


def status() -> dict[str, Any]:
    state = _state()
    if not state:
        return {"running": False}
    running = _alive(int(state.get("pid", 0))) and _health(state.get("url", ""))
    if not running and ensure_paths().web_state.exists():
        ensure_paths().web_state.unlink(missing_ok=True)
    return {**state, "running": running}


def serve(host: str, port: int, token: str, allow_remote: bool, multiuser: bool, open_browser: bool) -> int:
    if not _is_loopback(host) and not allow_remote:
        raise ValueError("Non-loopback binding requires --allow-remote.")
    import uvicorn
    from .web import create_app
    url = f"http://{host}:{port}"
    if open_browser:
        webbrowser.open(url + (f"/?token={token}" if allow_remote else ""))
    uvicorn.run(create_app(token, require_page_token=allow_remote, multiuser=multiuser), host=host, port=port, log_level="info")
    return 0


def start_background(host: str, port: int, token: str | None, allow_remote: bool, multiuser: bool) -> dict[str, Any]:
    existing = status()
    if existing.get("running"):
        return existing
    if not _is_loopback(host) and not allow_remote:
        raise ValueError("Non-loopback binding requires --allow-remote.")
    token = token or secrets.token_urlsafe(32)
    paths = ensure_paths()
    command = [sys.executable, "-m", "imr_intruder.command", "_web-serve", "--host", host, "--port", str(port), "--token", token]
    if allow_remote: command.append("--allow-remote")
    if multiuser: command.append("--multiuser")
    log = paths.web_log.open("a", encoding="utf-8")
    kwargs: dict[str, Any] = {"stdout": log, "stderr": subprocess.STDOUT, "stdin": subprocess.DEVNULL, "close_fds": os.name != "nt"}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True
    process = subprocess.Popen(command, **kwargs)
    url = f"http://{host}:{port}"
    state_data = {"pid": process.pid, "host": host, "port": port, "url": url, "token": token, "multiuser": multiuser, "log": str(paths.web_log)}
    atomic_json_write(paths.web_state, state_data)
    for _ in range(100):
        if _health(url):
            return {**state_data, "running": True}
        if process.poll() is not None:
            break
        time.sleep(0.1)
    tail = paths.web_log.read_text(encoding="utf-8", errors="replace")[-2000:] if paths.web_log.exists() else ""
    stop()
    raise RuntimeError(f"Web server did not become healthy. Log:\n{tail}")


def stop() -> dict[str, Any]:
    state = _state()
    if not state:
        return {"stopped": False, "reason": "not running"}
    pid = int(state.get("pid", 0))
    if _alive(pid):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
        for _ in range(50):
            if not _alive(pid):
                break
            time.sleep(0.1)
        if _alive(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except (OSError, AttributeError):
                pass
    ensure_paths().web_state.unlink(missing_ok=True)
    return {"stopped": True, "pid": pid}


def open_ui() -> str:
    state = status()
    if not state.get("running"):
        raise RuntimeError("Web console is not running.")
    url = state["url"]
    if not _is_loopback(state.get("host", "")):
        url += f"/?token={state['token']}"
    webbrowser.open(url)
    return url
