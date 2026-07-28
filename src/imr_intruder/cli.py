from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import ssl
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable

from rich.console import Console

from . import __version__
from .core import (
    MAX_REPEAT,
    MAX_WORKERS,
    build_intruder_requests,
    expand_env,
    load_config,
    load_values,
    merge_request,
    parse_column_specs,
    parse_headers,
    parse_json_argument,
    parse_key_value,
    run_requests,
    validate_columns,
)

CONSOLE = Console()
ERROR_CONSOLE = Console(stderr=True)
DEFAULT_USER_AGENT = f"imr-intruder/{__version__}"


def banner() -> None:
    CONSOLE.print("[bold cyan]imr-intruder[/bold cyan]")
    CONSOLE.print(f"[dim]imr :: v{__version__}[/dim]")


def _add_request_arguments(parser: argparse.ArgumentParser, *, multiple_urls: bool) -> None:
    parser.add_argument(
        "-u",
        "--url",
        action="append" if multiple_urls else "store",
        required=True,
        help="URL objetivo. En intrude puede contener {{VALUE}}.",
    )
    parser.add_argument("-X", "--method", default="GET", help="Método HTTP. Predeterminado: GET")
    parser.add_argument("--name", help="Nombre base mostrado en resultados")
    parser.add_argument("-p", "--param", action="append", help="Query parameter clave=valor")
    parser.add_argument("-H", "--header", action="append", help="Header 'Nombre: valor'")
    parser.add_argument("-b", "--cookie", action="append", help="Cookie clave=valor")
    parser.add_argument("-d", "--data", action="append", help="Formulario clave=valor")
    parser.add_argument("-j", "--json", dest="json_data", help="JSON inline o @archivo.json")
    parser.add_argument("--body", help="Body raw")
    parser.add_argument("--body-file", type=Path, help="Body raw desde archivo")
    parser.add_argument("--auth", help="Basic Auth usuario:contraseña")
    parser.add_argument("--proxy", help="Proxy HTTP/HTTPS, por ejemplo http://127.0.0.1:8080")
    parser.add_argument("--timeout", type=float, default=15.0, help="Timeout en segundos")
    parser.add_argument("-L", "--follow-redirects", action="store_true", help="Seguir redirecciones")
    parser.add_argument("-k", "--insecure", action="store_true", help="Desactivar validación TLS")
    parser.add_argument(
        "--column",
        action="append",
        help="Columna nombre=fuente:clave; puede repetirse",
    )


