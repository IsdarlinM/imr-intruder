# Security policy

Use `imr-intruder` only against systems you own or are explicitly authorized to test.

## Safe defaults

- TLS certificate verification is enabled.
- Redirects are not followed unless requested.
- The web console binds to `127.0.0.1` by default.
- Non-loopback listening requires `--allow-remote`.
- Remote and multiuser access is token protected.
- Payload generation, concurrency, response previews, jobs, archives, and retries are bounded.
- Common secrets are redacted from console metadata and HTML reports.
- Update ZIPs reject traversal, symlinks, excessive expansion, and unexpected structure.

## Reporting a vulnerability

Do not open a public issue containing exploit details or secrets. Contact the repository owner privately with affected version, reproduction steps, impact, and suggested remediation.
