from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from imr_intruder.collaboration import create_token
from imr_intruder.web import build_web_requests, create_app


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        body = f"path={self.path}".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.token = "test-token"
        self.client = TestClient(create_app(self.token))

    def test_health_and_security_headers(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["x-frame-options"], "DENY")

    def test_page_loads(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("imr-intruder", response.text)

    def test_api_requires_token(self):
        response = self.client.post("/api/jobs", json={"url": self.url})
        self.assertEqual(response.status_code, 403)

    def test_job_stream(self):
        payload = {
            "url": self.url + "/{{VALUE}}",
            "payloads": "a\nb",
            "workers": 2,
            "columns": "final=response:url",
        }
        response = self.client.post(
            "/api/jobs", headers={"X-Request-Token": self.token}, json=payload
        )
        self.assertEqual(response.status_code, 202)
        job = response.json()["job_id"]
        stream = self.client.get(f"/api/jobs/{job}/events", headers={"X-Request-Token": self.token})
        events = [json.loads(line) for line in stream.text.splitlines() if line.strip()]
        self.assertEqual(sum(event["event"] == "result" for event in events), 2)
        self.assertEqual(events[-1]["event"], "done")

    def test_remote_viewer_token_is_not_escalated(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            values = {
                "IMR_INTRUDER_HOME": str(root / "home"),
                "IMR_INTRUDER_CONFIG": str(root / "config"),
                "IMR_INTRUDER_STATE": str(root / "state"),
                "IMR_INTRUDER_DATA": str(root / "data"),
                "IMR_INTRUDER_CACHE": str(root / "cache"),
            }
            with patch.dict(os.environ, values):
                viewer = create_token("viewer", "viewer")
                operator = create_token("operator", "operator")
                client = TestClient(
                    create_app("admin-secret", require_page_token=True, multiuser=True)
                )
                page = client.get("/?token=" + viewer)
                self.assertEqual(page.status_code, 200)
                self.assertNotIn(viewer, page.text)
                self.assertNotIn("data-token", page.text)
                self.assertNotIn("admin-secret", page.text)
                denied = client.post(
                    "/api/jobs",
                    headers={"X-Request-Token": viewer},
                    json={"url": self.url},
                )
                self.assertEqual(denied.status_code, 403)
                allowed = client.post(
                    "/api/jobs",
                    headers={"X-Request-Token": operator},
                    json={"url": self.url},
                )
                self.assertEqual(allowed.status_code, 202)

    def test_build_multiple_payload_sections(self):
        requests, _, _ = build_web_requests(
            {
                "url": self.url + "/?u={{USER}}&t={{TOKEN}}",
                "payloads": "[USER]\na\nb\n[TOKEN]\nx\ny",
                "mode": "pitchfork",
            }
        )
        self.assertEqual(len(requests), 2)

    def test_strict_validation_happens_before_job_creation(self):
        for payload in (
            {"url": "http://"},
            {"url": self.url, "workers": 1.5},
            {"url": self.url, "match": "regex:["},
            {"url": self.url + "/{{VALUE}}", "payloads": "[VALUE]\na\n[UNUSED]\nb"},
        ):
            with self.subTest(payload=payload):
                response = self.client.post(
                    "/api/jobs", headers={"X-Request-Token": self.token}, json=payload
                )
                self.assertEqual(response.status_code, 400, response.text)

    def test_api_does_not_accept_tokens_from_query_strings(self):
        client = TestClient(create_app(self.token))
        response = client.post("/api/jobs?token=" + self.token, json={"url": self.url})
        self.assertEqual(response.status_code, 403)

    def test_job_body_is_limited(self):
        response = self.client.post(
            "/api/jobs",
            headers={"X-Request-Token": self.token, "Content-Type": "application/json"},
            content=b" " * (1024 * 1024 + 1),
        )
        self.assertEqual(response.status_code, 413)

    def test_event_history_can_be_replayed(self):
        created = self.client.post(
            "/api/jobs", headers={"X-Request-Token": self.token}, json={"url": self.url}
        )
        job = created.json()["job_id"]
        first = self.client.get(
            f"/api/jobs/{job}/events?after=0", headers={"X-Request-Token": self.token}
        )
        second = self.client.get(
            f"/api/jobs/{job}/events?after=0", headers={"X-Request-Token": self.token}
        )
        first_events = [json.loads(line) for line in first.text.splitlines() if line.strip()]
        second_events = [json.loads(line) for line in second.text.splitlines() if line.strip()]
        self.assertEqual(first_events, second_events)
        self.assertTrue(all("sequence" in event for event in first_events))

    def test_web_csv_includes_custom_columns_and_escapes_formulas(self):
        created = self.client.post(
            "/api/jobs",
            headers={"X-Request-Token": self.token},
            json={"url": self.url, "name": "=2+2", "columns": "evidence=literal:@cmd"},
        )
        job = created.json()["job_id"]
        self.client.get(f"/api/jobs/{job}/events", headers={"X-Request-Token": self.token})
        response = self.client.get(f"/api/jobs/{job}/csv", headers={"X-Request-Token": self.token})
        self.assertIn("evidence", response.text.splitlines()[0])
        self.assertIn("'=2+2", response.text)
        self.assertIn("'@cmd", response.text)
