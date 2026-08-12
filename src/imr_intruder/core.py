from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urlsplit

import httpx

from .intelligence import enrich_results, json_path, validate_rule
from .storage import atomic_json_write, read_json, utc_now

MAX_WORKERS = 32
DEFAULT_BODY_LIMIT = 1024 * 1024
_SECRET_HEADERS = {
    "authorization",
    "cookie",
    "set-cookie",
    "proxy-authorization",
    "x-api-key",
}
_FRAMING_HEADERS = {"content-length", "transfer-encoding"}
_HTTP_METHOD = re.compile(r"^[!#$%&'*+.^_\x60|~0-9A-Za-z-]+$")
_JITTER = random.SystemRandom()

_SECRET_FIELD_RE = re.compile(
    r"(?:pass(?:word)?|secret|token|api[_-]?key|authorization|cookie|session|csrf)",
    re.I,
)


def _bounded_integer(value: Any, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer between {minimum} and {maximum}.")
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be an integer between {minimum} and {maximum}.") from exc
    if not math.isfinite(numeric) or not numeric.is_integer():
        raise ValueError(f"{name} must be an integer between {minimum} and {maximum}.")
    converted = int(numeric)
    if not minimum <= converted <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")
    return converted


def _redact_value(value: Any, key: str = "") -> Any:
    if _SECRET_FIELD_RE.search(key):
        return "<REDACTED>"
    if isinstance(value, dict):
        return {
            str(item_key): _redact_value(item_value, str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_value(item) for item in value)
    return value


def _request_body_summary(request_cfg: dict[str, Any]) -> Any:
    if "json" in request_cfg:
        return _redact_value(request_cfg["json"])
    if "data" in request_cfg:
        return _redact_value(request_cfg["data"])
    if "multipart" in request_cfg:
        return {
            str(key): "<FILE>" if str(value).startswith("@") else _redact_value(value, str(key))
            for key, value in request_cfg["multipart"].items()
        }
    if "body" in request_cfg:
        raw = str(request_cfg["body"])
        return f"<raw body: {len(raw.encode('utf-8', errors='replace'))} bytes>"
    return None


def _transport_error_type(exc: Exception) -> str:
    if isinstance(exc, httpx.ConnectTimeout):
        return "connect_timeout"
    if isinstance(exc, httpx.ReadTimeout):
        return "read_timeout"
    if isinstance(exc, httpx.ProxyError):
        return "proxy_error"
    if isinstance(exc, httpx.ConnectError):
        text = str(exc).lower()
        if "name resolution" in text or "getaddrinfo" in text:
            return "dns_resolution"
        if "refused" in text:
            return "connection_refused"
        return "connect_error"
    if isinstance(exc, httpx.InvalidURL):
        return "invalid_url"
    if isinstance(exc, httpx.TransportError):
        return "transport_error"
    return "internal_error"


def redact_headers(headers: dict[str, Any]) -> dict[str, str]:
    return {
        str(key): "<REDACTED>"
        if str(key).lower() in _SECRET_HEADERS or _SECRET_FIELD_RE.search(str(key))
        else str(value)
        for key, value in headers.items()
    }


def validate_http_url(value: Any) -> str:
    url = str(value).strip()
    if not url or any(character.isspace() for character in url):
        raise ValueError("URL must be an absolute http:// or https:// URL without whitespace.")
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        parsed.port
    except ValueError as exc:
        raise ValueError(f"Invalid URL: {exc}") from exc
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc or not hostname:
        raise ValueError("URL must be an absolute http:// or https:// URL with a host.")
    return url


def validate_http_method(value: Any) -> str:
    method = str(value).upper().strip()
    if not method or not _HTTP_METHOD.fullmatch(method):
        raise ValueError("HTTP method contains invalid characters.")
    return method


def prepare_request_headers(
    headers: dict[str, Any] | None,
) -> tuple[dict[str, str], list[str]]:
    cleaned: dict[str, str] = {}
    removed: list[str] = []
    for key, value in (headers or {}).items():
        name = str(key)
        if name.lower() in _FRAMING_HEADERS:
            removed.append(name)
            continue
        cleaned[name] = str(value)
    return cleaned, removed


def parse_columns(specs: Iterable[str]) -> list[dict[str, str]]:
    columns: list[dict[str, str]] = []
    for spec in specs:
        name, separator, source_spec = spec.partition("=")
        if not separator or not name.strip():
            raise ValueError(f"Invalid column specification: {spec}")
        source, separator, key = source_spec.partition(":")
        if source not in {
            "header",
            "json",
            "regex",
            "cookie",
            "response",
            "request",
            "literal",
        }:
            raise ValueError(f"Unsupported column source: {source}")
        if source != "literal" and not separator:
            raise ValueError(f"Column requires source:key: {spec}")
        if source == "regex":
            try:
                re.compile(key)
            except re.error as exc:
                raise ValueError(f"Invalid column regular expression {key!r}: {exc}") from exc
        columns.append({"name": name.strip(), "source": source, "key": key})
    return columns


def _extract_column(
    column: dict[str, str],
    response: httpx.Response,
    request_cfg: dict[str, Any],
    parsed_json: Any,
) -> str:
    source, key = column["source"], column["key"]
    try:
        if source == "header":
            return response.headers.get(key, "")
        if source == "cookie":
            return response.cookies.get(key, "") or ""
        if source == "json":
            value = json_path(parsed_json, key) if parsed_json is not None else None
            return (
                ""
                if value is None
                else json.dumps(value, ensure_ascii=False)
                if isinstance(value, (dict, list))
                else str(value)
            )
        if source == "regex":
            match = re.search(key, response.text, re.I | re.S)
            return "" if not match else match.group(1) if match.groups() else match.group(0)
        if source == "response":
            values = {
                "url": str(response.url),
                "reason": response.reason_phrase,
                "http_version": response.http_version,
            }
            return str(values.get(key, ""))
        if source == "request":
            if key.startswith("header."):
                return str(request_cfg.get("headers", {}).get(key[7:], ""))
            if key.startswith("param."):
                return str(request_cfg.get("params", {}).get(key[6:], ""))
            return str(request_cfg.get(key, ""))
        if source == "literal":
            return key
    except Exception:
        return ""
    return ""


def _request_size(request: httpx.Request) -> int | None:
    try:
        return len(request.content)
    except httpx.RequestNotRead:
        raw = request.headers.get("Content-Length")
        try:
            return int(raw) if raw is not None else None
        except ValueError:
            return None


def _cancelled_result(index: int, cfg: dict[str, Any]) -> dict[str, Any]:
    effective_headers, removed_headers = prepare_request_headers(cfg.get("headers"))
    return {
        "index": index,
        "name": str(cfg.get("name") or f"request-{index}"),
        "method": str(cfg.get("method", "GET")).upper(),
        "url": str(cfg.get("url", "")),
        "status": None,
        "size_bytes": 0,
        "elapsed_ms": 0.0,
        "content_type": "",
        "http_version": "",
        "location": "",
        "error": "cancelled",
        "error_type": "cancelled",
        "outcome": "cancelled",
        "response_received": False,
        "body_preview": "",
        "body_truncated": False,
        "response_headers": {},
        "request_headers": redact_headers(effective_headers),
        "configured_request_headers": redact_headers(cfg.get("headers", {})),
        "removed_request_headers": removed_headers,
        "final_request_url": str(cfg.get("url", "")),
        "request_content_type": "",
        "request_size_bytes": 0,
        "request_body_summary": _request_body_summary(cfg),
        "payload_variables": _redact_value(cfg.get("payload_variables", {})),
        "custom": {},
        "timestamp": utc_now(),
    }


def _prepare_files(multipart: dict[str, Any]) -> tuple[dict[str, Any], list[Any]]:
    files: dict[str, Any] = {}
    handles: list[Any] = []
    for name, value in multipart.items():
        text = str(value)
        if text.startswith("@"):
            path = Path(text[1:]).expanduser().resolve()
            handle = path.open("rb")
            handles.append(handle)
            files[name] = (path.name, handle)
        else:
            files[name] = (None, text)
    return files, handles


def execute_request(
    index: int,
    request_cfg: dict[str, Any],
    columns: list[dict[str, str]] | None = None,
    *,
    body_limit: int = DEFAULT_BODY_LIMIT,
    retries: int = 0,
    backoff: bool = False,
    cancel_event: threading.Event | None = None,
) -> dict[str, Any]:
    columns = columns or []
    name = str(request_cfg.get("name") or f"request-{index}")
    method = str(request_cfg.get("method", "GET")).upper()
    url = str(request_cfg.get("url", ""))
    started = time.perf_counter()
    effective_headers, removed_headers = prepare_request_headers(request_cfg.get("headers"))
    result: dict[str, Any] = {
        "index": index,
        "name": name,
        "method": method,
        "url": url,
        "status": None,
        "size_bytes": 0,
        "elapsed_ms": 0.0,
        "content_type": "",
        "http_version": "",
        "location": "",
        "error": "",
        "body_preview": "",
        "response_headers": {},
        "request_headers": redact_headers(effective_headers),
        "configured_request_headers": redact_headers(request_cfg.get("headers", {})),
        "removed_request_headers": removed_headers,
        "final_request_url": url,
        "request_content_type": "",
        "request_size_bytes": 0,
        "request_body_summary": _request_body_summary(request_cfg),
        "response_received": False,
        "outcome": "pending",
        "error_type": "",
        "payload_variables": _redact_value(request_cfg.get("payload_variables", {})),
        "custom": {},
        "timestamp": utc_now(),
    }
    try:
        url = validate_http_url(url)
    except ValueError as exc:
        result["error"] = str(exc)
        result["error_type"] = "invalid_url"
        result["outcome"] = "validation_error"
        return result
    try:
        method = validate_http_method(method)
    except ValueError as exc:
        result["error"] = str(exc)
        result["error_type"] = "invalid_method"
        result["outcome"] = "validation_error"
        return result
    result["url"] = url
    result["method"] = method
    result["final_request_url"] = url

    try:
        timeout = float(request_cfg.get("timeout", 15))
        retries = _bounded_integer(retries, "retries", 0, 5)
        body_limit = _bounded_integer(body_limit, "body_limit", 1, 100 * 1024 * 1024)
        if not math.isfinite(timeout) or timeout <= 0 or timeout > 300:
            raise ValueError("timeout must be greater than 0 and at most 300 seconds.")
        for option in ("verify_tls", "follow_redirects", "http2"):
            if option in request_cfg and not isinstance(request_cfg[option], bool):
                raise ValueError(f"{option} must be true or false.")
    except (TypeError, ValueError, OverflowError) as exc:
        result["error"] = str(exc)
        result["error_type"] = "invalid_options"
        result["outcome"] = "validation_error"
        return result
    verify = request_cfg.get("verify_tls", True)
    follow = request_cfg.get("follow_redirects", False)
    http2 = request_cfg.get("http2", False)
    proxy = request_cfg.get("proxy")
    auth_cfg = request_cfg.get("auth")
    auth = None
    if isinstance(auth_cfg, dict):
        auth = httpx.BasicAuth(str(auth_cfg.get("username", "")), str(auth_cfg.get("password", "")))

    kwargs: dict[str, Any] = {
        "method": method,
        "url": url,
        "headers": effective_headers,
        "params": request_cfg.get("params"),
        "auth": auth,
    }
    if "json" in request_cfg:
        kwargs["json"] = request_cfg["json"]
    elif "data" in request_cfg:
        kwargs["data"] = request_cfg["data"]
    elif "body" in request_cfg:
        kwargs["content"] = request_cfg["body"]

    file_handles: list[Any] = []
    if request_cfg.get("multipart"):
        kwargs["files"], file_handles = _prepare_files(request_cfg["multipart"])

    attempts = max(0, int(retries)) + 1
    try:
        with httpx.Client(
            timeout=timeout,
            verify=verify,
            follow_redirects=follow,
            http2=http2,
            proxy=proxy,
            cookies=request_cfg.get("cookies"),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        ) as client:
            for attempt in range(attempts):
                if cancel_event and cancel_event.is_set():
                    return _cancelled_result(index, request_cfg)
                for handle in file_handles:
                    handle.seek(0)
                try:
                    preview_buffer = bytearray()
                    response_size = 0
                    with client.stream(**kwargs) as response:
                        for chunk in response.iter_bytes(chunk_size=64 * 1024):
                            if cancel_event and cancel_event.is_set():
                                return _cancelled_result(index, request_cfg)
                            response_size += len(chunk)
                            remaining = body_limit - len(preview_buffer)
                            if remaining > 0:
                                preview_buffer.extend(chunk[:remaining])
                    break
                except httpx.TransportError:
                    if attempt + 1 >= attempts:
                        raise
                    delay = (2**attempt if backoff else 1) + _JITTER.uniform(0, 0.2)
                    time.sleep(delay)

        preview_bytes = bytes(preview_buffer)
        encoding = response.encoding or "utf-8"
        preview = preview_bytes.decode(encoding, errors="replace")
        parsed_json = None
        if response_size <= len(preview_bytes):
            try:
                parsed_json = json.loads(preview)
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass
        result.update(
            {
                "status": response.status_code,
                "size_bytes": response_size,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                "content_type": response.headers.get("Content-Type", ""),
                "http_version": response.http_version,
                "location": response.headers.get("Location", ""),
                "body_preview": preview,
                "body_truncated": response_size > len(preview_bytes),
                "response_headers": redact_headers(dict(response.headers)),
                "request_headers": redact_headers(dict(response.request.headers)),
                "final_request_url": str(response.request.url),
                "request_content_type": response.request.headers.get("Content-Type", ""),
                "request_size_bytes": _request_size(response.request),
                "response_received": True,
                "outcome": "http_response",
            }
        )
        for column in columns:
            result["custom"][column["name"]] = _extract_column(
                column, response, request_cfg, parsed_json
            )
    except Exception as exc:
        result["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["error_type"] = _transport_error_type(exc)
        result["outcome"] = (
            "transport_error" if isinstance(exc, httpx.TransportError) else "internal_error"
        )
    finally:
        for handle in file_handles:
            handle.close()
    return result


def _checkpoint_state(
    path: Path | None, expected_signature: str | None = None
) -> tuple[set[int], list[dict[str, Any]]]:
    if path is None:
        return set(), []
    data = read_json(path, default={}) or {}
    if not isinstance(data, dict):
        raise ValueError("Checkpoint must be a JSON object.")
    stored_signature = data.get("request_signature")
    if expected_signature and stored_signature and stored_signature != expected_signature:
        raise ValueError("Checkpoint belongs to a different request configuration.")
    completed = {int(value) for value in data.get("completed", [])}
    stored = data.get("results", [])
    if not isinstance(stored, list) or any(not isinstance(item, dict) for item in stored):
        raise ValueError("Checkpoint results must be a list of objects.")
    if completed and not stored:
        return set(), []
    results = [item for item in stored if int(item.get("index", -1)) in completed]
    return completed, results


def _checkpoint_completed(path: Path | None) -> set[int]:
    return _checkpoint_state(path)[0]


def run_requests(
    requests_cfg: list[dict[str, Any]],
    *,
    columns: list[dict[str, str]] | None = None,
    workers: int = 1,
    delay_ms: int = 0,
    rate: float | None = None,
    retries: int = 0,
    backoff: bool = False,
    body_limit: int = DEFAULT_BODY_LIMIT,
    checkpoint: Path | None = None,
    cancel_event: threading.Event | None = None,
    pause_event: threading.Event | None = None,
    callback: Callable[[int, int, dict[str, Any]], None] | None = None,
    match_rules: list[str] | None = None,
    exclude_rules: list[str] | None = None,
    extract_rules: dict[str, str] | None = None,
    cluster_threshold: float = 98.0,
) -> list[dict[str, Any]]:
    match_rules = match_rules or []
    exclude_rules = exclude_rules or []
    extract_rules = extract_rules or {}
    for rule in [*match_rules, *exclude_rules, *extract_rules.values()]:
        validate_rule(rule)
    cluster_threshold = float(cluster_threshold)
    if not math.isfinite(cluster_threshold) or not 0 <= cluster_threshold <= 100:
        raise ValueError("cluster_threshold must be between 0 and 100.")
    workers = _bounded_integer(workers, "workers", 1, MAX_WORKERS)
    delay_ms = _bounded_integer(delay_ms, "delay_ms", 0, 3_600_000)
    retries = _bounded_integer(retries, "retries", 0, 5)
    body_limit = _bounded_integer(body_limit, "body_limit", 1, 100 * 1024 * 1024)
    if rate is not None:
        rate = float(rate)
        if not math.isfinite(rate) or not 0 < rate <= 10_000:
            raise ValueError("rate must be greater than 0 and at most 10000.")
    request_signature = hashlib.sha256(
        json.dumps(
            {
                "requests": requests_cfg,
                "columns": columns or [],
                "body_limit": body_limit,
                "retries": retries,
                "backoff": backoff,
            },
            ensure_ascii=False,
            sort_keys=True,
            default=str,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    completed_before, stored_results = _checkpoint_state(checkpoint, request_signature)
    pending = [
        (index, cfg)
        for index, cfg in enumerate(requests_cfg, start=1)
        if index not in completed_before
    ]
    results: list[dict[str, Any]] = stored_results
    lock = threading.Lock()
    last_start = 0.0

    def task(index: int, cfg: dict[str, Any]) -> dict[str, Any]:
        nonlocal last_start
        while pause_event and pause_event.is_set():
            if cancel_event and cancel_event.is_set():
                return _cancelled_result(index, cfg)
            time.sleep(0.05)
        minimum_interval = 1.0 / rate if rate and rate > 0 else delay_ms / 1000.0
        if minimum_interval > 0:
            with lock:
                now = time.monotonic()
                wait = max(0.0, last_start + minimum_interval - now)
                if wait:
                    time.sleep(wait)
                last_start = time.monotonic()
        return execute_request(
            index,
            cfg,
            columns,
            body_limit=body_limit,
            retries=cfg.get("retries", retries),
            backoff=backoff,
            cancel_event=cancel_event,
        )

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(task, index, cfg): index for index, cfg in pending}
        total = len(requests_cfg)
        completed_count = len(completed_before)
        for future in as_completed(futures):
            item = future.result()
            results.append(item)
            completed_count += 1
            if checkpoint:
                completed_indices = sorted(completed_before | {row["index"] for row in results})
                atomic_json_write(
                    checkpoint,
                    {
                        "request_signature": request_signature,
                        "completed": completed_indices,
                        "results": sorted(results, key=lambda row: row["index"]),
                        "updated_at": utc_now(),
                    },
                )
            if callback:
                callback(completed_count, total, item)

    results.sort(key=lambda item: item["index"])
    return enrich_results(
        results,
        match_rules=match_rules,
        exclude_rules=exclude_rules,
        extract_rules=extract_rules,
        cluster_threshold=cluster_threshold,
    )


def results_to_csv(results: list[dict[str, Any]]) -> str:
    custom_names = sorted({name for item in results for name in item.get("custom", {})})
    fields = [
        "index",
        "name",
        "method",
        "url",
        "status",
        "size_bytes",
        "elapsed_ms",
        "content_type",
        "http_version",
        "location",
        "final_request_url",
        "request_content_type",
        "request_size_bytes",
        "response_received",
        "outcome",
        "error_type",
        "similarity",
        "cluster",
        "anomaly_score",
        "matched",
        "excluded",
        "error",
    ]
    used = set(fields)
    custom_aliases: dict[str, str] = {}
    for name in custom_names:
        alias = name
        while alias in used:
            alias = f"custom.{alias}"
        custom_aliases[name] = alias
        used.add(alias)
    fields[-1:-1] = custom_aliases.values()
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for item in results:
        row = dict(item)
        custom = item.get("custom", {})
        for name, alias in custom_aliases.items():
            row[alias] = custom.get(name, "")
        for field in fields:
            value = row.get(field, "")
            if isinstance(value, str) and value.lstrip(" \t\r\n")[:1] in {
                "=",
                "+",
                "-",
                "@",
            }:
                row[field] = "'" + value
        writer.writerow(row)
    return buffer.getvalue()


def write_csv(path: Path, results: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(results_to_csv(results), encoding="utf-8-sig", newline="")


def write_jsonl(path: Path, results: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for item in results:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
