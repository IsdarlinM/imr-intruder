from __future__ import annotations

import csv
import io
import json
import queue
import re
import secrets
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import parse_qsl

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import __version__
from .collaboration import verify_token
from .core import parse_columns, run_requests
from .payloads import build_requests, placeholders

BASE_DIR = Path(__file__).resolve().parent
MAX_VALUES = 2000
MAX_REQUESTS = 10000
MAX_WORKERS = 16
MAX_ACTIVE_JOBS = 4
JOB_TTL = 3600
ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
_PAYLOAD_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass
class Job:
    id: str
    requests: list[dict[str, Any]]
    columns: list[dict[str, str]]
    options: dict[str, Any]
    events: queue.Queue[dict[str, Any]] = field(default_factory=queue.Queue)
    cancel: threading.Event = field(default_factory=threading.Event)
    pause: threading.Event = field(default_factory=threading.Event)
    results: list[dict[str, Any]] = field(default_factory=list)
    status: str = "queued"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


def _parse_map(raw: str, header: bool = False) -> dict[str, str]:
    result: dict[str, str] = {}
    for line_number, raw_line in enumerate(raw.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if header and ":" in line and ("=" not in line or line.index(":") < line.index("=")):
            key, value = line.split(":", 1)
        elif "=" in line:
            key, value = line.split("=", 1)
        else:
            raise ValueError(f"Line {line_number}: expected {'Name: value' if header else 'key=value'}.")
        if not key.strip():
            raise ValueError(f"Line {line_number}: empty key.")
        result[key.strip()] = value.strip()
    return result


def _parse_urlencoded(raw: str) -> dict[str, str]:
    """Accept both one-pair-per-line and conventional a=1&b=2 input."""
    result: dict[str, str] = {}
    for line_number, raw_line in enumerate(raw.splitlines() or [raw], start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "&" in line:
            pairs = parse_qsl(line, keep_blank_values=True, strict_parsing=False)
            if not pairs:
                raise ValueError(f"Line {line_number}: invalid URL-encoded form data.")
            result.update((str(key), str(value)) for key, value in pairs)
        else:
            result.update(_parse_map(line))
    return result


def _parse_cookies(raw: str) -> dict[str, str]:
    if ";" in raw and "\n" not in raw:
        return _parse_map("\n".join(part.strip() for part in raw.split(";") if part.strip()))
    return _parse_map(raw)


def _payloads(raw: str) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    current = "VALUE"
    for line_number, line in enumerate(raw.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            current = stripped[1:-1].strip()
            if not _PAYLOAD_NAME.fullmatch(current):
                raise ValueError(f"Line {line_number}: invalid payload section name {current!r}.")
            groups.setdefault(current, [])
        else:
            groups.setdefault(current, []).append(stripped)
    return groups


def _as_int(payload: dict[str, Any], name: str, default: int, minimum: int, maximum: int) -> int:
    value = payload.get(name, default)
    if value is None or isinstance(value, bool):
        raise ValueError(f"{name} must be an integer between {minimum} and {maximum}.")
    try:
        converted = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer between {minimum} and {maximum}.") from exc
    if not minimum <= converted <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")
    return converted


def _as_float(payload: dict[str, Any], name: str, default: float, minimum: float, maximum: float) -> float:
    value = payload.get(name, default)
    if value is None or isinstance(value, bool):
        raise ValueError(f"{name} must be a number between {minimum} and {maximum}.")
    try:
        converted = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number between {minimum} and {maximum}.") from exc
    if not minimum <= converted <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")
    return converted


def _as_bool(payload: dict[str, Any], name: str, default: bool) -> bool:
    value = payload.get(name, default)
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    raise ValueError(f"{name} must be true or false.")


def build_web_requests(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]], dict[str, Any]]:
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object.")

    url = str(payload.get("url", "")).strip()
    if not url.startswith(("http://", "https://")):
        raise ValueError("URL must begin with http:// or https://.")
    method = str(payload.get("method", "GET")).upper().strip()
    if method not in ALLOWED_METHODS:
        raise ValueError(f"Unsupported HTTP method: {method}.")

    base: dict[str, Any] = {
        "method": method,
        "url": url,
        "headers": _parse_map(str(payload.get("headers", "")), True),
        "params": _parse_urlencoded(str(payload.get("params", ""))),
        "cookies": _parse_cookies(str(payload.get("cookies", ""))),
        "timeout": _as_float(payload, "timeout", 15.0, 0.1, 300.0),
        "verify_tls": _as_bool(payload, "verify_tls", True),
        "follow_redirects": _as_bool(payload, "follow_redirects", False),
        "http2": _as_bool(payload, "http2", False),
    }
    name = str(payload.get("name", "")).strip()
    if name:
        base["name"] = name

    body_type = str(payload.get("body_type", "none")).lower().strip()
    body = str(payload.get("body", ""))
    if body_type == "json":
        try:
            base["json"] = json.loads(body or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON body at line {exc.lineno}, column {exc.colno}: {exc.msg}.") from exc
    elif body_type == "form":
        base["data"] = _parse_urlencoded(body)
    elif body_type == "raw":
        base["body"] = body
    elif body_type == "none":
        if body.strip():
            raise ValueError("A request body was entered, but Body type is None. Select JSON, Form URL encoded, or Raw.")
    else:
        raise ValueError("Invalid body type.")

    payload_groups = _payloads(str(payload.get("payloads", "")))
    nonempty_groups = {key: values for key, values in payload_groups.items() if values}
    if nonempty_groups:
        count = sum(len(values) for values in nonempty_groups.values())
        if count > MAX_VALUES:
            raise ValueError(f"Maximum payload values: {MAX_VALUES}.")
        request_placeholders = placeholders(base)
        if not request_placeholders:
            raise ValueError("Payload values were provided, but the request has no placeholder. Add {{VALUE}} or a named placeholder such as {{USER}}.")
        missing = request_placeholders - set(nonempty_groups)
        if missing:
            raise ValueError(f"Missing payload section(s): {', '.join(sorted(missing))}.")
        mode = str(payload.get("mode", "sniper"))
        max_requests = _as_int(payload, "max_requests", MAX_VALUES, 1, MAX_REQUESTS)
        requests = build_requests(base, nonempty_groups, mode, max_requests)
    else:
        requests = [base]

    columns = parse_columns([line.strip() for line in str(payload.get("columns", "")).splitlines() if line.strip()])
    options = {
        "workers": _as_int(payload, "workers", 1, 1, MAX_WORKERS),
        "delay_ms": _as_int(payload, "delay_ms", 0, 0, 3_600_000),
        "retries": _as_int(payload, "retries", 0, 0, 5),
        "backoff": _as_bool(payload, "backoff", False),
        "match_rules": [line.strip() for line in str(payload.get("match", "")).splitlines() if line.strip()],
        "exclude_rules": [line.strip() for line in str(payload.get("exclude", "")).splitlines() if line.strip()],
        "extract_rules": _parse_map(str(payload.get("extract", ""))),
    }
    return requests, columns, options


def create_app(request_token: str | None = None, require_page_token: bool = False, multiuser: bool = False) -> FastAPI:
    token = request_token or secrets.token_urlsafe(32)
    app = FastAPI(title="imr-intruder", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.token = token
    app.state.require_page_token = require_page_token
    app.state.multiuser = multiuser
    app.state.jobs: dict[str, Job] = {}
    app.state.lock = threading.Lock()
    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
    templates = Jinja2Templates(directory=BASE_DIR / "templates")

    def authorize(request: Request, required: str = "operator") -> tuple[str, str]:
        supplied = request.headers.get("X-Request-Token") or request.query_params.get("token") or request.cookies.get("imr_intruder_token", "")
        if not supplied:
            raise HTTPException(403, "Access token required.")
        if secrets.compare_digest(supplied, app.state.token):
            return "local", "admin"
        if app.state.multiuser:
            identity = verify_token(supplied)
            if identity:
                name, role = identity
                order = {"viewer": 0, "operator": 1, "admin": 2}
                if order[role] >= order[required]:
                    return name, role
        raise HTTPException(403, "Invalid or insufficient token.")

    def cleanup_jobs() -> None:
        cutoff = time.time() - JOB_TTL
        with app.state.lock:
            expired = [job_id for job_id, job in app.state.jobs.items() if job.updated_at < cutoff and job.status in {"done", "cancelled", "error"}]
            for job_id in expired:
                del app.state.jobs[job_id]

    def get_job(job_id: str) -> Job:
        cleanup_jobs()
        with app.state.lock:
            job = app.state.jobs.get(job_id)
        if not job:
            raise HTTPException(404, "Job not found.")
        return job

    def emit(job: Job, event: str, **payload: Any) -> None:
        job.updated_at = time.time()
        job.events.put({"event": event, **payload})

    def run_job(job: Job) -> None:
        job.status = "running"
        emit(job, "meta", total=len(job.requests))

        def callback(completed: int, total: int, result: dict[str, Any]) -> None:
            while job.pause.is_set() and not job.cancel.is_set():
                time.sleep(0.05)
            job.results.append(result)
            emit(job, "result", completed=completed, total=total, result=result)

        try:
            final_results = run_requests(
                job.requests,
                columns=job.columns,
                cancel_event=job.cancel,
                pause_event=job.pause,
                callback=callback,
                **job.options,
            )
            job.results = final_results
            emit(job, "snapshot", total=len(job.requests), results=job.results)
            job.status = "cancelled" if job.cancel.is_set() else "done"
            emit(job, "done", status=job.status, completed=len(job.results), total=len(job.requests))
        except Exception as exc:
            job.status = "error"
            emit(job, "fatal", error=f"{type(exc).__name__}: {exc}")

    @app.middleware("http")
    async def hardening(request: Request, call_next):
        response = await call_next(request)
        response.headers.update({
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "Cache-Control": "no-store",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
            "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
        })
        return response

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        page_token = app.state.token
        if app.state.require_page_token:
            authorize(request, "viewer")
            page_token = request.query_params.get("token") or request.cookies.get("imr_intruder_token", "") or request.headers.get("X-Request-Token", "")
        response = templates.TemplateResponse(request, "index.html", {"version": __version__, "token": page_token})
        response.set_cookie("imr_intruder_token", page_token, httponly=True, secure=False, samesite="strict", max_age=JOB_TTL)
        return response

    @app.get("/health")
    def health():
        return {"status": "ok", "version": __version__}

    @app.post("/api/jobs")
    async def create_job(request: Request):
        authorize(request, "operator")
        try:
            payload = await request.json()
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise HTTPException(400, "Request body must contain valid JSON.") from exc
        try:
            requests, columns, options = build_web_requests(payload)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise HTTPException(400, str(exc)) from exc
        cleanup_jobs()
        with app.state.lock:
            active = sum(job.status in {"queued", "running", "paused", "cancelling"} for job in app.state.jobs.values())
            if active >= MAX_ACTIVE_JOBS:
                raise HTTPException(429, "Too many active jobs.")
            job = Job(uuid.uuid4().hex, requests, columns, options)
            app.state.jobs[job.id] = job
        threading.Thread(target=run_job, args=(job,), daemon=True).start()
        return JSONResponse({"job_id": job.id, "total": len(requests)}, status_code=202)

    @app.get("/api/jobs/{job_id}")
    def job_status(job_id: str, request: Request):
        authorize(request, "viewer")
        job = get_job(job_id)
        return {"job_id": job.id, "status": job.status, "total": len(job.requests), "completed": len(job.results), "results": job.results if job.status in {"done", "cancelled", "error"} else []}

    @app.get("/api/jobs/{job_id}/events")
    def events(job_id: str, request: Request):
        authorize(request, "viewer")
        job = get_job(job_id)

        def generate() -> Iterator[str]:
            if job.status in {"done", "cancelled", "error"} and job.events.empty():
                yield json.dumps({"event": "snapshot", "total": len(job.requests), "results": job.results}, ensure_ascii=False) + "\n"
                yield json.dumps({"event": "done", "status": job.status, "completed": len(job.results), "total": len(job.requests)}) + "\n"
                return
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

    @app.post("/api/jobs/{job_id}/pause")
    def pause(job_id: str, request: Request):
        authorize(request, "operator")
        job = get_job(job_id)
        if job.status not in {"queued", "running"}:
            raise HTTPException(409, f"Cannot pause a job in state {job.status}.")
        job.pause.set()
        job.status = "paused"
        job.updated_at = time.time()
        return {"status": "paused"}

    @app.post("/api/jobs/{job_id}/resume")
    def resume(job_id: str, request: Request):
        authorize(request, "operator")
        job = get_job(job_id)
        if job.status != "paused":
            raise HTTPException(409, f"Cannot resume a job in state {job.status}.")
        job.pause.clear()
        job.status = "running"
        job.updated_at = time.time()
        return {"status": "running"}

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel(job_id: str, request: Request):
        authorize(request, "operator")
        job = get_job(job_id)
        if job.status not in {"queued", "running", "paused"}:
            raise HTTPException(409, f"Cannot cancel a job in state {job.status}.")
        job.cancel.set()
        job.pause.clear()
        job.status = "cancelling"
        job.updated_at = time.time()
        return {"status": "cancelling"}

    @app.get("/api/jobs/{job_id}/csv")
    def csv_export(job_id: str, request: Request):
        authorize(request, "viewer")
        job = get_job(job_id)
        buffer = io.StringIO()
        fields = ["index", "name", "method", "url", "status", "size_bytes", "elapsed_ms", "similarity", "cluster", "anomaly_score", "location", "outcome", "error_type", "error"]
        writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(job.results)
        return Response(buffer.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{job_id}.csv"'})

    return app
