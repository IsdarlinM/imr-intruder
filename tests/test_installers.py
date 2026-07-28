from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class InstallerTests(unittest.TestCase):
    def test_linux_installer_is_user_scoped_and_self_checks(self):
        content = (ROOT / "install.sh").read_text(encoding="utf-8")
        self.assertIn("$HOME/.local", content)
        self.assertIn("python3-venv", content)
        self.assertIn("doctor --json", content)
        self.assertIn("web start --background", content)
        self.assertNotIn("sudo pip", content)

    def test_windows_installer_uses_cmd_without_powershell(self):
        content = (ROOT / "install.cmd").read_text(encoding="utf-8")
        lowered = content.lower()
        self.assertIn("%localappdata%\\programs\\imr-intruder", lowered)
        self.assertIn("python.exe\" -m pip", lowered)
        self.assertIn("doctor --json", lowered)
        self.assertIn("windows_path.py", lowered)
        self.assertNotIn("powershell.exe", lowered)
        self.assertNotIn("powershell -", lowered)

    def test_uninstallers_stop_managed_web_process(self):
        linux = (ROOT / "uninstall.sh").read_text(encoding="utf-8")
        windows = (ROOT / "uninstall.cmd").read_text(encoding="utf-8")
        self.assertIn("web stop", linux)
        self.assertIn("web stop", windows)


if __name__ == "__main__":
    unittest.main()
