from __future__ import annotations

import fnmatch
import ipaddress
import json
import math
import re
import secrets
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import parse_qsl, urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import __version__
from .collaboration import verify_token
from .core import (
    parse_columns,
    redact_url,
    results_to_csv,
    run_requests,
    validate_http_method,
    validate_http_url,
)
from .importers import parse_curl, parse_har, parse_raw_request
from .intelligence import validate_rule
from .payloads import build_requests, placeholders
from .report import build_html_report
from .storage import (
    active_storage_directory,
    atomic_json_write,
    clear_current_workspace,
    create_workspace,
    current_workspace,
    list_sessions,
    list_workspaces,
    load_session,
    read_json,
    safe_name,
    save_history_record,
    set_current_workspace,
)

BASE_DIR = Path(__file__).resolve().parent
MAX_VALUES = 2000
MAX_REQUESTS = 10000
MAX_WORKERS = 16
MAX_ACTIVE_JOBS = 4
JOB_TTL = 3600
MAX_JOB_BODY_BYTES = 1024 * 1024
DEFAULT_BODY_LIMIT = 64 * 1024
MAX_RESULT_MEMORY = 64 * 1024 * 1024
_PAYLOAD_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass
class Job:
    id: str
    requests: list[dict[str, Any]]
    columns: list[dict[str, str]]
    options: dict[str, Any]
    owner: str = "local"
    owner_role: str = "admin"
    events: list[dict[str, Any]] = field(default_factory=list)
    event_condition: threading.Condition = field(default_factory=threading.Condition)
    cancel: threading.Event = field(default_factory=threading.Event)
    pause: threading.Event = field(default_factory=threading.Event)
    results: list[dict[str, Any]] = field(default_factory=list)
    status: str = "queued"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    next_sequence: int = 0


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
            raise ValueError(
                f"Line {line_number}: expected {'Name: value' if header else 'key=value'}."
            )
        if not key.strip():
            raise ValueError(f"Line {line_number}: empty key.")
        result[key.strip()] = value.strip()
    return result


def _store_multivalue(result: dict[str, Any], key: str, value: str) -> None:
    existing = result.get(key)
    if existing is None:
        result[key] = value
    elif isinstance(existing, list):
        existing.append(value)
    else:
        result[key] = [existing, value]


