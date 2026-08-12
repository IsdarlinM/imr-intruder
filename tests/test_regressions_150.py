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

from imr_intruder.cli_parser import build_parser
from imr_intruder.cli_runtime import cmd_batch
from imr_intruder.collaboration import create_token, list_tokens, verify_token
from imr_intruder.core import execute_request, parse_columns, results_to_csv, run_requests
from imr_intruder.importers import parse_raw_request
from imr_intruder.macros import run_macro
from imr_intruder.payloads import build_requests
from imr_intruder.storage import create_workspace, set_current_workspace
from imr_intruder.web import _parse_urlencoded, create_app


class RegressionHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        if self.path == "/set-cookie":
            body = b"cookie set"
            self.send_response(200)
            self.send_header("Set-Cookie", "sid=active; Path=/")
        elif self.path == "/needs-cookie":
            accepted = "sid=active" in self.headers.get("Cookie", "")
            body = b"accepted" if accepted else b"missing"
            self.send_response(200 if accepted else 401)
        elif self.path == "/truncated-a":
            body = b"identical-prefix-A"
            self.send_response(200)
        elif self.path == "/truncated-b":
            body = b"identical-prefix-B"
            self.send_response(200)
        else:
            body = b"prefix foo42 suffix"
            self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class Release150Regressions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), RegressionHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def environment(self, root: Path) -> dict[str, str]:
        return {
            "IMR_INTRUDER_HOME": str(root / "home"),
            "IMR_INTRUDER_CONFIG": str(root / "config"),
            "IMR_INTRUDER_STATE": str(root / "state"),
            "IMR_INTRUDER_DATA": str(root / "data"),
            "IMR_INTRUDER_CACHE": str(root / "cache"),
        }

    def test_regex_columns_use_streamed_preview(self):
        result = execute_request(
            1,
            {"url": self.url + "/regex"},
            parse_columns([r"capture=regex:(foo\d+)"]),
        )
        self.assertEqual(result["custom"]["capture"], "foo42")

    def test_duplicate_urlencoded_values_are_preserved(self):
        self.assertEqual(
            _parse_urlencoded("role=user&role=admin"),
            {"role": ["user", "admin"]},
        )

    def test_secret_payloads_do_not_leak_to_evidence_or_csv(self):
        secret = "DEMO_SECRET_123"
        request = build_requests({"url": self.url + "/?token={{TOKEN}}"}, {"TOKEN": [secret]})[0]
        result = execute_request(1, request)
        self.assertNotIn(secret, result["name"])
        self.assertNotIn(secret, result["url"])
        self.assertNotIn(secret, result["final_request_url"])
        self.assertNotIn(secret, results_to_csv([result]))

    def test_truncated_responses_with_different_tail_are_not_identical(self):
        rows = run_requests(
            [
                {"url": self.url + "/truncated-a"},
                {"url": self.url + "/truncated-b"},
            ],
            body_limit=len(b"identical-prefix-"),
        )
        self.assertNotEqual(rows[0]["body_hash"], rows[1]["body_hash"])
        self.assertNotEqual(rows[0]["cluster"], rows[1]["cluster"])
        self.assertIsNone(rows[1]["similarity"])

    def test_workspace_parent_name_is_rejected(self):
        with (
            tempfile.TemporaryDirectory() as temp,
            patch.dict(os.environ, self.environment(Path(temp))),
        ):
            create_workspace("safe")
            with self.assertRaises(ValueError):
                set_current_workspace("..")

    def test_macro_carries_response_cookies_to_later_steps(self):
        with tempfile.TemporaryDirectory() as temp:
            macro = Path(temp) / "macro.json"
            macro.write_text(
                json.dumps(
                    {
                        "steps": [
                            {"request": {"url": self.url + "/set-cookie"}},
                            {
                                "request": {"url": self.url + "/needs-cookie"},
                                "require_status": 200,
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            rows = run_macro(macro)
            self.assertEqual(rows[-1]["status"], 200)

    def test_raw_host_header_is_case_insensitive(self):
        parsed = parse_raw_request("GET / HTTP/1.1\nHOST: example.test\n")
        self.assertEqual(parsed["url"], "https://example.test/")

    def test_explicit_batch_default_takes_precedence(self):
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp) / "batch.json"
            config.write_text(
                json.dumps({"requests": [{"url": self.url}], "workers": 7}),
                encoding="utf-8",
            )
            args = build_parser().parse_args(["batch", str(config), "--workers", "1", "--quiet"])
            captured: dict[str, int] = {}

            def fake_run(run_args, _requests):
                captured["workers"] = run_args.workers
                return []

            with patch("imr_intruder.cli_runtime._run", side_effect=fake_run):
                cmd_batch(args)
            self.assertEqual(captured["workers"], 1)

    def test_web_history_library_import_and_exports(self):
        with (
            tempfile.TemporaryDirectory() as temp,
            patch.dict(os.environ, self.environment(Path(temp))),
        ):
            token = "release-token"
            client = TestClient(create_app(token))
            headers = {"X-Request-Token": token}
            saved = client.put(
                "/api/requests/demo",
                headers=headers,
                json={"name": "demo", "url": self.url},
            )
            self.assertEqual(saved.status_code, 200)
            self.assertEqual(client.get("/api/requests", headers=headers).json(), ["demo"])
            imported = client.post(
                "/api/import",
                headers=headers,
                json={"kind": "curl", "content": f"curl {self.url}/regex"},
            )
            self.assertEqual(imported.json()["requests"][0]["url"], self.url + "/regex")
            created = client.post("/api/jobs", headers=headers, json={"url": self.url})
            job_id = created.json()["job_id"]
            client.get(f"/api/jobs/{job_id}/events", headers=headers)
            history = client.get("/api/history", headers=headers).json()
            self.assertEqual(history[0]["job_id"], job_id)
            self.assertEqual(
                client.get(f"/api/jobs/{job_id}/json", headers=headers).status_code, 200
            )
            self.assertEqual(
                client.get(f"/api/jobs/{job_id}/jsonl", headers=headers).status_code, 200
            )

    def test_web_scope_rejects_targets_outside_allowlist(self):
        token = "scope-token"
        client = TestClient(
            create_app(token, allowed_hosts=["allowed.example"], persist_history=False)
        )
        response = client.post(
            "/api/jobs",
            headers={"X-Request-Token": token},
            json={"url": "https://outside.example/"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("outside the configured web scope", response.json()["detail"])

    def test_collaboration_tokens_include_expiration(self):
        with (
            tempfile.TemporaryDirectory() as temp,
            patch.dict(os.environ, self.environment(Path(temp))),
        ):
            token = create_token("temporary", "viewer", expires_hours=1)
            self.assertEqual(verify_token(token), ("temporary", "viewer"))
            row = list_tokens()[0]
            self.assertTrue(row["active"])
            self.assertTrue(row["expires_at"])


if __name__ == "__main__":
    unittest.main()
