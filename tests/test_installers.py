from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class InstallerTests(unittest.TestCase):
    def test_linux_installer_has_dependency_install_and_env(self):
        text = (ROOT / "install.sh").read_text(encoding="utf-8")
        self.assertIn("pip install", text)
        self.assertIn("requirements.txt", text)
        self.assertIn("IMR_INTRUDER_HOME", text)

    def test_windows_installer_configures_registry_and_dependencies(self):
        text = (ROOT / "install.cmd").read_text(encoding="utf-8")
        self.assertNotIn("powershell", text.lower())
        self.assertIn("windows_path.py", text)
        self.assertIn("requirements.txt", text)
        self.assertIn("doctor --json", text)

    def test_windows_installer_can_bootstrap_python(self):
        text = (ROOT / "install.cmd").read_text(encoding="utf-8")
        expected = (
            "choice /C YN",
            "/AUTO-INSTALL-PYTHON",
            "/NO-PYTHON-INSTALL",
            "call :winget_python Python.Python.3.14",
            "winget install --id %~1",
            "https://www.python.org/ftp/python/",
            "certutil -hashfile",
            "InstallAllUsers=0",
            "PrependPath=1",
            "Include_pip=1",
            "Include_launcher=1",
            "-m ensurepip --upgrade",
            "-m pip --version",
        )
        for value in expected:
            with self.subTest(value=value):
                self.assertIn(value, text)

    def test_windows_python_bootstrap_hashes_are_sha256(self):
        text = (ROOT / "install.cmd").read_text(encoding="utf-8")
        hashes = re.findall(r'set "PYTHON_SHA256=([0-9a-f]+)"', text)
        self.assertEqual(len(hashes), 3)
        self.assertTrue(all(len(value) == 64 for value in hashes))

    def test_windows_installer_goto_targets_exist(self):
        text = (ROOT / "install.cmd").read_text(encoding="utf-8")
        labels = {match.group(1).lower() for match in re.finditer(r"(?m)^:([A-Za-z0-9_-]+)\s*$", text)}
        targets = {
            match.group(1).lower()
            for match in re.finditer(r"(?im)\bgoto\s+:?([A-Za-z0-9_-]+)", text)
        }
        self.assertEqual(set(), targets - labels)

    def test_python_requirement(self):
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('requires-python = ">=3.10"', text)

    def test_update_commands_documented(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("check-update", text)
        self.assertIn("imr-intruder update", text)

    def test_python_bootstrap_documented(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        installation = (ROOT / "docs" / "INSTALLATION.md").read_text(encoding="utf-8")
        for text in (readme, installation):
            self.assertIn("/AUTO-INSTALL-PYTHON", text)
            self.assertIn("/NO-PYTHON-INSTALL", text)


if __name__ == "__main__":
    unittest.main()
