# Changelog

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
