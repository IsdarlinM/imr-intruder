# imr-intruder

```text
imr-intruder
imr :: v1.0.0
```

A professional multimode HTTP request matrix for authorized security testing, request replay, response comparison, and controlled parameter datasets.

## Features

- One live console table that updates as requests finish—no duplicate progress list.
- Direct request mode for one or many URLs.
- Intruder mode using `{{VALUE}}` in URLs, headers, query parameters, cookies, form data, JSON, or raw bodies.
- Batch mode for heterogeneous requests defined in JSON.
- Professional local web console started from the same CLI.
- Python API through `run_requests()` and `build_intruder_requests()`.
- GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS, and custom methods.
- Form, JSON, and raw bodies; Basic Auth; proxy; cookies; custom headers; TLS and redirect controls.
- Custom columns from response headers, cookies, JSON paths, regex, request values, and response metadata.
- CSV and JSONL exports.
- Search, status filters, anomaly highlighting, cancellation, and CSV export in the web UI.
- Diagnostics and self-update commands.
- Conservative rate defaults and localhost-only web binding.

> Use only on systems you own, laboratories, CTFs, or assessments with explicit authorization.

## Requirements

- Python 3.10 or newer
- Windows, Linux, macOS, Kali, or Termux with Python support

## Installation

### Linux / Kali / macOS

```bash
chmod +x install.sh
./install.sh
```

The installer creates an isolated environment under `~/.local/share/imr-intruder` and installs a launcher in `~/.local/bin`.

### Windows CMD

```cmd
install.cmd
```

The installer creates an isolated environment under `%LOCALAPPDATA%\imr-intruder` and adds `%USERPROFILE%\.local\bin` to the user PATH.

### Development installation

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Windows CMD:

```cmd
python -m venv .venv
.venv\Scripts\activate.bat
python -m pip install -e .
```

## Modes

```text
imr-intruder request   Direct requests from command arguments
imr-intruder intrude   One request per dataset value
imr-intruder batch     Requests from a JSON configuration
imr-intruder web       Local browser console
imr-intruder doctor    Installation diagnostics
imr-intruder update    Update from the official repository
imr-intruder version   Version and runtime details
```

Every command provides dedicated help:

```bash
imr-intruder COMMAND --help
```

## Direct request mode

GET with parameters and custom columns:

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

Use `--json @payload.json` or `--body-file payload.txt` to load request bodies from files.

## Intruder mode

Place `{{VALUE}}` wherever each dataset value must be inserted.

```bash
imr-intruder intrude \
  --url https://example.test/authorized-lab \
  --method POST \
  --data username=authorized-user \
  --data 'test_value={{VALUE}}' \
  --values-file values.txt \
  --column location=header:Location \
  --column final_url=response:url \
  --workers 2 \
  --delay-ms 150 \
  --csv results.csv
```

`values.txt`:

```text
alpha
beta
gamma
```

Inline values are also supported:

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

Configuration format:

```json
{
  "workers": 2,
  "delay_ms": 100,
  "defaults": {
    "timeout": 15,
    "verify_tls": true,
    "follow_redirects": false,
    "headers": {
      "User-Agent": "imr-intruder/1.0.0"
    }
  },
  "columns": [
    {"name": "server", "source": "header", "key": "Server", "default": "-"}
  ],
  "requests": [
    {
      "name": "get-example",
      "method": "GET",
      "url": "https://httpbin.org/get",
      "params": {"id": "7"}
    },
    {
      "name": "post-example",
      "method": "POST",
      "url": "https://httpbin.org/post",
      "json": {"enabled": true}
    }
  ]
}
```

Environment variables such as `${API_TOKEN}` are expanded when the JSON is loaded.

## Web console

```bash
imr-intruder web
```

Default address:

```text
http://127.0.0.1:7415
```

Custom port without opening the browser:

```bash
imr-intruder web --port 8088 --no-browser
```

Remote binding is intentionally blocked unless explicitly enabled:

```bash
imr-intruder web --host 0.0.0.0 --allow-remote
```

Remote mode prints a tokenized access URL. Prefer localhost or place the application behind a trusted TLS reverse proxy.

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

from imr_intruder import build_intruder_requests, run_requests

base_request = {
    "method": "POST",
    "url": "https://example.test/authorized-lab",
    "data": {
        "username": "authorized-user",
        "test_value": "{{VALUE}}",
    },
    "timeout": 15,
    "verify_tls": True,
    "follow_redirects": False,
}

requests_cfg = build_intruder_requests(
    base_request,
    ["alpha", "beta", "gamma"],
)

results = run_requests(
    requests_cfg=requests_cfg,
    workers=2,
    delay_ms=100,
    csv_path=Path("results.csv"),
    live=True,
)
```

`live=True` maintains one updating table. Use `live=False` for silent integrations.

## Diagnostics and updates

```bash
imr-intruder doctor
imr-intruder doctor --json
imr-intruder update
```

## Testing

```bash
python -m pip install .
python -m compileall -q src tests
python -m unittest discover -s tests -v
node --check src/imr_intruder/static/app.js
```

## Security recommendations

- Keep TLS verification enabled outside controlled certificate labs.
- Start with one or two workers and an explicit delay.
- Do not commit tokens, cookies, captured bodies, or target data.
- Keep the web UI on localhost unless remote access is strictly required.
- Review the target's rate limits, program policy, and test-account requirements.
- Treat response exports as potentially sensitive.

See [SECURITY.md](SECURITY.md) for the security policy.
