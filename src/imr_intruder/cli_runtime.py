from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl

from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.text import Text

from .core import parse_columns, run_requests, write_csv, write_jsonl
from .payloads import build_requests
from .storage import (
    load_session,
)

console = Console()
_PAYLOAD_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _json_print(value: Any) -> None:
    console.print_json(json.dumps(value, ensure_ascii=False, default=str))


def _parse_key_values(values: Iterable[str], *, header: bool = False) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in values:
        if header and ":" in item and ("=" not in item or item.index(":") < item.index("=")):
            key, value = item.split(":", 1)
        elif "=" in item:
            key, value = item.split("=", 1)
        else:
            raise ValueError(f"Expected {'Name: value' if header else 'key=value'}: {item}")
        if not key.strip():
            raise ValueError("Empty key is not allowed.")
        result[key.strip()] = value.strip()
    return result


def _parse_urlencoded_values(values: Iterable[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in values:
        if "&" in item:
            pairs = parse_qsl(item, keep_blank_values=True, strict_parsing=False)
            if not pairs:
                raise ValueError(f"Invalid URL-encoded value: {item}")
            result.update((str(key), str(value)) for key, value in pairs)
        else:
            result.update(_parse_key_values([item]))
    return result


def _load_json_value(raw: str) -> Any:
    if raw.startswith("@"):
        return json.loads(Path(raw[1:]).read_text(encoding="utf-8"))
    return json.loads(raw)


def _load_values(path: Path) -> list[str]:
    return [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line and not line.lstrip().startswith("#")
    ]


def _payload_maps(items: list[str]) -> dict[str, list[str]]:
    payloads: dict[str, list[str]] = {}
    for item in items:
        name, separator, path = item.partition("=")
        if not separator:
            raise ValueError(f"Payload must be NAME=file: {item}")
        if not _PAYLOAD_NAME.fullmatch(name):
            raise ValueError(f"Invalid payload name: {name!r}")
        if name in payloads:
            raise ValueError(f"Duplicate payload name: {name}")
        payloads[name] = _load_values(Path(path).expanduser())
    return payloads


def _base_request(args: argparse.Namespace) -> dict[str, Any]:
    headers = _parse_key_values(args.header or [], header=True)
    params = _parse_urlencoded_values(args.param or [])
    cookies = _parse_key_values(args.cookie or [])
    request: dict[str, Any] = {
        "method": args.method.upper(),
        "url": args.url,
        "headers": headers,
        "params": params,
        "cookies": cookies,
        "timeout": args.timeout,
        "verify_tls": not args.insecure,
        "follow_redirects": args.follow_redirects,
        "http2": args.http2,
    }
    if args.name:
        request["name"] = args.name
    if args.proxy:
        request["proxy"] = args.proxy
    if args.user:
        username, separator, password = args.user.partition(":")
        if not separator:
            raise ValueError("--user requires USER:PASSWORD.")
        request["auth"] = {"username": username, "password": password}
    if args.json is not None:
        request["json"] = _load_json_value(args.json)
    elif args.data:
        request["data"] = _parse_urlencoded_values(args.data)
    elif args.body is not None:
        request["body"] = (
            Path(args.body[1:]).read_text(encoding="utf-8")
            if args.body.startswith("@")
            else args.body
        )
    if args.form:
        request["multipart"] = _parse_key_values(args.form)
    if getattr(args, "session", None):
        session = load_session(args.session)
        request["headers"] = {**session.get("headers", {}), **request["headers"]}
        request["cookies"] = {**session.get("cookies", {}), **request["cookies"]}
        if session.get("auth") and "auth" not in request:
            request["auth"] = session["auth"]
        if session.get("proxy") and "proxy" not in request:
            request["proxy"] = session["proxy"]
        if session.get("verify_tls") is False and not args.insecure:
            request["verify_tls"] = False
    return request


def _table(results: list[dict[str, Any]], total: int) -> Table:
    table = Table(
        title=f"imr-intruder · {len(results)}/{total} completed",
        title_style="bold cyan",
        border_style="bright_black",
        header_style="bold bright_white",
        row_styles=["", "on #101722"],
        expand=True,
    )
    table.add_column("#", justify="right", style="dim", no_wrap=True)
    table.add_column("Name", ratio=2, overflow="fold")
    table.add_column("Method", style="cyan", no_wrap=True)
    table.add_column("Status", justify="center", no_wrap=True)
    table.add_column("Bytes", justify="right", no_wrap=True)
    table.add_column("Time", justify="right", no_wrap=True)
    table.add_column("Similarity", justify="right", no_wrap=True)
    table.add_column("Cluster", justify="center", no_wrap=True)
    table.add_column("Anomaly", justify="right", no_wrap=True)
    table.add_column("Location", ratio=2, overflow="fold")
    table.add_column("Error", ratio=2, overflow="fold")

    def value(item: dict[str, Any], key: str, suffix: str = "") -> Text:
        raw = item.get(key)
        return Text("—" if raw in (None, "") else f"{raw}{suffix}")

    for item in sorted(results, key=lambda row: row["index"]):
        status = str(item.get("status") or "—")
        status_style = (
            "bold green"
            if status.startswith("2")
            else "bold cyan"
            if status.startswith("3")
            else "bold red"
            if status != "—"
            else "magenta"
        )
        table.add_row(
            value(item, "index"),
            value(item, "name"),
            value(item, "method"),
            Text(status, style=status_style),
            value(item, "size_bytes"),
            value(item, "elapsed_ms", " ms"),
            value(item, "similarity", "%"),
            value(item, "cluster"),
            value(item, "anomaly_score"),
            value(item, "location"),
            Text(str(item.get("error") or "—"), style="red" if item.get("error") else ""),
        )
    return table


def _run(args: argparse.Namespace, requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    columns = parse_columns(args.column or [])
    current: list[dict[str, Any]] = []
    callback = None
    if not args.quiet:
        live = Live(
            _table(current, len(requests)),
            console=console,
            refresh_per_second=8,
            transient=False,
        )
        live.start()

        def callback(completed: int, total: int, item: dict[str, Any]) -> None:
            current.append(item)
            live.update(_table(current, total), refresh=True)

    try:
        results = run_requests(
            requests,
            columns=columns,
            workers=args.workers,
            delay_ms=args.delay_ms,
            rate=args.rate,
            retries=args.retries,
            backoff=args.backoff,
            body_limit=args.body_limit,
            checkpoint=Path(args.checkpoint).expanduser() if args.checkpoint else None,
            callback=callback,
            match_rules=args.match or [],
            exclude_rules=args.exclude or [],
            extract_rules=_parse_key_values(args.extract or []),
            cluster_threshold=args.cluster_threshold,
        )
        if not args.quiet:
            live.update(_table(results, len(requests)), refresh=True)
        if args.csv:
            write_csv(Path(args.csv), results)
        if args.jsonl:
            write_jsonl(Path(args.jsonl), results)
        if args.output_json:
            output_json = Path(args.output_json).expanduser()
            output_json.parent.mkdir(parents=True, exist_ok=True)
            output_json.write_text(
                json.dumps(results, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        return results
    finally:
        if not args.quiet:
            live.stop()


def cmd_request(args: argparse.Namespace) -> int:
    results = _run(args, [_base_request(args)])
    return 1 if any(item.get("error") for item in results) else 0


def cmd_intrude(args: argparse.Namespace) -> int:
    base = _base_request(args)
    payloads = _payload_maps(args.payload or [])
    if args.values_file:
        payloads.setdefault("VALUE", _load_values(Path(args.values_file)))
    if not payloads:
        raise ValueError("intrude requires --payload NAME=file or --values-file.")
    requests = build_requests(base, payloads, args.mode, args.max_requests)
    results = _run(args, requests)
    return 1 if any(item.get("error") for item in results) else 0


def cmd_batch(args: argparse.Namespace) -> int:
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    requests = config.get("requests") if isinstance(config, dict) else None
    if not isinstance(requests, list) or not requests:
        raise ValueError("Batch config requires a non-empty requests list.")
    if config.get("columns") and not args.column:
        args.column = config["columns"]
    for key in ("workers", "delay_ms", "retries", "backoff", "cluster_threshold"):
        if key in config and getattr(args, key, None) == parser_defaults().get(key):
            setattr(args, key, config[key])
    results = _run(args, requests)
    return 1 if any(item.get("error") for item in results) else 0


def parser_defaults() -> dict[str, Any]:
    return {
        "workers": 1,
        "delay_ms": 0,
        "retries": 0,
        "backoff": False,
        "cluster_threshold": 98.0,
    }
