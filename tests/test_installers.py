from __future__ import annotations

import importlib.util
import os
import re
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load_windows_installer_module():
    path = ROOT / "scripts" / "install_windows.py"
    spec = importlib.util.spec_from_file_location("install_windows", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load install_windows.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class InstallerTests(unittest.TestCase):
    def test_linux_installer_has_dependency_install_and_env(self):
        text = (ROOT / "install.sh").read_text(encoding="utf-8")
        self.assertIn("pip install", text)
        self.assertIn("requirements.txt", text)
        self.assertIn("IMR_INTRUDER_HOME", text)

    def test_windows_bootstrap_delegates_transaction_to_python(self):
        cmd = (ROOT / "install.cmd").read_text(encoding="utf-8")
        helper = (ROOT / "scripts" / "install_windows.py").read_text(encoding="utf-8")
        self.assertNotIn("powershell", cmd.lower())
        self.assertIn('scripts\\install_windows.py" --source', cmd)
        self.assertIn("requirements.txt", helper)
        self.assertIn("windows_path.py", helper)
        self.assertIn('"doctor", "--json"', helper)
        self.assertIn("current-version", helper)
        self.assertIn("backup", helper.lower())

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

    def test_windows_installer_discovers_python_after_winget(self):
        text = (ROOT / "install.cmd").read_text(encoding="utf-8")
        expected = (
            "call :find_python_with_retry",
            "call :refresh_process_path",
            "call :find_python_registry",
            r"HKCU\Software\Python",
            r"%LOCALAPPDATA%\Microsoft\WinGet\Packages",
            r"%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe",
            "PYTHON_DETECT_ATTEMPTS=12",
        )
        for value in expected:
            with self.subTest(value=value):
                self.assertIn(value, text)

    def test_windows_direct_installer_uses_deterministic_target(self):
        text = (ROOT / "install.cmd").read_text(encoding="utf-8")
        self.assertIn('TargetDir="%PYTHON_TARGET_DIR%"', text)
        self.assertIn(r'call :check_python_path "%PYTHON_TARGET_DIR%\python.exe"', text)
        self.assertIn("imr-intruder-python-install.log", text)
        self.assertIn("InstallLauncherAllUsers=0", text)

    def test_winget_success_requires_a_runnable_interpreter(self):
        text = (ROOT / "install.cmd").read_text(encoding="utf-8")
        winget_section = text.split(":install_python", 1)[1].split(":direct_python_download", 1)[0]
        self.assertGreaterEqual(winget_section.count("call :find_python_with_retry"), 3)
        self.assertIn("WinGet did not expose a usable interpreter", winget_section)

    def test_windows_python_bootstrap_hashes_are_sha256(self):
        text = (ROOT / "install.cmd").read_text(encoding="utf-8")
        hashes = re.findall(r'set "PYTHON_SHA256=([0-9a-f]+)"', text)
        self.assertEqual(len(hashes), 3)
        self.assertTrue(all(len(value) == 64 for value in hashes))

    def test_windows_python_paths_are_well_formed(self):
        text = (ROOT / "install.cmd").read_text(encoding="utf-8")
        self.assertIn(r"%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe", text)
        self.assertIn(r'"%PYTHON_URL%"', text)
        self.assertNotIn(r"Programs\Python312", text)

    def test_windows_installer_goto_targets_exist(self):
        text = (ROOT / "install.cmd").read_text(encoding="utf-8")
        labels = {match.group(1).lower() for match in re.finditer(r"(?m)^:([A-Za-z0-9_-]+)\s*$", text)}
        targets = {
            match.group(1).lower()
            for match in re.finditer(r"(?im)\bgoto\s+:?([A-Za-z0-9_-]+)", text)
        }
        self.assertEqual(set(), targets - labels)

    def test_helper_cleans_inherited_python_and_pip_overrides(self):
        module = load_windows_installer_module()
        with patch.dict(
            os.environ,
            {
                "PYTHONPATH": "bad",
                "PYTHONHOME": "bad",
                "PIP_TARGET": "bad",
                "PIP_PREFIX": "bad",
            },
            clear=False,
        ):
            env = module.clean_python_environment()
        for name in ("PYTHONPATH", "PYTHONHOME", "PIP_TARGET", "PIP_PREFIX"):
            self.assertNotIn(name, env)

    def test_helper_launcher_uses_versioned_python_module(self):
        module = load_windows_installer_module()
        paths = {
            "app_home": Path(r"C:\Users\tester\AppData\Local\Programs\imr-intruder"),
            "config": Path(r"C:\Users\tester\AppData\Roaming\imr-intruder"),
            "state": Path(r"C:\Users\tester\AppData\Local\imr-intruder\state"),
            "data": Path(r"C:\Users\tester\AppData\Local\imr-intruder\data"),
            "cache": Path(r"C:\Users\tester\AppData\Local\imr-intruder\cache"),
            "bin": Path(r"C:\Users\tester\AppData\Local\Programs\imr-intruder\bin"),
        }
        launcher = module.launcher_text(paths)
        self.assertIn("current-version", launcher)
        self.assertIn(r"venv\Scripts\python.exe", launcher)
        self.assertIn("-m imr_intruder %*", launcher)
        for name in module.ENV_NAMES:
            self.assertIn(name, launcher)

    def test_helper_reads_project_version(self):
        module = load_windows_installer_module()
        self.assertEqual(module.project_version(ROOT), "1.3.2")

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
