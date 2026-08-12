# Changelog

## Unreleased

## 1.5.0

- Added persistent CLI/web run history with `history list/show/replay/delete`, active-job browser reconnection, workspace-aware request libraries, and saved-request management.
- Added web import for cURL, raw HTTP, HAR, Burp, and ZAP requests; session, proxy, Basic/Bearer authentication, multipart-field, copy-as-cURL, and extended HTTP method controls.
- Added sortable responsive results, extracted fields and match badges, structured evidence tabs, bounded 500-row rendering, and CSV/JSON/JSONL/redacted-HTML exports for current and historical jobs.
- Added CLI `--format table|json|jsonl|csv`, stderr error routing, bounded executor submission, and automatic workspace-aware result persistence.
- Fixed regex response columns after streamed reads, full-body hashing for truncated responses, duplicate URL/form parameters, macro cookie propagation, raw `Host` case handling, batch-option precedence, and unsafe `.`/`..` storage names.
- Prevented secret payloads from leaking through generated names, request URLs, response locations, custom URL columns, history summaries, or CSV evidence.
- Hardened remote web operation with required scope allowlists, expiring collaboration tokens, real displayed identities, read-only viewer controls, secure-cookie awareness, stale-job cancellation, IPv6 listener URLs, and tokens removed from process arguments and status records.
- Expanded the regression suite from 86 to 101 tests before release packaging.

## 1.4.6

- Published a stable GitHub release for Linux updates, verified the activated version after installation, and stopped stale web-console processes during updates so old code cannot remain in service.
- Rebuilt the web console as a professional application workspace with persistent navigation, a compact command bar, a focused request editor, grouped execution settings, responsive layouts, keyboard-accessible tabs and rows, and a dedicated response-intelligence view.
- Hardened web jobs with strict integer and URL validation, preflight rule validation, 1 MiB API-body and 64 MiB result-preview budgets, non-destructive event history, and replay cursors.
- Removed access tokens from the rendered DOM and API query-string authentication; remote bootstrap tokens are exchanged for an HttpOnly same-site cookie.
- Streamed response bodies into bounded previews instead of loading entire responses, preserved all cancellation results, repaired checkpoint resumes, and made multipart retries rewind files safely.
- Hardened CSV exports against spreadsheet formulas and included dynamic extraction columns in both CLI and web exports.
- Expanded cURL import support for options before or after URLs, inline options, cookies, auth, timeouts, retries, GET data, JSON, HTTP/2, and explicit unsupported-option errors.
- Fixed Windows background-server PID tracking and inherited pipe handles, eliminating status failures and smoke-test hangs; fixed the Linux installer to install through the new virtual environment rather than the host interpreter.
- Expanded secret redaction to token/session/CSRF/API-key variants and sensitive URL query parameters.
- Added strict linting, formatting, typing, security, extended smoke, and regression coverage to CI.
## 1.4.5

- Windows installer now guarantees persistent registration of the imr-intruder launcher directory in the current user's `Path`.
- Adds a managed `imr-intruder.cmd` shim to an already-active, writable user PATH directory such as `%LOCALAPPDATA%\Microsoft\WindowsApps`, making the command immediately resolvable in existing CMD/PowerShell sessions when WindowsApps is already present in PATH.
- Verifies the immediate shim by launching `imr-intruder version` without injecting the application bin directory into the probe PATH.
- Records and removes the managed shim during uninstall, while refusing to overwrite unrelated commands with the same name.
- Keeps Python runtime and `Scripts` directories in the persistent user PATH without creating `PYTHONHOME` or `PYTHONPATH`.

## 1.4.4

- Fixed Windows source-path forwarding when `install.cmd` starts from `%~dp0`, whose trailing backslash could escape the closing quote and deliver a literal trailing `"` to Python.
- Canonicalizes `SOURCE` before invoking helper scripts and passes `SOURCE\.` to avoid a backslash immediately before the argument-closing quote.
- Added defensive source normalization in `install_windows.py` so older bootstrap callers with a trailing quote recover safely.
- Added regression coverage for default and `/SOURCE` paths with trailing separators and for the exact `Invalid source directory: ..."` failure.

## 1.4.3

- Fixed Windows Python detection rejecting every valid interpreter because CMD passed the caret-escaped token `^<` literally to `python -c`, producing `SyntaxError`.
- Replaced all CMD version probes with a shell-safe `operator.ge` check that contains no redirection metacharacters.
- Added regression coverage that compiles the exact probe and rejects future caret-escaped comparison operators.
- Existing Python installations are now accepted immediately, allowing PATH and application environment registration to complete.

## 1.4.2

