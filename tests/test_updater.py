from __future__ import annotations

import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from imr_intruder.updater import _clean_env, _safe_extract, _verify_active_version


def archive(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, value in files.items():
            z.writestr(name, value)
    return buf.getvalue()


class UpdaterTests(unittest.TestCase):
    def test_safe_extract(self):
        with tempfile.TemporaryDirectory() as temp:
            root = _safe_extract(
                archive({"project/pyproject.toml": '[project]\nname="x"'}), Path(temp)
            )
            self.assertTrue((root / "pyproject.toml").is_file())

    def test_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                _safe_extract(archive({"../x": "bad", "project/pyproject.toml": "x"}), Path(temp))

    def test_clean_env(self):
        import os

        os.environ["PYTHONPATH"] = "bad"
        self.assertNotIn("PYTHONPATH", _clean_env())

    def test_active_version_must_match_downloaded_archive(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            (home / "current-version").write_text("1.3.3\n", encoding="utf-8")
            environment = {
                "IMR_INTRUDER_HOME": str(home),
                "IMR_INTRUDER_CONFIG": str(home / "config"),
                "IMR_INTRUDER_STATE": str(home / "state"),
                "IMR_INTRUDER_DATA": str(home / "data"),
                "IMR_INTRUDER_CACHE": str(home / "cache"),
            }
            with patch.dict("os.environ", environment):
                with self.assertRaisesRegex(RuntimeError, "still 1.3.3"):
                    _verify_active_version("1.5.0")
                (home / "current-version").write_text("1.5.0\n", encoding="utf-8")
                self.assertEqual(_verify_active_version("1.5.0"), "1.5.0")
