@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "SOURCE=%~dp0"
set "PYTHON_CMD="
set "PYTHON_OVERRIDE="
set "AUTO_INSTALL_PYTHON=0"
set "NO_INSTALL_PYTHON=0"
set "PYTHON_BOOTSTRAP_VERSION=3.14.6"
set "PYTHON_BOOTSTRAP_TAG=314"
set "PYTHON_DETECT_ATTEMPTS=12"

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
call :find_python_with_retry
if errorlevel 1 (
  echo [ERROR] Python installation completed, but the interpreter is not discoverable.
  echo [ERROR] Installer log: %TEMP%\imr-intruder-python-install.log
  echo [ERROR] Run install.cmd /PYTHON "full\path\to\python.exe" only if the log confirms a nonstandard path.
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

:find_python_with_retry
set /a PYTHON_DETECT_ATTEMPT=0
:find_python_retry
call :refresh_process_path
call :find_python
if defined PYTHON_CMD exit /b 0
set /a PYTHON_DETECT_ATTEMPT+=1
if %PYTHON_DETECT_ATTEMPT% GEQ %PYTHON_DETECT_ATTEMPTS% exit /b 1
>nul 2>&1 timeout /t 1 /nobreak
goto find_python_retry

:refresh_process_path
set "USER_ENV_PATH="
set "SYSTEM_ENV_PATH="
for /f "tokens=2,*" %%A in ('reg query "HKCU\Environment" /v Path 2^>nul ^| findstr /I "REG_"') do set "USER_ENV_PATH=%%B"
for /f "tokens=2,*" %%A in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul ^| findstr /I "REG_"') do set "SYSTEM_ENV_PATH=%%B"
if defined SYSTEM_ENV_PATH set "PATH=%SYSTEM_ENV_PATH%;%PATH%"
if defined USER_ENV_PATH set "PATH=%USER_ENV_PATH%;%PATH%"
if exist "%LOCALAPPDATA%\Microsoft\WindowsApps" set "PATH=%LOCALAPPDATA%\Microsoft\WindowsApps;%PATH%"
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

call :check_python_path "%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe"
if defined PYTHON_CMD exit /b 0
call :check_python_path "%LOCALAPPDATA%\Microsoft\WindowsApps\python3.exe"
if defined PYTHON_CMD exit /b 0
call :find_python_registry
if defined PYTHON_CMD exit /b 0

for %%V in (314 313 312 311 310) do (
  call :check_python_path "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
  if defined PYTHON_CMD exit /b 0
  call :check_python_path "%LOCALAPPDATA%\Programs\Python\Python%%V-32\python.exe"
  if defined PYTHON_CMD exit /b 0
  call :check_python_path "%LOCALAPPDATA%\Programs\Python\Python%%V-arm64\python.exe"
  if defined PYTHON_CMD exit /b 0
)
for %%V in (314 313 312 311 310) do (
  call :check_python_path "%ProgramFiles%\Python%%V\python.exe"
  if defined PYTHON_CMD exit /b 0
  if exist "%ProgramFiles(x86)%\Python%%V-32\python.exe" call :check_python_path "%ProgramFiles(x86)%\Python%%V-32\python.exe"
  if defined PYTHON_CMD exit /b 0
)

call :search_python_tree "%LOCALAPPDATA%\Programs\Python"
if defined PYTHON_CMD exit /b 0
call :search_python_tree "%LOCALAPPDATA%\Microsoft\WinGet\Packages"
if defined PYTHON_CMD exit /b 0
call :search_python_tree "%LOCALAPPDATA%\Python"
exit /b 0

:find_python_registry
for %%K in ("HKCU\Software\Python" "HKLM\Software\Python") do (
  for /f "tokens=2,*" %%A in ('reg query %%K /s /v ExecutablePath 2^>nul ^| findstr /I "ExecutablePath"') do (
    call :check_python_path "%%B"
    if defined PYTHON_CMD exit /b 0
  )
)
for %%K in ("HKLM\Software\Python" "HKLM\Software\WOW6432Node\Python") do (
  for /f "tokens=2,*" %%A in ('reg query %%K /s /v ExecutablePath 2^>nul ^| findstr /I "ExecutablePath"') do (
    call :check_python_path "%%B"
    if defined PYTHON_CMD exit /b 0
  )
)
exit /b 0

:search_python_tree
if not exist "%~1" exit /b 0
for /f "delims=" %%P in ('where /r "%~1" python.exe 2^>nul') do (
  call :check_python_path "%%P"
  if defined PYTHON_CMD exit /b 0
)
exit /b 0

:check_python_path
set "PYTHON_CANDIDATE=%~1"
if not defined PYTHON_CANDIDATE exit /b 0
if not exist "%PYTHON_CANDIDATE%" exit /b 0
"%PYTHON_CANDIDATE%" -c "import sys; raise SystemExit(sys.version_info ^< (3,10))" >nul 2>&1
if not errorlevel 1 set PYTHON_CMD="%PYTHON_CANDIDATE%"
exit /b 0

:install_python
echo [+] Installing Python %PYTHON_BOOTSTRAP_VERSION% for the current user
where winget >nul 2>&1
if errorlevel 1 goto direct_python_download

call :winget_python Python.Python.3.14
if not errorlevel 1 (
  call :find_python_with_retry
  if not errorlevel 1 exit /b 0
)
call :winget_python Python.Python.3.13
if not errorlevel 1 (
  call :find_python_with_retry
  if not errorlevel 1 exit /b 0
)
call :winget_python Python.Python.3.12
if not errorlevel 1 (
  call :find_python_with_retry
  if not errorlevel 1 exit /b 0
)

echo [!] WinGet did not expose a usable interpreter. Falling back to the verified official installer.
goto direct_python_download

:winget_python
echo [+] Trying WinGet package %~1
winget install --id %~1 --exact --source winget --scope user --silent --accept-package-agreements --accept-source-agreements --disable-interactivity
if not errorlevel 1 exit /b 0
winget install --id %~1 --exact --source winget --silent --accept-package-agreements --accept-source-agreements --disable-interactivity
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
set "PYTHON_INSTALL_LOG=%TEMP%\imr-intruder-python-install.log"
set "NATIVE_ARCH=%PROCESSOR_ARCHITECTURE%"
if defined PROCESSOR_ARCHITEW6432 set "NATIVE_ARCH=%PROCESSOR_ARCHITEW6432%"
set "PYTHON_TARGET_DIR=%LOCALAPPDATA%\Programs\Python\Python%PYTHON_BOOTSTRAP_TAG%"
set "PYTHON_URL=https://www.python.org/ftp/python/%PYTHON_BOOTSTRAP_VERSION%/python-%PYTHON_BOOTSTRAP_VERSION%-amd64.exe"
set "PYTHON_SHA256=14b3e9a710a3fcf0bd9b55ab6b60412bd91227563f813fc49040cabc0209e0bd"
if /I "%NATIVE_ARCH%"=="ARM64" (
  set "PYTHON_TARGET_DIR=%LOCALAPPDATA%\Programs\Python\Python%PYTHON_BOOTSTRAP_TAG%-arm64"
  set "PYTHON_URL=https://www.python.org/ftp/python/%PYTHON_BOOTSTRAP_VERSION%/python-%PYTHON_BOOTSTRAP_VERSION%-arm64.exe"
  set "PYTHON_SHA256=517412448c44f0583c994723640e208ca82723e340b0cb6a667696ba2eea63fc"
)
if /I "%NATIVE_ARCH%"=="x86" (
  set "PYTHON_TARGET_DIR=%LOCALAPPDATA%\Programs\Python\Python%PYTHON_BOOTSTRAP_TAG%-32"
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

"%PYTHON_INSTALLER%" /quiet /log "%PYTHON_INSTALL_LOG%" InstallAllUsers=0 TargetDir="%PYTHON_TARGET_DIR%" PrependPath=1 Include_exe=1 Include_lib=1 Include_dev=1 Include_pip=1 Include_launcher=1 InstallLauncherAllUsers=0 Include_test=0 Include_doc=0 Shortcuts=0
set "PYTHON_INSTALL_RESULT=%errorlevel%"
del /q "%PYTHON_INSTALLER%" 2>nul
if not "%PYTHON_INSTALL_RESULT%"=="0" if not "%PYTHON_INSTALL_RESULT%"=="3010" (
  echo [ERROR] The official Python installer failed with exit code %PYTHON_INSTALL_RESULT%.
  echo [ERROR] Installer log: %PYTHON_INSTALL_LOG%
  exit /b 1
)

call :check_python_path "%PYTHON_TARGET_DIR%\python.exe"
if defined PYTHON_CMD exit /b 0
call :find_python_with_retry
exit /b %errorlevel%

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
