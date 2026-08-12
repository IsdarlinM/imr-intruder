from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from .core import execute_request
from .intelligence import extract_value
from .payloads import render
from .storage import load_session, save_session


def run_macro(path: Path, session_name: str | None = None) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    steps = data.get("steps") if isinstance(data, dict) else None
    if not isinstance(steps, list):
        raise ValueError("Macro requires a steps list.")
    session = (
        load_session(session_name)
        if session_name
        else {"headers": {}, "cookies": {}, "variables": {}}
    )
    variables = dict(session.get("variables", {}))
    cookie_jar = httpx.Cookies(session.get("cookies", {}))
    results: list[dict[str, Any]] = []
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict) or "request" not in step:
            raise ValueError(f"Macro step {index} requires a request object.")
        request = render(step["request"], variables)
        request["headers"] = {
            **session.get("headers", {}),
            **request.get("headers", {}),
        }
        request["cookies"] = {
            **session.get("cookies", {}),
            **request.get("cookies", {}),
        }
        result = execute_request(index, request, cookie_jar=cookie_jar)
        results.append(result)
        for name, rule in (step.get("extract") or {}).items():
            variables[name] = extract_value(str(rule), result)
        if step.get("require_status") is not None and result.get("status") != int(
            step["require_status"]
        ):
            raise RuntimeError(
                f"Macro step {index} returned {result.get('status')} instead of {step['require_status']}."
            )
    if session_name:
        session["variables"] = variables
        session["cookies"] = {cookie.name: cookie.value for cookie in cookie_jar.jar}
        save_session(session_name, session)
    return results
