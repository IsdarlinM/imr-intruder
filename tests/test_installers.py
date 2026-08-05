from __future__ import annotations

import importlib.util
import os
import re
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
CMDS = ("install.cmd", "scripts/find_python.cmd", "scripts/bootstrap_python.cmd")


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def load_module(name: str, path: Path, *, fake_winreg: bool = False):
    previous = sys.modules.get("winreg")
    if fake_winreg:
        sys.modules["winreg"] = types.SimpleNamespace()
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if fake_winreg:
            if previous is None:
                sys.modules.pop("winreg", None)
            else:
                sys.modules["winreg"] = previous


class InstallerTests(unittest.TestCase):
    def test_clean_windows_bootstrap_contract(self):
        main = read("install.cmd")
        discovery = read("scripts/find_python.cmd")
        bootstrap = read("scripts/bootstrap_python.cmd")
        combined = "\n".join((main, discovery, bootstrap))
        self.assertNotIn("powershell", combined.lower())
        for value in (
            r"scripts\find_python.cmd",
            r"scripts\bootstrap_python.cmd",
            r"scripts\windows_path.py",
            "/AUTO-INSTALL-PYTHON",
            "/NO-PYTHON-INSTALL",
            "/FORCE-PYTHON-BOOTSTRAP",
            "/NO-WINGET",
            'set "PYTHON_ID=Python.Python.3.13"',
            "https://www.python.org/ftp/python/",
            "-hashfile",
            'TargetDir="%TARGET%"',
            "InstallAllUsers=0",
            "PrependPath=0",
            "Include_pip=1",
            "Include_launcher=0",
        ):
            self.assertIn(value, combined)
        self.assertEqual(bootstrap.count(" install --id "), 1)
        self.assertIn('if "%RESULT%"=="1625"', bootstrap)
        hashes = re.findall(r'set "HASH=([0-9a-f]+)"', bootstrap)
        self.assertEqual(3, len(hashes))
        self.assertTrue(all(len(value) == 64 for value in hashes))

    def test_post_install_rediscovery_and_isolated_probe(self):
        bootstrap = read("scripts/bootstrap_python.cmd")
        discovery = read("scripts/find_python.cmd")
        main = read("install.cmd")
        installer_call = bootstrap.index('"%INSTALLER%" /quiet')
        direct_candidate = bootstrap.index('call :candidate "%TARGET%\\python.exe"', installer_call)
        rediscovery = bootstrap.index("call :rediscover", direct_candidate)
        failure = bootstrap.index("Python exists but Windows could not execute it", rediscovery)
        self.assertLess(installer_call, direct_candidate)
        self.assertLess(direct_candidate, rediscovery)
        self.assertLess(rediscovery, failure)
        self.assertIn("-I -S -c", discovery)
        self.assertIn("-I -S -c", bootstrap)
        self.assertIn("-I -S -c", main)
        self.assertIn(r"%LOCALAPPDATA%\Python", discovery)
        self.assertIn(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages", discovery)
        self.assertNotIn('pymanager "exec"', discovery)
        self.assertIn("print(sys.executable)", main)
        self.assertIn("PYTHON_RUNTIME", main)
        combined = "\n".join((main, discovery, bootstrap))
        version_probe = "import operator,sys; raise SystemExit(not operator.ge(sys.version_info,(3,10)))"
        self.assertNotIn("^<", combined)
        self.assertEqual(4, combined.count(version_probe))
        compile(version_probe, "<windows-version-probe>", "exec")

    def test_discovery_and_cmd_syntax_guards(self):
        discovery = read("scripts/find_python.cmd")
        self.assertNotRegex(discovery.lower(), r"(?m)^setlocal\b")
        self.assertNotRegex(discovery, r'set "PATH=.*%PATH%')
        self.assertNotIn('>>"%BOOT_LOG%" 2>&1\nif errorlevel', discovery)
        for value in (r"HKCU\Software\Python\PythonCore", "/v ExecutablePath", "/ve"):
            self.assertIn(value, discovery)
        for path in CMDS:
            text = read(path)
            labels = {m.group(1).lower() for m in re.finditer(r"(?m)^:([\w-]+)\s*$", text)}
            targets = {m.group(1).lower() for m in re.finditer(r"(?im)\bgoto\s+:?([\w-]+)", text)}
            self.assertEqual(set(), targets - labels, path)
            self.assertLess(max(map(len, text.splitlines())), 1024)

    def test_python_and_application_environment_registration(self):
        path = ROOT / "scripts" / "windows_path.py"
        module = load_module("windows_path_test", path, fake_winreg=True)
        self.assertEqual(
            [r"C:\Python313", r"C:\Python313\Scripts"],
            module.python_path_entries(r"C:\Python313\python.exe"),
        )
        written: dict[str, str] = {}
        module.read_environment = lambda: {
            "Path": r"C:\Old;%LOCALAPPDATA%\Programs\Python\Python313;C:\Old"
        }
        module.write_value = lambda name, value: written.__setitem__(name, value)
        with patch.dict(os.environ, {"LOCALAPPDATA": r"C:\Users\test\AppData\Local"}):
            result = module.update_user_path(
                add=[
                    r"C:\App\bin",
                    r"C:\Users\test\AppData\Local\Programs\Python\Python313",
                    r"C:\Users\test\AppData\Local\Programs\Python\Python313\Scripts",
                ],
                remove=[r"C:\App\bin"],
            )
        self.assertEqual(result, written["Path"])
        self.assertEqual(1, result.lower().count(r"c:\old"))
        self.assertTrue(result.startswith(r"C:\App\bin;"))
        self.assertIn(r"C:\Users\test\AppData\Local\Programs\Python\Python313", result)
        self.assertIn(r"Python313\Scripts", result)

    def test_python_transaction_helper_and_launcher_isolation(self):
        path = ROOT / "scripts" / "install_windows.py"
        module = load_module("install_windows", path)
        helper = read("scripts/install_windows.py")
        for value in (
            '"--retries", "5"',
            '"--timeout", "60"',
            '"doctor", "--json"',
            "current-version",
            "backup",
            '"--python-executable"',
        ):
            self.assertIn(value, helper)
        self.assertNotIn("install_from_host", helper)
        self.assertEqual("1.4.3", module.project_version(ROOT))
        paths = {
            "app_home": Path(r"C:\App"),
            "config": Path(r"C:\Config"),
            "state": Path(r"C:\State"),
            "data": Path(r"C:\Data"),
            "cache": Path(r"C:\Cache"),
            "bin": Path(r"C:\App\bin"),
        }
        launcher = module.launcher_text(paths)
        for name in ("PYTHONHOME", "PYTHONPATH", "PIP_TARGET", "VIRTUAL_ENV"):
            self.assertIn(name, launcher)
        self.assertIn('set "PYTHONNOUSERSITE=1"', launcher)

    def test_ci_docs_and_uninstaller(self):
        workflow = read(".github/workflows/ci.yml")
        for value in (
            "windows-clean-bootstrap:",
            "runs-on: windows-2022",
            "/FORCE-PYTHON-BOOTSTRAP /NO-WINGET",
        ):
            self.assertIn(value, workflow)
        for path in ("README.md", "docs/INSTALLATION.md"):
            for value in (
                "/AUTO-INSTALL-PYTHON",
                "/NO-PYTHON-INSTALL",
                "/FORCE-PYTHON-BOOTSTRAP",
                "/NO-WINGET",
            ):
                self.assertIn(value, read(path))
        documentation = read("docs/INSTALLATION.md")
        self.assertIn("Python directory", documentation)
        self.assertIn("`Scripts` directory", documentation)
        self.assertIn("does **not** create persistent `PYTHONHOME`", documentation)
        uninstall = read("uninstall.cmd")
        self.assertIn(r"releases\%CURRENT_VERSION%\venv\Scripts\python.exe", uninstall)
        self.assertLess(
            uninstall.index("windows_path.py"),
            uninstall.index('if exist "%APP_HOME%\\releases" rmdir'),
        )


if __name__ == "__main__":
    unittest.main()
