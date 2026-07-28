@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
set "ROOT=%CD%"
set "APP_ROOT=%LOCALAPPDATA%\Programs\imr-intruder"
set "RELEASES_DIR=%APP_ROOT%\releases"
set "BIN_DIR=%APP_ROOT%\bin"
set "STATE_DIR=%LOCALAPPDATA%\imr-intruder\state"

where py >nul 2>nul
if not errorlevel 1 (
  set "PY_CMD=py -3"
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo [ERROR] Python 3.10 or newer is required.
    exit /b 1
  )
  set "PY_CMD=python"
)

%PY_CMD% -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)"
if errorlevel 1 (
  echo [ERROR] Python 3.10 or newer is required.
  exit /b 1
)

for /f "usebackq delims=" %%V in (`%PY_CMD% -c "import re,pathlib; s=pathlib.Path(r'%ROOT%\src\imr_intruder\__init__.py').read_text(encoding='utf-8'); print(re.search(r'__version__\s*=\s*[\"\x27]([^\"\x27]+)',s).group(1))"`) do set "VERSION=%%V"
if not defined VERSION (
  echo [ERROR] Unable to determine the package version.
  exit /b 1
)

set "RELEASE_DIR=%RELEASES_DIR%\%VERSION%"
if not exist "%RELEASES_DIR%" mkdir "%RELEASES_DIR%"
if not exist "%BIN_DIR%" mkdir "%BIN_DIR%"
if not exist "%STATE_DIR%" mkdir "%STATE_DIR%"
if exist "%RELEASE_DIR%" rmdir /S /Q "%RELEASE_DIR%"

%PY_CMD% -m venv "%RELEASE_DIR%\venv"
if errorlevel 1 goto :fail
"%RELEASE_DIR%\venv\Scripts\python.exe" -m pip install --disable-pip-version-check --upgrade pip
if errorlevel 1 goto :fail
"%RELEASE_DIR%\venv\Scripts\python.exe" -m pip install --disable-pip-version-check --upgrade "%ROOT%"
if errorlevel 1 goto :fail
"%RELEASE_DIR%\venv\Scripts\imr-intruder.exe" doctor --json >nul
if errorlevel 1 goto :fail
"%RELEASE_DIR%\venv\Scripts\imr-intruder.exe" version >nul
if errorlevel 1 goto :fail

> "%BIN_DIR%\imr-intruder.cmd" echo @echo off
>> "%BIN_DIR%\imr-intruder.cmd" echo "%RELEASE_DIR%\venv\Scripts\imr-intruder.exe" %%*
copy /Y "%ROOT%\uninstall.cmd" "%APP_ROOT%\uninstall.cmd" >nul
copy /Y "%ROOT%\scripts\windows_path.py" "%APP_ROOT%\windows_path.py" >nul
> "%APP_ROOT%\VERSION" echo %VERSION%
%PY_CMD% "%ROOT%\scripts\windows_path.py" add "%BIN_DIR%"
if errorlevel 1 goto :fail

set "PATH=%BIN_DIR%;%PATH%"
echo.
echo imr-intruder v%VERSION% installed successfully.
echo Launcher: %BIN_DIR%\imr-intruder.cmd
echo Run now: imr-intruder doctor
echo Web UI:  imr-intruder web start --background
echo Uninstall: %APP_ROOT%\uninstall.cmd
echo.
echo Open a new CMD or PowerShell window if the command is not yet visible there.
exit /b 0

:fail
echo [ERROR] Installation failed.
if exist "%RELEASE_DIR%" rmdir /S /Q "%RELEASE_DIR%"
exit /b 1
