from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from rich.console import Console
from rich.markup import escape

from . import APP_NAME
from .cli_parser import build_parser
from .storage import atomic_json_write
from .webctl import serve

error_console = Console(stderr=True)


def main(argv: list[str] | None = None) -> int:
    resolved = list(sys.argv[1:] if argv is None else argv)
    if resolved[:1] == ["_web-serve"]:
        hidden = argparse.ArgumentParser(prog=f"{APP_NAME} _web-serve")
        hidden.add_argument("--host", required=True)
        hidden.add_argument("--port", type=int, required=True)
        hidden.add_argument("--token")
        hidden.add_argument("--allow-remote", action="store_true")
        hidden.add_argument("--multiuser", action="store_true")
        hidden.add_argument("--scope", action="append", default=[])
        hidden.add_argument("--pid-file")
        args = hidden.parse_args(resolved[1:])
        if args.pid_file:
            atomic_json_write(Path(args.pid_file), {"pid": os.getpid()})
        runtime_token = args.token or os.environ.pop("IMR_INTRUDER_WEB_RUNTIME_TOKEN", "")
        if not runtime_token:
            hidden.error("a runtime token is required")
        return serve(
            args.host,
            args.port,
            runtime_token,
            args.allow_remote,
            args.multiuser,
            False,
            args.scope,
        )
    parser = build_parser()
    args = parser.parse_args(resolved)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        error_console.print("[yellow]Interrupted.[/yellow]")
        return 130
    except Exception as exc:
        error_console.print(f"[red]ERROR:[/red] {escape(type(exc).__name__ + ': ' + str(exc))}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
