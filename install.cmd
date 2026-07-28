@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "ROOT=%CD%"
set "APP_HOME=%LOCALAPPDATA%\imr-intruder"
set "VENV=%APP_HOME%\venv"
set "BIN_DIR=%USERPROFILE%\.local\bin"

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python 3.10 or newer is required.
  exit /b 1
)

python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)"
if errorlevel 1 (
  echo [ERROR] Python 3.10 or newer is required.
  exit /b 1
)

if not exist "%APP_HOME%" mkdir "%APP_HOME%"
if not exist "%BIN_DIR%" mkdir "%BIN_DIR%"
python -m venv "%VENV%"
if errorlevel 1 exit /b 1
"%VENV%\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 exit /b 1
"%VENV%\Scripts\python.exe" -m pip install --upgrade "%ROOT%"
if errorlevel 1 exit /b 1

> "%BIN_DIR%\imr-intruder.cmd" echo @echo off
>> "%BIN_DIR%\imr-intruder.cmd" echo "%VENV%\Scripts\imr-intruder.exe" %%*
copy /Y "%ROOT%\uninstall.cmd" "%APP_HOME%\uninstall.cmd" >nul
copy /Y "%ROOT%\scripts\windows_path.py" "%APP_HOME%\windows_path.py" >nul
python "%ROOT%\scripts\windows_path.py" add "%BIN_DIR%"

echo.
echo imr-intruder installed successfully.
echo Launcher: %BIN_DIR%\imr-intruder.cmd
echo Run now: "%BIN_DIR%\imr-intruder.cmd" version
echo New CMD windows can use: imr-intruder web
endlocal
