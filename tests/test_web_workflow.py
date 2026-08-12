from __future__ import annotations

import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs

from fastapi.testclient import TestClient

from imr_intruder.web import build_web_requests, create_app

ROOT = Path(__file__).resolve().parents[1]


class PostHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        content_type = self.headers.get("Content-Type", "")
        accepted = False
        username = ""
        if "application/json" in content_type:
            try:
                data = json.loads(raw)
                username = str(data.get("username", ""))
                accepted = bool(username) and data.get("password") == "fixed"
            except json.JSONDecodeError:
                accepted = False
        elif "application/x-www-form-urlencoded" in content_type:
            data = parse_qs(raw.decode(), keep_blank_values=True)
            username = data.get("username", [""])[0]
            accepted = bool(username) and data.get("password", [""])[0] == "fixed"
        body = json.dumps({"accepted": accepted, "username": username}).encode()
        self.send_response(200 if accepted else 400)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class WebWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), PostHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}/Pi"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.token = "workflow-token"
        self.client = TestClient(create_app(self.token))
        self.headers = {"X-Request-Token": self.token}

    def test_form_query_string_is_split_into_fields(self):
        requests, _, _ = build_web_requests(
            {
                "url": self.url,
                "method": "POST",
                "body_type": "form",
                "body": "username={{USER}}&password=fixed",
                "payloads": "[USER]\nalice\nbob",
                "mode": "sniper",
            }
        )
        self.assertEqual(
            [row["data"] for row in requests],
            [
                {"username": "alice", "password": "fixed"},
                {"username": "bob", "password": "fixed"},
            ],
        )
        self.assertEqual([row["name"] for row in requests], ["USER=alice", "USER=bob"])

    def test_full_web_post_scan_and_enriched_snapshot(self):
        response = self.client.post(
            "/api/jobs",
            headers=self.headers,
            json={
                "url": self.url,
                "method": "POST",
                "body_type": "form",
                "body": "username={{USER}}&password=fixed",
                "payloads": "[USER]\nalice\nbob",
                "mode": "sniper",
                "workers": 1,
                "delay_ms": 0,
                "timeout": 5,
                "retries": 0,
                "verify_tls": True,
                "follow_redirects": False,
                "http2": False,
                "backoff": False,
                "max_requests": 10,
            },
        )
        self.assertEqual(response.status_code, 202, response.text)
        job_id = response.json()["job_id"]
        stream = self.client.get(f"/api/jobs/{job_id}/events", headers=self.headers)
        events = [json.loads(line) for line in stream.text.splitlines() if line.strip()]
        snapshots = [event for event in events if event["event"] == "snapshot"]
        self.assertEqual(len(snapshots), 1)
        final = snapshots[0]["results"]
        self.assertEqual([row["status"] for row in final], [200, 200])
        self.assertEqual([row["name"] for row in final], ["USER=alice", "USER=bob"])
        self.assertTrue(
            all(row["request_body_summary"]["password"] == "<REDACTED>" for row in final)
        )
        self.assertTrue(all(row["outcome"] == "http_response" for row in final))
        self.assertTrue(all("similarity" in row and "cluster" in row for row in final))

        status = self.client.get(f"/api/jobs/{job_id}", headers=self.headers)
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["status"], "done")
        csv_response = self.client.get(f"/api/jobs/{job_id}/csv", headers=self.headers)
        self.assertEqual(csv_response.status_code, 200)
        self.assertIn("outcome", csv_response.text.splitlines()[0])

    def test_backend_returns_specific_validation_details(self):
        missing_placeholder = self.client.post(
            "/api/jobs",
            headers=self.headers,
            json={
                "url": self.url,
                "method": "POST",
                "payloads": "alice\nbob",
            },
        )
        self.assertEqual(missing_placeholder.status_code, 400)
        self.assertIn("no placeholder", missing_placeholder.json()["detail"].lower())

        bad_json = self.client.post(
            "/api/jobs",
            headers=self.headers,
            json={
                "url": self.url,
                "method": "POST",
                "body_type": "json",
                "body": '{"username":',
            },
        )
        self.assertEqual(bad_json.status_code, 400)
        self.assertIn("invalid json body", bad_json.json()["detail"].lower())

    def test_pause_resume_and_cancel_state_transitions(self):
        started = threading.Event()

        def fake_run(requests, *, cancel_event=None, pause_event=None, callback=None, **options):
            started.set()
            while not cancel_event.is_set():
                time.sleep(0.01)
            return []

        with patch("imr_intruder.web.run_requests", side_effect=fake_run):
            response = self.client.post(
                "/api/jobs",
                headers=self.headers,
                json={"url": self.url, "method": "POST"},
            )
            self.assertEqual(response.status_code, 202)
            job_id = response.json()["job_id"]
            self.assertTrue(started.wait(1))
            paused = self.client.post(f"/api/jobs/{job_id}/pause", headers=self.headers)
            self.assertEqual(paused.status_code, 200)
            self.assertEqual(paused.json()["status"], "paused")
            resumed = self.client.post(f"/api/jobs/{job_id}/resume", headers=self.headers)
            self.assertEqual(resumed.status_code, 200)
            cancelled = self.client.post(f"/api/jobs/{job_id}/cancel", headers=self.headers)
            self.assertEqual(cancelled.status_code, 200)
            self.assertEqual(cancelled.json()["status"], "cancelling")
            second_cancel = self.client.post(f"/api/jobs/{job_id}/cancel", headers=self.headers)
            self.assertEqual(second_cancel.status_code, 409)

    def test_all_web_controls_are_wired(self):
        html = (ROOT / "src" / "imr_intruder" / "templates" / "index.html").read_text(
            encoding="utf-8"
        )
        js = (ROOT / "src" / "imr_intruder" / "static" / "app.js").read_text(encoding="utf-8")
        for control in (
            "runButton",
            "pauseButton",
            "cancelButton",
            "csvLink",
            "themeButton",
            "drawerClose",
            "search",
            "statusFilter",
            "differenceOnly",
        ):
            self.assertIn(f'id="{control}"', html)
        for action in (
            "elements.run.addEventListener",
            "elements.pause.addEventListener",
            "elements.cancel.addEventListener",
            "elements.drawerClose.addEventListener",
        ):
            self.assertIn(action, js)
        self.assertIn('api("/api/jobs"', js)
        self.assertIn('event.event === "snapshot"', js)
        self.assertIn("validatePayload", js)
        self.assertNotIn("/csv?token=", js)


if __name__ == "__main__":
    unittest.main()
