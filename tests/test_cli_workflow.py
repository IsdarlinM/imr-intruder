from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs

from imr_intruder.command import main


class CliHandler(BaseHTTPRequestHandler):
    received: list[dict[str, str]] = []

    def log_message(self, *args):
        pass

    def do_GET(self):
        body = json.dumps({"path": self.path}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        content_type = self.headers.get("Content-Type", "")
        if "application/json" in content_type:
            data = json.loads(raw)
        else:
            data = {
                key: values[0]
                for key, values in parse_qs(raw.decode(), keep_blank_values=True).items()
            }
        type(self).received.append(data)
        accepted = bool(data.get("username")) and data.get("password") == "fixed"
        body = json.dumps({"accepted": accepted}).encode()
        self.send_response(200 if accepted else 400)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class CliWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), CliHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.root = root
        self.env = patch.dict(
            os.environ,
            {
                "IMR_INTRUDER_HOME": str(root / "home"),
                "IMR_INTRUDER_CONFIG": str(root / "config"),
                "IMR_INTRUDER_STATE": str(root / "state"),
                "IMR_INTRUDER_DATA": str(root / "data"),
                "IMR_INTRUDER_CACHE": str(root / "cache"),
            },
        )
        self.env.start()
        CliHandler.received.clear()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def invoke(self, args: list[str]) -> int:
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            return main(args)

    def test_intrude_post_accepts_conventional_urlencoded_data(self):
        values = self.root / "users.txt"
        values.write_text("alice\nbob\n", encoding="utf-8")
        output = self.root / "results.json"
        code = self.invoke(
            [
                "intrude",
                "--url",
                self.url + "/Pi",
                "--method",
                "POST",
                "--data",
                "username={{USER}}&password=fixed",
                "--payload",
                f"USER={values}",
                "--mode",
                "sniper",
                "--workers",
                "1",
                "--quiet",
                "--output-json",
                str(output),
            ]
        )
        self.assertEqual(code, 0)
        self.assertEqual(
            CliHandler.received,
            [
                {"username": "alice", "password": "fixed"},
                {"username": "bob", "password": "fixed"},
            ],
        )
        results = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual([row["name"] for row in results], ["USER=alice", "USER=bob"])
        self.assertEqual([row["status"] for row in results], [200, 200])

    def test_batch_repeater_report_and_import_output_directory(self):
        batch = self.root / "batch.json"
        batch.write_text(
            json.dumps({"requests": [{"url": self.url + "/one"}, {"url": self.url + "/two"}]}),
            encoding="utf-8",
        )
        jsonl = self.root / "batch.jsonl"
        self.assertEqual(self.invoke(["batch", str(batch), "--quiet", "--jsonl", str(jsonl)]), 0)
        self.assertEqual(len(jsonl.read_text(encoding="utf-8").splitlines()), 2)

        raw = self.root / "request.txt"
        raw.write_text(
            f"GET {self.url}/repeat HTTP/1.1\nHost: 127.0.0.1:{self.server.server_port}\n\n",
            encoding="utf-8",
        )
        repeated = self.root / "repeat.json"
        self.assertEqual(
            self.invoke(
                [
                    "repeater",
                    str(raw),
                    "--repeat",
                    "2",
                    "--quiet",
                    "--output-json",
                    str(repeated),
                ]
            ),
            0,
        )
        names = [row["name"] for row in json.loads(repeated.read_text(encoding="utf-8"))]
        self.assertEqual(names, ["repeater-r1", "repeater-r2"])

        imported = self.root / "nested" / "imported.json"
        self.assertEqual(self.invoke(["import", "raw", str(raw), "--output", str(imported)]), 0)
        self.assertTrue(imported.is_file())

        report = self.root / "report.html"
        self.assertEqual(self.invoke(["report", str(repeated), "--output", str(report)]), 0)
        self.assertIn("imr-intruder report", report.read_text(encoding="utf-8"))

        single = self.root / "single.json"
        single.write_text(
            json.dumps(
                [
                    {
                        "index": 1,
                        "name": "single",
                        "status": 200,
                        "size_bytes": 1,
                        "elapsed_ms": 1,
                        "similarity": None,
                        "cluster": None,
                        "anomaly_score": None,
                    }
                ]
            ),
            encoding="utf-8",
        )
        single_report = self.root / "single-report.html"
        self.assertEqual(self.invoke(["report", str(single), "--output", str(single_report)]), 0)
        self.assertTrue(single_report.is_file())

    def test_remaining_cli_dispatchers(self):
        self.assertEqual(self.invoke(["doctor", "--json"]), 0)
        self.assertEqual(self.invoke(["version"]), 0)
        self.assertEqual(self.invoke(["plugins"]), 0)

        with patch("imr_intruder.cli_actions.fetch_page", return_value={"status": 200}):
            self.assertEqual(self.invoke(["browser", self.url]), 0)
        with patch(
            "imr_intruder.cli_actions.run_websocket",
            return_value=[{"sent": "x", "received": "y", "error": ""}],
        ):
            self.assertEqual(self.invoke(["websocket", "ws://127.0.0.1/", "--message", "x"]), 0)
        with patch(
            "imr_intruder.cli_actions.run_websocket",
            return_value=[{"sent": "x", "received": "", "error": "timeout"}],
        ):
            self.assertEqual(self.invoke(["websocket", "ws://127.0.0.1/", "--message", "x"]), 1)

        with patch("imr_intruder.cli_actions.web_status", return_value={"running": True}) as status:
            self.assertEqual(self.invoke(["web", "status"]), 0)
            status.assert_called_once()
        with patch("imr_intruder.cli_actions.open_ui", return_value="http://127.0.0.1:7415"):
            self.assertEqual(self.invoke(["web", "open"]), 0)
        with patch("imr_intruder.cli_actions.web_stop", return_value={"stopped": True}):
            self.assertEqual(self.invoke(["web", "stop"]), 0)

        token_output = StringIO()
        with redirect_stdout(token_output), redirect_stderr(StringIO()):
            self.assertEqual(main(["collab", "create-token", "operator", "--role", "operator"]), 0)
        self.assertEqual(self.invoke(["collab", "list"]), 0)
        self.assertEqual(self.invoke(["collab", "revoke", "operator"]), 0)

    def test_session_scalar_values_and_workspace_subcommands(self):
        self.assertEqual(self.invoke(["session", "create", "typed"]), 0)
        self.assertEqual(self.invoke(["session", "set", "typed", "verify_tls", "false"]), 0)
        self.assertEqual(self.invoke(["session", "set", "typed", "retries", "2"]), 0)
        from imr_intruder.storage import load_session

        session = load_session("typed")
        self.assertIs(session["verify_tls"], False)
        self.assertEqual(session["retries"], 2)
        self.assertEqual(self.invoke(["session", "show", "typed"]), 0)
        self.assertEqual(self.invoke(["session", "list", "--json"]), 0)

        self.assertEqual(self.invoke(["workspace", "create", "typed-workspace"]), 0)
        self.assertEqual(self.invoke(["workspace", "use", "typed-workspace"]), 0)
        self.assertEqual(self.invoke(["workspace", "show"]), 0)
        self.assertEqual(self.invoke(["workspace", "list", "--json"]), 0)
        self.assertEqual(self.invoke(["session", "delete", "typed"]), 0)

    def test_history_lifecycle_and_structured_stdout(self):
        output = StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            self.assertEqual(
                main(["request", "--url", self.url + "/history", "--format", "json"]),
                0,
            )
        self.assertEqual(json.loads(output.getvalue())[0]["status"], 200)
        history_dir = self.root / "data" / "history"
        records = list(history_dir.glob("*.json"))
        self.assertEqual(len(records), 1)
        job_id = records[0].stem
        self.assertEqual(self.invoke(["history", "list", "--json"]), 0)
        self.assertEqual(self.invoke(["history", "show", job_id]), 0)
        self.assertEqual(self.invoke(["history", "replay", job_id, "--quiet"]), 0)
        self.assertEqual(self.invoke(["history", "delete", job_id]), 0)

    def test_update_dispatchers_with_mocked_network(self):
        from types import SimpleNamespace

        available = SimpleNamespace(
            current="1.4.0", latest="1.4.1", available=True, source="release"
        )
        current = SimpleNamespace(
            current="1.4.0", latest="1.4.0", available=False, source="release"
        )
        with patch("imr_intruder.cli_actions.check_update", return_value=available):
            self.assertEqual(self.invoke(["check-update"]), 0)
        with patch("imr_intruder.cli_actions.check_update", return_value=current):
            self.assertEqual(self.invoke(["check-update"]), 2)
            self.assertEqual(self.invoke(["update", "--dry-run"]), 0)
        with (
            patch("imr_intruder.cli_actions.check_update", return_value=available),
            patch(
                "imr_intruder.cli_actions.install_update",
                return_value={"status": "dry-run"},
            ) as installer,
        ):
            self.assertEqual(self.invoke(["update", "--dry-run"]), 0)
            installer.assert_called_once()

    def test_update_stops_stale_web_process_before_installing(self):
        from types import SimpleNamespace

        available = SimpleNamespace(
            current="1.3.3", latest="1.5.0", available=True, source="release"
        )
        with (
            patch("imr_intruder.cli_actions.check_update", return_value=available),
            patch("imr_intruder.cli_actions.web_status", return_value={"running": True}),
            patch("imr_intruder.cli_actions.web_stop") as stop,
            patch(
                "imr_intruder.cli_actions.install_update",
                return_value={"installed": True, "version": "1.5.0"},
            ),
        ):
            self.assertEqual(self.invoke(["update"]), 0)
            stop.assert_called_once_with()

    def test_help_for_every_cli_command(self):
        commands = [
            ["request"],
            ["intrude"],
            ["batch"],
            ["repeater"],
            ["import"],
            ["session"],
            ["workspace"],
            ["history"],
            ["report"],
            ["macro"],
            ["websocket"],
            ["browser"],
            ["plugins"],
            ["collab"],
            ["web"],
            ["check-update"],
            ["update"],
            ["doctor"],
            ["version"],
            ["session", "create"],
            ["session", "list"],
            ["session", "show"],
            ["session", "set"],
            ["session", "cookies"],
            ["session", "delete"],
            ["workspace", "create"],
            ["workspace", "list"],
            ["workspace", "use"],
            ["workspace", "show"],
            ["workspace", "export"],
            ["history", "list"],
            ["history", "show"],
            ["history", "delete"],
            ["history", "replay"],
            ["collab", "create-token"],
            ["collab", "list"],
            ["collab", "revoke"],
        ]
        from imr_intruder.cli_parser import build_parser

        for command in commands:
            with self.subTest(command=command):
                output = StringIO()
                with (
                    redirect_stdout(output),
                    redirect_stderr(output),
                    self.assertRaises(SystemExit) as raised,
                ):
                    build_parser().parse_args([*command, "--help"])
                self.assertEqual(raised.exception.code, 0)
                self.assertIn("usage:", output.getvalue().lower())


if __name__ == "__main__":
    unittest.main()
