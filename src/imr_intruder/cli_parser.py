from __future__ import annotations

import argparse
from typing import Any

from . import APP_NAME, __version__
from .updater import DEFAULT_REPOSITORY
from .cli_runtime import cmd_request, cmd_intrude, cmd_batch
from .cli_actions import (cmd_repeater, cmd_import, cmd_session, cmd_workspace, cmd_report,
    cmd_macro, cmd_websocket, cmd_browser, cmd_plugins, cmd_collab, cmd_web,
    cmd_check_update, cmd_update, cmd_doctor, console)

def add_http_options(parser: argparse.ArgumentParser, require_url: bool = True) -> None:
    parser.add_argument("--url", "-u", required=require_url)
    parser.add_argument("--method", "-X", default="GET")
    parser.add_argument("--name")
    parser.add_argument("--header", "-H", action="append", default=[])
    parser.add_argument("--param", "-p", action="append", default=[])
    parser.add_argument("--cookie", action="append", default=[])
    body = parser.add_mutually_exclusive_group()
    body.add_argument("--json")
    body.add_argument("--data", action="append")
    body.add_argument("--body")
    parser.add_argument("--form", action="append", default=[])
    parser.add_argument("--user", help="Basic auth USER:PASSWORD")
    parser.add_argument("--session")
    parser.add_argument("--proxy")
    parser.add_argument("--timeout", type=float, default=15)
    parser.add_argument("--insecure", action="store_true")
    parser.add_argument("--follow-redirects", action="store_true")
    parser.add_argument("--http2", action="store_true")


def add_execution_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--delay-ms", type=int, default=0)
    parser.add_argument("--rate", type=float)
    parser.add_argument("--retries", type=int, default=0)
    parser.add_argument("--backoff", action="store_true")
    parser.add_argument("--body-limit", type=int, default=1024 * 1024)
    parser.add_argument("--checkpoint")
    parser.add_argument("--column", action="append", default=[])
    parser.add_argument("--match", action="append", default=[])
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument("--extract", action="append", default=[])
    parser.add_argument("--cluster-threshold", type=float, default=98.0)
    parser.add_argument("--csv")
    parser.add_argument("--jsonl")
    parser.add_argument("--output-json")
    parser.add_argument("--quiet", action="store_true")


