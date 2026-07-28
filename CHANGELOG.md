# Changelog

## 1.1.0

- Added professional web lifecycle commands: `web start`, `web stop`, `web status`, and `web open`.
- Added managed background web execution with PID state, health checks, logs, stale-state cleanup, and graceful termination.
- Preserved backward compatibility: `imr-intruder web` still starts the console in the foreground.
- Added `update --dry-run` for safe validation and automation.
- Redesigned Linux and Windows native user installers around versioned isolated releases and pre-completion smoke checks.
- Added automatic PATH configuration and Windows environment-change notification without PowerShell.
- Updated uninstallers to stop the managed web process and preserve runtime state unless purge is requested.
- Expanded GitHub installation, command, lifecycle, and troubleshooting documentation.
- Removed duplicate dead code in request-body and remote-token handling.

## 1.0.0

- Added the `imr-intruder` command with direct request, dataset, batch, web, doctor, update, and version modes.
- Added a single live Rich table instead of duplicate progress and final result lists.
- Added recursive `{{VALUE}}` insertion in URLs, headers, parameters, cookies, form data, JSON, and raw bodies.
- Added custom response columns, CSV and JSONL export, configurable concurrency, delay, timeout, proxy, Basic Auth, TLS, and redirect behavior.
- Added a responsive local web console with live streaming, filters, anomaly highlighting, cancellation, and CSV export.
- Added localhost-only defaults, session tokens, CSP, defensive headers, active-job limits, and explicit remote-mode controls.
- Added Linux and Windows installers, uninstallers, examples, diagnostics, and automated tests.
