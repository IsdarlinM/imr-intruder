from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import urllib.request
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, status: int, body: bytes, **headers: str) -> None:
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Type", headers.pop("Content-Type", "application/json"))
        self.send_header("X-Smoke-Test", "imr-intruder")
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        payload = json.dumps(
            {"method": "GET", "path": parsed.path, "query": parse_qs(parsed.query)}
        ).encode()
        self._send(200, payload)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        payload = json.dumps(
            {
                "method": "POST",
                "body": body.decode("utf-8", errors="replace"),
                "content_type": self.headers.get("Content-Type", ""),
            }
        ).encode()
        self._send(200, payload)

    def log_message(self, _format: str, *_args: object) -> None:
        return


@contextmanager
def local_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def run(command: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    label = " ".join(command[3:]) if len(command) > 3 else " ".join(command)
    print(f"[{'PASS' if completed.returncode == 0 else 'FAIL'}] {label}")
    if completed.returncode != 0:
        print(completed.stdout)
        print(completed.stderr, file=sys.stderr)
        raise SystemExit(completed.returncode)
    return completed


def main() -> int:
    parser = argparse.ArgumentParser(description="Local imr-intruder command smoke suite")
    parser.add_argument(
        "--external-url",
        help="Optional single external GET target for an explicitly authorized availability check",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src") + os.pathsep + env.get("PYTHONPATH", "")
    base_command = [sys.executable, "-m", "imr_intruder"]

    with tempfile.TemporaryDirectory(prefix="imr-intruder-smoke-") as temp, local_server() as base:
        temp_path = Path(temp)
        env["XDG_STATE_HOME"] = str(temp_path / "state")
        values = temp_path / "values.txt"
        values.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")

        run(base_command + ["--help"], env)
        run(base_command + ["version"], env)
        run(base_command + ["doctor", "--json"], env)
        run(base_command + ["update", "--dry-run"], env)

        run(
            base_command
            + [
                "request",
                "--url",
                f"{base}/echo",
                "--param",
                "id=7",
                "--column",
                "server=header:X-Smoke-Test",
                "--csv",
                str(temp_path / "request.csv"),
                "--jsonl",
                str(temp_path / "request.jsonl"),
                "--no-live",
            ],
            env,
        )
        run(
            base_command
            + [
                "request",
                "--url",
                f"{base}/echo",
                "--method",
                "POST",
                "--json",
                '{"enabled":true}',
                "--no-live",
            ],
            env,
        )
        run(
            base_command
            + [
                "intrude",
                "--url",
                f"{base}/echo",
                "--method",
                "POST",
                "--data",
                "value={{VALUE}}",
                "--values-file",
                str(values),
                "--workers",
                "2",
                "--delay-ms",
                "5",
                "--no-live",
            ],
            env,
        )

        batch = temp_path / "batch.json"
        batch.write_text(
            json.dumps(
                {
                    "workers": 2,
                    "defaults": {"timeout": 5, "verify_tls": True},
                    "requests": [
                        {"name": "get", "method": "GET", "url": f"{base}/one"},
                        {
                            "name": "post",
                            "method": "POST",
                            "url": f"{base}/two",
                            "data": {"value": "two"},
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        run(base_command + ["batch", str(batch), "--no-live"], env)

        web_port = free_port()
        run(
            base_command
            + [
                "web",
                "start",
                "--background",
                "--no-browser",
                "--port",
                str(web_port),
            ],
            env,
        )
        try:
            run(base_command + ["web", "status"], env)
            with urllib.request.urlopen(  # noqa: S310
                f"http://127.0.0.1:{web_port}/health", timeout=3
            ) as response:
                health = json.loads(response.read())
            if response.status != 200 or health.get("status") != "ok":
                raise SystemExit("Web health check failed")
            with urllib.request.urlopen(  # noqa: S310
                f"http://127.0.0.1:{web_port}/", timeout=3
            ) as response:
                page = response.read()
            if response.status != 200 or b"imr-intruder" not in page:
                raise SystemExit("Web page check failed")
            print("[PASS] web /health and / on 127.0.0.1")
        finally:
            run(base_command + ["web", "stop"], env)

        if args.external_url:
            run(
                base_command
                + [
                    "request",
                    "--url",
                    args.external_url,
                    "--method",
                    "GET",
                    "--workers",
                    "1",
                    "--timeout",
                    "15",
                    "--no-live",
                ],
                env,
            )

    print("All smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
