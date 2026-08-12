from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .browser import fetch_page
from .cli_runtime import (
    _json_print,
    _load_json_value,
    _load_values,
    _parse_key_values,
    _run,
    console,
)
from .collaboration import create_token, list_tokens, revoke_token
from .core import write_jsonl
from .importers import load_import
from .macros import run_macro
from .paths import ensure_paths
from .plugins import plugin_status
from .report import build_html_report, load_results
from .storage import (
    create_session,
    create_workspace,
    current_workspace,
    delete_session,
    export_workspace,
    list_sessions,
    list_workspaces,
    load_session,
    save_session,
    set_current_workspace,
    workspace_path,
)
from .updater import check_update, install_update
from .webctl import (
    open_ui,
    serve,
    start_background,
)
from .webctl import (
    status as web_status,
)
from .webctl import (
    stop as web_stop,
)
from .websocket_client import run_websocket


def _parse_session_value(raw: str) -> Any:
    if raw.startswith("@"):
        return _load_json_value(raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def cmd_repeater(args: argparse.Namespace) -> int:
    imported = load_import(args.kind, Path(args.request_file))
    requests: list[dict[str, Any]] = []
    for repetition in range(1, args.repeat + 1):
        for position, request in enumerate(imported, start=1):
            item = dict(request)
            base_name = str(item.get("name") or "repeater")
            item["name"] = f"{base_name}-r{repetition}" if args.repeat > 1 else base_name
            requests.append(item)
    results = _run(args, requests)
    return 1 if any(item.get("error") for item in results) else 0


def cmd_import(args: argparse.Namespace) -> int:
    requests = load_import(args.kind, Path(args.input))
    output = Path(args.output).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps({"requests": requests}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    console.print(f"[green]Imported {len(requests)} request(s) to {output}[/green]")
    return 0


def cmd_session(args: argparse.Namespace) -> int:
    if args.session_action == "create":
        create_session(args.name)
        console.print(f"Created session {args.name}")
    elif args.session_action == "list":
        _json_print(list_sessions()) if args.json_output else console.print(
            "\n".join(list_sessions()) or "No sessions"
        )
    elif args.session_action == "show":
        data = load_session(args.name)
        if not args.show_secrets:
            for key in ("auth", "cookies"):
                if data.get(key):
                    data[key] = "<REDACTED>"
        _json_print(data)
    elif args.session_action == "delete":
        delete_session(args.name)
        console.print(f"Deleted session {args.name}")
    elif args.session_action == "set":
        data = load_session(args.name)
        data[args.key] = _parse_session_value(args.value)
        save_session(args.name, data)
        console.print(f"Updated session {args.name}")
    elif args.session_action == "cookies":
        data = load_session(args.name)
        data["cookies"] = _parse_key_values(args.cookie)
        save_session(args.name, data)
        console.print(f"Updated cookies for {args.name}")
    return 0


def cmd_workspace(args: argparse.Namespace) -> int:
    if args.workspace_action == "create":
        console.print(str(create_workspace(args.name)))
    elif args.workspace_action == "list":
        _json_print(list_workspaces()) if args.json_output else console.print(
            "\n".join(list_workspaces()) or "No workspaces"
        )
    elif args.workspace_action == "use":
        console.print(str(set_current_workspace(args.name)))
    elif args.workspace_action == "show":
        name = args.name or current_workspace()
        if not name:
            raise ValueError("No workspace selected.")
        _json_print(
            {
                "name": name,
                "path": str(workspace_path(name)),
                "current": name == current_workspace(),
            }
        )
    elif args.workspace_action == "export":
        console.print(str(export_workspace(args.name, Path(args.output))))
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    results = load_results(Path(args.input))
    output = build_html_report(results, Path(args.output), args.title)
    console.print(str(output))
    return 0


def cmd_macro(args: argparse.Namespace) -> int:
    results = run_macro(Path(args.file), args.session)
    if args.output:
        write_jsonl(Path(args.output), results)
    _json_print(results)
    return 1 if any(item.get("error") for item in results) else 0


def cmd_websocket(args: argparse.Namespace) -> int:
    messages = args.message or (
        _load_values(Path(args.messages_file)) if args.messages_file else []
    )
    if not messages:
        raise ValueError("Provide --message or --messages-file.")
    results = run_websocket(
        args.url, messages, args.timeout, _parse_key_values(args.header, header=True)
    )
    _json_print(results)
    return 1 if any(item.get("error") for item in results) else 0


def cmd_browser(args: argparse.Namespace) -> int:
    _json_print(
        fetch_page(
            args.url,
            Path(args.screenshot) if args.screenshot else None,
            int(args.timeout * 1000),
        )
    )
    return 0


def cmd_plugins(args: argparse.Namespace) -> int:
    _json_print(plugin_status())
    return 0


def cmd_collab(args: argparse.Namespace) -> int:
    if args.collab_action == "create-token":
        token = create_token(args.name, args.role)
        console.print(token)
    elif args.collab_action == "list":
        _json_print(list_tokens())
    elif args.collab_action == "revoke":
        revoke_token(args.name)
        console.print(f"Revoked {args.name}")
    return 0


def cmd_web(args: argparse.Namespace) -> int:
    action = args.web_action or "start"
    if action == "start":
        if args.background:
            _json_print(
                start_background(
                    args.host, args.port, args.token, args.allow_remote, args.multiuser
                )
            )
            return 0
        token = args.token or os.environ.get("IMR_INTRUDER_WEB_TOKEN") or os.urandom(24).hex()
        return serve(
            args.host,
            args.port,
            token,
            args.allow_remote,
            args.multiuser,
            not args.no_browser,
        )
    if action == "status":
        current = web_status()
        _json_print(current)
        return 0 if current.get("running") else 1
    if action == "stop":
        _json_print(web_stop())
        return 0
    if action == "open":
        console.print(open_ui())
        return 0
    raise ValueError(f"Unknown web action: {action}")


def cmd_check_update(args: argparse.Namespace) -> int:
    info = check_update(args.repository, args.channel, args.token)
    _json_print(info.__dict__) if args.json_output else console.print(
        f"Current: {info.current}\nLatest: {info.latest}\nAvailable: {info.available}\nSource: {info.source}"
    )
    return 0 if info.available else 2


def cmd_update(args: argparse.Namespace) -> int:
    info = check_update(args.repository, args.channel, args.token)
    if not info.available and not args.force:
        console.print("Already up to date.")
        return 0
    web_was_running = False
    if not args.dry_run:
        current_web = web_status()
        web_was_running = bool(current_web.get("running"))
        if web_was_running:
            web_stop()
    result = install_update(info, token=args.token, dry_run=args.dry_run)
    if web_was_running:
        result["web_console"] = "stopped; restart it with: imr-intruder web start"
    _json_print(result)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    paths = ensure_paths()
    required_modules = (
        "httpx",
        "fastapi",
        "uvicorn",
        "jinja2",
        "rich",
        "packaging",
        "websockets",
    )
    dependencies = {name: importlib.util.find_spec(name) is not None for name in required_modules}
    writable: dict[str, bool] = {}
    for key, path in paths.__dict__.items():
        try:
            probe = path / ".imr-intruder-write-test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            writable[key] = True
        except OSError:
            writable[key] = False
    checks = {
        "version": __version__,
        "python": sys.version.split()[0],
        "python_supported": sys.version_info >= (3, 10),
        "executable": sys.executable,
        "dependencies": dependencies,
        "dependencies_ok": all(dependencies.values()),
        "paths": {key: str(value) for key, value in paths.__dict__.items()},
        "paths_writable": writable,
        "paths_ok": all(writable.values()),
        "browser_optional_installed": importlib.util.find_spec("playwright") is not None,
        "environment": {
            name: os.environ.get(name, "")
            for name in (
                "IMR_INTRUDER_HOME",
                "IMR_INTRUDER_CONFIG",
                "IMR_INTRUDER_STATE",
                "IMR_INTRUDER_DATA",
                "IMR_INTRUDER_CACHE",
            )
        },
    }
    checks["ok"] = checks["python_supported"] and checks["dependencies_ok"] and checks["paths_ok"]
    _json_print(checks) if args.json_output else console.print_json(json.dumps(checks))
    return 0 if checks["ok"] else 1
