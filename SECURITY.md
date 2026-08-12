# Security policy

Use `imr-intruder` only against systems you own or are explicitly authorized to test.

## Safe defaults

- TLS certificate verification is enabled.
- Redirects are not followed unless requested.
- The web console binds to `127.0.0.1` by default.
- Non-loopback listening requires `--allow-remote` plus an explicit host/wildcard/CIDR `--scope` allowlist.
- The built-in server speaks HTTP; remote deployments must add TLS through a trusted reverse proxy, VPN, or SSH tunnel.
- Remote and multiuser access is token protected. Browser bootstrap tokens are exchanged for HttpOnly same-site cookies, kept out of the DOM, and rejected from API query strings.
- Background bootstrap tokens are passed through the child environment, excluded from process arguments and status responses, and removed from the address bar immediately after cookie exchange.
- Collaboration tokens expire after seven days by default; viewers cannot access sessions, saved request configurations, or replayable raw requests.
- Payload generation, concurrency, streamed response previews, per-job memory, API request bodies, jobs, archives, and retries are bounded.
- Secret-like headers, fields, payload variables, generated names, URL query parameters, evidence, CSV, and HTML reports are redacted.
- CSV exports neutralize spreadsheet formulas and preserve dynamic evidence columns.
- Update ZIPs reject traversal, symlinks, excessive expansion, and unexpected structure.

## Reporting a vulnerability

Do not open a public issue containing exploit details or secrets. Contact the repository owner privately with affected version, reproduction steps, impact, and suggested remediation.