def _parse_urlencoded(raw: str) -> dict[str, Any]:
    """Accept both one-pair-per-line and conventional a=1&b=2 input."""
    result: dict[str, Any] = {}
    for line_number, raw_line in enumerate(raw.splitlines() or [raw], start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "&" in line:
            pairs = parse_qsl(line, keep_blank_values=True, strict_parsing=False)
            if not pairs:
                raise ValueError(f"Line {line_number}: invalid URL-encoded form data.")
            for key, value in pairs:
                _store_multivalue(result, str(key), str(value))
        else:
            for key, value in _parse_map(line).items():
                _store_multivalue(result, key, value)
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
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer between {minimum} and {maximum}.") from exc
    if not math.isfinite(numeric) or not numeric.is_integer():
        raise ValueError(f"{name} must be an integer between {minimum} and {maximum}.")
    converted = int(numeric)
    if not minimum <= converted <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")
    return converted


def _as_float(
    payload: dict[str, Any], name: str, default: float, minimum: float, maximum: float
) -> float:
    value = payload.get(name, default)
    if value is None or isinstance(value, bool):
        raise ValueError(f"{name} must be a number between {minimum} and {maximum}.")
    try:
        converted = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number between {minimum} and {maximum}.") from exc
    if not math.isfinite(converted):
        raise ValueError(f"{name} must be a finite number.")
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


def build_web_requests(
    payload: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, str]], dict[str, Any]]:
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object.")

    url = validate_http_url(payload.get("url", ""))
    method = validate_http_method(payload.get("method", "GET"))

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

    proxy = str(payload.get("proxy", "")).strip()
    if proxy:
        base["proxy"] = proxy
    auth_type = str(payload.get("auth_type", "none")).lower().strip()
    if auth_type == "basic":
        base["auth"] = {
            "username": str(payload.get("auth_username", "")),
            "password": str(payload.get("auth_password", "")),
        }
    elif auth_type == "bearer":
        bearer = str(payload.get("bearer_token", ""))
        if not bearer:
            raise ValueError("Bearer authentication requires a token.")
        base["headers"]["Authorization"] = f"Bearer {bearer}"
    elif auth_type != "none":
        raise ValueError("Invalid authentication type.")

    session_name = str(payload.get("session", "")).strip()
    if session_name:
        session = load_session(session_name)
        base["headers"] = {**session.get("headers", {}), **base["headers"]}
        base["cookies"] = {**session.get("cookies", {}), **base["cookies"]}
        if session.get("auth") and "auth" not in base:
            base["auth"] = session["auth"]
        if session.get("proxy") and "proxy" not in base:
            base["proxy"] = session["proxy"]
        if session.get("verify_tls") is False and payload.get("verify_tls") is None:
            base["verify_tls"] = False

    body_type = str(payload.get("body_type", "none")).lower().strip()
    body = str(payload.get("body", ""))
    if body_type == "json":
        try:
            base["json"] = json.loads(body or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid JSON body at line {exc.lineno}, column {exc.colno}: {exc.msg}."
            ) from exc
    elif body_type == "form":
        base["data"] = _parse_urlencoded(body)
    elif body_type == "raw":
        base["body"] = body
    elif body_type == "multipart":
        multipart = _parse_map(body)
        if any(str(value).startswith("@") for value in multipart.values()):
            raise ValueError("Web multipart fields cannot read server-side file paths.")
        base["multipart"] = multipart
    elif body_type == "none":
        if body.strip():
            raise ValueError(
                "A request body was entered, but Body type is None. Select JSON, Form URL encoded, or Raw."
            )
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
            raise ValueError(
                "Payload values were provided, but the request has no placeholder. Add {{VALUE}} or a named placeholder such as {{USER}}."
            )
        missing = request_placeholders - set(nonempty_groups)
        if missing:
            raise ValueError(f"Missing payload section(s): {', '.join(sorted(missing))}.")
        unused = set(nonempty_groups) - request_placeholders
        if unused:
            raise ValueError(f"Unused payload section(s): {', '.join(sorted(unused))}.")
        mode = str(payload.get("mode", "sniper"))
        max_requests = _as_int(payload, "max_requests", MAX_VALUES, 1, MAX_REQUESTS)
        requests = build_requests(base, nonempty_groups, mode, max_requests)
    else:
        requests = [base]

    columns = parse_columns(
        [line.strip() for line in str(payload.get("columns", "")).splitlines() if line.strip()]
    )
    options: dict[str, Any] = {
        "workers": _as_int(payload, "workers", 1, 1, MAX_WORKERS),
        "delay_ms": _as_int(payload, "delay_ms", 0, 0, 3_600_000),
        "retries": _as_int(payload, "retries", 0, 0, 5),
        "backoff": _as_bool(payload, "backoff", False),
        "match_rules": [
            line.strip() for line in str(payload.get("match", "")).splitlines() if line.strip()
        ],
        "exclude_rules": [
            line.strip() for line in str(payload.get("exclude", "")).splitlines() if line.strip()
        ],
        "extract_rules": _parse_map(str(payload.get("extract", ""))),
        "body_limit": _as_int(payload, "body_limit", DEFAULT_BODY_LIMIT, 1, 1024 * 1024),
        "cluster_threshold": _as_float(payload, "cluster_threshold", 98.0, 0.0, 100.0),
    }
    rate = payload.get("rate")
    if rate not in (None, ""):
        options["rate"] = _as_float(payload, "rate", 1.0, 0.001, 10000.0)
    for rule in [
        *options["match_rules"],
        *options["exclude_rules"],
        *options["extract_rules"].values(),
    ]:
        validate_rule(rule)
    if len(requests) * options["body_limit"] > MAX_RESULT_MEMORY:
        raise ValueError("Requested response previews exceed the 64 MiB per-job memory budget.")
    return requests, columns, options