- Fixed post-install discovery when the official Python installer enters maintenance mode or installs to a registered path different from the requested `TargetDir`.
- Revalidates Python through direct paths, commands, PEP 514 registry entries, Python Install Manager locations, and WinGet package directories after installation.
- Runs interpreter probes in isolated mode and records failed candidates in the bootstrap log.
- Registers the selected Python directory and its `Scripts` directory in the user PATH before dependency installation.
- Keeps Python PATH entries after uninstalling imr-intruder while removing only the application launcher and `IMR_INTRUDER_*` variables.
- Shields the installed launcher from inherited `PYTHONHOME`, `PYTHONPATH`, pip, and virtual-environment overrides.

## 1.4.1

- Split the Windows bootstrap into a small `install.cmd`, `scripts/find_python.cmd`, and `scripts/bootstrap_python.cmd` so discovery and installation remain testable and avoid CMD line-length failures.
- Added a clean-machine bootstrap path that ignores preinstalled Python, optionally skips WinGet, downloads pinned CPython 3.13.14, verifies SHA-256, installs pip per-user, and then installs all project dependencies.
- Hardened Python discovery across commands, launcher paths, PEP 514 registry keys, standard installation directories, and WinGet package directories without mutating PATH.
- Cleared inherited Python, pip, and virtual-environment overrides before discovery and installation.
- Added explicit handling and logs for WinGet failures, checksum errors, installer policy error 1625, missing pip, dependency failures, rollback, PATH registration, and uninstall cleanup.
- Corrected the GitHub Actions workflow YAML and added a `windows-clean-bootstrap` job on `windows-2022` that does not use `setup-python` for the installation under test.

## 1.4.0

- Fixed POST form scans that incorrectly serialized `username={{USER}}&password=fixed` as one field and caused target endpoints such as `/Pi` to return `400 Bad Request`.
- Added equivalent URL-encoded parsing to the web console and CLI `--data`/`--param` options.
- Removed stale `Content-Length` and `Transfer-Encoding` headers before sending modified or replayed requests.
- Added effective request diagnostics, redacted body summaries, final URL, request size, outcome, and transport-error classification.
- Reworked the web job lifecycle with validation, status snapshots, enriched final events, pause/resume/cancel state checks, job cleanup, and safer CSV export.
- Audited and wired every web control: Run scan, tabs, pause/resume, cancel, CSV, filters, theme, result drawer, and close actions.
- Corrected generated scan names, single-response intelligence, transport-error clustering, case-insensitive header analysis, and report generation when anomaly values are unavailable.
- Corrected CLI repeater aggregation, typed session values, WebSocket exit codes, output-directory creation, range validation, doctor checks, and web background lifecycle behavior.
- Added integration coverage for POST `/Pi`, all top-level and nested CLI help flows, web controls, job events, request framing, session/workspace/update flows, and background web start/status/stop.

## 1.3.3

- Fixed Windows `cmd.exe` "The input line is too long" failures during post-install Python discovery.
- Removed recursive PATH expansion from Python detection retries.
- Switched registry, timeout, search, and checksum utilities to explicit System32 paths.
- Added regression coverage preventing PATH growth in future installers.

## 1.3.2

- Fixed Windows Python discovery immediately after automatic installation.
- Added PEP 514 registry discovery, WinGet package-tree discovery, WindowsApps discovery, PATH refresh, and bounded retries.
- Added a deterministic `TargetDir` for the verified official Python installer and preserved its diagnostic log.
- WinGet success is now accepted only after a compatible interpreter is executed successfully.

## 1.3.1

- Windows installer now prompts to install Python automatically when Python 3.10+ is missing.
- Added unattended `/AUTO-INSTALL-PYTHON` and opt-out `/NO-PYTHON-INSTALL` modes.
- Added WinGet installation with official Python installer fallback.
- Added SHA-256 verification before executing the downloaded Python installer.
- Added post-install Python, pip, dependency, launcher, PATH, and `doctor` validation.

## 1.3.0

- Added response normalization, hashes, similarity, clustering, anomaly scoring, match/exclude/extract rules, and response reports.
- Added persistent sessions, workspaces, macros, checkpoints, CSV/JSONL/HTML evidence, and secret redaction.
- Added raw, cURL, HAR, Burp, and ZAP importers.
- Added named placeholders and sniper, battering-ram, pitchfork, and bounded cluster-bomb modes.
- Added controlled retries, backoff, rate limiting, HTTP/2, WebSocket, optional browser automation, multipart data, and plugins.
- Added multiuser web tokens with viewer/operator/admin roles.
- Added professional responsive web console with live streaming, filters, details, pause/resume, cancellation, and export.
- Added native dependency-installing Linux and Windows CMD installers with automatic PATH and environment configuration.
- Added `check-update` and staged `update` commands that do not require cloning the repository again.
- Raised the minimum supported Python version to 3.10.

## 1.1.0

- Added the initial multimode CLI, managed web console, native installers, and single live result table.
