from __future__ import annotations

import json
import os
import re
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .paths import ensure_paths

_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")


def safe_name(value: str, label: str = "name") -> str:
    if not _SAFE_NAME.fullmatch(value):
        raise ValueError(f"Invalid {label}; use letters, numbers, dot, underscore, or hyphen.")
    return value


def atomic_json_write(path: Path, data: Any, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.chmod(temp_name, mode)
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON file {path}: {exc}") from exc


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def session_path(name: str) -> Path:
    return ensure_paths().sessions / f"{safe_name(name, 'session name')}.json"


def workspace_path(name: str) -> Path:
    return ensure_paths().workspaces / safe_name(name, "workspace name")


def create_session(name: str, data: dict[str, Any] | None = None) -> Path:
    path = session_path(name)
    if path.exists():
        raise ValueError(f"Session already exists: {name}")
    payload: dict[str, Any] = {
        "name": name,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "headers": {},
        "cookies": {},
        "variables": {},
        "auth": None,
        "proxy": None,
        "verify_tls": True,
    }
    if data:
        payload.update(data)
    atomic_json_write(path, payload)
    return path


def load_session(name: str) -> dict[str, Any]:
    path = session_path(name)
    data = read_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"Session not found: {name}")
    return data


def save_session(name: str, data: dict[str, Any]) -> Path:
    data = dict(data)
    data["name"] = name
    data["updated_at"] = utc_now()
    path = session_path(name)
    atomic_json_write(path, data)
    return path


def list_sessions() -> list[str]:
    return sorted(path.stem for path in ensure_paths().sessions.glob("*.json"))


def delete_session(name: str) -> None:
    session_path(name).unlink(missing_ok=False)


def create_workspace(name: str) -> Path:
    root = workspace_path(name)
    if root.exists():
        raise ValueError(f"Workspace already exists: {name}")
    for child in (
        "requests",
        "payloads",
        "sessions",
        "results",
        "bodies",
        "exports",
        "macros",
    ):
        (root / child).mkdir(parents=True, exist_ok=True)
    atomic_json_write(root / "workspace.json", {"name": name, "created_at": utc_now()})
    return root


def list_workspaces() -> list[str]:
    return sorted(path.name for path in ensure_paths().workspaces.iterdir() if path.is_dir())


def set_current_workspace(name: str) -> Path:
    root = workspace_path(name)
    if not root.is_dir():
        raise ValueError(f"Workspace not found: {name}")
    marker = ensure_paths().config / "current_workspace"
    marker.write_text(name + "\n", encoding="utf-8")
    try:
        marker.chmod(0o600)
    except OSError:
        pass
    return root


def current_workspace() -> str | None:
    marker = ensure_paths().config / "current_workspace"
    try:
        value = marker.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    return value or None


def export_workspace(name: str, destination: Path) -> Path:
    root = workspace_path(name)
    if not root.is_dir():
        raise ValueError(f"Workspace not found: {name}")
    destination = destination.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(destination, "w:gz") as archive:
        archive.add(root, arcname=root.name, recursive=True)
    return destination
