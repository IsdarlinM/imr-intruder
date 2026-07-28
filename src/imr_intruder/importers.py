from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urljoin, urlsplit


def _split_headers_body(text: str) -> tuple[str, str]:
    normalized = text.replace("\r\n", "\n")
    head, separator, body = normalized.partition("\n\n")
    return head, body if separator else ""


def parse_raw_request(text: str, default_scheme: str = "https") -> dict[str, Any]:
    head, body = _split_headers_body(text)
    lines = [line for line in head.splitlines() if line.strip()]
    if not lines:
        raise ValueError("Raw request is empty.")
    parts = lines[0].split()
    if len(parts) < 2:
        raise ValueError("Invalid raw request line.")
    method, target = parts[0].upper(), parts[1]
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" not in line:
            raise ValueError(f"Invalid header line: {line}")
        key, value = line.split(":", 1)
        headers[key.strip()] = value.strip()

    if target.startswith(("http://", "https://")):
        url = target
    else:
        host = headers.get("Host") or headers.get("host")
        if not host:
            raise ValueError("Raw request requires a Host header for relative targets.")
        url = f"{default_scheme}://{host}{target}"

    request: dict[str, Any] = {"method": method, "url": url, "headers": headers}
    content_type = headers.get("Content-Type", headers.get("content-type", "")).lower()
    if body:
        if "application/json" in content_type:
            try:
                request["json"] = json.loads(body)
            except json.JSONDecodeError:
                request["body"] = body
        elif "application/x-www-form-urlencoded" in content_type:
            request["data"] = dict(parse_qsl(body, keep_blank_values=True))
        else:
            request["body"] = body
    return request


def parse_curl(command: str) -> dict[str, Any]:
    tokens = shlex.split(command, posix=True)
    if not tokens or tokens[0] not in {"curl", "curl.exe"}:
        raise ValueError("Input must begin with curl.")

    method = "GET"
    url: str | None = None
    headers: dict[str, str] = {}
    data_parts: list[str] = []
    form: dict[str, Any] = {}
    follow_redirects = False
    verify_tls = True
    proxy: str | None = None
    index = 1

    while index < len(tokens):
        token = tokens[index]
        if token in {"-X", "--request"}:
            index += 1
            method = tokens[index].upper()
        elif token in {"-H", "--header"}:
            index += 1
            header = tokens[index]
            if ":" not in header:
                raise ValueError(f"Invalid cURL header: {header}")
            key, value = header.split(":", 1)
            headers[key.strip()] = value.strip()
        elif token in {"-d", "--data", "--data-raw", "--data-binary", "--data-urlencode"}:
            index += 1
            data_parts.append(tokens[index])
            if method == "GET":
                method = "POST"
        elif token in {"-F", "--form"}:
            index += 1
            item = tokens[index]
            if "=" not in item:
                raise ValueError(f"Invalid cURL form item: {item}")
            key, value = item.split("=", 1)
            form[key] = value
            if method == "GET":
                method = "POST"
        elif token in {"-L", "--location"}:
            follow_redirects = True
        elif token in {"-k", "--insecure"}:
            verify_tls = False
        elif token in {"-x", "--proxy"}:
            index += 1
            proxy = tokens[index]
        elif token in {"-u", "--user"}:
            index += 1
            username, _, password = tokens[index].partition(":")
            auth = {"username": username, "password": password}
        elif token.startswith("-"):
            pass
        else:
            url = token
        index += 1

    if not url:
        raise ValueError("cURL command does not contain a URL.")
    request: dict[str, Any] = {
        "method": method,
        "url": url,
        "headers": headers,
        "follow_redirects": follow_redirects,
        "verify_tls": verify_tls,
    }
    if proxy:
        request["proxy"] = proxy
    if "auth" in locals():
        request["auth"] = auth
    if form:
        request["multipart"] = form
    elif data_parts:
        body = "&".join(data_parts)
        content_type = headers.get("Content-Type", "").lower()
        if "application/json" in content_type:
            try:
                request["json"] = json.loads(body)
            except json.JSONDecodeError:
                request["body"] = body
        elif "application/x-www-form-urlencoded" in content_type or "=" in body:
            request["data"] = dict(parse_qsl(body, keep_blank_values=True))
        else:
            request["body"] = body
    return request


def parse_har(data: dict[str, Any]) -> list[dict[str, Any]]:
    entries = data.get("log", {}).get("entries", [])
    if not isinstance(entries, list):
        raise ValueError("Invalid HAR: log.entries must be a list.")
    requests: list[dict[str, Any]] = []
    for position, entry in enumerate(entries, start=1):
        source = entry.get("request", {})
        url = source.get("url")
        if not url:
            continue
        headers = {item["name"]: item.get("value", "") for item in source.get("headers", []) if item.get("name")}
        cookies = {item["name"]: item.get("value", "") for item in source.get("cookies", []) if item.get("name")}
        params = {item["name"]: item.get("value", "") for item in source.get("queryString", []) if item.get("name")}
        request: dict[str, Any] = {
            "name": f"har-{position}",
            "method": source.get("method", "GET"),
            "url": url,
            "headers": headers,
            "cookies": cookies,
            "params": params,
        }
        post = source.get("postData") or {}
        mime = str(post.get("mimeType", "")).lower()
        text = post.get("text")
        if post.get("params"):
            request["data"] = {item["name"]: item.get("value", "") for item in post["params"] if item.get("name")}
        elif isinstance(text, str):
            if "application/json" in mime:
                try:
                    request["json"] = json.loads(text)
                except json.JSONDecodeError:
                    request["body"] = text
            else:
                request["body"] = text
        requests.append(request)
    return requests


def load_import(kind: str, path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    kind = kind.lower()
    if kind in {"raw", "burp", "zap"}:
        return [parse_raw_request(text)]
    if kind == "curl":
        return [parse_curl(text)]
    if kind == "har":
        return parse_har(json.loads(text))
    raise ValueError(f"Unsupported import type: {kind}")
