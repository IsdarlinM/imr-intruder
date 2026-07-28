from __future__ import annotations

import csv
import io
import ipaddress
import json
import queue
import secrets
import threading
import time
import uuid
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import __version__
from .core import (
    PLACEHOLDER,
    build_intruder_requests,
    collect_column_names,
    contains_placeholder,
    iter_request_results,
    parse_column_specs,
)

MAX_VALUES = 500
MAX_WEB_WORKERS = 10
MAX_ACTIVE_JOBS = 4
JOB_TTL_SECONDS = 3600
BASE_DIR = Path(__file__).resolve().parent


@dataclass
class Job:
    id: str
    requests_cfg: list[dict[str, Any]]
    columns: list[dict[str, Any]]
    workers: int
    delay_ms: int
    events: queue.Queue[dict[str, Any]] = field(default_factory=queue.Queue)
    cancel_event: threading.Event = field(default_factory=threading.Event)
    results: list[dict[str, Any]] = field(default_factory=list)
    status: str = "queued"
    created_at: float = field(default_factory=time.time)


def parse_lines_map(raw: str, label: str, header_mode: bool = False) -> dict[str, str]:
    result: dict[str, str] = {}
    for line_number, raw_line in enumerate(raw.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if header_mode and ":" in line:
            key, value = line.split(":", 1)
        elif "=" in line:
            key, value = line.split("=", 1)
        else:
            separator = "Nombre: valor" if header_mode else "clave=valor"
            raise ValueError(f"{label}, línea {line_number}: usa {separator}.")

        key = key.strip()
        if not key:
            raise ValueError(f"{label}, línea {line_number}: clave vacía.")
        result[key] = value.strip()
    return result


def build_requests(payload: dict[str, Any]) -> tuple[
    list[dict[str, Any]], list[dict[str, Any]], int, int
]:
    url = str(payload.get("url", "")).strip()
    if not url.startswith(("http://", "https://")):
        raise ValueError("La URL debe comenzar con http:// o https://.")

    method = str(payload.get("method", "GET")).upper().strip()
    if not method.isalpha() or len(method) > 12:
        raise ValueError("Método HTTP inválido.")

    try:
        timeout = float(payload.get("timeout", 15))
        workers = int(payload.get("workers", 1))
        delay_ms = int(payload.get("delay_ms", 0))
    except (TypeError, ValueError) as exc:
        raise ValueError("Timeout, workers y delay deben ser numéricos.") from exc

    if not 0.1 <= timeout <= 300:
        raise ValueError("El timeout debe estar entre 0.1 y 300 segundos.")
    if not 1 <= workers <= MAX_WEB_WORKERS:
        raise ValueError(f"La concurrencia debe estar entre 1 y {MAX_WEB_WORKERS}.")
    if not 0 <= delay_ms <= 60_000:
        raise ValueError("El retraso debe estar entre 0 y 60000 ms.")

    headers = parse_lines_map(str(payload.get("headers", "")), "Headers", True)
    headers.setdefault("User-Agent", f"imr-intruder/{__version__}")
    params = parse_lines_map(str(payload.get("params", "")), "Parámetros")
    cookies = parse_lines_map(str(payload.get("cookies", "")), "Cookies")

    base_request: dict[str, Any] = {
        "name": "request-1",
        "method": method,
        "url": url,
        "headers": headers,
        "params": params,
        "cookies": cookies,
        "timeout": timeout,
        "verify_tls": bool(payload.get("verify_tls", True)),
        "follow_redirects": bool(payload.get("follow_redirects", False)),
    }

    body_type = str(payload.get("body_type", "none"))
    body_raw = str(payload.get("body", ""))
    if body_type == "form":
        base_request["data"] = parse_lines_map(body_raw, "Datos de formulario")
    elif body_type == "json":
        try:
            base_request["json"] = json.loads(body_raw or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"JSON inválido: línea {exc.lineno}, columna {exc.colno}: {exc.msg}"
            ) from exc
    elif body_type == "raw":
        base_request["body"] = body_raw
    elif body_type != "none":
        raise ValueError("Tipo de body inválido.")

    value_lines = [
        line.strip()
        for line in str(payload.get("values", "")).splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    values = list(dict.fromkeys(value_lines))
    if len(values) > MAX_VALUES:
        raise ValueError(f"La lista admite como máximo {MAX_VALUES} valores.")

    column_lines = [
        line.strip()
        for line in str(payload.get("columns", "")).splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    columns = parse_column_specs(column_lines)

    if values:
        if not contains_placeholder(base_request):
            raise ValueError(
                f"Agrega {PLACEHOLDER} en URL, headers, parámetros, cookies o body."
            )
        requests_cfg = build_intruder_requests(base_request, values)
    else:
        requests_cfg = [base_request]

    return requests_cfg, columns, workers, delay_ms


def create_app(
    *,
    request_token: str | None = None,
    require_page_token: bool = False,
) -> FastAPI:
    token = request_token or secrets.token_urlsafe(32)
    app = FastAPI(
        title="imr-intruder",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.request_token = token
    app.state.require_page_token = require_page_token
    app.state.jobs = {}
    app.state.jobs_lock = threading.Lock()

    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
    templates = Jinja2Templates(directory=BASE_DIR / "templates")

    def require_api_token(request: Request) -> None:
        supplied = request.headers.get("X-Request-Token", "")
        if not secrets.compare_digest(supplied, app.state.request_token):
            raise HTTPException(status_code=403, detail="Token de sesión inválido.")

    def get_job(job_id: str) -> Job:
        with app.state.jobs_lock:
            job = app.state.jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Trabajo no encontrado.")
        return job

    def emit(job: Job, event: str, **payload: Any) -> None:
        job.events.put({"event": event, **payload})

    def run_job(job: Job) -> None:
        job.status = "running"
        custom_names = collect_column_names(job.columns, job.requests_cfg)
        emit(job, "meta", total=len(job.requests_cfg), columns=custom_names)
        try:
            for completed, total, item in iter_request_results(
                requests_cfg=job.requests_cfg,
                global_columns=job.columns,
                workers=job.workers,
                delay_ms=job.delay_ms,
                cancel_event=job.cancel_event,
            ):
                job.results.append(item)
                emit(job, "result", completed=completed, total=total, result=item)
            job.results.sort(key=lambda row: row["index"])
            job.status = "cancelled" if job.cancel_event.is_set() else "done"
            emit(
                job,
                "done",
                status=job.status,
                completed=len(job.results),
                total=len(job.requests_cfg),
            )
        except Exception as exc:
            job.status = "error"
            emit(job, "fatal", error=f"{type(exc).__name__}: {exc}")

    def cleanup_jobs() -> None:
        cutoff = time.time() - JOB_TTL_SECONDS
        with app.state.jobs_lock:
            expired = [
                job_id
                for job_id, job in app.state.jobs.items()
                if job.created_at < cutoff
            ]
            for job_id in expired:
                app.state.jobs.pop(job_id, None)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
            "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        )
        return response

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        if app.state.require_page_token:
            query_token = request.query_params.get("token", "")
            cookie_token = request.cookies.get("imr_intruder_token", "")
            supplied = query_token or cookie_token
            if not secrets.compare_digest(supplied, app.state.request_token):
                raise HTTPException(status_code=403, detail="Token de acceso requerido.")

        response = templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "version": __version__,
                "request_token": app.state.request_token,
                "max_values": MAX_VALUES,
                "max_workers": MAX_WEB_WORKERS,
                "remote_mode": app.state.require_page_token,
            },
        )
        if app.state.require_page_token:
            response.set_cookie(
                "imr_intruder_token",
                app.state.request_token,
                httponly=True,
                samesite="strict",
                secure=False,
                max_age=JOB_TTL_SECONDS,
            )
        return response

    @app.head("/")
    def index_head(request: Request) -> Response:
        if app.state.require_page_token:
            query_token = request.query_params.get("token", "")
            cookie_token = request.cookies.get("imr_intruder_token", "")
            if not secrets.compare_digest(query_token or cookie_token, app.state.request_token):
                raise HTTPException(status_code=403, detail="Token de acceso requerido.")
        return Response(status_code=200)

    @app.get("/health")
    def health() -> JSONResponse:
        return JSONResponse({"status": "ok", "version": __version__})

    @app.post("/api/jobs")
    async def create_job(request: Request) -> JSONResponse:
        require_api_token(request)
        cleanup_jobs()
        try:
            payload = await request.json()
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="Se esperaba JSON válido.") from exc
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="Se esperaba un objeto JSON.")

        try:
            requests_cfg, columns, workers, delay_ms = build_requests(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        with app.state.jobs_lock:
            active = sum(
                1 for job in app.state.jobs.values()
                if job.status in {"queued", "running"}
            )
            if active >= MAX_ACTIVE_JOBS:
                raise HTTPException(
                    status_code=429,
                    detail=f"Máximo de {MAX_ACTIVE_JOBS} ejecuciones activas.",
                )
            job_id = uuid.uuid4().hex
            job = Job(
                id=job_id,
                requests_cfg=requests_cfg,
                columns=columns,
                workers=workers,
                delay_ms=delay_ms,
            )
            app.state.jobs[job_id] = job

        threading.Thread(target=run_job, args=(job,), daemon=True).start()
        return JSONResponse(
            status_code=202,
            content={"job_id": job_id, "total": len(requests_cfg)},
        )

    @app.get("/api/jobs/{job_id}/events")
    def job_events(job_id: str, request: Request) -> StreamingResponse:
        require_api_token(request)
        job = get_job(job_id)

        def generate() -> Iterator[str]:
            while True:
                try:
                    event = job.events.get(timeout=15)
                except queue.Empty:
                    yield json.dumps({"event": "heartbeat"}) + "\n"
                    if job.status in {"done", "cancelled", "error"}:
                        break
                    continue
                yield json.dumps(event, ensure_ascii=False) + "\n"
                if event["event"] in {"done", "fatal"}:
                    break

        return StreamingResponse(generate(), media_type="application/x-ndjson")

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job(job_id: str, request: Request) -> JSONResponse:
        require_api_token(request)
        job = get_job(job_id)
        job.cancel_event.set()
        return JSONResponse({"status": "cancelling"})

    @app.get("/api/jobs/{job_id}/csv")
    def export_job_csv(job_id: str, request: Request) -> Response:
        require_api_token(request)
        job = get_job(job_id)
        custom_names = collect_column_names(job.columns, job.requests_cfg)
        fieldnames = [
            "index", "name", "method", "status", "size_bytes",
            "elapsed_ms", "content_type", *custom_names, "error",
        ]
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for item in sorted(job.results, key=lambda row: row["index"]):
            row = {
                "index": item["index"],
                "name": item["name"],
                "method": item["method"],
                "status": item["status"],
                "size_bytes": item["size_bytes"],
                "elapsed_ms": item["elapsed_ms"],
                "content_type": item["content_type"],
                "error": item["error"],
            }
            row.update({name: item["custom"].get(name, "") for name in custom_names})
            writer.writerow(row)
        return Response(
            content=output.getvalue().encode("utf-8-sig"),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="imr-intruder-{job_id[:8]}.csv"'
            },
        )

    return app


def _is_loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def run_server(
    *,
    host: str = "127.0.0.1",
    port: int = 7415,
    open_browser: bool = True,
    allow_remote: bool = False,
    token: str | None = None,
) -> None:
    if not 1 <= port <= 65535:
        raise ValueError("El puerto debe estar entre 1 y 65535.")
    loopback = _is_loopback(host)
    if not loopback and not allow_remote:
        raise ValueError(
            "El host no es local. Agrega --allow-remote conscientemente o usa 127.0.0.1."
        )

    request_token = token or secrets.token_urlsafe(32)
    app = create_app(
        request_token=request_token,
        require_page_token=not loopback,
    )
    display_host = "127.0.0.1" if host == "0.0.0.0" else host
    url = f"http://{display_host}:{port}"
    access_url = f"{url}/?token={request_token}" if not loopback else url

    print(f"Web UI: {access_url}", flush=True)
    print(f"Session token: {request_token}", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    if not loopback:
        print("WARNING: remote mode enabled. Use a trusted network or reverse proxy with TLS.", flush=True)

    if open_browser and loopback:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()

    uvicorn.run(app, host=host, port=port, log_level="info", access_log=True)


app = create_app()


if __name__ == "__main__":
    run_server()
