# Changelog

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
