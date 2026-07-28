from __future__ import annotations

import os
import socket
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from imr_intruder.webctl import start_background, stop_background, web_status


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class WebControlTests(unittest.TestCase):
    def test_background_lifecycle(self):
        with TemporaryDirectory() as temp:
            port = free_port()
            env = {"XDG_STATE_HOME": temp}
            with patch.dict(os.environ, env, clear=False):
                state = start_background(
                    host="127.0.0.1",
                    port=port,
                    open_browser=False,
                    allow_remote=False,
                    token=None,
                    log_file=Path(temp) / "web.log",
                )
                try:
                    self.assertTrue(state["running"])
                    status = web_status()
                    self.assertTrue(status["running"])
                    self.assertTrue(status["healthy"])
                    self.assertEqual(status["port"], port)
                finally:
                    self.assertTrue(stop_background())
                self.assertFalse(web_status()["running"])

    def test_remote_background_generates_page_token(self):
        with TemporaryDirectory() as temp:
            port = free_port()
            with patch.dict(os.environ, {"XDG_STATE_HOME": temp}, clear=False):
                state = start_background(
                    host="0.0.0.0",
                    port=port,
                    open_browser=False,
                    allow_remote=True,
                    token=None,
                    log_file=Path(temp) / "remote-web.log",
                )
                try:
                    self.assertIn("?token=", state["access_url"])
                    import urllib.request

                    with urllib.request.urlopen(state["access_url"], timeout=3) as response:  # noqa: S310
                        self.assertEqual(response.status, 200)
                finally:
                    self.assertTrue(stop_background())


if __name__ == "__main__":
    unittest.main()
