from __future__ import annotations

import csv
import json
import os
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Iterable

import httpx

from .intelligence import enrich_results, json_path
from .storage import atomic_json_write, read_json, utc_now

MAX_WORKERS = 32
DEFAULT_BODY_LIMIT = 1024 * 1024
_SECRET_HEADERS = {"authorization", "cookie", "set-cookie", "proxy-authorization", "x-api-key"}


def redact_headers(headers: dict[str, Any]) -> dict[str, str]:
    return {
        str(key): "<REDACTED>" if str(key).lower() in _SECRET_HEADERS else str(value)
        for key, value in headers.items()
    }


def parse_columns(specs: Iterable[str]) -> list[dict[str, str]]:
    columns: list[dict[str, str]] = []
    for spec in specs:
        name, separator, source_spec = spec.partition("=")
        if not separator or not name.strip():
            raise ValueError(f"Invalid column specification: {spec}")
        source, separator, key = source_spec.partition(":")
        if source not in {"header", "json", "regex", "cookie", "response", "request", "literal"}:
            raise ValueError(f"Unsupported column source: {source}")
        if source != "literal" and not separator:
            raise ValueError(f"Column requires source:key: {spec}")
        columns.append({"name": name.strip(), "source": source, "key": key})
    return columns


def _extract_column(column: dict[str, str], response: httpx.Response, request_cfg: dict[str, Any], parsed_json: Any) -> str:
    source, key = column["source"], column["key"]
    try:
        if source == "header":
            return response.headers.get(key, "")
        if source == "cookie":
            return response.cookies.get(key, "")
        if source == "json":
            value = json_path(parsed_json, key) if parsed_json is not None else None
            return "" if value is None else json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
        if source == "regex":
            match = re.search(key, response.text, re.I | re.S)
            return "" if not match else match.group(1) if match.groups() else match.group(0)
        if source == "response":
            values = {"url": str(response.url), "reason": response.reason_phrase, "http_version": response.http_version}
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
        "request_headers": redact_headers(request_cfg.get("headers", {})),
        "payload_variables": request_cfg.get("payload_variables", {}),
        "custom": {},
        "timestamp": utc_now(),
    }
    if not url.startswith(("http://", "https://")):
        result["error"] = "URL must begin with http:// or https://"
        return result

    timeout = float(request_cfg.get("timeout", 15))
    verify = bool(request_cfg.get("verify_tls", True))
    follow = bool(request_cfg.get("follow_redirects", False))
    http2 = bool(request_cfg.get("http2", False))
    proxy = request_cfg.get("proxy")
    auth_cfg = request_cfg.get("auth")
    auth = None
    if isinstance(auth_cfg, dict):
        auth = httpx.BasicAuth(str(auth_cfg.get("username", "")), str(auth_cfg.get("password", "")))

    kwargs: dict[str, Any] = {
        "method": method,
        "url": url,
        "headers": request_cfg.get("headers"),
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
        for attempt in range(attempts):
            if cancel_event and cancel_event.is_set():
                result["error"] = "cancelled"
                return result
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
                    response = client.request(**kwargs)
                break
            except httpx.TransportError:
                if attempt + 1 >= attempts:
                    raise
                delay = (2 ** attempt if backoff else 1) + random.uniform(0, 0.2)
                time.sleep(delay)

        body = response.content
        preview_bytes = body[:body_limit]
        encoding = response.encoding or "utf-8"
        preview = preview_bytes.decode(encoding, errors="replace")
        try:
            parsed_json = response.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            parsed_json = None
        result.update(
            {
                "status": response.status_code,
                "size_bytes": len(body),
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                "content_type": response.headers.get("Content-Type", ""),
                "http_version": response.http_version,
                "location": response.headers.get("Location", ""),
                "body_preview": preview,
                "body_truncated": len(body) > len(preview_bytes),
                "response_headers": redact_headers(dict(response.headers)),
            }
        )
        for column in columns:
            result["custom"][column["name"]] = _extract_column(column, response, request_cfg, parsed_json)
    except Exception as exc:
        result["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        for handle in file_handles:
            handle.close()
    return result


def _checkpoint_completed(path: Path | None) -> set[int]:
    if path is None:
        return set()
    data = read_json(path, default={}) or {}
    return {int(value) for value in data.get("completed", [])}


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
    workers = max(1, min(int(workers), MAX_WORKERS))
    completed_before = _checkpoint_completed(checkpoint)
    pending = [(index, cfg) for index, cfg in enumerate(requests_cfg, start=1) if index not in completed_before]
    results: list[dict[str, Any]] = []
    lock = threading.Lock()
    last_start = 0.0

    def task(index: int, cfg: dict[str, Any]) -> dict[str, Any]:
        nonlocal last_start
        while pause_event and pause_event.is_set():
            if cancel_event and cancel_event.is_set():
                return {
                    "index": index, "name": str(cfg.get("name") or f"request-{index}"),
                    "method": str(cfg.get("method", "GET")).upper(), "url": str(cfg.get("url", "")),
                    "status": None, "size_bytes": 0, "elapsed_ms": 0.0, "content_type": "",
                    "http_version": "", "location": "", "error": "cancelled", "body_preview": "",
                    "response_headers": {}, "request_headers": redact_headers(cfg.get("headers", {})),
                    "payload_variables": cfg.get("payload_variables", {}), "custom": {}, "timestamp": utc_now(),
                }
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
            retries=retries,
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
                atomic_json_write(checkpoint, {"completed": completed_indices, "updated_at": utc_now()})
            if callback:
                callback(completed_count, total, item)
            if cancel_event and cancel_event.is_set():
                for queued in futures:
                    queued.cancel()
                break

    results.sort(key=lambda item: item["index"])
    return enrich_results(
        results,
        match_rules=match_rules,
        exclude_rules=exclude_rules,
        extract_rules=extract_rules,
        cluster_threshold=cluster_threshold,
    )


def write_csv(path: Path, results: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    custom_names = sorted({name for item in results for name in item.get("custom", {})})
    fields = [
        "index", "name", "method", "url", "status", "size_bytes", "elapsed_ms", "content_type",
        "http_version", "location", "similarity", "cluster", "anomaly_score", "matched", "excluded",
        *custom_names, "error",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for item in results:
            row = dict(item)
            row.update(item.get("custom", {}))
            for field in fields:
                value = row.get(field, "")
                if isinstance(value, str) and value[:1] in {"=", "+", "-", "@"}:
                    row[field] = "'" + value
            writer.writerow(row)


def write_jsonl(path: Path, results: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for item in results:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
