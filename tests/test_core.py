from __future__ import annotations

import io
import json
import threading
import unittest
from contextlib import contextmanager, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlparse

from imr_intruder.core import (
    build_intruder_requests,
    load_values,
    parse_headers,
    run_requests,
)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, status: int, payload: bytes, **headers: str) -> None:
        self.send_response(status)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Content-Type", headers.pop("Content-Type", "application/json"))
        self.send_header("X-Test-Server", "imr-suite")
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/redirect":
            self._send(302, b"", Location="/final")
            return
        payload = json.dumps(
            {
                "method": "GET",
                "query": parse_qs(parsed.query),
                "marker": "alpha-marker",
            }
        ).encode()
        self._send(200, payload)

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        content_type = self.headers.get("Content-Type", "")
        if b"redirect-me" in body:
            self._send(302, b"", Location="/authorized-result")
            return
        payload = json.dumps(
            {
                "method": "POST",
                "content_type": content_type,
                "body": body.decode("utf-8", errors="replace"),
                "request_header": self.headers.get("X-Test-ID", ""),
                "nested": {"id": 73},
            }
        ).encode()
        self._send(200, payload)

    def log_message(self, _format, *_args):
        return


@contextmanager
def server_url():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class CoreTests(unittest.TestCase):
    def test_header_equals_value_may_contain_colon(self):
        parsed = parse_headers(["Referer=https://example.test/path"])
        self.assertEqual(parsed["Referer"], "https://example.test/path")

    def test_values_and_recursive_placeholder(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "values.txt"
            path.write_text("# comment\nalpha\nbeta\nalpha\n\n", encoding="utf-8")
            values = load_values(path, ["gamma"])
        self.assertEqual(values, ["alpha", "beta", "gamma"])

        requests_cfg = build_intruder_requests(
            {
                "method": "POST",
                "url": "https://example.test/{{VALUE}}",
                "headers": {"X-Test": "{{VALUE}}"},
                "params": {"id": "{{VALUE}}"},
                "json": {"items": ["{{VALUE}}"]},
            },
            values[:2],
        )
        self.assertEqual(requests_cfg[0]["url"], "https://example.test/alpha")
        self.assertEqual(requests_cfg[1]["headers"]["X-Test"], "beta")
        self.assertEqual(requests_cfg[0]["json"]["items"], ["alpha"])
        self.assertEqual(requests_cfg[0]["name"], "alpha")

    def test_placeholder_is_required(self):
        with self.assertRaisesRegex(ValueError, "no contiene"):
            build_intruder_requests({"url": "https://example.test"}, ["alpha"])

    def test_get_post_redirect_columns_and_exports(self):
        with server_url() as base, TemporaryDirectory() as temp:
            csv_path = Path(temp) / "results.csv"
            output = io.StringIO()
            requests_cfg = [
                {
                    "name": "get",
                    "method": "GET",
                    "url": f"{base}/echo",
                    "params": {"id": "7"},
                    "columns": [
                        {"name": "server", "source": "header", "key": "X-Test-Server"},
                        {"name": "marker", "source": "regex", "pattern": '"marker": "([^"]+)', "group": 1},
                        {"name": "tested", "source": "request_param", "key": "id"},
                    ],
                },
                {
                    "name": "post-json",
                    "method": "POST",
                    "url": f"{base}/echo",
                    "headers": {"X-Test-ID": "abc"},
                    "json": {"enabled": True},
                    "columns": [
                        {"name": "nested", "source": "json", "key": "nested.id"},
                        {"name": "final_url", "source": "response", "key": "url"},
                    ],
                },
                {
                    "name": "redirect",
                    "method": "POST",
                    "url": f"{base}/echo",
                    "data": {"value": "redirect-me"},
                    "follow_redirects": False,
                    "columns": [
                        {"name": "location", "source": "header", "key": "Location", "default": "-"}
                    ],
                },
            ]
            with redirect_stdout(output):
                results = run_requests(
                    requests_cfg,
                    workers=2,
                    delay_ms=1,
                    csv_path=csv_path,
                    live=False,
                )

            self.assertEqual(output.getvalue(), "")
            self.assertEqual([item["status"] for item in results], [200, 200, 302])
            self.assertGreater(results[0]["size_bytes"], 0)
            self.assertEqual(results[0]["custom"]["server"], "imr-suite")
            self.assertEqual(results[0]["custom"]["marker"], "alpha-marker")
            self.assertEqual(results[0]["custom"]["tested"], "7")
            self.assertEqual(results[1]["custom"]["nested"], "73")
            self.assertEqual(results[2]["custom"]["location"], "/authorized-result")
            self.assertTrue(csv_path.exists())
            self.assertIn("location", csv_path.read_text(encoding="utf-8-sig"))

    def test_invalid_request_returns_structured_error(self):
        results = run_requests(
            [{"name": "bad", "method": "GET", "url": "file:///etc/passwd"}],
            live=False,
        )
        self.assertIn("URL inválida", results[0]["error"])


if __name__ == "__main__":
    unittest.main()
