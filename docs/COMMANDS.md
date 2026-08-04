# Command reference

Use `imr-intruder COMMAND --help` for the authoritative option list.

## HTTP execution

### `request`
Sends one HTTP request with custom method, headers, parameters, cookies, authentication, proxy, JSON/form/raw/multipart body, TLS, redirect, HTTP/2, retries, rate control, custom columns, response rules, and exports. URL-encoded `--param` and `--data` accept either repeated `key=value` options or a conventional `a=1&b=2` string.

### `intrude`
Renders named `{{PLACEHOLDER}}` values using sniper, battering-ram, pitchfork, or cluster-bomb modes. `--max-requests` prevents accidental unbounded combinations. Generated names identify the active payload assignment, such as `USER=alice`.

POST form example:

```bash
imr-intruder intrude \
  --url 'https://example.test/Pi' \
  --method POST \
  --data 'username={{USER}}&password=fixed' \
  --payload USER=users.txt \
  --mode sniper \
  --workers 1
```

### `batch`
Executes a JSON object containing a `requests` list.

### `repeater`
Imports and repeats raw, cURL, HAR, Burp, or ZAP requests in one execution. Repetitions receive stable names such as `repeater-r1`; stale framing headers are removed before transmission.

## Import

```text
import raw
import curl
import har
import burp
import zap
```

Output is a batch-compatible JSON file.

## State

### `session`
Creates, lists, displays, updates, and deletes persistent session configuration. Cookies and authentication data are hidden unless explicitly requested.

### `workspace`
Creates and selects isolated project directories and exports them as compressed archives.

### `macro`
Runs ordered request steps, extracts variables, and stores variables in a session.

## Intelligence and evidence

- `--match text:VALUE`
- `--match regex:PATTERN`
- `--exclude ...`
- `--extract name=header:Header-Name`
- `--extract name=json:path.to.value`
- `--extract name=regex:(capture)`
- `--cluster-threshold 98`
- `--column name=header:Server`
- `--column name=response:url`

### `report`
Builds an offline, redacted HTML report from JSON/JSONL results.

## Extended transports

### `websocket`
Sends a bounded list of messages and records each reply or timeout.

### `browser`
Uses optional Playwright/Chromium for client-rendered pages and screenshots.

### `plugins`
Lists Python entry-point plugins registered under `imr_intruder.plugins`.

## Web lifecycle

```text
web start
web start --background
web status
web open
web stop
```

Remote listening requires `--allow-remote`. Multiuser role tokens are managed with `collab`.

## Update lifecycle

### `check-update`
Checks the latest GitHub release or the `main` commit. Exit code `0` means an update is available; exit code `2` means the installation is current.

### `update`
Downloads and safely installs an update without requiring a new clone. Supports release/main channels, private repository tokens, dry-run, and force.

## Diagnostics

### `doctor`
Reports Python compatibility, executable, required dependency availability, storage-path writability, optional browser support, and configured environment variables.

### `version`
Prints the installed version.
