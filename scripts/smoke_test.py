from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import websockets

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        if self.path.startswith("/redirect"):
            self.send_response(302)
            self.send_header("Location", "/ok")
            self.end_headers()
            return
        if self.path.startswith("/token"):
            body = json.dumps({"token": "macro-token"}).encode()
        else:
            body = json.dumps({"path": self.path}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-Smoke", "yes")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        data = self.rfile.read(length)
        body = b"received:" + data
        self.send_response(201)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def run(args: list[str], env: dict[str, str], expected=(0,), timeout=60) -> subprocess.CompletedProcess[str]:
    command = [PYTHON, "-m", "imr_intruder.command", *args]
    result = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, timeout=timeout)
    if result.returncode not in expected:
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(command)}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")
    return result


async def websocket_echo(websocket):
    async for message in websocket:
        await websocket.send("echo:" + message)


def start_websocket(port: int, ready: threading.Event, stop: threading.Event) -> None:
    async def server_main():
        async with websockets.serve(websocket_echo, "127.0.0.1", port):
            ready.set()
            while not stop.is_set():
                await asyncio.sleep(0.05)
    asyncio.run(server_main())


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="imr-intruder-smoke-") as temp:
        root = Path(temp)
        env = dict(os.environ)
        env["PYTHONPATH"] = str(ROOT / "src")
        env.update({
            "IMR_INTRUDER_HOME": str(root / "home"),
            "IMR_INTRUDER_CONFIG": str(root / "config"),
            "IMR_INTRUDER_STATE": str(root / "state"),
            "IMR_INTRUDER_DATA": str(root / "data"),
            "IMR_INTRUDER_CACHE": str(root / "cache"),
        })
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_port}"
        try:
            run(["--help"], env)
            run(["version"], env)
            run(["doctor", "--json"], env)
            run(["plugins"], env)
            run(["request", "--url", url + "/ok", "--column", "smoke=header:X-Smoke", "--quiet", "--jsonl", str(root / "request.jsonl")], env)
            run(["request", "--url", url + "/post", "-X", "POST", "--json", '{"x":1}', "--quiet"], env)

            values = root / "values.txt"
            values.write_text("alpha\nbeta\n", encoding="utf-8")
            run(["intrude", "--url", url + "/{{VALUE}}", "--values-file", str(values), "--workers", "2", "--quiet", "--csv", str(root / "intrude.csv"), "--jsonl", str(root / "intrude.jsonl")], env)

            batch = root / "batch.json"
            batch.write_text(json.dumps({"requests": [{"name": "a", "url": url + "/a"}, {"name": "b", "url": url + "/b"}]}), encoding="utf-8")
            run(["batch", str(batch), "--quiet", "--output-json", str(root / "batch-results.json")], env)

            raw = root / "request.txt"
            raw.write_text(f"GET {url}/raw HTTP/1.1\nHost: 127.0.0.1\n", encoding="utf-8")
            run(["import", "raw", str(raw), "--output", str(root / "imported.json")], env)
            run(["repeater", str(raw), "--kind", "raw", "--repeat", "2", "--quiet"], env)

            run(["session", "create", "lab"], env)
            run(["session", "cookies", "lab", "--cookie", "session=test"], env)
            run(["request", "--session", "lab", "--url", url + "/session", "--quiet"], env)
            run(["workspace", "create", "assessment"], env)
            run(["workspace", "use", "assessment"], env)
            run(["workspace", "export", "assessment", "--output", str(root / "assessment.tar.gz")], env)

            macro = root / "macro.json"
            macro.write_text(json.dumps({"steps": [{"request": {"url": url + "/token"}, "extract": {"TOKEN": "json:token"}, "require_status": 200}, {"request": {"url": url + "/check?token={{TOKEN}}"}, "require_status": 200}]}), encoding="utf-8")
            run(["macro", str(macro), "--session", "lab", "--output", str(root / "macro.jsonl")], env)
            run(["report", str(root / "intrude.jsonl"), "--output", str(root / "report.html")], env)

            ws_port = free_port()
            ws_ready = threading.Event(); ws_stop = threading.Event()
            ws_thread = threading.Thread(target=start_websocket, args=(ws_port, ws_ready, ws_stop), daemon=True)
            ws_thread.start(); ws_ready.wait(5)
            run(["websocket", f"ws://127.0.0.1:{ws_port}", "--message", "ping"], env)
            ws_stop.set(); ws_thread.join(5)

            run(["collab", "create-token", "operator", "--role", "operator"], env)
            run(["collab", "list"], env)

            web_port = free_port()
            run(["web", "start", "--background", "--port", str(web_port), "--no-browser"], env)
            run(["web", "status"], env)
            with urllib.request.urlopen(f"http://127.0.0.1:{web_port}/health", timeout=5) as response:
                if response.status != 200:
                    raise RuntimeError("Web health endpoint failed")
            with urllib.request.urlopen(f"http://127.0.0.1:{web_port}/", timeout=5) as response:
                if b"imr-intruder" not in response.read():
                    raise RuntimeError("Web UI did not load")
            run(["web", "stop"], env)

            expected = ["request.jsonl", "intrude.csv", "intrude.jsonl", "batch-results.json", "imported.json", "assessment.tar.gz", "macro.jsonl", "report.html"]
            for name in expected:
                if not (root / name).is_file():
                    raise RuntimeError(f"Missing smoke artifact: {name}")
        finally:
            server.shutdown(); server.server_close()
    print("All imr-intruder smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
