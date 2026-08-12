from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl


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
    cookies: dict[str, str] = {}
    data_parts: list[str] = []
    form: dict[str, Any] = {}
    follow_redirects = False
    verify_tls = True
    proxy: str | None = None
    auth: dict[str, str] | None = None
    timeout: float | None = None
    retries: int | None = None
    http2 = False
    data_as_query = False
    index = 1

    value_options = {
        "-X",
        "--request",
        "-H",
        "--header",
        "-d",
        "--data",
        "--data-raw",
        "--data-binary",
        "--data-urlencode",
        "--json",
        "-F",
        "--form",
        "-x",
        "--proxy",
        "-u",
        "--user",
        "--url",
        "-A",
        "--user-agent",
        "-e",
        "--referer",
        "-b",
        "--cookie",
        "--connect-timeout",
        "--max-time",
        "--retry",
        "-o",
        "--output",
        "-w",
        "--write-out",
        "-c",
        "--cookie-jar",
    }
    ignored_value_options = {
        "-o",
        "--output",
        "-w",
        "--write-out",
        "-c",
        "--cookie-jar",
    }
    flag_options = {
        "-L",
        "--location",
        "-k",
        "--insecure",
        "-I",
        "--head",
        "-G",
        "--get",
        "-s",
        "--silent",
        "-S",
        "--show-error",
        "-f",
        "--fail",
        "--compressed",
        "-g",
        "--globoff",
        "--http1.1",
        "--http2",
        "--http2-prior-knowledge",
    }
    short_value_prefixes = (
        "-X",
        "-H",
        "-d",
        "-F",
        "-x",
        "-u",
        "-A",
        "-e",
        "-b",
        "-o",
        "-w",
        "-c",
    )

    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            index += 1
            if index >= len(tokens):
                raise ValueError("cURL command does not contain a URL after --.")
            for candidate in tokens[index:]:
                if url is not None:
                    raise ValueError("cURL command contains more than one URL.")
                url = candidate
            break

        option = token
        attached: str | None = None
        if token.startswith("--") and "=" in token:
            option, attached = token.split("=", 1)
        elif token.startswith("-Gd") and len(token) > 3:
            data_as_query = True
            method = "GET"
            option, attached = "-d", token[3:]
        elif token.startswith("-") and not token.startswith("--"):
            for prefix in short_value_prefixes:
                if token.startswith(prefix) and token != prefix:
                    option, attached = prefix, token[len(prefix) :]
                    break

        value: str | None = attached
        if option in value_options and value is None:
            index += 1
            if index >= len(tokens):
                raise ValueError(f"cURL option {option} requires a value.")
            value = tokens[index]

        if option in {"-X", "--request"}:
            method = str(value).upper()
        elif option in {"-H", "--header"}:
            header = str(value)
            if ":" not in header:
                raise ValueError(f"Invalid cURL header: {header}")
            key, value = header.split(":", 1)
            headers[key.strip()] = value.strip()
        elif option in {
            "-d",
            "--data",
            "--data-raw",
            "--data-binary",
            "--data-urlencode",
            "--json",
        }:
            data_parts.append(str(value))
            if option == "--json":
                headers.setdefault("Content-Type", "application/json")
                headers.setdefault("Accept", "application/json")
            if method == "GET" and not data_as_query:
                method = "POST"
        elif option in {"-F", "--form"}:
            item = str(value)
            if "=" not in item:
                raise ValueError(f"Invalid cURL form item: {item}")
            key, value = item.split("=", 1)
            form[key] = value
            if method == "GET":
                method = "POST"
        elif option in {"-L", "--location"}:
            follow_redirects = True
        elif option in {"-k", "--insecure"}:
            verify_tls = False
        elif option in {"-x", "--proxy"}:
            proxy = str(value)
        elif option in {"-u", "--user"}:
            username, separator, password = str(value).partition(":")
            if not separator:
                raise ValueError("cURL --user requires USER:PASSWORD.")
            auth = {"username": username, "password": password}
        elif option == "--url":
            if url is not None:
                raise ValueError("cURL command contains more than one URL.")
            url = str(value)
        elif option in {"-A", "--user-agent"}:
            headers["User-Agent"] = str(value)
        elif option in {"-e", "--referer"}:
            headers["Referer"] = str(value)
        elif option in {"-b", "--cookie"}:
            raw_cookie = str(value)
            if raw_cookie.startswith("@") or "=" not in raw_cookie:
                raise ValueError("Cookie files are not supported; provide name=value pairs.")
            for item in raw_cookie.split(";"):
                key, separator, cookie_value = item.strip().partition("=")
                if not separator or not key:
                    raise ValueError(f"Invalid cURL cookie: {item}")
                cookies[key] = cookie_value
        elif option in {"--connect-timeout", "--max-time"}:
            try:
                timeout = float(str(value))
            except ValueError as exc:
                raise ValueError(f"Invalid cURL timeout: {value}") from exc
            if timeout <= 0:
                raise ValueError("cURL timeout must be greater than zero.")
        elif option == "--retry":
            try:
                retries = int(str(value))
            except ValueError as exc:
                raise ValueError(f"Invalid cURL retry count: {value}") from exc
            if not 0 <= retries <= 5:
                raise ValueError("cURL retry count must be between 0 and 5.")
        elif option in ignored_value_options:
            pass
        elif option in {"-I", "--head"}:
            method = "HEAD"
        elif option in {"-G", "--get"}:
            data_as_query = True
            method = "GET"
        elif option in {"--http2", "--http2-prior-knowledge"}:
            http2 = True
        elif option in flag_options or (
            option.startswith("-")
            and not option.startswith("--")
            and len(option) > 2
            and set(option[1:]) <= {"s", "S", "f", "g"}
        ):
            pass
        elif option.startswith("-"):
            raise ValueError(f"Unsupported cURL option: {option}")
        else:
            if url is not None:
                raise ValueError("cURL command contains more than one URL.")
            url = option
        index += 1

    if not url:
        raise ValueError("cURL command does not contain a URL.")
    if form and data_parts:
        raise ValueError("Cannot combine cURL form and data bodies.")
    request: dict[str, Any] = {
        "method": method,
        "url": url,
        "headers": headers,
        "follow_redirects": follow_redirects,
        "verify_tls": verify_tls,
        "http2": http2,
    }
    if proxy:
        request["proxy"] = proxy
    if auth:
        request["auth"] = auth
    if cookies:
        request["cookies"] = cookies
    if timeout is not None:
        request["timeout"] = timeout
    if retries is not None:
        request["retries"] = retries
    if form:
        request["multipart"] = form
    elif data_parts:
        body = "&".join(data_parts)
        if data_as_query:
            request["params"] = dict(parse_qsl(body, keep_blank_values=True))
            return request
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
        headers = {
            item["name"]: item.get("value", "")
            for item in source.get("headers", [])
            if item.get("name")
        }
        cookies = {
            item["name"]: item.get("value", "")
            for item in source.get("cookies", [])
            if item.get("name")
        }
        params = {
            item["name"]: item.get("value", "")
            for item in source.get("queryString", [])
            if item.get("name")
        }
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
            request["data"] = {
                item["name"]: item.get("value", "") for item in post["params"] if item.get("name")
            }
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
