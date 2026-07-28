from __future__ import annotations

import json
import threading
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fastapi.testclient import TestClient

from imr_intruder.web import create_app, parse_lines_map


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        if b"redirect" in body:
            self.send_response(302)
            self.send_header("Location", "/result")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        payload = b"A" * 128
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("X-Web-Test", "ok")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format, *_args):
        return


@contextmanager
def server_url():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}/test"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class WebTests(unittest.TestCase):
    def test_header_equals_value_may_contain_colon(self):
        parsed = parse_lines_map("Referer=https://example.test/path", "Headers", True)
        self.assertEqual(parsed["Referer"], "https://example.test/path")

    def setUp(self):
        self.token = "test-token-123"
        self.app = create_app(request_token=self.token)
        self.client = TestClient(self.app)
        self.headers = {"X-Request-Token": self.token}

    def test_index_health_assets_and_headers(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"imr-intruder", response.content)
        self.assertIn(b"{{VALUE}}", response.content)
        self.assertEqual(response.headers["x-frame-options"], "DENY")
        self.assertIn("default-src 'self'", response.headers["content-security-policy"])
        self.assertEqual(self.client.get("/health").json()["status"], "ok")
        self.assertEqual(self.client.head("/").status_code, 200)
        self.assertEqual(self.client.get("/static/app.js").status_code, 200)

    def test_remote_page_requires_token(self):
        app = create_app(request_token=self.token, require_page_token=True)
        client = TestClient(app)
        self.assertEqual(client.get("/").status_code, 403)
        accepted = client.get(f"/?token={self.token}")
        self.assertEqual(accepted.status_code, 200)
        self.assertIn("imr_intruder_token", accepted.headers.get("set-cookie", ""))

    def test_api_token_is_required(self):
        self.assertEqual(self.client.post("/api/jobs", json={}).status_code, 403)

    def test_live_job_stream_and_csv(self):
        with server_url() as url:
            payload = {
                "url": url,
                "method": "POST",
                "body_type": "form",
                "body": "value={{VALUE}}",
                "headers": "X-Lab: authorized",
                "params": "",
                "cookies": "",
                "values": "alpha\nredirect",
                "columns": "location=header:Location\nweb=header:X-Web-Test",
                "workers": 2,
                "timeout": 5,
                "delay_ms": 0,
                "verify_tls": True,
                "follow_redirects": False,
            }
            created = self.client.post("/api/jobs", json=payload, headers=self.headers)
            self.assertEqual(created.status_code, 202)
            job_id = created.json()["job_id"]

            stream = self.client.get(f"/api/jobs/{job_id}/events", headers=self.headers)
            self.assertEqual(stream.status_code, 200)
            events = [
                json.loads(line)
                for line in stream.content.decode().splitlines()
                if line.strip()
            ]
            names = [event["event"] for event in events]
            self.assertIn("meta", names)
            self.assertEqual(names.count("result"), 2)
            self.assertIn("done", names)

            csv_response = self.client.get(f"/api/jobs/{job_id}/csv", headers=self.headers)
            self.assertEqual(csv_response.status_code, 200)
            self.assertIn(b"valor_probado", csv_response.content)
            self.assertIn(b"location", csv_response.content)

    def test_dataset_requires_placeholder(self):
        payload = {
            "url": "https://example.test",
            "method": "GET",
            "body_type": "none",
            "values": "alpha\nbeta",
            "workers": 1,
            "timeout": 5,
            "delay_ms": 0,
        }
        response = self.client.post("/api/jobs", json=payload, headers=self.headers)
        self.assertEqual(response.status_code, 400)
        self.assertIn("{{VALUE}}", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