def parser_defaults() -> dict[str, Any]:
    return {"workers": 1, "delay_ms": 0, "retries": 0, "backoff": False, "cluster_threshold": 98.0}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=APP_NAME, description="Professional multimode HTTP and response intelligence toolkit.")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    request = sub.add_parser("request", help="Send one custom HTTP request")
    add_http_options(request); add_execution_options(request); request.set_defaults(func=cmd_request)

    intrude = sub.add_parser("intrude", help="Run controlled payload variations")
    add_http_options(intrude); add_execution_options(intrude)
    intrude.add_argument("--payload", action="append", default=[], help="NAME=values.txt")
    intrude.add_argument("--values-file")
    intrude.add_argument("--mode", choices=["sniper", "battering-ram", "pitchfork", "cluster-bomb"], default="sniper")
    intrude.add_argument("--max-requests", type=int, default=10000)
    intrude.set_defaults(func=cmd_intrude)

    batch = sub.add_parser("batch", help="Execute requests from JSON config")
    batch.add_argument("config"); add_execution_options(batch); batch.set_defaults(func=cmd_batch)

    repeater = sub.add_parser("repeater", help="Repeat an imported request")
    repeater.add_argument("request_file"); repeater.add_argument("--kind", choices=["raw", "curl", "har", "burp", "zap"], default="raw")
    repeater.add_argument("--repeat", type=int, default=1); add_execution_options(repeater); repeater.set_defaults(func=cmd_repeater)

    importer = sub.add_parser("import", help="Import HTTP requests")
    importer.add_argument("kind", choices=["raw", "curl", "har", "burp", "zap"]); importer.add_argument("input"); importer.add_argument("--output", "-o", required=True); importer.set_defaults(func=cmd_import)

    session = sub.add_parser("session", help="Manage persistent HTTP sessions"); session_sub = session.add_subparsers(dest="session_action", required=True)
    for action in ("create", "show", "delete"):
        child = session_sub.add_parser(action); child.add_argument("name")
        if action == "show": child.add_argument("--show-secrets", action="store_true")
    child = session_sub.add_parser("list"); child.add_argument("--json", dest="json_output", action="store_true")
    child = session_sub.add_parser("set"); child.add_argument("name"); child.add_argument("key"); child.add_argument("value")
    child = session_sub.add_parser("cookies"); child.add_argument("name"); child.add_argument("--cookie", action="append", required=True)
    session.set_defaults(func=cmd_session)

    workspace = sub.add_parser("workspace", help="Manage isolated workspaces"); workspace_sub = workspace.add_subparsers(dest="workspace_action", required=True)
    child = workspace_sub.add_parser("create"); child.add_argument("name")
    child = workspace_sub.add_parser("list"); child.add_argument("--json", dest="json_output", action="store_true")
    child = workspace_sub.add_parser("use"); child.add_argument("name")
    child = workspace_sub.add_parser("show"); child.add_argument("name", nargs="?")
    child = workspace_sub.add_parser("export"); child.add_argument("name"); child.add_argument("--output", "-o", required=True)
    workspace.set_defaults(func=cmd_workspace)

    report = sub.add_parser("report", help="Build a redacted HTML report"); report.add_argument("input"); report.add_argument("--output", "-o", required=True); report.add_argument("--title", default="imr-intruder report"); report.set_defaults(func=cmd_report)
    macro = sub.add_parser("macro", help="Run a multi-step authentication/request macro"); macro.add_argument("file"); macro.add_argument("--session"); macro.add_argument("--output"); macro.set_defaults(func=cmd_macro)
    websocket = sub.add_parser("websocket", help="Send controlled WebSocket messages"); websocket.add_argument("url"); websocket.add_argument("--message", action="append"); websocket.add_argument("--messages-file"); websocket.add_argument("--header", action="append", default=[]); websocket.add_argument("--timeout", type=float, default=10); websocket.set_defaults(func=cmd_websocket)
    browser = sub.add_parser("browser", help="Render a page using optional Playwright"); browser.add_argument("url"); browser.add_argument("--screenshot"); browser.add_argument("--timeout", type=float, default=30); browser.set_defaults(func=cmd_browser)
    plugins = sub.add_parser("plugins", help="List installed plugins"); plugins.set_defaults(func=cmd_plugins)

    collab = sub.add_parser("collab", help="Manage multiuser web tokens"); collab_sub = collab.add_subparsers(dest="collab_action", required=True)
    child = collab_sub.add_parser("create-token"); child.add_argument("name"); child.add_argument("--role", choices=["viewer", "operator", "admin"], required=True)
    collab_sub.add_parser("list")
    child = collab_sub.add_parser("revoke"); child.add_argument("name")
    collab.set_defaults(func=cmd_collab)

    web = sub.add_parser("web", help="Manage the web console"); web.add_argument("web_action", nargs="?", choices=["start", "stop", "status", "open"], default="start")
    web.add_argument("--host", default="127.0.0.1"); web.add_argument("--port", type=int, default=7415); web.add_argument("--token"); web.add_argument("--allow-remote", action="store_true"); web.add_argument("--multiuser", action="store_true"); web.add_argument("--background", action="store_true"); web.add_argument("--no-browser", action="store_true"); web.set_defaults(func=cmd_web)

    check = sub.add_parser("check-update", help="Check GitHub for a newer version"); check.add_argument("--repository", default=DEFAULT_REPOSITORY); check.add_argument("--channel", choices=["release", "main"], default="release"); check.add_argument("--token"); check.add_argument("--json", dest="json_output", action="store_true"); check.set_defaults(func=cmd_check_update)
    update = sub.add_parser("update", help="Download and install an update without git clone"); update.add_argument("--repository", default=DEFAULT_REPOSITORY); update.add_argument("--channel", choices=["release", "main"], default="release"); update.add_argument("--token"); update.add_argument("--dry-run", action="store_true"); update.add_argument("--force", action="store_true"); update.set_defaults(func=cmd_update)
    doctor = sub.add_parser("doctor", help="Validate runtime and configured paths"); doctor.add_argument("--json", dest="json_output", action="store_true"); doctor.set_defaults(func=cmd_doctor)
    version = sub.add_parser("version", help="Print version"); version.set_defaults(func=lambda args: (console.print(__version__) or 0))
    return parser
