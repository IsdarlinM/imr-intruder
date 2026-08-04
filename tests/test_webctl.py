from __future__ import annotations

import os
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from imr_intruder.webctl import start_background, status, stop


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class WebControlTests(unittest.TestCase):
    def test_background_lifecycle(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            env = {
                "IMR_INTRUDER_HOME": str(root / "home"),
                "IMR_INTRUDER_CONFIG": str(root / "config"),
                "IMR_INTRUDER_STATE": str(root / "state"),
                "IMR_INTRUDER_DATA": str(root / "data"),
                "IMR_INTRUDER_CACHE": str(root / "cache"),
                "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
            }
            with patch.dict(os.environ, env, clear=False):
                port = free_port()
                started = start_background("127.0.0.1", port, "--dash-prefixed-token", False, False)
                try:
                    self.assertTrue(started["running"])
                    current = status()
                    self.assertTrue(current["running"])
                    self.assertEqual(current["port"], port)
                finally:
                    stopped = stop()
                self.assertTrue(stopped["stopped"])
                self.assertFalse(status()["running"])

    def test_stop_does_not_kill_unverified_stale_pid(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            env = {
                "IMR_INTRUDER_HOME": str(root / "home"),
                "IMR_INTRUDER_CONFIG": str(root / "config"),
                "IMR_INTRUDER_STATE": str(root / "state"),
                "IMR_INTRUDER_DATA": str(root / "data"),
                "IMR_INTRUDER_CACHE": str(root / "cache"),
            }
            with patch.dict(os.environ, env, clear=False):
                from imr_intruder.paths import ensure_paths
                from imr_intruder.storage import atomic_json_write
                paths = ensure_paths()
                atomic_json_write(paths.web_state, {"pid": os.getpid(), "url": "http://127.0.0.1:1"})
                result = stop()
                self.assertFalse(result["stopped"])
                self.assertEqual(result["reason"], "stale state removed")


if __name__ == "__main__":
    unittest.main()
