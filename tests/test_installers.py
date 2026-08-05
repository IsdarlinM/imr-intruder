from __future__ import annotations

import importlib.util
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CMDS = ("install.cmd", "scripts/find_python.cmd", "scripts/bootstrap_python.cmd")


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


class InstallerTests(unittest.TestCase):
    def test_clean_windows_bootstrap_contract(self):
        main = read("install.cmd")
        discovery = read("scripts/find_python.cmd")
        bootstrap = read("scripts/bootstrap_python.cmd")
        combined = "\n".join((main, discovery, bootstrap))
        self.assertNotIn("powershell", combined.lower())
        for value in (
            r"scripts\find_python.cmd", r"scripts\bootstrap_python.cmd",
            "/AUTO-INSTALL-PYTHON", "/NO-PYTHON-INSTALL",
            "/FORCE-PYTHON-BOOTSTRAP", "/NO-WINGET",
            'set "PYTHON_ID=Python.Python.3.13"',
            "https://www.python.org/ftp/python/", "-hashfile",
            'TargetDir="%TARGET%"', "InstallAllUsers=0",
            "PrependPath=0", "Include_pip=1", "Include_launcher=0",
        ):
            self.assertIn(value, combined)
        self.assertEqual(bootstrap.count(" install --id "), 1)
        self.assertIn('if "%RESULT%"=="1625"', bootstrap)
        hashes = re.findall(r'set "HASH=([0-9a-f]+)"', bootstrap)
        self.assertEqual(3, len(hashes))
        self.assertTrue(all(len(value) == 64 for value in hashes))

    def test_discovery_and_cmd_syntax_guards(self):
        discovery = read("scripts/find_python.cmd")
        self.assertNotRegex(discovery.lower(), r"(?m)^setlocal\b")
        self.assertNotRegex(discovery, r'set "PATH=.*%PATH%')
        for value in (r"HKCU\Software\Python\PythonCore", "/v ExecutablePath", "/ve"):
            self.assertIn(value, discovery)
        for path in CMDS:
            text = read(path)
            labels = {m.group(1).lower() for m in re.finditer(r"(?m)^:([\w-]+)\s*$", text)}
            targets = {m.group(1).lower() for m in re.finditer(r"(?im)\bgoto\s+:?([\w-]+)", text)}
            self.assertEqual(set(), targets - labels, path)
            self.assertLess(max(map(len, text.splitlines())), 1024)

    def test_python_transaction_helper(self):
        path = ROOT / "scripts" / "install_windows.py"
        spec = importlib.util.spec_from_file_location("install_windows", path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        helper = read("scripts/install_windows.py")
        for value in ('"--retries", "5"', '"--timeout", "60"', '"doctor", "--json"', "current-version", "backup"):
            self.assertIn(value, helper)
        self.assertNotIn("install_from_host", helper)
        self.assertEqual("1.4.1", module.project_version(ROOT))

    def test_ci_docs_and_uninstaller(self):
        workflow = read(".github/workflows/ci.yml")
        for value in ("windows-clean-bootstrap:", "runs-on: windows-2022", "/FORCE-PYTHON-BOOTSTRAP /NO-WINGET"):
            self.assertIn(value, workflow)
        for path in ("README.md", "docs/INSTALLATION.md"):
            for value in ("/AUTO-INSTALL-PYTHON", "/NO-PYTHON-INSTALL", "/FORCE-PYTHON-BOOTSTRAP", "/NO-WINGET"):
                self.assertIn(value, read(path))
        uninstall = read("uninstall.cmd")
        self.assertIn(r"releases\%CURRENT_VERSION%\venv\Scripts\python.exe", uninstall)
        self.assertLess(uninstall.index("windows_path.py"), uninstall.index('if exist "%APP_HOME%\\releases" rmdir'))


if __name__ == "__main__":
    unittest.main()