def _add_execution_arguments(
    parser: argparse.ArgumentParser,
    *,
    default_workers: int,
    default_delay: int,
) -> None:
    parser.add_argument(
        "--workers",
        type=int,
        default=default_workers,
        help=f"Concurrencia entre 1 y {MAX_WORKERS}",
    )
    parser.add_argument(
        "--delay-ms",
        type=int,
        default=default_delay,
        help="Pausa entre envíos en milisegundos",
    )
    parser.add_argument("--csv", type=Path, help="Exportar resultados a CSV")
    parser.add_argument("--jsonl", type=Path, help="Exportar resultados a JSON Lines")
    parser.add_argument(
        "--no-live",
        action="store_true",
        help="No dibujar la tabla; útil para integraciones",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="imr-intruder",
        description=(
            "Cliente HTTP multimodo para solicitudes directas, datasets, lotes JSON "
            "y consola web local. Uso exclusivo en sistemas autorizados."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"imr-intruder {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    request = subparsers.add_parser(
        "request",
        aliases=["run"],
        help="Ejecutar una o varias solicitudes directas",
        description="Ejecuta solicitudes HTTP configuradas por argumentos.",
    )
    _add_request_arguments(request, multiple_urls=True)
    _add_execution_arguments(request, default_workers=1, default_delay=0)
    request.add_argument(
        "--repeat",
        type=int,
        default=1,
        help=f"Repeticiones por URL, entre 1 y {MAX_REPEAT}",
    )

    intrude = subparsers.add_parser(
        "intrude",
        help="Insertar una lista en {{VALUE}} y comparar respuestas",
        description=(
            "Crea una solicitud por valor y reemplaza {{VALUE}} en URL, headers, "
            "params, cookies o body."
        ),
    )
    _add_request_arguments(intrude, multiple_urls=False)
    _add_execution_arguments(intrude, default_workers=2, default_delay=100)
    intrude.add_argument(
        "-V",
        "--value",
        action="append",
        help="Valor de prueba; puede repetirse",
    )
    intrude.add_argument(
        "-W",
        "--values-file",
        type=Path,
        help="Archivo con un valor por línea; usa - para stdin",
    )
    intrude.add_argument(
        "--value-column",
        default="valor_probado",
        help="Nombre de la columna que contiene el valor probado",
    )

    batch = subparsers.add_parser(
        "batch",
        help="Ejecutar requests definidos en un archivo JSON",
        description="Carga defaults, columns y requests desde un archivo JSON.",
    )
    batch.add_argument("config", type=Path, help="Ruta al archivo JSON")
    batch.add_argument("--workers", type=int, help="Sobrescribir concurrencia del JSON")
    batch.add_argument("--delay-ms", type=int, help="Sobrescribir delay del JSON")
    batch.add_argument("--csv", type=Path, help="Exportar resultados a CSV")
    batch.add_argument("--jsonl", type=Path, help="Exportar resultados a JSON Lines")
    batch.add_argument("--no-live", action="store_true")

    web = subparsers.add_parser(
        "web",
        help="Iniciar la consola web",
        description="Inicia la UI web local profesional.",
    )
    web.add_argument("--host", default="127.0.0.1", help="Host de escucha")
    web.add_argument("--port", type=int, default=7415, help="Puerto de escucha")
    web.add_argument("--no-browser", action="store_true", help="No abrir el navegador")
    web.add_argument(
        "--allow-remote",
        action="store_true",
        help="Permitir bind no-local; requiere token y se muestra advertencia",
    )
    web.add_argument("--token", help="Token API fijo; por defecto se genera uno aleatorio")

    doctor = subparsers.add_parser("doctor", help="Diagnosticar instalación y dependencias")
    doctor.add_argument("--json", action="store_true", help="Salida JSON")

    update = subparsers.add_parser("update", help="Actualizar desde el repositorio oficial")
    update.add_argument("--pre", action="store_true", help="Permitir versiones prerelease")

    subparsers.add_parser("version", help="Mostrar versión y entorno")
    return parser


def _validate_runtime(workers: int, delay_ms: int, timeout: float) -> None:
    if not 1 <= workers <= MAX_WORKERS:
        raise ValueError(f"--workers debe estar entre 1 y {MAX_WORKERS}.")
    if not 0 <= delay_ms <= 60_000:
        raise ValueError("--delay-ms debe estar entre 0 y 60000.")
    if not 0.1 <= timeout <= 300:
        raise ValueError("--timeout debe estar entre 0.1 y 300 segundos.")


def _build_base_request(args: argparse.Namespace, url: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    headers = parse_headers(args.header)
    headers.setdefault("User-Agent", DEFAULT_USER_AGENT)
    params = parse_key_value(args.param, "Parámetro")
    cookies = parse_key_value(args.cookie, "Cookie")
    form_data = parse_key_value(args.data, "Dato")
    columns = parse_column_specs(args.column)

    selected_bodies = sum(
        bool(value)
        for value in (args.data, args.json_data, args.body, args.body_file)
    )
    if selected_bodies > 1:
        raise ValueError("Usa solo uno: --data, --json, --body o --body-file.")

    cfg: dict[str, Any] = {
        "name": args.name,
        "method": str(args.method).upper(),
        "url": os.path.expandvars(url),
        "headers": headers,
        "params": params,
        "cookies": cookies,
        "timeout": args.timeout,
        "verify_tls": not args.insecure,
        "follow_redirects": args.follow_redirects,
        "proxy": args.proxy,
    }

    if args.auth:
        if ":" not in args.auth:
            raise ValueError("--auth debe usar usuario:contraseña.")
        username, password = args.auth.split(":", 1)
        cfg["auth"] = {"username": username, "password": password}

    if args.json_data:
        cfg["json"] = parse_json_argument(args.json_data)
    elif args.data:
        cfg["data"] = form_data
    elif args.body is not None:
        cfg["body"] = os.path.expandvars(args.body)
    elif args.body_file:
        try:
            cfg["body"] = args.body_file.expanduser().read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"No se pudo leer el body: {exc}") from exc

    return cfg, columns


def _write_jsonl(path: Path, results: Iterable[dict[str, Any]]) -> None:
    try:
        with path.expanduser().open("w", encoding="utf-8") as output:
            for item in results:
                output.write(json.dumps(item, ensure_ascii=False) + "\n")
    except OSError as exc:
        raise ValueError(f"No se pudo guardar JSONL {path}: {exc}") from exc


def _execute_request_mode(args: argparse.Namespace) -> int:
    _validate_runtime(args.workers, args.delay_ms, args.timeout)
    if not 1 <= args.repeat <= MAX_REPEAT:
        raise ValueError(f"--repeat debe estar entre 1 y {MAX_REPEAT}.")

    requests_cfg: list[dict[str, Any]] = []
    columns: list[dict[str, Any]] | None = None
    urls = args.url if isinstance(args.url, list) else [args.url]
    for url_index, url in enumerate(urls, start=1):
        base, current_columns = _build_base_request(args, url)
        columns = current_columns
        for repetition in range(1, args.repeat + 1):
            cfg = dict(base)
            cfg["name"] = args.name or (
                f"request-{url_index}.{repetition}"
                if len(urls) > 1 or args.repeat > 1
                else "request-1"
            )
            requests_cfg.append(cfg)

    results = run_requests(
        requests_cfg=requests_cfg,
        global_columns=columns or [],
        workers=args.workers,
        csv_path=args.csv,
        delay_ms=args.delay_ms,
        live=not args.no_live,
    )
    if args.jsonl:
        _write_jsonl(args.jsonl, results)
    return 1 if any(item["error"] for item in results) else 0


def _execute_intrude_mode(args: argparse.Namespace) -> int:
    _validate_runtime(args.workers, args.delay_ms, args.timeout)
    values = load_values(args.values_file, args.value)
    base, columns = _build_base_request(args, args.url)
    base["name"] = None
    requests_cfg = build_intruder_requests(
        base,
        values,
        value_column=args.value_column,
    )
    results = run_requests(
        requests_cfg=requests_cfg,
        global_columns=columns,
        workers=args.workers,
        csv_path=args.csv,
        delay_ms=args.delay_ms,
        live=not args.no_live,
    )
    if args.jsonl:
        _write_jsonl(args.jsonl, results)
    return 1 if any(item["error"] for item in results) else 0


def _execute_batch_mode(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    defaults = config.get("defaults", {})
    if not isinstance(defaults, dict):
        raise ValueError('"defaults" debe ser un objeto.')
    columns = validate_columns(config.get("columns"))
    requests_cfg = []
    for position, item in enumerate(config["requests"], start=1):
        if not isinstance(item, dict):
            raise ValueError(f"El request #{position} debe ser un objeto.")
        requests_cfg.append(merge_request(defaults, expand_env(item)))

    workers = args.workers if args.workers is not None else int(config.get("workers", 1))
    delay_ms = args.delay_ms if args.delay_ms is not None else int(config.get("delay_ms", 0))
    timeout = float(defaults.get("timeout", 15))
    _validate_runtime(workers, delay_ms, timeout)

    results = run_requests(
        requests_cfg=requests_cfg,
        global_columns=columns,
        workers=workers,
        csv_path=args.csv,
        delay_ms=delay_ms,
        live=not args.no_live,
    )
    if args.jsonl:
        _write_jsonl(args.jsonl, results)
    return 1 if any(item["error"] for item in results) else 0


def _doctor_data() -> dict[str, Any]:
    required = ["requests", "rich", "fastapi", "uvicorn", "jinja2"]
    dependencies = {
        name: importlib.util.find_spec(name) is not None
        for name in required
    }
    writable = False
    try:
        with tempfile.NamedTemporaryFile(prefix="imr-intruder-", delete=True):
            writable = True
    except OSError:
        pass

    return {
        "version": __version__,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "openssl": ssl.OPENSSL_VERSION,
        "dependencies": dependencies,
        "temp_writable": writable,
        "ok": all(dependencies.values()) and writable and sys.version_info >= (3, 10),
    }


def _run_doctor(as_json: bool) -> int:
    data = _doctor_data()
    if as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        banner()
        CONSOLE.print(f"Python: [bold]{data['python']}[/bold]")
        CONSOLE.print(f"Plataforma: {data['platform']}")
        CONSOLE.print(f"OpenSSL: {data['openssl']}")
        for name, installed in data["dependencies"].items():
            marker = "[green]OK[/green]" if installed else "[red]FALTA[/red]"
            CONSOLE.print(f"{name}: {marker}")
        CONSOLE.print(
            "Directorio temporal: "
            + ("[green]escribible[/green]" if data["temp_writable"] else "[red]sin acceso[/red]")
        )
    return 0 if data["ok"] else 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command in {"request", "run"}:
            banner()
            return _execute_request_mode(args)
        if args.command == "intrude":
            banner()
            return _execute_intrude_mode(args)
        if args.command == "batch":
            banner()
            return _execute_batch_mode(args)
        if args.command == "web":
            from .web import run_server

            banner()
            run_server(
                host=args.host,
                port=args.port,
                open_browser=not args.no_browser,
                allow_remote=args.allow_remote,
                token=args.token,
            )
            return 0
        if args.command == "doctor":
            return _run_doctor(args.json)
        if args.command == "update":
            banner()
            package = "git+https://github.com/IsdarlinM/imr-intruder.git"
            command = [sys.executable, "-m", "pip", "install", "--upgrade"]
            if args.pre:
                command.append("--pre")
            command.append(package)
            completed = subprocess.run(command, check=False)
            return int(completed.returncode)
        if args.command == "version":
            banner()
            CONSOLE.print(f"Python {platform.python_version()} · {platform.system()}")
            return 0
    except KeyboardInterrupt:
        CONSOLE.print("\n[yellow]Ejecución interrumpida por el usuario.[/yellow]")
        return 130
    except (OSError, TypeError, ValueError) as exc:
        ERROR_CONSOLE.print(f"[red][ERROR][/red] {exc}")
        return 2

    parser.error("Comando no reconocido.")
    return 2