def create_app(
    request_token: str | None = None,
    require_page_token: bool = False,
    multiuser: bool = False,
    persist_history: bool = True,
    allowed_hosts: list[str] | None = None,
) -> FastAPI:
    token = request_token or secrets.token_urlsafe(32)
    app = FastAPI(
        title="imr-intruder",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.token = token
    app.state.require_page_token = require_page_token
    app.state.multiuser = multiuser
    app.state.jobs = {}
    app.state.lock = threading.Lock()
    app.state.allowed_hosts = tuple(
        item.lower().strip() for item in (allowed_hosts or []) if item.strip()
    )
    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
    templates = Jinja2Templates(directory=BASE_DIR / "templates")

    def history_file(job_id: str) -> Path:
        return active_storage_directory("results") / f"{safe_name(job_id, 'job id')}.json"

    def request_file(name: str) -> Path:
        return active_storage_directory("requests") / f"{safe_name(name, 'request name')}.json"

    def job_summary(job: Job) -> dict[str, Any]:
        return {
            "job_id": job.id,
            "name": str(job.requests[0].get("name") or "Untitled request")
            if job.requests
            else "Untitled request",
            "target": redact_url(str(job.requests[0].get("url") or "")) if job.requests else "",
            "status": job.status,
            "total": len(job.requests),
            "completed": len(job.results),
            "owner": job.owner,
            "owner_role": job.owner_role,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
        }

    def persist_job(job: Job) -> None:
        if not persist_history:
            return
        save_history_record(
            job.requests,
            job.results,
            job_id=job.id,
            owner=job.owner,
            owner_role=job.owner_role,
            status=job.status,
        )

    def authorize(
        request: Request,
        required: str = "operator",
        *,
        allow_query: bool = False,
    ) -> tuple[str, str]:
        supplied = request.headers.get("X-Request-Token") or request.cookies.get(
            "imr_intruder_token", ""
        )
        if allow_query and not supplied:
            supplied = request.query_params.get("token", "")
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

    def target_in_scope(url: str) -> bool:
        if not app.state.allowed_hosts:
            return True
        hostname = (urlsplit(url).hostname or "").lower()
        for pattern in app.state.allowed_hosts:
            try:
                if ipaddress.ip_address(hostname) in ipaddress.ip_network(pattern, strict=False):
                    return True
            except ValueError:
                if fnmatch.fnmatchcase(hostname, pattern):
                    return True
        return False

    def cleanup_jobs() -> None:
        cutoff = time.time() - JOB_TTL
        with app.state.lock:
            stale_active = [
                job
                for job in app.state.jobs.values()
                if job.updated_at < cutoff
                and job.status in {"queued", "running", "paused", "cancelling"}
            ]
            for job in stale_active:
                job.cancel.set()
                job.pause.clear()
                job.status = "cancelling"
                job.updated_at = time.time()
            expired = [
                job_id
                for job_id, job in app.state.jobs.items()
                if job.updated_at < cutoff and job.status in {"done", "cancelled", "error"}
            ]
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
        with job.event_condition:
            job.next_sequence += 1
            job.events.append({"sequence": job.next_sequence, "event": event, **payload})
            job.event_condition.notify_all()

    def run_job(job: Job) -> None:
        job.status = "running"
        emit(job, "meta", total=len(job.requests))

        def callback(completed: int, total: int, result: dict[str, Any]) -> None:
            while job.pause.is_set() and not job.cancel.is_set():
                time.sleep(0.05)
            live_fields = {
                "index",
                "name",
                "method",
                "url",
                "status",
                "size_bytes",
                "elapsed_ms",
                "content_type",
                "http_version",
                "location",
                "error",
                "error_type",
                "outcome",
                "response_received",
            }
            stable_result = {key: value for key, value in result.items() if key in live_fields}
            job.results.append(stable_result)
            emit(job, "result", completed=completed, total=total, result=stable_result)

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
            persist_job(job)
            emit(
                job,
                "done",
                status=job.status,
                completed=len(job.results),
                total=len(job.requests),
            )
        except Exception as exc:
            job.status = "error"
            emit(job, "fatal", error=f"{type(exc).__name__}: {exc}")
            persist_job(job)

    @app.middleware("http")
    async def hardening(request: Request, call_next):
        response = await call_next(request)
        response.headers.update(
            {
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "Referrer-Policy": "no-referrer",
                "Cache-Control": "no-store",
                "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
            }
        )
        return response

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        page_token = app.state.token
        if app.state.require_page_token:
            authorize(request, "viewer", allow_query=True)
            page_token = (
                request.query_params.get("token")
                or request.cookies.get("imr_intruder_token", "")
                or request.headers.get("X-Request-Token", "")
            )
        if app.state.require_page_token and request.query_params.get("token"):
            response: Response = RedirectResponse(url="/", status_code=303)
        else:
            response = templates.TemplateResponse(request, "index.html", {"version": __version__})
        response.set_cookie(
            "imr_intruder_token",
            page_token,
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="strict",
            max_age=JOB_TTL,
        )
        return response

    @app.get("/health")
    def health():
        return {"status": "ok", "version": __version__}

    @app.get("/api/me")
    def identity(request: Request):
        name, role = authorize(request, "viewer")
        return {"name": name, "role": role, "multiuser": app.state.multiuser}

    @app.post("/api/jobs")
    async def create_job(request: Request):
        owner, owner_role = authorize(request, "operator")
        try:
            length = int(request.headers.get("content-length", "0") or 0)
            if length > MAX_JOB_BODY_BYTES:
                raise HTTPException(413, "Request body exceeds 1 MiB.")
            raw = await request.body()
            if len(raw) > MAX_JOB_BODY_BYTES:
                raise HTTPException(413, "Request body exceeds 1 MiB.")
            payload = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise HTTPException(400, "Request body must contain valid JSON.") from exc
        try:
            requests, columns, options = build_web_requests(payload)
            outside_scope = [
                urlsplit(item["url"]).hostname or "unknown"
                for item in requests
                if not target_in_scope(item["url"])
            ]
            if outside_scope:
                raise ValueError(
                    f"Target host is outside the configured web scope: {outside_scope[0]}"
                )
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise HTTPException(400, str(exc)) from exc
        cleanup_jobs()
        with app.state.lock:
            active = sum(
                job.status in {"queued", "running", "paused", "cancelling"}
                for job in app.state.jobs.values()
            )
            if active >= MAX_ACTIVE_JOBS:
                raise HTTPException(429, "Too many active jobs.")
            job = Job(
                uuid.uuid4().hex,
                requests,
                columns,
                options,
                owner=owner,
                owner_role=owner_role,
            )
            app.state.jobs[job.id] = job
        threading.Thread(target=run_job, args=(job,), daemon=True).start()
        return JSONResponse({"job_id": job.id, "total": len(requests)}, status_code=202)

    @app.get("/api/jobs")
    def jobs(request: Request):
        authorize(request, "viewer")
        cleanup_jobs()
        with app.state.lock:
            rows = [job_summary(job) for job in app.state.jobs.values()]
        return sorted(rows, key=lambda item: item["updated_at"], reverse=True)

    @app.get("/api/jobs/{job_id}")
    def job_status(job_id: str, request: Request):
        authorize(request, "viewer")
        job = get_job(job_id)
        return {
            "job_id": job.id,
            "status": job.status,
            "total": len(job.requests),
            "completed": len(job.results),
            "results": job.results if job.status in {"done", "cancelled", "error"} else [],
        }

    @app.get("/api/jobs/{job_id}/events")
    def events(job_id: str, request: Request):
        authorize(request, "viewer")
        job = get_job(job_id)
        try:
            cursor = int(request.query_params.get("after", "0"))
        except ValueError as exc:
            raise HTTPException(400, "after must be a non-negative integer.") from exc
        if cursor < 0:
            raise HTTPException(400, "after must be a non-negative integer.")

        def generate() -> Iterator[str]:
            nonlocal cursor
            while True:
                with job.event_condition:
                    latest = job.events[-1]["sequence"] if job.events else 0
                    if cursor >= latest and job.status not in {
                        "done",
                        "cancelled",
                        "error",
                    }:
                        job.event_condition.wait(timeout=15)
                    batch = [event for event in job.events if event["sequence"] > cursor]
                    if batch:
                        cursor = batch[-1]["sequence"]
                    terminal = job.status in {"done", "cancelled", "error"}
                for event in batch:
                    yield json.dumps(event, ensure_ascii=False) + "\n"
                if terminal:
                    return
                if not batch:
                    yield json.dumps({"event": "heartbeat", "sequence": cursor}) + "\n"

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
        return Response(
            results_to_csv(job.results),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{job_id}.csv"'},
        )

    @app.get("/api/jobs/{job_id}/json")
    def json_export(job_id: str, request: Request):
        authorize(request, "viewer")
        job = get_job(job_id)
        return Response(
            json.dumps(job.results, ensure_ascii=False, indent=2) + "\n",
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{job_id}.json"'},
        )

    @app.get("/api/jobs/{job_id}/jsonl")
    def jsonl_export(job_id: str, request: Request):
        authorize(request, "viewer")
        content = "".join(
            json.dumps(item, ensure_ascii=False) + "\n" for item in get_job(job_id).results
        )
        return Response(
            content,
            media_type="application/x-ndjson; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{job_id}.jsonl"'},
        )

    @app.get("/api/jobs/{job_id}/report")
    def html_report(job_id: str, request: Request):
        authorize(request, "viewer")
        job = get_job(job_id)
        with tempfile.TemporaryDirectory(prefix="imr-intruder-report-") as temporary:
            path = build_html_report(
                job.results,
                Path(temporary) / "report.html",
                f"imr-intruder · {job.requests[0].get('name') or job.id}",
            )
            content = path.read_text(encoding="utf-8")
        return Response(
            content,
            media_type="text/html; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{job_id}-report.html"'},
        )

    @app.get("/api/history")
    def history(request: Request):
        authorize(request, "viewer")
        rows: list[dict[str, Any]] = []
        for path in active_storage_directory("results").glob("*.json"):
            record = read_json(path, default={}) or {}
            if isinstance(record, dict):
                rows.append({key: value for key, value in record.items() if key != "results"})
        return sorted(rows, key=lambda item: float(item.get("updated_at", 0)), reverse=True)[:100]

    @app.get("/api/history/{job_id}")
    def history_item(job_id: str, request: Request):
        _name, role = authorize(request, "viewer")
        record = read_json(history_file(job_id))
        if not isinstance(record, dict):
            raise HTTPException(404, "History item not found.")
        if role != "admin":
            record = dict(record)
            record.pop("requests", None)
        return record

    @app.delete("/api/history/{job_id}")
    def delete_history(job_id: str, request: Request):
        authorize(request, "operator")
        path = history_file(job_id)
        if not path.exists():
            raise HTTPException(404, "History item not found.")
        path.unlink()
        return {"job_id": job_id, "deleted": True}

    @app.get("/api/history/{job_id}/{format_name}")
    def history_export(job_id: str, format_name: str, request: Request):
        authorize(request, "viewer")
        record = read_json(history_file(job_id))
        if not isinstance(record, dict) or not isinstance(record.get("results"), list):
            raise HTTPException(404, "History item not found.")
        results = record["results"]
        if format_name == "csv":
            content = results_to_csv(results)
            media_type = "text/csv; charset=utf-8"
            extension = "csv"
        elif format_name == "json":
            content = json.dumps(results, ensure_ascii=False, indent=2) + "\n"
            media_type = "application/json; charset=utf-8"
            extension = "json"
        elif format_name == "jsonl":
            content = "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in results)
            media_type = "application/x-ndjson; charset=utf-8"
            extension = "jsonl"
        elif format_name == "report":
            with tempfile.TemporaryDirectory(prefix="imr-intruder-report-") as temporary:
                path = build_html_report(
                    results,
                    Path(temporary) / "report.html",
                    f"imr-intruder · {record.get('name') or job_id}",
                )
                content = path.read_text(encoding="utf-8")
            media_type = "text/html; charset=utf-8"
            extension = "html"
        else:
            raise HTTPException(404, "Unsupported history export format.")
        return Response(
            content,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{job_id}.{extension}"'},
        )

    @app.post("/api/import")
    async def import_request(request: Request):
        authorize(request, "operator")
        raw = await request.body()
        if len(raw) > MAX_JOB_BODY_BYTES:
            raise HTTPException(413, "Import body exceeds 1 MiB.")
        try:
            payload = json.loads(raw.decode("utf-8"))
            kind = str(payload.get("kind", "raw")).lower()
            content = str(payload.get("content", ""))
            if kind in {"raw", "burp", "zap"}:
                imported = [parse_raw_request(content)]
            elif kind == "curl":
                imported = [parse_curl(content)]
            elif kind == "har":
                imported = parse_har(json.loads(content))
            else:
                raise ValueError(f"Unsupported import type: {kind}")
        except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"requests": imported}

    @app.get("/api/requests")
    def saved_requests(request: Request):
        authorize(request, "operator")
        return sorted(path.stem for path in active_storage_directory("requests").glob("*.json"))

    @app.get("/api/requests/{name}")
    def saved_request(name: str, request: Request):
        authorize(request, "operator")
        data = read_json(request_file(name))
        if not isinstance(data, dict):
            raise HTTPException(404, "Saved request not found.")
        return data

    @app.put("/api/requests/{name}")
    async def save_request(name: str, request: Request):
        authorize(request, "operator")
        raw = await request.body()
        if len(raw) > MAX_JOB_BODY_BYTES:
            raise HTTPException(413, "Saved request exceeds 1 MiB.")
        try:
            data = json.loads(raw.decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Saved request must be a JSON object.")
            path = request_file(name)
            atomic_json_write(path, data)
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"name": path.stem, "saved": True}

    @app.delete("/api/requests/{name}")
    def delete_saved_request(name: str, request: Request):
        authorize(request, "operator")
        path = request_file(name)
        if not path.exists():
            raise HTTPException(404, "Saved request not found.")
        path.unlink()
        return {"name": name, "deleted": True}

    @app.get("/api/sessions")
    def sessions(request: Request):
        authorize(request, "operator")
        return list_sessions()

    @app.get("/api/workspaces")
    def workspaces(request: Request):
        authorize(request, "viewer")
        return {"current": current_workspace(), "items": list_workspaces()}

    @app.post("/api/workspaces")
    async def change_workspace(request: Request):
        authorize(request, "operator")
        try:
            payload = json.loads((await request.body()).decode("utf-8"))
            name = str(payload.get("name", "")).strip()
            if not name:
                clear_current_workspace()
                return {"current": None}
            if _as_bool(payload, "create", False) and name not in list_workspaces():
                create_workspace(name)
            set_current_workspace(name)
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"current": name}

    return app
