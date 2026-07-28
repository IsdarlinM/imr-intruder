from __future__ import annotations

import csv
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

import requests
from rich.console import Console
from rich.live import Live
from rich.table import Table

MAX_WORKERS = 20
MAX_REPEAT = 1000
MAX_VALUES = 10_000
PLACEHOLDER = "{{VALUE}}"
METHOD_RE = re.compile(r"^[A-Z]+$")


def expand_env(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: expand_env(item) for key, item in value.items()}
    if isinstance(value, list):
        return [expand_env(item) for item in value]
    return os.path.expandvars(value) if isinstance(value, str) else value


def load_config(path: Path) -> dict[str, Any]:
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"No existe el archivo: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"JSON inválido: línea {exc.lineno}, columna {exc.colno}: {exc.msg}"
        ) from exc
    config = expand_env(config)
    if not isinstance(config, dict):
        raise ValueError("La raíz del JSON debe ser un objeto.")
    if not isinstance(config.get("requests"), list) or not config["requests"]:
        raise ValueError('Debes definir una lista no vacía en "requests".')
    return config


def validate_columns(columns: Any) -> list[dict[str, Any]]:
    if columns is None:
        return []
    if not isinstance(columns, list):
        raise ValueError('"columns" debe ser una lista.')
    validated: list[dict[str, Any]] = []
    for position, column in enumerate(columns, 1):
        if not isinstance(column, dict):
            raise ValueError(f"La columna #{position} debe ser un objeto.")
        if not column.get("name") or not column.get("source"):
            raise ValueError(f"La columna #{position} necesita 'name' y 'source'.")
        validated.append(dict(column))
    return validated


def merge_request(defaults: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    merged = {**defaults, **item}
    merged["headers"] = {**defaults.get("headers", {}), **item.get("headers", {})}
    merged["cookies"] = {**defaults.get("cookies", {}), **item.get("cookies", {})}
    return merged


def parse_key_value(values: Iterable[str] | None, label: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in values or []:
        if "=" not in raw:
            raise ValueError(f"{label} inválido: {raw!r}. Usa clave=valor.")
        key, value = raw.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"{label} inválido: la clave está vacía.")
        result[key] = os.path.expandvars(value)
    return result


def parse_headers(values: Iterable[str] | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in values or []:
        separator = ":" if ":" in raw else "=" if "=" in raw else None
        if separator is None:
            raise ValueError(f"Header inválido: {raw!r}. Usa 'Nombre: valor'.")
        key, value = raw.split(separator, 1)
        if not key.strip():
            raise ValueError("El nombre del header no puede estar vacío.")
        result[key.strip()] = os.path.expandvars(value.strip())
    return result


def parse_json_argument(raw: str) -> Any:
    if raw.startswith("@"):
        path = Path(raw[1:]).expanduser()
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"No se pudo leer el JSON {path}: {exc}") from exc
    try:
        return expand_env(json.loads(raw))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"JSON inválido: línea {exc.lineno}, columna {exc.colno}: {exc.msg}"
        ) from exc


def parse_column_specs(values: Iterable[str] | None) -> list[dict[str, Any]]:
    valid = {
        "header", "cookie", "json", "regex", "request_header",
        "request_param", "response", "literal",
    }
    columns: list[dict[str, Any]] = []
    for raw in values or []:
        if "=" not in raw or ":" not in raw:
            raise ValueError(f"Columna inválida: {raw!r}. Usa nombre=fuente:clave.")
        name, specification = raw.split("=", 1)
        source, key = specification.split(":", 1)
        name, source = name.strip(), source.strip().lower()
        if not name or source not in valid:
            raise ValueError(f"Fuente inválida. Admitidas: {', '.join(sorted(valid))}")
        column: dict[str, Any] = {"name": name, "source": source, "default": "-"}
        if source == "regex":
            column.update(pattern=key, group=1 if "(" in key else 0)
        elif source == "literal":
            column["value"] = key
        else:
            column["key"] = key
        columns.append(column)
    return columns


def json_path_get(data: Any, path: str) -> Any:
    if path in ("", "$"):
        return data
    current = data
    for match in re.finditer(r"([^. \[\]]+)|\[(\d+)\]", path.removeprefix("$.")):
        key, index = match.groups()
        if key is not None:
            if not isinstance(current, dict):
                return None
            actual = key if key in current else next(
                (candidate for candidate in current if candidate.lower() == key.lower()), None
            )
            if actual is None:
                return None
            current = current[actual]
        else:
            position = int(index)
            if not isinstance(current, list) or position >= len(current):
                return None
            current = current[position]
    return current


def stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def extract_column(
    column: dict[str, Any],
    response: requests.Response,
    request_cfg: dict[str, Any],
    parsed_json: Any,
) -> str:
    source = str(column.get("source", "")).lower()
    key = str(column.get("key", ""))
    default = stringify(column.get("default", ""))
    try:
        if source == "header":
            return response.headers.get(key, default)
        if source == "cookie":
            return response.cookies.get(key, default)
        if source == "json":
            value = json_path_get(parsed_json, key) if parsed_json is not None else None
            return stringify(value) or default
        if source == "regex":
            flags = re.IGNORECASE if column.get("ignore_case", False) else 0
            match = re.search(str(column.get("pattern", "")), response.text, flags)
            return stringify(match.group(int(column.get("group", 0)))) if match else default
        if source == "request_header":
            return stringify(request_cfg.get("headers", {}).get(key, default))
        if source == "request_param":
            return stringify(request_cfg.get("params", {}).get(key, default))
        if source == "response":
            metadata = {
                "url": response.url,
                "reason": response.reason,
                "encoding": response.encoding,
                "http_version": getattr(response.raw, "version", ""),
            }
            return stringify(metadata.get(key, default))
        if source == "literal":
            return stringify(column.get("value", default))
    except (IndexError, KeyError, TypeError, ValueError, re.error):
        return default
    return default


