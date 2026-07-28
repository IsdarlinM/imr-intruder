# imr-intruder

```text
imr-intruder
imr :: v1.1.0
```

`imr-intruder` is a professional multimode HTTP request matrix for controlled request replay, response comparison, API testing, authorized security assessments, laboratories, CTFs, and bug-bounty targets that explicitly permit the performed tests.

## Highlights

- One live console table that updates while requests finish; no duplicate progress output.
- Direct request, dataset/intruder, heterogeneous batch, and professional web-console modes.
- Recursive `{{VALUE}}` replacement in URLs, headers, parameters, cookies, form data, JSON, and raw bodies.
- GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS, and custom HTTP methods.
- Form, JSON, and raw request bodies; cookies; custom headers; Basic Auth; proxy support; TLS and redirect controls.
- Custom columns extracted from headers, cookies, JSON paths, regex, request values, and response metadata.
- CSV and JSONL exports.
- Web UI with live streaming, search, HTTP-status filters, anomaly highlighting, cancellation, and CSV export.
- Foreground and managed background web execution with `start`, `stop`, `status`, and `open` commands.
- Native user-level installers for Linux (`install.sh`) and Windows CMD (`install.cmd`), with isolated environments and automatic PATH configuration.
- Conservative concurrency defaults, explicit delays, local-only web binding by default, API session tokens, CSP, and defensive headers.

> Use this tool only against systems you own or are explicitly authorized to test. Keep request rates within the target's published limits.

## Command structure

```text
imr-intruder request                 Send one or more direct HTTP requests
imr-intruder intrude                 Insert dataset values into {{VALUE}}
imr-intruder batch CONFIG.json       Execute heterogeneous requests from JSON
imr-intruder web start               Run the web console in the foreground
imr-intruder web start --background  Run the web console as a user process
imr-intruder web status              Show web-console status, PID, URL, and log
imr-intruder web open                Open the active background console
imr-intruder web stop                Stop the background console
imr-intruder doctor                  Validate the installation and dependencies
imr-intruder update                  Upgrade from the official repository
imr-intruder version                 Show application and runtime versions
```

Every command has dedicated help:

```bash
imr-intruder COMMAND --help
imr-intruder web --help
```

## Installation

Python 3.10 or newer is required. The native installers build an isolated virtual environment during installation; no binaries or virtual environments are stored in the repository.

### Linux, Kali, Debian, Ubuntu

```bash
chmod +x install.sh
./install.sh
```

The installer:

1. Validates Python 3.10+ and the `venv` module.
2. Creates a versioned release under `~/.local/share/imr-intruder/releases/`.
3. Installs the Python package in an isolated environment.
4. Runs `doctor` and `version` smoke checks before completing.
5. Creates `~/.local/bin/imr-intruder`.
6. Adds `~/.local/bin` to `.profile`, `.bashrc`, and `.zshrc` when applicable.

Skip PATH modifications when managing PATH yourself:

```bash
./install.sh --skip-path
```

Uninstall while retaining runtime logs:

```bash
~/.local/share/imr-intruder/uninstall.sh
```

Remove runtime logs and state too:

```bash
~/.local/share/imr-intruder/uninstall.sh --purge
```

### Windows 10/11 — CMD installer

Open **Command Prompt** in the project folder and run:

```cmd
install.cmd
```

The installer:

1. Selects `py -3` or `python` and validates Python 3.10+.
2. Creates a versioned release under `%LOCALAPPDATA%\Programs\imr-intruder\releases\`.
3. Installs the package in an isolated virtual environment.
4. Runs `doctor` and `version` smoke checks.
5. Creates `%LOCALAPPDATA%\Programs\imr-intruder\bin\imr-intruder.cmd`.
6. Adds the launcher directory to the current user's PATH through the Windows user environment registry and broadcasts the environment change.

Open a new CMD or PowerShell window after installation, then run:

```cmd
imr-intruder doctor
```

Uninstall:

```cmd
%LOCALAPPDATA%\Programs\imr-intruder\uninstall.cmd
```

Purge runtime logs and state:

```cmd
%LOCALAPPDATA%\Programs\imr-intruder\uninstall.cmd /PURGE
```

Detailed installation and troubleshooting: [`docs/INSTALLATION.md`](docs/INSTALLATION.md).

## Quick verification

```bash
imr-intruder doctor
imr-intruder version
imr-intruder --help
```

A low-impact public availability smoke test:

```bash
imr-intruder request \
  --url https://h4cker.org/ \
  --method GET \
  --column server=header:Server \
  --column final_url=response:url
