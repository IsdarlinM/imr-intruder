from __future__ import annotations

import asyncio
import json
from typing import Any

import websockets


async def _run(url: str, messages: list[str], timeout: float, headers: dict[str, str] | None) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    async with websockets.connect(url, additional_headers=headers, open_timeout=timeout) as socket:
        for message in messages:
            await socket.send(message)
            try:
                reply = await asyncio.wait_for(socket.recv(), timeout=timeout)
                results.append({"sent": message, "received": reply, "error": ""})
            except asyncio.TimeoutError:
                results.append({"sent": message, "received": "", "error": "timeout"})
    return results


def run_websocket(url: str, messages: list[str], timeout: float = 10, headers: dict[str, str] | None = None) -> list[dict[str, Any]]:
    return asyncio.run(_run(url, messages, timeout, headers))
