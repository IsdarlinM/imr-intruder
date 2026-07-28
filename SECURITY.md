# Security Policy

## Authorized use

imr-intruder is intended for systems you own, controlled laboratories, CTFs, or explicitly authorized assessments. Keep concurrency and request rates within the applicable scope and rules.

## Safe defaults

- TLS verification is enabled.
- Redirects are not followed unless requested.
- CLI dataset mode defaults to two workers and a 100 ms submission delay.
- The web console binds to `127.0.0.1` by default.
- Remote binding requires `--allow-remote` and token-gated page/API access.
- Web jobs and dataset sizes are bounded.

## Reporting a vulnerability

Do not open a public issue containing secrets, tokens, or exploitable private-target details. Use a private GitHub security advisory when available, or contact the repository owner privately.