```

This sends one ordinary GET request. Do not use dataset mode against third-party services unless their authorization and rate limits explicitly allow it.

## Direct request mode

GET with parameters and custom response columns:

```bash
imr-intruder request \
  --url https://httpbin.org/get \
  --param id=7 \
  --header "Accept: application/json" \
  --column server=header:Server \
  --column final_url=response:url
```

POST form:

```bash
imr-intruder request \
  --url https://httpbin.org/post \
  --method POST \
  --data username=imr \
  --data enabled=true
```

POST JSON:

```bash
imr-intruder request \
  --url https://httpbin.org/post \
  --method POST \
  --json '{"username":"imr","enabled":true}'
```

Read JSON or raw bodies from files:

```bash
imr-intruder request --url https://example.test/api --method POST --json @payload.json
imr-intruder request --url https://example.test/api --method POST --body-file payload.xml
```

Multiple URLs with bounded concurrency:

```bash
imr-intruder request \
  --url https://example.test/health \
  --url https://example.test/version \
  --workers 2
```

## Dataset / intruder mode

Insert `{{VALUE}}` wherever each supplied value must be placed:

```bash
imr-intruder intrude \
  --url https://example.test/authorized-lab \
  --method POST \
  --data username=authorized-user \
  --data 'test_value={{VALUE}}' \
  --values-file examples/values.txt \
  --column location=header:Location \
  --workers 2 \
  --delay-ms 150 \
  --csv results.csv
```

Inline values:

```bash
imr-intruder intrude \
  --url 'https://example.test/api?id={{VALUE}}' \
  --value alpha \
  --value beta \
  --value gamma
```

The placeholder works recursively in:

```text
URL:     https://example.test/items/{{VALUE}}
Header:  X-Test-ID: {{VALUE}}
Param:   id={{VALUE}}
Cookie:  experiment={{VALUE}}
Form:    value={{VALUE}}
JSON:    {"value":"{{VALUE}}"}
Raw:     <value>{{VALUE}}</value>
```

## Batch mode

```bash
imr-intruder batch examples/batch.json --workers 2 --csv batch-results.csv
```

Batch files support defaults, global columns, request-specific columns, environment-variable expansion, and heterogeneous methods/bodies. See [`examples/batch.json`](examples/batch.json).

## Web console

Run in the foreground:

```bash
imr-intruder web start
```

Equivalent compatibility command:

```bash
imr-intruder web
```

Default URL:

```text
http://127.0.0.1:7415
```

Run in the background:

```bash
imr-intruder web start --background
```

Manage it:

```bash
imr-intruder web status
imr-intruder web open
imr-intruder web stop
```

Custom port and log:

```bash
imr-intruder web start \
  --background \
  --port 8088 \
  --no-browser \
  --log-file ~/.local/state/imr-intruder/custom-web.log
```

Remote binding is rejected unless explicitly enabled:

```bash
imr-intruder web start --host 0.0.0.0 --allow-remote
```

Prefer localhost. For remote access, use a trusted network and a TLS reverse proxy; the application prints a tokenized access URL.

## Custom columns

```text
server=header:Server
location=header:Location
request_id=header:X-Request-ID
session=cookie:sessionid
user_id=json:data.user.id
final_url=response:url
reason=response:reason
tested_id=request_param:id
marker=regex:marker=([^&]+)
```

Supported sources:

- `header`
- `cookie`
- `json`
- `regex`
- `request_header`
- `request_param`
- `response`
- `literal`

## Python API

```python
from pathlib import Path

from imr_intruder import run_requests

results = run_requests(
    requests_cfg=[
        {
            "name": "health",
            "method": "GET",
            "url": "http://127.0.0.1:8000/health",
            "timeout": 5,
        }
    ],
    workers=1,
    csv_path=Path("results.csv"),
    live=False,
)
```

## Development and validation

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python -m compileall -q src tests
python -m unittest discover -s tests -v
node --check src/imr_intruder/static/app.js
bash -n install.sh uninstall.sh
```

Windows development environment:

```cmd
python -m venv .venv
.venv\Scripts\activate.bat
python -m pip install -e .
python -m unittest discover -s tests -v
```

Detailed command reference: [`docs/COMMANDS.md`](docs/COMMANDS.md).

## Security model

- The web console binds to `127.0.0.1` by default.
- Non-loopback binding requires `--allow-remote`.
- API calls require an unpredictable session token.
- Remote page access uses a tokenized URL and an HTTP-only, same-site cookie.
- CSP, frame denial, no-sniff, no-store, referrer, and permissions headers are enabled.
- Web runs are bounded by job, value, worker, timeout, and delay limits.
- TLS verification is enabled unless `--insecure` is explicitly used.
- Secrets may be supplied through environment variables in batch configurations.

See [`SECURITY.md`](SECURITY.md) for responsible disclosure and operational guidance.
