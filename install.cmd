@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "SOURCE=%~dp0"
set "PYTHON_CMD="
set "PYTHON_OVERRIDE="
set "AUTO_INSTALL_PYTHON=0"
set "NO_INSTALL_PYTHON=0"
set "PYTHON_BOOTSTRAP_VERSION=3.14.6"

:parse
if "%~1"=="" goto parsed
if /I "%~1"=="/SOURCE" (
  if "%~2"=="" (
    echo [ERROR] /SOURCE requires a directory.
    exit /b 2
  )
  set "SOURCE=%~2"
  shift
  shift
  goto parse
)
if /I "%~1"=="/PYTHON" (
  if "%~2"=="" (
    echo [ERROR] /PYTHON requires the path to python.exe.
    exit /b 2
  )
  set "PYTHON_OVERRIDE=%~2"
  shift
  shift
  goto parse
)
if /I "%~1"=="/AUTO-INSTALL-PYTHON" (
  set "AUTO_INSTALL_PYTHON=1"
  shift
  goto parse
)
if /I "%~1"=="/NO-PYTHON-INSTALL" (
  set "NO_INSTALL_PYTHON=1"
  shift
  goto parse
)
if /I "%~1"=="/?" goto help
if /I "%~1"=="/HELP" goto help
echo [ERROR] Unknown option: %~1
exit /b 2

:help
echo Usage: install.cmd [options]
echo.
echo   /SOURCE DIR                 Install from another source directory.
echo   /PYTHON PATH                Use a specific Python executable.
echo   /AUTO-INSTALL-PYTHON        Install Python automatically without prompting.
echo   /NO-PYTHON-INSTALL          Do not offer to install Python automatically.
echo   /HELP, /?                   Show this help.
exit /b 0

:parsed
call :ensure_python
if errorlevel 1 exit /b 1

%PYTHON_CMD% "%SOURCE%\scripts\install_windows.py" --source "%SOURCE%"
exit /b %errorlevel%

:ensure_python
if defined PYTHON_OVERRIDE (
  if not exist "%PYTHON_OVERRIDE%" (
    echo [ERROR] The Python executable was not found: %PYTHON_OVERRIDE%
    exit /b 1
  )
  "%PYTHON_OVERRIDE%" -c "import sys; raise SystemExit(sys.version_info ^< (3,10))" >nul 2>&1
  if errorlevel 1 (
    echo [ERROR] /PYTHON must point to Python 3.10 or newer.
    exit /b 1
  )
  set PYTHON_CMD="%PYTHON_OVERRIDE%"
  exit /b 0
)

call :find_python
if defined PYTHON_CMD exit /b 0

if "%NO_INSTALL_PYTHON%"=="1" (
  echo [ERROR] Python 3.10 or newer is required and automatic installation is disabled.
  exit /b 1
)

if "%AUTO_INSTALL_PYTHON%"=="0" (
  echo.
  echo [!] Python 3.10 or newer was not found.
  choice /C YN /N /M "Install Python %PYTHON_BOOTSTRAP_VERSION% automatically for the current user? [Y/N] "
  if errorlevel 2 (
    echo [INFO] Installation cancelled. No system changes were made by imr-intruder.
    exit /b 1
  )
)

call :install_python
if errorlevel 1 exit /b 1
call :find_python
if not defined PYTHON_CMD (
  echo [ERROR] Python installation completed, but a compatible interpreter could not be located.
  echo [ERROR] Restart CMD and run install.cmd again, or use /PYTHON path\to\python.exe.
  exit /b 1
)
%PYTHON_CMD% -m ensurepip --upgrade >nul 2>&1
%PYTHON_CMD% -m pip --version >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python was installed but pip is unavailable.
  exit /b 1
)
echo [+] Python installed and detected: %PYTHON_CMD%
exit /b 0

:find_python
set "PYTHON_CMD="
py -3 -c "import sys; raise SystemExit(sys.version_info ^< (3,10))" >nul 2>&1
if not errorlevel 1 (
  set "PYTHON_CMD=py -3"
  exit /b 0
)
python -c "import sys; raise SystemExit(sys.version_info ^< (3,10))" >nul 2>&1
if not errorlevel 1 (
  set "PYTHON_CMD=python"
  exit /b 0
)
python3 -c "import sys; raise SystemExit(sys.version_info ^< (3,10))" >nul 2>&1
if not errorlevel 1 (
  set "PYTHON_CMD=python3"
  exit /b 0
)
for %%V in (314 313 312 311 310) do (
  call :check_python_path "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
  if defined PYTHON_CMD exit /b 0
)
for %%V in (314 313 312 311 310) do (
  call :check_python_path "%ProgramFiles%\Python%%V\python.exe"
  if defined PYTHON_CMD exit /b 0
)
exit /b 0

