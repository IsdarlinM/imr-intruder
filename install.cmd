@echo off
setlocal EnableExtensions DisableDelayedExpansion

rem Keep Python discovery independent from broken user Python and pip overrides.
set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHONSTARTUP="
set "PYTHONUSERBASE="
set "PYTHONNOUSERSITE=1"
set "PIP_TARGET="
set "PIP_PREFIX="

set "SOURCE=%~dp0"
set "PYTHON_EXE="
set "PYTHON_ARGS="
set "PYTHON_OVERRIDE="
set "AUTO_INSTALL_PYTHON=0"
set "NO_INSTALL_PYTHON=0"
set "PYTHON_BOOTSTRAP_VERSION=3.13.14"
set "PYTHON_BOOTSTRAP_TAG=313"
set "PYTHON_WINGET_ID=Python.Python.3.13"
set "PYTHON_DETECT_ATTEMPTS=15"
set "PYTHON_INSTALL_LOG=%TEMP%\imr-intruder-python-install.log"
set "PYTHON_BOOTSTRAP_LOG=%TEMP%\imr-intruder-python-bootstrap.log"

>"%PYTHON_BOOTSTRAP_LOG%" echo imr-intruder Python bootstrap

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

"%PYTHON_EXE%" %PYTHON_ARGS% "%SOURCE%\scripts\install_windows.py" --source "%SOURCE%"
exit /b %errorlevel%

:ensure_python
if defined PYTHON_OVERRIDE (
  call :check_python_path "%PYTHON_OVERRIDE%"
  if not defined PYTHON_EXE (
    echo [ERROR] /PYTHON must point to a runnable Python 3.10 or newer executable.
    exit /b 1
  )
  goto validate_pip
)

call :find_python
if defined PYTHON_EXE goto validate_pip

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
  echo [ERROR] Python installation completed, but no runnable interpreter was found.
  echo [ERROR] Bootstrap log: %PYTHON_BOOTSTRAP_LOG%
  echo [ERROR] Installer log: %PYTHON_INSTALL_LOG%
  exit /b 1
)

:validate_pip
"%PYTHON_EXE%" %PYTHON_ARGS% -m ensurepip --upgrade >nul 2>&1
"%PYTHON_EXE%" %PYTHON_ARGS% -m pip --version >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python was found but pip is unavailable.
  echo [ERROR] Python: %PYTHON_EXE% %PYTHON_ARGS%
  exit /b 1
)
echo [+] Python detected: %PYTHON_EXE% %PYTHON_ARGS%
exit /b 0

:find_python_with_retry
set /a PYTHON_DETECT_ATTEMPT=0
:find_python_retry
call :find_python
if defined PYTHON_EXE exit /b 0
set /a PYTHON_DETECT_ATTEMPT+=1
if %PYTHON_DETECT_ATTEMPT% GEQ %PYTHON_DETECT_ATTEMPTS% exit /b 1
>nul 2>&1 "%SystemRoot%\System32\timeout.exe" /t 1 /nobreak
goto find_python_retry

:find_python
set "PYTHON_EXE="
set "PYTHON_ARGS="

call :check_command py -3
if defined PYTHON_EXE exit /b 0
call :check_command python
if defined PYTHON_EXE exit /b 0
call :check_command python3
if defined PYTHON_EXE exit /b 0
call :check_command python3.14
if defined PYTHON_EXE exit /b 0
call :check_command python3.13
if defined PYTHON_EXE exit /b 0
call :check_command python3.12
if defined PYTHON_EXE exit /b 0
call :check_command python3.11
if defined PYTHON_EXE exit /b 0
call :check_command python3.10
if defined PYTHON_EXE exit /b 0

call :check_python_launcher "%LOCALAPPDATA%\Programs\Python\Launcher\py.exe"
if defined PYTHON_EXE exit /b 0
call :check_python_launcher "%SystemRoot%\py.exe"
if defined PYTHON_EXE exit /b 0
call :check_python_launcher "%ProgramFiles%\Python Launcher\py.exe"
if defined PYTHON_EXE exit /b 0

call :find_python_registry
if defined PYTHON_EXE exit /b 0

for %%V in (314 313 312 311 310) do (
  call :check_python_path "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
  if defined PYTHON_EXE exit /b 0
  call :check_python_path "%LOCALAPPDATA%\Programs\Python\Python%%V-32\python.exe"
  if defined PYTHON_EXE exit /b 0
  call :check_python_path "%LOCALAPPDATA%\Programs\Python\Python%%V-arm64\python.exe"
  if defined PYTHON_EXE exit /b 0
)
for %%V in (314 313 312 311 310) do (
  call :check_python_path "%ProgramFiles%\Python%%V\python.exe"
  if defined PYTHON_EXE exit /b 0
  call :check_python_path "%ProgramFiles%\Python%%V-32\python.exe"
  if defined PYTHON_EXE exit /b 0
  call :check_python_path "%ProgramFiles%\Python%%V-arm64\python.exe"
  if defined PYTHON_EXE exit /b 0
)

