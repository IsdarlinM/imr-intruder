from __future__ import annotations

import os
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from imr_intruder.command import build_parser, main


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        body = b"ok"
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(body)


class CommandTests(unittest.TestCase):
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
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
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

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def invoke(self, args):
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            return main(args)

    def test_parser_has_all_top_level_commands(self):
        parser = build_parser()
        choices = next(action for action in parser._actions if action.dest == "command").choices
        expected = {
            "request",
            "intrude",
            "batch",
            "repeater",
            "import",
            "session",
            "workspace",
            "history",
            "report",
            "macro",
            "websocket",
            "browser",
            "plugins",
            "collab",
            "web",
            "check-update",
            "update",
            "doctor",
            "version",
        }
        self.assertTrue(expected.issubset(choices))

    def test_request_command(self):
        self.assertEqual(self.invoke(["request", "--url", self.url, "--quiet"]), 0)

    def test_session_commands(self):
        self.assertEqual(self.invoke(["session", "create", "lab"]), 0)
        self.assertEqual(self.invoke(["session", "show", "lab"]), 0)
        self.assertEqual(self.invoke(["session", "delete", "lab"]), 0)

    def test_workspace_commands(self):
        self.assertEqual(self.invoke(["workspace", "create", "lab"]), 0)
        self.assertEqual(self.invoke(["workspace", "use", "lab"]), 0)
        self.assertEqual(self.invoke(["workspace", "show"]), 0)

    def test_import_command(self):
        root = Path(self.temp.name)
        raw = root / "r.txt"
        out = root / "b.json"
        raw.write_text(f"GET {self.url}/ HTTP/1.1\nHost: 127.0.0.1\n")
        self.assertEqual(self.invoke(["import", "raw", str(raw), "--output", str(out)]), 0)
        self.assertTrue(out.is_file())
