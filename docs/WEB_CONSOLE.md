# Web console workflow

The web console is a thin client over the same request builder, payload renderer, HTTP engine, and response-intelligence pipeline used by the CLI.

It also exposes persistent workspaces, saved request configurations, request import, completed-run history, structured evidence views, sessions, proxy/authentication controls, and CSV/JSON/JSONL/HTML exports. An interrupted browser tab reconnects to its active in-memory job through the replay cursor.

## Start and lifecycle

```bash
imr-intruder web start
imr-intruder web start --background
imr-intruder web status
imr-intruder web open
imr-intruder web stop
```

The default listener is `127.0.0.1:7415`. Non-loopback binding requires `--allow-remote` and at least one `--scope` host, wildcard, or CIDR. The background process writes state and logs under `IMR_INTRUDER_STATE`, validates `/health`, refuses to terminate an unrelated process from stale state, and keeps its bootstrap token out of the process argument list and public status record.

## Run scan flow

1. **Run request** collects method, URL, transport options, request components, payloads, and analysis rules from the request workspace.
2. Browser-side validation checks the URL, numeric limits, body type, JSON syntax, and placeholder presence.
3. The browser sends JSON to `POST /api/jobs` using the HttpOnly same-site session cookie established when the page loads; tokens are not exposed in the DOM or accepted in API query strings.
4. The backend independently validates every field and builds one or more request configurations.
5. Named placeholders are rendered according to Sniper, Battering ram, Pitchfork, or Cluster bomb mode.
6. Results stream as NDJSON from `GET /api/jobs/{job_id}/events?after=<sequence>`. Event history is non-destructive, so reconnecting or multiple viewers can replay it safely.
7. Provisional rows are replaced by the final enriched snapshot containing hashes, similarity, clusters, anomaly score, rules, diagnostics, and classifications.
8. The completed or cancelled job can be exported with `GET /api/jobs/{job_id}/csv`. Dynamic columns are included and spreadsheet formulas are neutralized.
9. Final results are persisted in the global history or selected workspace, can be reopened after a server restart, and can be exported as CSV, JSON, JSONL, or a redacted HTML report.

The API accepts at most 1 MiB of job JSON. Response previews default to 64 KiB each, are streamed without buffering the full response, and are limited to a 64 MiB aggregate preview budget per job.

## Controls

| Control | Operation |
|---|---|
| Run request | Validates input, creates one job, disables duplicate submission, streams results, and restores controls on completion or error. `Ctrl+Enter` is the keyboard shortcut. |
| Workspace navigation | Moves between the request builder and response analysis. On compact screens it becomes an accessible slide-out panel. |
| Workspace switcher | Creates or selects an isolated project. Saved requests and history follow the selected workspace. |
| Import | Parses pasted cURL, raw HTTP, HAR JSON, Burp, or ZAP request content into the builder. |
| Save | Stores the complete builder configuration in the selected request library. |
| Copy cURL | Copies an equivalent cURL command for the current request. |
| Headers tab | One `Name: value` header per line. Framing headers are recorded and removed before transmission. |
| Parameters tab | Accepts `a=1&b=2` or one `key=value` pair per line. |
| Cookies tab | Accepts one cookie per line or a conventional semicolon-separated cookie string. |
| Body tab | Selects None, JSON, Form URL encoded, Raw, or multipart text fields. A non-empty body with type None is rejected. |
| Session and routing | Selects a persistent session, upstream proxy, Basic authentication, or Bearer token. |
| Payloads tab | Accepts one value per line. Named groups use `[USER]`, `[TOKEN]`, etc. |
| Analysis tab | Configures custom columns, match rules, exclude rules, extraction rules, and response clustering. Invalid regular expressions are rejected before requests begin. |
| Pause / Resume | Stops pending request starts and callbacks; an already active network operation completes or times out normally. |
| Cancel | Sets the cancellation event, clears pause, disables further cancellation, and classifies cancelled pending work. |
| Export | Downloads the current or historical job as CSV, JSON, JSONL, or a redacted HTML report without placing the token in the URL. |
| Search | Filters the local result rows using all serialized result fields. |
| Status filter | Selects all, 2xx, 3xx, 4xx, 5xx, or transport/error results. |
| Differences only | Hides baseline-equivalent rows; single-response runs have no synthetic comparison. |
| Result row | Opens a right-side drawer with Summary, Request, Response, Analysis, and Raw JSON sections. |
| Saved requests | Opens or deletes reusable request configurations. |
| Run history | Reopens or deletes completed jobs; an active job reconnects automatically after a page reload. |
| Close / Escape | Closes the evidence drawer. |
| Theme | Toggles light/dark mode and stores the preference locally. |

## Correct POST form example

Target:

```text
https://example.test/Pi
```

Body type:

```text
Form URL encoded
```

Body, conventional format:

```text
username={{USER}}&password=fixed
```

Equivalent line format:

```text
username={{USER}}
password=fixed
```

Payloads:

```text
[USER]
alice
bob
```

The engine sends two correctly framed requests:

```text
username=alice&password=fixed
username=bob&password=fixed
```

It does **not** send the incorrect single-field representation `username=alice%26password%3Dfixed`.

Repeated parameters such as `role=user&role=admin` are preserved as repeated wire values instead of being collapsed into one dictionary entry.

## Remote scope

```bash
imr-intruder web start \
  --host 0.0.0.0 \
  --allow-remote \
  --multiuser \
  --scope app.lab.example \
  --scope '10.20.0.0/16' \
  --background
```

Every submitted target must match a configured host wildcard or CIDR. Collaboration tokens expire after 168 hours by default and the displayed identity reflects the authenticated name and role.

The built-in server speaks HTTP. For remote access, place it behind a TLS-terminating reverse proxy or use a trusted VPN/SSH tunnel; do not expose the listener directly to an untrusted network.

## Diagnosing HTTP 400

Open the result row and compare:

- `final_request_url`
- `request_content_type`
- `request_size_bytes`
- `request_headers`
- `removed_request_headers`
- `request_body_summary`
- `status`
- `body_preview`

A `400` with `outcome: http_response` means the target accepted the network request but rejected its application syntax or required fields. A transport failure has `response_received: false`, a populated `error_type`, and no response cluster.