call :search_python_tree "%LOCALAPPDATA%\Programs\Python"
if defined PYTHON_EXE exit /b 0
call :search_python_tree "%LOCALAPPDATA%\Microsoft\WinGet\Packages"
if defined PYTHON_EXE exit /b 0
call :search_python_tree "%ProgramFiles%"
exit /b 0

:check_command
for /f "delims=" %%P in ('%SystemRoot%\System32\where.exe %~1 2^>nul') do (
  call :check_python_with_args "%%P" "%~2"
  if defined PYTHON_EXE exit /b 0
)
exit /b 0

:check_python_launcher
if not exist "%~1" exit /b 0
call :check_python_with_args "%~1" "-3"
exit /b 0

:check_python_with_args
set "PYTHON_CANDIDATE=%~1"
set "PYTHON_CANDIDATE_ARGS=%~2"
if not exist "%PYTHON_CANDIDATE%" exit /b 0
"%PYTHON_CANDIDATE%" %PYTHON_CANDIDATE_ARGS% -c "import sys; raise SystemExit(sys.version_info ^< (3,10))" >nul 2>&1
if errorlevel 1 exit /b 0
set "PYTHON_EXE=%PYTHON_CANDIDATE%"
set "PYTHON_ARGS=%PYTHON_CANDIDATE_ARGS%"
>>"%PYTHON_BOOTSTRAP_LOG%" echo Found: "%PYTHON_EXE%" %PYTHON_ARGS%
exit /b 0

:check_python_path
call :check_python_with_args "%~1" ""
exit /b 0

:find_python_registry
for %%V in (3.14 3.13 3.12 3.11 3.10 3.14-32 3.13-32 3.12-32 3.11-32 3.10-32 3.14-arm64 3.13-arm64 3.12-arm64 3.11-arm64 3.10-arm64) do (
  call :check_registry_install_key "HKCU\Software\Python\PythonCore\%%V\InstallPath"
  if defined PYTHON_EXE exit /b 0
  call :check_registry_install_key "HKLM\Software\Python\PythonCore\%%V\InstallPath"
  if defined PYTHON_EXE exit /b 0
  call :check_registry_install_key "HKLM\Software\WOW6432Node\Python\PythonCore\%%V\InstallPath"
  if defined PYTHON_EXE exit /b 0
)
exit /b 0

:check_registry_install_key
for /f "tokens=2,*" %%A in ('%SystemRoot%\System32\reg.exe query "%~1" /v ExecutablePath 2^>nul ^| %SystemRoot%\System32\findstr.exe /I "REG_SZ REG_EXPAND_SZ"') do (
  call :check_python_path "%%B"
  if defined PYTHON_EXE exit /b 0
)
for /f "tokens=2,*" %%A in ('%SystemRoot%\System32\reg.exe query "%~1" /ve 2^>nul ^| %SystemRoot%\System32\findstr.exe /I "REG_SZ REG_EXPAND_SZ"') do (
  call :check_python_path "%%B\python.exe"
  if defined PYTHON_EXE exit /b 0
)
exit /b 0

:search_python_tree
if not exist "%~1" exit /b 0
for /f "delims=" %%P in ('%SystemRoot%\System32\where.exe /r "%~1" python.exe 2^>nul') do (
  call :check_python_path "%%P"
  if defined PYTHON_EXE exit /b 0
)
exit /b 0

:install_python
set "NATIVE_ARCH=%PROCESSOR_ARCHITECTURE%"
if defined PROCESSOR_ARCHITEW6432 set "NATIVE_ARCH=%PROCESSOR_ARCHITEW6432%"
set "PYTHON_TARGET_DIR=%LOCALAPPDATA%\Programs\Python\Python%PYTHON_BOOTSTRAP_TAG%"
if /I "%NATIVE_ARCH%"=="ARM64" set "PYTHON_TARGET_DIR=%LOCALAPPDATA%\Programs\Python\Python%PYTHON_BOOTSTRAP_TAG%-arm64"
if /I "%NATIVE_ARCH%"=="x86" set "PYTHON_TARGET_DIR=%LOCALAPPDATA%\Programs\Python\Python%PYTHON_BOOTSTRAP_TAG%-32"

