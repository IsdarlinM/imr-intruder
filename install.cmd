@echo off
setlocal EnableExtensions DisableDelayedExpansion

rem Isolate bootstrap from broken Python, pip, and virtualenv variables.
for %%V in (PYTHONHOME PYTHONPATH PYTHONSTARTUP PYTHONUSERBASE PIP_TARGET PIP_PREFIX PIP_USER PIP_REQUIRE_VIRTUALENV VIRTUAL_ENV __PYVENV_LAUNCHER__) do set "%%V="
set "PYTHONNOUSERSITE=1"

set "SOURCE=%~dp0"
set "PYTHON_OVERRIDE="
set "AUTO_INSTALL_PYTHON=0"
set "NO_INSTALL_PYTHON=0"
set "FORCE_PYTHON_BOOTSTRAP=0"
set "NO_WINGET=0"

:parse
if "%~1"=="" goto parsed
if /I "%~1"=="/SOURCE" if not "%~2"=="" (set "SOURCE=%~2"& shift& shift& goto parse)
if /I "%~1"=="/PYTHON" if not "%~2"=="" (set "PYTHON_OVERRIDE=%~2"& shift& shift& goto parse)
if /I "%~1"=="/AUTO-INSTALL-PYTHON" (set "AUTO_INSTALL_PYTHON=1"& shift& goto parse)
if /I "%~1"=="/NO-PYTHON-INSTALL" (set "NO_INSTALL_PYTHON=1"& shift& goto parse)
if /I "%~1"=="/FORCE-PYTHON-BOOTSTRAP" (set "FORCE_PYTHON_BOOTSTRAP=1"& set "AUTO_INSTALL_PYTHON=1"& shift& goto parse)
if /I "%~1"=="/NO-WINGET" (set "NO_WINGET=1"& shift& goto parse)
if /I "%~1"=="/?" goto help
if /I "%~1"=="/HELP" goto help
echo [ERROR] Unknown or incomplete option: %~1
exit /b 2

:help
echo Usage: install.cmd [options]
echo   /SOURCE DIR                 Install from another source directory.
echo   /PYTHON PATH                Use a specific Python 3.10+ executable.
echo   /AUTO-INSTALL-PYTHON        Install Python without prompting.
echo   /NO-PYTHON-INSTALL          Fail instead of installing Python.
echo   /FORCE-PYTHON-BOOTSTRAP     Test the clean-machine Python bootstrap.
echo   /NO-WINGET                  Use the verified official installer directly.
echo   /HELP, /?                   Show this help.
exit /b 0

:parsed
for %%F in (scripts\find_python.cmd scripts\bootstrap_python.cmd scripts\install_windows.py scripts\windows_path.py) do if not exist "%SOURCE%\%%F" (echo [ERROR] Missing required file: %%F& exit /b 2)

set "PYTHON_EXE="
set "PYTHON_ARGS="
if "%FORCE_PYTHON_BOOTSTRAP%"=="0" call "%SOURCE%\scripts\find_python.cmd"
if defined PYTHON_EXE goto validate
if "%NO_INSTALL_PYTHON%"=="1" (echo [ERROR] Python 3.10+ is required and automatic installation is disabled.& exit /b 1)
if "%AUTO_INSTALL_PYTHON%"=="0" (
  echo [!] Python 3.10 or newer was not found.
  "%SystemRoot%\System32\choice.exe" /C YN /N /M "Install Python automatically for the current user? [Y/N] "
  if errorlevel 2 exit /b 1
)
call "%SOURCE%\scripts\bootstrap_python.cmd"
if errorlevel 1 exit /b 1
if not defined PYTHON_EXE call "%SOURCE%\scripts\find_python.cmd"
if not defined PYTHON_EXE (echo [ERROR] Python bootstrap completed but no runnable interpreter was found.& exit /b 1)

:validate
echo [+] Validating Python and pip
"%PYTHON_EXE%" %PYTHON_ARGS% -I -S -c "import sys; raise SystemExit(sys.version_info ^< (3,10))" >nul 2>&1
if errorlevel 1 (echo [ERROR] Python 3.10 or newer is required.& exit /b 1)
"%PYTHON_EXE%" %PYTHON_ARGS% -m ensurepip --upgrade >nul 2>&1
"%PYTHON_EXE%" %PYTHON_ARGS% -m pip --version >nul 2>&1
if errorlevel 1 (echo [ERROR] Python was found but pip is unavailable.& exit /b 1)
echo [+] Python detected: "%PYTHON_EXE%" %PYTHON_ARGS%
echo [+] Registering Python and Scripts in the user PATH
"%PYTHON_EXE%" %PYTHON_ARGS% "%SOURCE%\scripts\windows_path.py" python "%PYTHON_EXE%"
if errorlevel 1 (echo [ERROR] Python works, but its user PATH entries could not be registered.& exit /b 1)
"%PYTHON_EXE%" %PYTHON_ARGS% "%SOURCE%\scripts\install_windows.py" --source "%SOURCE%"
exit /b %errorlevel%
