from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from difflib import SequenceMatcher
from html import unescape
from typing import Any

_VOLATILE_PATTERNS = [
    re.compile(r"\b[0-9a-f]{32,64}\b", re.I),
    re.compile(r"\b\d{10,}\b"),
    re.compile(r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:[^\s<]+"),
]


def normalize_body(body: str, content_type: str = "") -> str:
    text = body.replace("\r\n", "\n").strip()
    if "json" in content_type.lower():
        try:
            parsed = json.loads(text)
            text = json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        except json.JSONDecodeError:
            pass
    elif "html" in content_type.lower():
        text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
        text = re.sub(r">\s+<", "><", text)
        text = unescape(text)
    for pattern in _VOLATILE_PATTERNS:
        text = pattern.sub("<VOLATILE>", text)
    return re.sub(r"\s+", " ", text).strip()


def body_hash(body: str, content_type: str = "") -> str:
    return hashlib.sha256(
        normalize_body(body, content_type).encode("utf-8", errors="replace")
    ).hexdigest()


def similarity(left: str, right: str) -> float:
    if left == right:
        return 100.0
    return round(SequenceMatcher(None, left, right, autojunk=False).ratio() * 100, 2)


def _header_value(headers: dict[str, Any], name: str) -> str:
    wanted = name.lower()
    for key, value in headers.items():
        if str(key).lower() == wanted:
            return str(value)
    return ""


def parse_rule(spec: str) -> tuple[str, str]:
    if ":" not in spec:
        return "text", spec
    kind, value = spec.split(":", 1)
    if kind not in {"text", "regex", "header", "json"}:
        return "text", spec
    return kind, value


def validate_rule(spec: str) -> None:
    kind, value = parse_rule(spec)
    if kind == "regex":
        try:
            re.compile(value)
        except re.error as exc:
            raise ValueError(f"Invalid regular expression {value!r}: {exc}") from exc
    elif kind == "header":
        name, _, _ = value.partition("=")
        if not name.strip():
            raise ValueError("Header rule requires a header name.")
    elif kind == "json" and not value.partition("=")[0].strip():
        raise ValueError("JSON rule requires a path.")


def json_path(data: Any, path: str) -> Any:
    if path in {"", "$"}:
        return data
    current = data
    for match in re.finditer(r"([^.[\]]+)|\[(\d+)\]", path.removeprefix("$.")):
        key, index = match.groups()
        if key is not None:
            if not isinstance(current, dict) or key not in current:
                return None
            current = current[key]
        else:
            if not isinstance(current, list) or int(index) >= len(current):
                return None
            current = current[int(index)]
    return current


def rule_matches(spec: str, result: dict[str, Any]) -> bool:
    kind, value = parse_rule(spec)
    body = result.get("body_preview", "")
    if kind == "text":
        return value in body
    if kind == "regex":
        return re.search(value, body, re.I | re.S) is not None
    if kind == "header":
        name, _, expected = value.partition("=")
        actual = _header_value(result.get("response_headers", {}), name)
        return expected in actual if expected else bool(actual)
    if kind == "json":
        path, _, expected = value.partition("=")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            return False
        actual = json_path(parsed, path)
        return str(actual) == expected if expected else actual is not None
    return False


def extract_value(spec: str, result: dict[str, Any]) -> str:
    kind, value = parse_rule(spec)
    body = result.get("body_preview", "")
    if kind == "header":
        return _header_value(result.get("response_headers", {}), value)
    if kind == "regex":
        match = re.search(value, body, re.I | re.S)
        if not match:
            return ""
        return match.group(1) if match.groups() else match.group(0)
    if kind == "json":
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            return ""
        value_found = json_path(parsed, value)
        return "" if value_found is None else str(value_found)
    return value if value in body else ""


def enrich_results(
    results: list[dict[str, Any]],
    baseline_index: int = 0,
    match_rules: list[str] | None = None,
    exclude_rules: list[str] | None = None,
    extract_rules: dict[str, str] | None = None,
    cluster_threshold: float = 98.0,
) -> list[dict[str, Any]]:
    """Enrich only real HTTP responses; transport errors are not response clusters."""
    if not results:
        return results
    match_rules = match_rules or []
    exclude_rules = exclude_rules or []
    extract_rules = extract_rules or {}

    valid = [item for item in results if item.get("status") is not None and not item.get("error")]
    invalid = [item for item in results if item not in valid]
    for result in invalid:
        result.update(
            {
                "body_hash": None,
                "similarity": None,
                "delta_bytes": None,
                "matched": False,
                "excluded": False,
                "cluster": None,
                "anomaly_score": None,
            }
        )

    if not valid:
        return results

    baseline = valid[min(max(baseline_index, 0), len(valid) - 1)]
    baseline_normalized = normalize_body(
        baseline.get("body_preview", ""), baseline.get("content_type", "")
    )
    compare = len(valid) > 1
    clusters: list[tuple[str, str]] = []

    for result in valid:
        normalized = normalize_body(result.get("body_preview", ""), result.get("content_type", ""))
        result["body_hash"] = hashlib.sha256(normalized.encode()).hexdigest()
        result["similarity"] = similarity(baseline_normalized, normalized) if compare else None
        result["delta_bytes"] = (
            result.get("size_bytes", 0) - baseline.get("size_bytes", 0) if compare else None
        )
        result["matched"] = (
            all(rule_matches(rule, result) for rule in match_rules) if match_rules else False
        )
        result["excluded"] = any(rule_matches(rule, result) for rule in exclude_rules)
        result.setdefault("custom", {})
        for name, rule in extract_rules.items():
            result["custom"][name] = extract_value(rule, result)

        if compare:
            cluster_id = None
            for existing_id, representative in clusters:
                if similarity(representative, normalized) >= cluster_threshold:
                    cluster_id = existing_id
                    break
            if cluster_id is None:
                cluster_id = f"C{len(clusters) + 1}"
                clusters.append((cluster_id, normalized))
            result["cluster"] = cluster_id
        else:
            result["cluster"] = None

    if not compare:
        valid[0]["anomaly_score"] = None
        return results

    sizes = [float(item.get("size_bytes", 0)) for item in valid]
    times = [float(item.get("elapsed_ms", 0)) for item in valid]
    status_counts = Counter(item.get("status") for item in valid)
    mean_size = sum(sizes) / len(sizes)
    mean_time = sum(times) / len(times)
    std_size = math.sqrt(sum((value - mean_size) ** 2 for value in sizes) / len(sizes)) or 1.0
    std_time = math.sqrt(sum((value - mean_time) ** 2 for value in times) / len(times)) or 1.0

    for result in valid:
        rarity = 1.0 / status_counts[result.get("status")]
        size_z = abs(float(result.get("size_bytes", 0)) - mean_size) / std_size
        time_z = abs(float(result.get("elapsed_ms", 0)) - mean_time) / std_time
        similarity_component = max(0.0, 100.0 - float(result.get("similarity", 100.0))) / 25.0
        result["anomaly_score"] = round(size_z + time_z + similarity_component + rarity, 2)
    return results
