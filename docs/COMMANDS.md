# Command reference

## Global help

```bash
imr-intruder --help
imr-intruder --version
```

## `request`

Sends one or more direct requests. Repeated `--url` values share the same request options.

```bash
imr-intruder request --url URL [--url URL] [options]
```

Important options:

```text
-X, --method METHOD
-p, --param KEY=VALUE
-H, --header "Name: value"
-b, --cookie KEY=VALUE
-d, --data KEY=VALUE
-j, --json JSON|@FILE
--body TEXT
--body-file FILE
--auth USER:PASSWORD
--proxy URL
--timeout SECONDS
-L, --follow-redirects
-k, --insecure
--repeat COUNT
--workers COUNT
--delay-ms MILLISECONDS
--column SPEC
--csv FILE
--jsonl FILE
--no-live
```

Only one body mode may be used: form data, JSON, raw body, or body file.

## `intrude`

Creates one request per value and recursively replaces `{{VALUE}}`.

```bash
imr-intruder intrude --url URL_WITH_PLACEHOLDER [options]
```

Dataset options:

```text
-V, --value VALUE
-W, --values-file FILE
--value-column NAME
```

Values from files and repeated `--value` options are merged in order and deduplicated.

## `batch`

```bash
imr-intruder batch CONFIG.json [options]
```

Options may override the JSON configuration:

```text
--workers COUNT
--delay-ms MILLISECONDS
--csv FILE
--jsonl FILE
--no-live
```

## `web`

```bash
imr-intruder web [start|stop|status|open] [options]
```

`web` without an action is equivalent to `web start`.

Foreground:

```bash
imr-intruder web start --host 127.0.0.1 --port 7415
```

Background lifecycle:

```bash
imr-intruder web start --background --no-browser
imr-intruder web status
imr-intruder web open
imr-intruder web stop
```

Start options:

```text
--host HOST
--port PORT
--no-browser
--background
--log-file FILE
--allow-remote
--token TOKEN
```

## `doctor`

```bash
imr-intruder doctor
imr-intruder doctor --json
```

Checks Python, OpenSSL, required dependencies, temporary-directory access, and package version.

## `update`

```bash
imr-intruder update
imr-intruder update --pre
imr-intruder update --dry-run
```

The repository may require GitHub authentication when it is private.

## `version`

```bash
imr-intruder version
```

Displays the application signature, application version, Python version, and operating system.
