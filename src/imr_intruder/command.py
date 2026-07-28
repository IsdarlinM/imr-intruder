from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence

from rich.console import Console

from . import __version__
from .cli import main as legacy_main
from .web import run_server
from .webctl import open_background_web, start_background, stop_background, web_status

CONSOLE = Console()
ERROR_CONSOLE = Console(stderr=True)


def _banner() -> None:
    CONSOLE.print("[bold cyan]imr-intruder[/bold cyan]")
    CONSOLE.print(f"[dim]imr :: v{__version__}[/dim]")


def _web_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="imr-intruder web",
        description="Administra la consola web local de imr-intruder.",
    )
    parser.add_argument(
        "action",
        nargs="?",
        choices=("start", "stop", "status", "open"),
        default="start",
        help="Acción. Predeterminado: start.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host de escucha")
    parser.add_argument("--port", type=int, default=7415, help="Puerto de escucha")
    parser.add_argument("--no-browser", action="store_true", help="No abrir navegador")
    parser.add_argument("--background", action="store_true", help="Ejecutar como proceso de usuario")
    parser.add_argument("--foreground", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--log-file", help="Archivo de log del proceso en segundo plano")
    parser.add_argument("--allow-remote", action="store_true", help="Permitir bind no local")
    parser.add_argument("--token", help="Token fijo; por defecto se genera uno aleatorio")
    return parser


def _update_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="imr-intruder update",
        description="Actualiza imr-intruder desde el repositorio oficial.",
    )
    parser.add_argument("--pre", action="store_true", help="Permitir prereleases")
    parser.add_argument("--dry-run", action="store_true", help="Mostrar el comando sin ejecutarlo")
    return parser


def _top_help() -> None:
    CONSOLE.print(
        """[bold]Uso:[/bold] imr-intruder COMMAND [opciones]

[bold]Comandos:[/bold]
  request      Ejecutar una o varias solicitudes directas
  intrude      Insertar valores en {{VALUE}} y comparar respuestas
  batch        Ejecutar solicitudes heterogéneas desde JSON
  web          Iniciar, detener, consultar o abrir la consola web
  doctor       Diagnosticar instalación y dependencias
  update       Actualizar desde el repositorio oficial
  version      Mostrar versión y entorno

Ejecuta [cyan]imr-intruder COMMAND --help[/cyan] para ayuda específica.
"""
    )


def _run_web(argv: Sequence[str]) -> int:
    args = _web_parser().parse_args(list(argv))
    _banner()

    if args.action == "status":
        status = web_status()
        if not status.get("running"):
            CONSOLE.print("Estado: [yellow]detenido[/yellow]")
            return 1
        CONSOLE.print(f"Estado: [green]activo[/green] · PID {status['pid']}")
        CONSOLE.print(f"URL: {status.get('access_url', status.get('url', ''))}")
        CONSOLE.print(f"Log: {status.get('log_file', '-')}")
        return 0

    if args.action == "stop":
        stopped = stop_background()
        CONSOLE.print(
            "Consola web detenida."
            if stopped
            else "No había una consola web en segundo plano activa."
        )
        return 0

    if args.action == "open":
        url = open_background_web()
        CONSOLE.print(f"Abriendo: {url}")
        return 0

    if args.background and args.foreground:
        raise ValueError("Usa solo uno: --background o --foreground.")

    if args.background:
        state = start_background(
            host=args.host,
            port=args.port,
            open_browser=not args.no_browser,
            allow_remote=args.allow_remote,
            token=args.token,
            log_file=args.log_file,
        )
        CONSOLE.print(f"Estado: [green]activo en segundo plano[/green] · PID {state['pid']}")
        CONSOLE.print(f"URL: {state['access_url']}")
        CONSOLE.print(f"Log: {state['log_file']}")
        return 0

    run_server(
        host=args.host,
        port=args.port,
        open_browser=not args.no_browser,
        allow_remote=args.allow_remote,
        token=args.token,
    )
    return 0


def _run_update(argv: Sequence[str]) -> int:
    args = _update_parser().parse_args(list(argv))
    _banner()
    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--upgrade",
    ]
    if args.pre:
        command.append("--pre")
    command.append("git+https://github.com/IsdarlinM/imr-intruder.git")

    if args.dry_run:
        CONSOLE.print("Comando de actualización:")
        CONSOLE.print(" ".join(command))
        return 0
    return int(subprocess.run(command, check=False).returncode)


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments[0] in {"-h", "--help"}:
        _top_help()
        return 0

    try:
        if arguments[0] == "web":
            return _run_web(arguments[1:])
        if arguments[0] == "update":
            return _run_update(arguments[1:])
        return int(legacy_main(arguments))
    except KeyboardInterrupt:
        ERROR_CONSOLE.print("\n[yellow]Ejecución interrumpida por el usuario.[/yellow]")
        return 130
    except (OSError, TypeError, ValueError) as exc:
        ERROR_CONSOLE.print(f"[red][ERROR][/red] {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
