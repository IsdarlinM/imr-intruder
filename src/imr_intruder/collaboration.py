from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from .paths import ensure_paths
from .storage import atomic_json_write, read_json, utc_now

ROLES = {"viewer", "operator", "admin"}


def _file():
    return ensure_paths().config / "collaboration.json"


def create_token(name: str, role: str, expires_hours: int | None = 168) -> str:
    if role not in ROLES:
        raise ValueError(f"Role must be one of: {', '.join(sorted(ROLES))}")
    token = secrets.token_urlsafe(32)
    salt = secrets.token_hex(16)
    digest = hashlib.sha256((salt + token).encode()).hexdigest()
    data = read_json(_file(), default={}) or {}
    if expires_hours is not None and not 1 <= expires_hours <= 8760:
        raise ValueError("Token expiration must be between 1 and 8760 hours.")
    expires_at = (
        (datetime.now(timezone.utc) + timedelta(hours=expires_hours)).isoformat()
        if expires_hours is not None
        else ""
    )
    data[name] = {
        "role": role,
        "salt": salt,
        "digest": digest,
        "created_at": utc_now(),
        "expires_at": expires_at,
    }
    atomic_json_write(_file(), data)
    return token


def verify_token(token: str) -> tuple[str, str] | None:
    data: dict[str, Any] = read_json(_file(), default={}) or {}
    for name, record in data.items():
        expires_at = str(record.get("expires_at", ""))
        if expires_at:
            try:
                if datetime.fromisoformat(expires_at) <= datetime.now(timezone.utc):
                    continue
            except ValueError:
                continue
        digest = hashlib.sha256((record["salt"] + token).encode()).hexdigest()
        if hmac.compare_digest(digest, record["digest"]):
            return name, record["role"]
    return None


def list_tokens() -> list[dict[str, Any]]:
    data: dict[str, Any] = read_json(_file(), default={}) or {}
    return [
        {
            "name": name,
            "role": record["role"],
            "created_at": record.get("created_at", ""),
            "expires_at": record.get("expires_at", ""),
            "active": (
                not record.get("expires_at")
                or datetime.fromisoformat(record["expires_at"]) > datetime.now(timezone.utc)
            ),
        }
        for name, record in sorted(data.items())
    ]


def revoke_token(name: str) -> None:
    data: dict[str, Any] = read_json(_file(), default={}) or {}
    if name not in data:
        raise ValueError(f"Token not found: {name}")
    del data[name]
    atomic_json_write(_file(), data)
