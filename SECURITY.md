# Security policy

Use `imr-intruder` only against systems you own or are explicitly authorized to test.

## Safe defaults

- TLS certificate verification is enabled.
- Redirects are not followed unless requested.
- The web console binds to `127.0.0.1` by default.
- Non-loopback listening requires `--allow-remote`.
- Remote and multiuser access is token protected. Browser bootstrap tokens are exchanged for HttpOnly same-site cookies, kept out of the DOM, and rejected from API query strings.
- Payload generation, concurrency, streamed response previews, per-job memory, API request bodies, jobs, archives, and retries are bounded.
- Secret-like headers, fields, payload variables, and sensitive URL query parameters are redacted from evidence and HTML reports.
- CSV exports neutralize spreadsheet formulas and preserve dynamic evidence columns.
- Update ZIPs reject traversal, symlinks, excessive expansion, and unexpected structure.

## Reporting a vulnerability

Do not open a public issue containing exploit details or secrets. Contact the repository owner privately with affected version, reproduction steps, impact, and suggested remediation.
