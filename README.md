# imr-intruder

`imr-intruder` is a professional multimode HTTP request and response-intelligence toolkit for authorized security testing, laboratories, CTFs, and reproducible application diagnostics.

```text
imr-intruder
imr :: v1.3.1
```

## Requirements

- Python **3.10 or newer**.
- Linux, Kali, Debian, Ubuntu, or Windows 10/11.
- Network authorization for every tested target.

## Native installation

### Linux / Kali

```bash
chmod +x install.sh
./install.sh
source ~/.profile
imr-intruder doctor
```

The installer creates an isolated versioned environment, installs dependencies, creates `~/.local/bin/imr-intruder`, and configures these variables automatically:

```text
IMR_INTRUDER_HOME
IMR_INTRUDER_CONFIG
IMR_INTRUDER_STATE
IMR_INTRUDER_DATA
IMR_INTRUDER_CACHE
```

### Windows CMD

```cmd
install.cmd
```

When Python 3.10+ is not detected, the installer asks whether it should install Python automatically. It uses WinGet when available and otherwise downloads a checksum-verified official Python installer. For unattended setup:

```cmd
install.cmd /AUTO-INSTALL-PYTHON
```

To disable automatic Python installation:

```cmd
install.cmd /NO-PYTHON-INSTALL
```

Open a new CMD window and verify:

```cmd
imr-intruder doctor
```

The installer uses a versioned virtual environment under `%LOCALAPPDATA%\Programs\imr-intruder`, installs dependencies, creates a native CMD launcher, updates the user PATH, and sets the same `IMR_INTRUDER_*` variables through the Windows user environment registry.

Complete installation details: [docs/INSTALLATION.md](docs/INSTALLATION.md).

## Command structure

```text
imr-intruder request
imr-intruder intrude
imr-intruder batch
imr-intruder repeater
imr-intruder import
imr-intruder session
imr-intruder workspace
imr-intruder report
imr-intruder macro
imr-intruder websocket
imr-intruder browser
imr-intruder plugins
imr-intruder collab
imr-intruder web
imr-intruder check-update
imr-intruder update
imr-intruder doctor
imr-intruder version
```

Every command supports `--help`.

## Direct request

```bash
imr-intruder request \
  --url https://example.test/api \
  --method POST \
  --json '{"name":"research"}' \
  --column server=header:Server \
  --column final_url=response:url
```

## Controlled payload variations

Place one or more named placeholders anywhere in URL, headers, query parameters, cookies, JSON, form data, raw body, or multipart values:

```text
{{VALUE}}
{{USER}}
{{ID}}
```

```bash
imr-intruder intrude \
  --url 'https://example.test/search?q={{VALUE}}' \
  --values-file values.txt \
  --mode sniper \
  --workers 2 \
  --delay-ms 150 \
  --match 'text:Welcome' \
  --exclude 'text:Invalid request' \
  --extract 'request_id=header:X-Request-ID' \
  --csv results.csv \
  --jsonl results.jsonl
```

Supported modes:

- `sniper`
- `battering-ram`
- `pitchfork`
- `cluster-bomb`, bounded by `--max-requests`

## Response intelligence

Each result can include:

- HTTP status, body size, elapsed time, content type, HTTP version, and redirect location.
- Normalized SHA-256 body hash.
- Similarity against the baseline.
- Response cluster.
- Size delta and anomaly score.
- Match/exclude results.
- Extracted header, JSON, regex, cookie, request, or response columns.

The terminal uses one live Rich table; it does not print a second duplicate table after completion.

## Importing real requests

```bash
imr-intruder import raw request.txt --output batch.json
imr-intruder import curl request.curl --output batch.json
imr-intruder import har traffic.har --output batch.json
imr-intruder import burp request.txt --output batch.json
imr-intruder import zap request.txt --output batch.json
```

## Sessions and workspaces

```bash
imr-intruder session create lab
imr-intruder session cookies lab --cookie session=test
imr-intruder request --session lab --url https://example.test/account

imr-intruder workspace create assessment
imr-intruder workspace use assessment
imr-intruder workspace export assessment --output assessment.tar.gz
```

Session files use restrictive permissions. Secret fields are redacted by default when displayed.

## Macros

Macros execute ordered requests, extract variables, and reuse them in later steps:

```bash
imr-intruder macro examples/macro.json --session lab --output macro-results.jsonl
```

## Web console

Foreground:

```bash
imr-intruder web start
```

Background lifecycle:

```bash
imr-intruder web start --background
imr-intruder web status
imr-intruder web open
imr-intruder web stop
```

Default URL:

```text
http://127.0.0.1:7415
```

The web console provides live results, payload modes, response intelligence, search, filters, details drawer, pause/resume, cancellation, CSV export, dark/light mode, and responsive mobile layout.

Remote binding requires explicit authorization:

```bash
imr-intruder web start --host 0.0.0.0 --allow-remote --multiuser --background
```

Create role-based tokens:

```bash
imr-intruder collab create-token analyst --role operator
imr-intruder collab list
```

## Updates without cloning again

Check the latest published release:

```bash
imr-intruder check-update
```

Install it:

```bash
imr-intruder update
```

Track `main` instead of releases:

```bash
imr-intruder check-update --channel main
imr-intruder update --channel main
```

For a private repository, set a GitHub token:

```bash
export IMR_INTRUDER_GITHUB_TOKEN='token'
imr-intruder check-update
```

Windows CMD:

```cmd
set IMR_INTRUDER_GITHUB_TOKEN=token
imr-intruder check-update
```

The updater downloads a GitHub ZIP, enforces archive safety limits, rejects traversal and symlink entries, cleans inherited Python/pip environment overrides, stages the installation, validates it, and activates the versioned release through the native installer.

## Optional capabilities

HTTP/2:

```bash
imr-intruder request --http2 --url https://example.test/
```

WebSocket:

```bash
imr-intruder websocket wss://example.test/socket --message ping
```

Browser rendering:

```bash
python -m pip install 'imr-intruder[browser]'
playwright install chromium
imr-intruder browser https://example.test --screenshot page.png
```

Plugins are discovered through the `imr_intruder.plugins` Python entry-point group.

## Reports

```bash
imr-intruder report results.jsonl --output report.html --title 'Authorized assessment'
```

HTML reports redact common authentication headers, cookies, passwords, tokens, and secrets.

## Security defaults

- TLS verification enabled.
- Redirect following disabled.
- Localhost-only web binding.
- Explicit opt-in for remote binding.
- Bounded concurrency and payload generation.
- Safe update archive extraction.
- Redacted secrets and CSV-injection protection.
- Response preview size limits.
- Checkpoints for interrupted runs.

See [SECURITY.md](SECURITY.md) and [docs/COMMANDS.md](docs/COMMANDS.md).
