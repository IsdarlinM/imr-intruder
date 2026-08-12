from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from imr_intruder.report import build_html_report


class ReportTests(unittest.TestCase):
    def test_report_redacts_secret_like_keys_and_url_parameters(self):
        rows = [
            {
                "index": 1,
                "name": "redaction",
                "status": 200,
                "access_token": "top-secret-token",
                "csrf_value": "csrf-secret",
                "url": "https://example.test/path?access_token=url-secret&visible=yes",
                "final_request_url": "https://example.test/path?api_key=key-secret",
                "custom": {"session_id": "session-secret", "public": "kept"},
            }
        ]
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "report.html"
            build_html_report(rows, output)
            document = output.read_text(encoding="utf-8")
        for secret in (
            "top-secret-token",
            "csrf-secret",
            "url-secret",
            "key-secret",
            "session-secret",
        ):
            self.assertNotIn(secret, document)
        self.assertIn("visible=yes", document)
        self.assertIn("kept", document)


if __name__ == "__main__":
    unittest.main()
