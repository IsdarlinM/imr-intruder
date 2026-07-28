from __future__ import annotations

import csv
import io
import json
import queue
import secrets
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import __version__
from .collaboration import verify_token
from .core import parse_columns, run_requests
from .payloads import build_requests, placeholders

BASE_DIR = Path(__file__).resolve().parent
MAX_VALUES = 2000
MAX_WORKERS = 16
MAX_ACTIVE_JOBS = 4
JOB_TTL = 3600


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


def _payloads(raw: str) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    current = "VALUE"
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            current = stripped[1:-1].strip()
            groups.setdefault(current, [])
        else:
            groups.setdefault(current, []).append(stripped)
    return groups


def build_web_requests(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]], dict[str, Any]]:
    url = str(payload.get("url", "")).strip()
    if not url.startswith(("http://", "https://")):
        raise ValueError("URL must begin with http:// or https://.")
    method = str(payload.get("method", "GET")).upper()
    base: dict[str, Any] = {
        "name": "request-1",
        "method": method,
        "url": url,
        "headers": _parse_map(str(payload.get("headers", "")), True),
        "params": _parse_map(str(payload.get("params", ""))),
        "cookies": _parse_map(str(payload.get("cookies", ""))),
        "timeout": float(payload.get("timeout", 15)),
        "verify_tls": bool(payload.get("verify_tls", True)),
        "follow_redirects": bool(payload.get("follow_redirects", False)),
        "http2": bool(payload.get("http2", False)),
    }
    body_type = str(payload.get("body_type", "none"))
    body = str(payload.get("body", ""))
    if body_type == "json":
        base["json"] = json.loads(body or "{}")
    elif body_type == "form":
        base["data"] = _parse_map(body)
    elif body_type == "raw":
        base["body"] = body
    elif body_type != "none":
        raise ValueError("Invalid body type.")

    payload_groups = _payloads(str(payload.get("payloads", "")))
    if any(payload_groups.values()):
        count = sum(len(values) for values in payload_groups.values())
        if count > MAX_VALUES:
            raise ValueError(f"Maximum payload values: {MAX_VALUES}.")
        if not placeholders(base):
            raise ValueError("Add a placeholder such as {{VALUE}} to the request.")
        requests = build_requests(base, payload_groups, str(payload.get("mode", "sniper")), int(payload.get("max_requests", MAX_VALUES)))
    else:
        requests = [base]

    columns = parse_columns([line.strip() for line in str(payload.get("columns", "")).splitlines() if line.strip()])
    options = {
        "workers": min(MAX_WORKERS, max(1, int(payload.get("workers", 1)))),
        "delay_ms": max(0, int(payload.get("delay_ms", 0))),
        "retries": max(0, min(5, int(payload.get("retries", 0)))),
        "backoff": bool(payload.get("backoff", False)),
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

    def get_job(job_id: str) -> Job:
        with app.state.lock:
            job = app.state.jobs.get(job_id)
        if not job:
            raise HTTPException(404, "Job not found.")
        return job

    def emit(job: Job, event: str, **payload: Any) -> None:
        job.events.put({"event": event, **payload})

    def run_job(job: Job) -> None:
        job.status = "running"
        emit(job, "meta", total=len(job.requests))

        def callback(completed: int, total: int, result: dict[str, Any]) -> None:
            while job.pause.is_set() and not job.cancel.is_set():
                time.sleep(0.1)
            job.results.append(result)
            emit(job, "result", completed=completed, total=total, result=result)

        try:
            run_requests(job.requests, columns=job.columns, cancel_event=job.cancel, pause_event=job.pause, callback=callback, **job.options)
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
            page_token = (
                request.query_params.get("token")
                or request.cookies.get("imr_intruder_token", "")
                or request.headers.get("X-Request-Token", "")
            )
        response = templates.TemplateResponse(request, "index.html", {"version": __version__, "token": page_token})
        response.set_cookie("imr_intruder_token", page_token, httponly=True, samesite="strict", max_age=JOB_TTL)
        return response

    @app.get("/health")
    def health():
        return {"status": "ok", "version": __version__}

    @app.post("/api/jobs")
    async def create_job(request: Request):
        authorize(request, "operator")
        payload = await request.json()
        try:
            requests, columns, options = build_web_requests(payload)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise HTTPException(400, str(exc)) from exc
        with app.state.lock:
            active = sum(job.status in {"queued", "running", "paused"} for job in app.state.jobs.values())
            if active >= MAX_ACTIVE_JOBS:
                raise HTTPException(429, "Too many active jobs.")
            job = Job(uuid.uuid4().hex, requests, columns, options)
            app.state.jobs[job.id] = job
        threading.Thread(target=run_job, args=(job,), daemon=True).start()
        return JSONResponse({"job_id": job.id, "total": len(requests)}, status_code=202)

    @app.get("/api/jobs/{job_id}/events")
    def events(job_id: str, request: Request):
        authorize(request, "viewer")
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

    @app.post("/api/jobs/{job_id}/pause")
    def pause(job_id: str, request: Request):
        authorize(request, "operator")
        job = get_job(job_id); job.pause.set(); job.status = "paused"
        return {"status": "paused"}

    @app.post("/api/jobs/{job_id}/resume")
    def resume(job_id: str, request: Request):
        authorize(request, "operator")
        job = get_job(job_id); job.pause.clear(); job.status = "running"
        return {"status": "running"}

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel(job_id: str, request: Request):
        authorize(request, "operator")
        job = get_job(job_id); job.cancel.set(); job.pause.clear()
        return {"status": "cancelling"}

    @app.get("/api/jobs/{job_id}/csv")
    def csv_export(job_id: str, request: Request):
        authorize(request, "viewer")
        job = get_job(job_id)
        buffer = io.StringIO()
        fields = ["index", "name", "status", "size_bytes", "elapsed_ms", "similarity", "cluster", "anomaly_score", "location", "error"]
        writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore"); writer.writeheader(); writer.writerows(job.results)
        return Response(buffer.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{job_id}.csv"'})

    return app
