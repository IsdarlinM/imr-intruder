from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from imr_intruder.cli import build_parser, main


class CliTests(unittest.TestCase):
    def test_all_modes_have_help(self):
        parser = build_parser()
        help_text = parser.format_help()
        for command in ("request", "intrude", "batch", "web", "doctor", "update", "version"):
            self.assertIn(command, help_text)

    def test_version(self):
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["version"])
        self.assertEqual(code, 0)
        self.assertIn("imr-intruder", output.getvalue())

    def test_doctor_json(self):
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["doctor", "--json"])
        data = json.loads(output.getvalue())
        self.assertIn(code, (0, 1))
        self.assertIn("dependencies", data)

    def test_web_command_passes_options(self):
        with patch("imr_intruder.web.run_server") as run_server:
            code = main(["web", "--port", "8123", "--no-browser"])
        self.assertEqual(code, 0)
        run_server.assert_called_once_with(
            host="127.0.0.1",
            port=8123,
            open_browser=False,
            allow_remote=False,
            token=None,
        )

    def test_batch_validation_error(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "bad.json"
            path.write_text("{}", encoding="utf-8")
            code = main(["batch", str(path), "--no-live"])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
