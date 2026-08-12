from __future__ import annotations

from importlib.metadata import entry_points
from typing import Any


def discover_plugins() -> dict[str, Any]:
    plugins: dict[str, Any] = {}
    selected = entry_points(group="imr_intruder.plugins")
    for entry in selected:
        try:
            plugins[entry.name] = entry.load()
        except Exception as exc:
            plugins[entry.name] = exc
    return plugins


def plugin_status() -> list[dict[str, str]]:
    rows = []
    for name, value in discover_plugins().items():
        if isinstance(value, Exception):
            rows.append(
                {
                    "name": name,
                    "status": "error",
                    "detail": f"{type(value).__name__}: {value}",
                }
            )
        else:
            rows.append(
                {
                    "name": name,
                    "status": "loaded",
                    "detail": getattr(value, "__doc__", "") or "",
                }
            )
    return rows
