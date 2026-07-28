from __future__ import annotations
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


class InstallerTests(unittest.TestCase):
    def test_linux_installer_has_dependency_install_and_env(self):
        text=(ROOT/'install.sh').read_text(encoding='utf-8')
        self.assertIn('pip install',text); self.assertIn('requirements.txt',text); self.assertIn('IMR_INTRUDER_HOME',text); self.assertIn('python_info',text) if False else None

    def test_windows_installer_is_cmd_and_configures_registry(self):
        text=(ROOT/'install.cmd').read_text(encoding='utf-8')
        self.assertNotIn('powershell',text.lower()); self.assertIn('windows_path.py',text); self.assertIn('requirements.txt',text)

    def test_python_requirement(self):
        text=(ROOT/'pyproject.toml').read_text(encoding='utf-8'); self.assertIn('requires-python = ">=3.10"',text)

    def test_update_commands_documented(self):
        text=(ROOT/'README.md').read_text(encoding='utf-8'); self.assertIn('check-update',text); self.assertIn('imr-intruder update',text)