def execute_request(
    index: int,
    request_cfg: dict[str, Any],
    global_columns: list[dict[str, Any]],
) -> dict[str, Any]:
    method = str(request_cfg.get("method", "GET")).upper()
    url = request_cfg.get("url")
    result: dict[str, Any] = {
        "index": index + 1,
        "name": str(request_cfg.get("name") or f"request-{index + 1}"),
        "method": method,
        "status": "-",
        "size_bytes": 0,
        "elapsed_ms": 0,
        "content_type": "",
        "custom": {},
        "error": "",
    }
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        result["error"] = "URL inválida o ausente"
        return result
    if not METHOD_RE.fullmatch(method):
        result["error"] = f"Método HTTP inválido: {method}"
        return result
    body_fields = [field for field in ("json", "data", "body") if field in request_cfg]
    if len(body_fields) > 1:
        result["error"] = "Usa solo uno de estos campos: json, data o body"
        return result

    kwargs: dict[str, Any] = {
        "method": method,
        "url": url,
        "params": request_cfg.get("params"),
        "headers": request_cfg.get("headers"),
        "cookies": request_cfg.get("cookies"),
        "timeout": float(request_cfg.get("timeout", 15)),
        "verify": bool(request_cfg.get("verify_tls", True)),
        "allow_redirects": bool(request_cfg.get("follow_redirects", False)),
    }
    if "json" in request_cfg:
        kwargs["json"] = request_cfg["json"]
    elif "data" in request_cfg:
        kwargs["data"] = request_cfg["data"]
    elif "body" in request_cfg:
        kwargs["data"] = request_cfg["body"]
    if isinstance(request_cfg.get("auth"), dict):
        auth = request_cfg["auth"]
        kwargs["auth"] = (str(auth.get("username", "")), str(auth.get("password", "")))
    if request_cfg.get("proxy"):
        kwargs["proxies"] = {"http": request_cfg["proxy"], "https": request_cfg["proxy"]}

    handles: list[Any] = []
    files = request_cfg.get("files")
    if files:
        if not isinstance(files, dict):
            result["error"] = '"files" debe ser un objeto {campo: ruta}'
            return result
        try:
            prepared = {}
            for field, filename in files.items():
                path = Path(str(filename)).expanduser()
                handle = path.open("rb")
                handles.append(handle)
                prepared[field] = (path.name, handle)
            kwargs["files"] = prepared
        except OSError as exc:
            for handle in handles:
                handle.close()
            result["error"] = f"No se pudo abrir un archivo: {exc}"
            return result

    started = time.perf_counter()
    try:
        with requests.Session() as session:
            response = session.request(**kwargs)
        result.update(
            status=response.status_code,
            size_bytes=len(response.content),
            elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
            content_type=response.headers.get("Content-Type", ""),
        )
        columns = global_columns + validate_columns(request_cfg.get("columns"))
        parsed_json = None
        if any(str(column.get("source", "")).lower() == "json" for column in columns):
            try:
                parsed_json = response.json()
            except requests.JSONDecodeError:
                pass
        for column in columns:
            result["custom"][str(column["name"])] = extract_column(
                column, response, request_cfg, parsed_json
            )
    except requests.RequestException as exc:
        result["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        for handle in handles:
            handle.close()
    return result


def truncate(value: Any, limit: int = 48) -> str:
    text = stringify(value).replace("\r", "\\r").replace("\n", "\\n")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def collect_column_names(
    global_columns: list[dict[str, Any]], requests_cfg: list[dict[str, Any]]
) -> list[str]:
    names: list[str] = []
    for column in global_columns:
        if str(column["name"]) not in names:
            names.append(str(column["name"]))
    for request_cfg in requests_cfg:
        for column in validate_columns(request_cfg.get("columns")):
            if str(column["name"]) not in names:
                names.append(str(column["name"]))
    return names


def build_rich_table(
    results: list[dict[str, Any]], custom_names: list[str], completed: int, total: int
) -> Table:
    table = Table(
        title=f"Resultados HTTP · {completed}/{total}",
        expand=True,
        header_style="bold cyan",
        border_style="bright_black",
    )
    columns = ["#", "name", "method", "status", "size_bytes", "elapsed_ms", "content_type"]
    for column in columns + custom_names + ["error"]:
        table.add_column(column, overflow="fold", no_wrap=column in {"#", "method", "status"})
    for item in sorted(results, key=lambda row: row["index"]):
        status = item["status"]
        style = "green" if isinstance(status, int) and 200 <= status < 300 else (
            "yellow" if isinstance(status, int) and 300 <= status < 400 else "red"
        )
        row = [
            str(item["index"]), truncate(item["name"]), truncate(item["method"]),
            f"[{style}]{status}[/{style}]", str(item["size_bytes"]),
            str(item["elapsed_ms"]), truncate(item["content_type"]),
        ]
        row.extend(truncate(item["custom"].get(name, "")) for name in custom_names)
        row.append(truncate(item["error"]))
        table.add_row(*row)
    return table


def render_table(results: list[dict[str, Any]], custom_names: list[str]) -> str:
    headers = [
        "#", "name", "method", "status", "size_bytes", "elapsed_ms",
        "content_type", *custom_names, "error",
    ]
    rows: list[list[str]] = []
    for item in results:
        row = [truncate(item.get(key, "")) for key in (
            "index", "name", "method", "status", "size_bytes", "elapsed_ms", "content_type"
        )]
        row.extend(truncate(item["custom"].get(name, "")) for name in custom_names)
        row.append(truncate(item["error"]))
        rows.append(row)
    widths = [min(48, max([len(headers[i]), *[len(row[i]) for row in rows]])) for i in range(len(headers))]
    format_row = lambda row: " | ".join(value.ljust(widths[i]) for i, value in enumerate(row))
    return "\n".join([format_row(headers), "-+-".join("-" * width for width in widths), *map(format_row, rows)])


def write_csv(path: Path, results: list[dict[str, Any]], custom_names: list[str]) -> None:
    fields = [
        "index", "name", "method", "status", "size_bytes", "elapsed_ms",
        "content_type", *custom_names, "error",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        for item in results:
            row = {key: item[key] for key in fields if key in item and key != "custom"}
            row.update({name: item["custom"].get(name, "") for name in custom_names})
            writer.writerow(row)


def iter_request_results(
    requests_cfg: list[dict[str, Any]],
    global_columns: list[dict[str, Any]] | None = None,
    workers: int = 1,
    delay_ms: int = 0,
    cancel_event: threading.Event | None = None,
) -> Iterator[tuple[int, int, dict[str, Any]]]:
    columns = validate_columns(global_columns or [])
    if not requests_cfg:
        raise ValueError("No hay solicitudes para ejecutar.")
    if not 1 <= workers <= MAX_WORKERS:
        raise ValueError(f"workers debe estar entre 1 y {MAX_WORKERS}.")
    if not 0 <= delay_ms <= 60_000:
        raise ValueError("delay_ms debe estar entre 0 y 60000.")

    total, completed, next_index = len(requests_cfg), 0, 0
    pending: dict[Future[dict[str, Any]], int] = {}
    cancelled = cancel_event or threading.Event()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        def submit_one() -> bool:
            nonlocal next_index
            if cancelled.is_set() or next_index >= total:
                return False
            if next_index and delay_ms:
                time.sleep(delay_ms / 1000)
            pending[executor.submit(execute_request, next_index, requests_cfg[next_index], columns)] = next_index
            next_index += 1
            return True

        while len(pending) < workers and submit_one():
            pass
        while pending:
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                original_index = pending.pop(future)
                try:
                    item = future.result()
                except Exception as exc:
                    item = {
                        "index": original_index + 1, "name": "worker-error", "method": "-",
                        "status": "-", "size_bytes": 0, "elapsed_ms": 0,
                        "content_type": "", "custom": {},
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                completed += 1
                yield completed, total, item
            if cancelled.is_set():
                for future in pending:
                    future.cancel()
                break
            while len(pending) < workers and submit_one():
                pass


def run_requests(
    requests_cfg: list[dict[str, Any]],
    global_columns: list[dict[str, Any]] | None = None,
    workers: int = 1,
    csv_path: Path | None = None,
    delay_ms: int = 0,
    live: bool = True,
    on_result: Callable[[int, int, dict[str, Any]], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> list[dict[str, Any]]:
    columns = validate_columns(global_columns or [])
    custom_names = collect_column_names(columns, requests_cfg)
    results: list[dict[str, Any]] = []
    iterator = iter_request_results(requests_cfg, columns, workers, delay_ms, cancel_event)
    total = len(requests_cfg)
    if live and sys.stdout.isatty():
        with Live(build_rich_table([], custom_names, 0, total), console=Console(), refresh_per_second=8) as view:
            for completed, _, item in iterator:
                results.append(item)
                if on_result:
                    on_result(completed, total, item)
                view.update(build_rich_table(results, custom_names, completed, total))
    else:
        for completed, _, item in iterator:
            results.append(item)
            if on_result:
                on_result(completed, total, item)
        results.sort(key=lambda item: item["index"])
        if live:
            print(render_table(results, custom_names))
    results.sort(key=lambda item: item["index"])
    if csv_path:
        write_csv(csv_path, results, custom_names)
    return results


def replace_placeholder(value: Any, replacement: str) -> Any:
    if isinstance(value, dict):
        return {replace_placeholder(key, replacement): replace_placeholder(item, replacement) for key, item in value.items()}
    if isinstance(value, list):
        return [replace_placeholder(item, replacement) for item in value]
    if isinstance(value, tuple):
        return tuple(replace_placeholder(item, replacement) for item in value)
    return value.replace(PLACEHOLDER, replacement) if isinstance(value, str) else value


def contains_placeholder(value: Any) -> bool:
    if isinstance(value, dict):
        return any(contains_placeholder(key) or contains_placeholder(item) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return any(map(contains_placeholder, value))
    return isinstance(value, str) and PLACEHOLDER in value


def load_values(path: Path | None = None, inline: Iterable[str] | None = None) -> list[str]:
    raw: list[str] = []
    if path is not None:
        try:
            text = sys.stdin.read() if str(path) == "-" else path.expanduser().read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"No se pudo leer la lista {path}: {exc}") from exc
        raw.extend(text.splitlines())
    raw.extend(inline or [])
    values = list(dict.fromkeys(str(item).strip() for item in raw if str(item).strip() and not str(item).strip().startswith("#")))
    if not values:
        raise ValueError("No se encontraron valores de prueba.")
    if len(values) > MAX_VALUES:
        raise ValueError(f"La lista supera el máximo de {MAX_VALUES} valores.")
    return values


def build_intruder_requests(
    base_request: dict[str, Any],
    values: Iterable[str],
    *,
    value_column: str = "valor_probado",
) -> list[dict[str, Any]]:
    clean_values = [str(value) for value in values]
    if not clean_values:
        raise ValueError("No hay valores para insertar.")
    if not contains_placeholder(base_request):
        raise ValueError(
            f"La solicitud base no contiene {PLACEHOLDER} en URL, headers, parámetros, cookies o body."
        )
    requests_cfg: list[dict[str, Any]] = []
    for index, value in enumerate(clean_values, 1):
        cfg = replace_placeholder(base_request, value)
        cfg["name"] = str(value if cfg.get("name") in (None, "", "request-1") else cfg["name"])
        columns = validate_columns(cfg.get("columns"))
        columns.append({"name": value_column, "source": "literal", "value": value})
        cfg["columns"] = columns
        requests_cfg.append(cfg)
    return requests_cfg
