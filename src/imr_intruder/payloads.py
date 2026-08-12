from __future__ import annotations

import itertools
import json
import re
from collections.abc import Iterable, Mapping
from copy import deepcopy
from typing import Any

_TOKEN = re.compile(r"\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}")
_SECRET_NAME = re.compile(
    r"(?:pass(?:word)?|secret|token|api[_-]?key|authorization|cookie|session|csrf)", re.I
)


def placeholders(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            found.update(placeholders(key))
            found.update(placeholders(item))
    elif isinstance(value, list):
        for item in value:
            found.update(placeholders(item))
    elif isinstance(value, str):
        found.update(_TOKEN.findall(value))
    return found


def render(value: Any, variables: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {render(key, variables): render(item, variables) for key, item in value.items()}
    if isinstance(value, list):
        return [render(item, variables) for item in value]
    if isinstance(value, tuple):
        return tuple(render(item, variables) for item in value)
    if not isinstance(value, str):
        return value

    exact = _TOKEN.fullmatch(value)
    if exact and exact.group(1) in variables:
        return variables[exact.group(1)]

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        replacement = variables.get(name, match.group(0))
        if isinstance(replacement, (dict, list)):
            return json.dumps(replacement, ensure_ascii=False, separators=(",", ":"))
        return str(replacement)

    return _TOKEN.sub(replace, value)


def _normalize_payloads(payloads: Mapping[str, Iterable[Any]]) -> dict[str, list[Any]]:
    normalized = {name: list(values) for name, values in payloads.items()}
    for name, values in normalized.items():
        if not values:
            raise ValueError(f"Payload list is empty: {name}")
    return normalized


def generate_assignments(
    payloads: Mapping[str, Iterable[Any]],
    mode: str = "sniper",
    max_requests: int = 10000,
) -> list[dict[str, Any]]:
    normalized = _normalize_payloads(payloads)
    names = list(normalized)
    if not names:
        return [{}]

    assignments: list[dict[str, Any]] = []
    mode = mode.lower().replace("_", "-")

    if mode == "sniper":
        baseline = {name: values[0] for name, values in normalized.items()}
        for name in names:
            for value in normalized[name]:
                item = dict(baseline)
                item[name] = value
                assignments.append(item)
    elif mode in {"battering-ram", "batteringram"}:
        first = normalized[names[0]]
        for value in first:
            assignments.append({name: value for name in names})
    elif mode == "pitchfork":
        lengths = {len(values) for values in normalized.values()}
        if len(lengths) != 1:
            raise ValueError("Pitchfork requires payload lists with the same number of values.")
        for values in zip(*(normalized[name] for name in names), strict=True):
            assignments.append(dict(zip(names, values, strict=True)))
    elif mode in {"cluster-bomb", "clusterbomb"}:
        for values in itertools.product(*(normalized[name] for name in names)):
            assignments.append(dict(zip(names, values, strict=True)))
            if len(assignments) > max_requests:
                raise ValueError(f"Cluster bomb exceeds --max-requests={max_requests}.")
    else:
        raise ValueError(f"Unsupported payload mode: {mode}")

    if len(assignments) > max_requests:
        raise ValueError(f"Generated {len(assignments)} requests; maximum is {max_requests}.")
    return assignments


def build_requests(
    base_request: dict[str, Any],
    payloads: Mapping[str, Iterable[Any]],
    mode: str = "sniper",
    max_requests: int = 10000,
) -> list[dict[str, Any]]:
    required = placeholders(base_request)
    missing = required - set(payloads)
    if missing:
        raise ValueError(f"Missing payload lists for: {', '.join(sorted(missing))}")
    unused = set(payloads) - required
    if unused:
        raise ValueError(f"Unused payload lists: {', '.join(sorted(unused))}")

    assignments = generate_assignments(payloads, mode=mode, max_requests=max_requests)
    requests: list[dict[str, Any]] = []
    explicit_name = str(base_request.get("name") or "").strip()
    for index, variables in enumerate(assignments, start=1):
        rendered = render(deepcopy(base_request), variables)
        generated_name = (
            ",".join(
                f"{key}={'<REDACTED>' if _SECRET_NAME.search(key) else value}"
                for key, value in variables.items()
            )
            or f"request-{index}"
        )
        if not explicit_name or explicit_name == "request-1":
            rendered["name"] = generated_name
        else:
            rendered["name"] = f"{rendered.get('name') or explicit_name} [{generated_name}]"
        rendered["payload_variables"] = variables
        requests.append(rendered)
    return requests
