from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Any

from .paths import ensure_paths
from .storage import atomic_json_write, read_json, utc_now

ROLES = {"viewer", "operator", "admin"}


def _file():
    return ensure_paths().config / "collaboration.json"


def create_token(name: str, role: str) -> str:
    if role not in ROLES:
        raise ValueError(f"Role must be one of: {', '.join(sorted(ROLES))}")
    token = secrets.token_urlsafe(32)
    salt = secrets.token_hex(16)
    digest = hashlib.sha256((salt + token).encode()).hexdigest()
    data = read_json(_file(), default={}) or {}
    data[name] = {"role": role, "salt": salt, "digest": digest, "created_at": utc_now()}
    atomic_json_write(_file(), data)
    return token


def verify_token(token: str) -> tuple[str, str] | None:
    data: dict[str, Any] = read_json(_file(), default={}) or {}
    for name, record in data.items():
        digest = hashlib.sha256((record["salt"] + token).encode()).hexdigest()
        if hmac.compare_digest(digest, record["digest"]):
            return name, record["role"]
    return None


def list_tokens() -> list[dict[str, str]]:
    data: dict[str, Any] = read_json(_file(), default={}) or {}
    return [
        {
            "name": name,
            "role": record["role"],
            "created_at": record.get("created_at", ""),
        }
        for name, record in sorted(data.items())
    ]


def revoke_token(name: str) -> None:
    data: dict[str, Any] = read_json(_file(), default={}) or {}
    if name not in data:
        raise ValueError(f"Token not found: {name}")
    del data[name]
    atomic_json_write(_file(), data)