:check_python_path
if not exist "%~1" exit /b 0
"%~1" -c "import sys; raise SystemExit(sys.version_info ^< (3,10))" >nul 2>&1
if not errorlevel 1 set PYTHON_CMD="%~1"
exit /b 0

:install_python
echo [+] Installing Python %PYTHON_BOOTSTRAP_VERSION% for the current user
where winget >nul 2>&1
if errorlevel 1 goto direct_python_download

call :winget_python Python.Python.3.14
if not errorlevel 1 exit /b 0
call :winget_python Python.Python.3.13
if not errorlevel 1 exit /b 0
call :winget_python Python.Python.3.12
if not errorlevel 1 exit /b 0

echo [!] WinGet could not install Python. Falling back to the official Python installer.
goto direct_python_download

:winget_python
winget install --id %~1 --exact --source winget --scope user --silent --accept-package-agreements --accept-source-agreements --disable-interactivity >nul 2>&1
if not errorlevel 1 exit /b 0
winget install --id %~1 --exact --source winget --silent --accept-package-agreements --accept-source-agreements --disable-interactivity >nul 2>&1
exit /b %errorlevel%

:direct_python_download
where curl.exe >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Neither WinGet nor curl.exe is available to install Python automatically.
  echo [ERROR] Install Python 3.10+ from https://www.python.org/downloads/windows/ and rerun install.cmd.
  exit /b 1
)
where certutil.exe >nul 2>&1
if errorlevel 1 (
  echo [ERROR] certutil.exe is required to verify the Python installer checksum.
  exit /b 1
)

set "PYTHON_INSTALLER=%TEMP%\python-%PYTHON_BOOTSTRAP_VERSION%-%RANDOM%.exe"
set "NATIVE_ARCH=%PROCESSOR_ARCHITECTURE%"
if defined PROCESSOR_ARCHITEW6432 set "NATIVE_ARCH=%PROCESSOR_ARCHITEW6432%"
set "PYTHON_URL=https://www.python.org/ftp/python/%PYTHON_BOOTSTRAP_VERSION%/python-%PYTHON_BOOTSTRAP_VERSION%-amd64.exe"
set "PYTHON_SHA256=14b3e9a710a3fcf0bd9b55ab6b60412bd91227563f813fc49040cabc0209e0bd"
if /I "%NATIVE_ARCH%"=="ARM64" (
  set "PYTHON_URL=https://www.python.org/ftp/python/%PYTHON_BOOTSTRAP_VERSION%/python-%PYTHON_BOOTSTRAP_VERSION%-arm64.exe"
  set "PYTHON_SHA256=517412448c44f0583c994723640e208ca82723e340b0cb6a667696ba2eea63fc"
)
if /I "%NATIVE_ARCH%"=="x86" (
  set "PYTHON_URL=https://www.python.org/ftp/python/%PYTHON_BOOTSTRAP_VERSION%/python-%PYTHON_BOOTSTRAP_VERSION%.exe"
  set "PYTHON_SHA256=30e6397e4dda5b128ec8ac2a57016b0ad5491a2bee83921a6006cc0323fc466c"
)

curl.exe --fail --location --retry 3 --connect-timeout 20 --output "%PYTHON_INSTALLER%" "%PYTHON_URL%"
if errorlevel 1 (
  del /q "%PYTHON_INSTALLER%" 2>nul
  echo [ERROR] Failed to download the official Python installer.
  exit /b 1
)

call :verify_sha256 "%PYTHON_INSTALLER%" "%PYTHON_SHA256%"
if errorlevel 1 (
  del /q "%PYTHON_INSTALLER%" 2>nul
  echo [ERROR] Python installer checksum verification failed. The installer was not executed.
  exit /b 1
)

"%PYTHON_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_exe=1 Include_lib=1 Include_pip=1 Include_launcher=1 Include_test=0 Include_doc=0 Shortcuts=0
set "PYTHON_INSTALL_RESULT=%errorlevel%"
del /q "%PYTHON_INSTALLER%" 2>nul
if "%PYTHON_INSTALL_RESULT%"=="0" exit /b 0
if "%PYTHON_INSTALL_RESULT%"=="3010" (
  echo [!] Python requested a reboot, but installation can continue in the current user session.
  exit /b 0
)
echo [ERROR] The official Python installer failed with exit code %PYTHON_INSTALL_RESULT%.
exit /b 1

:verify_sha256
setlocal EnableDelayedExpansion
set "ACTUAL_HASH="
for /f "skip=1 tokens=*" %%H in ('certutil -hashfile "%~1" SHA256') do if not defined ACTUAL_HASH set "ACTUAL_HASH=%%H"
set "ACTUAL_HASH=!ACTUAL_HASH: =!"
if /I not "!ACTUAL_HASH!"=="%~2" (
  endlocal
  exit /b 1
)
endlocal
exit /b 0