echo [+] Installing Python %PYTHON_BOOTSTRAP_VERSION% for the current user
"%SystemRoot%\System32\where.exe" winget >nul 2>&1
if errorlevel 1 goto direct_python_download

call :winget_python "%PYTHON_WINGET_ID%" "%PYTHON_TARGET_DIR%"
if errorlevel 1 goto direct_python_download

call :check_python_path "%PYTHON_TARGET_DIR%\python.exe"
if defined PYTHON_EXE exit /b 0
call :find_python_with_retry
if defined PYTHON_EXE exit /b 0

echo [ERROR] WinGet reported success, but Python could not be executed.
echo [ERROR] The installer will not install additional Python versions or overwrite the successful WinGet installation.
echo [ERROR] WinGet logs: %LOCALAPPDATA%\Packages\Microsoft.DesktopAppInstaller_8wekyb3d8bbwe\LocalState\DiagOutputDir
exit /b 1

:winget_python
set "WINGET_LOG=%TEMP%\imr-intruder-winget-python.log"
winget install --id %~1 --exact --source winget --scope user --location "%~2" --silent --accept-package-agreements --accept-source-agreements --disable-interactivity --log "%WINGET_LOG%"
set "WINGET_RESULT=%errorlevel%"
>>"%PYTHON_BOOTSTRAP_LOG%" echo WinGet exit code: %WINGET_RESULT%
exit /b %WINGET_RESULT%

:direct_python_download
"%SystemRoot%\System32\where.exe" curl.exe >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Neither WinGet nor curl.exe is available to install Python automatically.
  exit /b 1
)
"%SystemRoot%\System32\where.exe" certutil.exe >nul 2>&1
if errorlevel 1 (
  echo [ERROR] certutil.exe is required to verify the Python installer checksum.
  exit /b 1
)

set "PYTHON_INSTALLER=%TEMP%\python-%PYTHON_BOOTSTRAP_VERSION%-%RANDOM%.exe"
set "PYTHON_URL=https://www.python.org/ftp/python/%PYTHON_BOOTSTRAP_VERSION%/python-%PYTHON_BOOTSTRAP_VERSION%-amd64.exe"
set "PYTHON_SHA256=c54d9b9bbb8a36e6489363ddd01139707fd781d72f1f9e90c7ec65d0061368e0"
if /I "%NATIVE_ARCH%"=="ARM64" (
  set "PYTHON_URL=https://www.python.org/ftp/python/%PYTHON_BOOTSTRAP_VERSION%/python-%PYTHON_BOOTSTRAP_VERSION%-arm64.exe"
  set "PYTHON_SHA256=3090f98038f332ceeca0ba40d77b7a4d94a4a25b7107e6cf341547e91d983f18"
)
if /I "%NATIVE_ARCH%"=="x86" (
  set "PYTHON_URL=https://www.python.org/ftp/python/%PYTHON_BOOTSTRAP_VERSION%/python-%PYTHON_BOOTSTRAP_VERSION%.exe"
  set "PYTHON_SHA256=012f050539353e6521ac7976a6b63e232102977e1dfcc747ca7fb743357ae8d1"
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
if "%PYTHON_INSTALL_RESULT%"=="1625" (
  echo [ERROR] Windows policy blocked the official Python installer ^(exit code 1625^).
  echo [ERROR] Use the WinGet installation permitted by your organization or contact the system administrator.
  echo [ERROR] Installer log: %PYTHON_INSTALL_LOG%
  exit /b 1
)
if not "%PYTHON_INSTALL_RESULT%"=="0" if not "%PYTHON_INSTALL_RESULT%"=="3010" (
  echo [ERROR] The official Python installer failed with exit code %PYTHON_INSTALL_RESULT%.
  echo [ERROR] Installer log: %PYTHON_INSTALL_LOG%
  exit /b 1
)

call :check_python_path "%PYTHON_TARGET_DIR%\python.exe"
if defined PYTHON_EXE exit /b 0
call :find_python_with_retry
exit /b %errorlevel%

:verify_sha256
setlocal EnableDelayedExpansion
set "ACTUAL_HASH="
for /f "skip=1 tokens=*" %%H in ('%SystemRoot%\System32\certutil.exe -hashfile "%~1" SHA256') do if not defined ACTUAL_HASH set "ACTUAL_HASH=%%H"
set "ACTUAL_HASH=!ACTUAL_HASH: =!"
if /I not "!ACTUAL_HASH!"=="%~2" (
  endlocal
  exit /b 1
)
endlocal
exit /b 0
