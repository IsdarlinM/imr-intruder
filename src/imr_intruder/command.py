from __future__ import annotations

import argparse
import sys

from . import APP_NAME
from .cli_actions import console
from .cli_parser import build_parser
from .webctl import serve


def main(argv: list[str] | None = None) -> int:
    resolved = list(sys.argv[1:] if argv is None else argv)
    if resolved[:1] == ["_web-serve"]:
        hidden = argparse.ArgumentParser(prog=f"{APP_NAME} _web-serve")
        hidden.add_argument("--host", required=True)
        hidden.add_argument("--port", type=int, required=True)
        hidden.add_argument("--token", required=True)
        hidden.add_argument("--allow-remote", action="store_true")
        hidden.add_argument("--multiuser", action="store_true")
        args = hidden.parse_args(resolved[1:])
        return serve(args.host, args.port, args.token, args.allow_remote, args.multiuser, False)
    parser = build_parser()
    args = parser.parse_args(resolved)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        console.print("[yellow]Interrupted.[/yellow]")
        return 130
    except Exception as exc:
        console.print(f"[red]ERROR:[/red] {type(exc).__name__}: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
