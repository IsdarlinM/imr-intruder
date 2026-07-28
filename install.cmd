@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "SOURCE=%~dp0"
set "PYTHON_CMD="
set "APP_HOME=%LOCALAPPDATA%\Programs\imr-intruder"
set "CONFIG_HOME=%APPDATA%\imr-intruder"
set "STATE_HOME=%LOCALAPPDATA%\imr-intruder\state"
set "DATA_HOME=%LOCALAPPDATA%\imr-intruder\data"
set "CACHE_HOME=%LOCALAPPDATA%\imr-intruder\cache"
set "BIN_DIR=%APP_HOME%\bin"

:parse
if "%~1"=="" goto parsed
if /I "%~1"=="/SOURCE" (
  set "SOURCE=%~2"
  shift
  shift
  goto parse
)
if /I "%~1"=="/PYTHON" (
  set "PYTHON_CMD=%~2"
  shift
  shift
  goto parse
)
echo [ERROR] Unknown option: %~1
exit /b 2

:parsed
if not defined PYTHON_CMD (
  py -3 -c "import sys; raise SystemExit(sys.version_info ^< (3,10))" >nul 2>&1
  if not errorlevel 1 set "PYTHON_CMD=py -3"
)
if not defined PYTHON_CMD (
  python -c "import sys; raise SystemExit(sys.version_info ^< (3,10))" >nul 2>&1
  if not errorlevel 1 set "PYTHON_CMD=python"
)
if not defined PYTHON_CMD (
  echo [ERROR] Python 3.10 or newer is required.
  exit /b 1
)

for /f "delims=" %%V in ('%PYTHON_CMD% "%SOURCE%\scripts\project_version.py" "%SOURCE%\src\imr_intruder\__init__.py"') do set "VERSION=%%V"
if not defined VERSION (
  echo [ERROR] Unable to determine project version.
  exit /b 1
)

set "RELEASE_DIR=%APP_HOME%\releases\%VERSION%"
set "BACKUP=%APP_HOME%\releases\.backup-%VERSION%-%RANDOM%"
set "VENV=%RELEASE_DIR%\venv"
set "OLD_VERSION="
if exist "%APP_HOME%\current-version" set /p OLD_VERSION=<"%APP_HOME%\current-version"

mkdir "%APP_HOME%\releases" 2>nul
mkdir "%CONFIG_HOME%" 2>nul
mkdir "%STATE_HOME%" 2>nul
mkdir "%DATA_HOME%" 2>nul
mkdir "%CACHE_HOME%" 2>nul
mkdir "%BIN_DIR%" 2>nul

if exist "%BACKUP%" rmdir /s /q "%BACKUP%"
if exist "%RELEASE_DIR%" move "%RELEASE_DIR%" "%BACKUP%" >nul
mkdir "%RELEASE_DIR%" 2>nul
echo [+] Creating isolated Python environment for v%VERSION%
%PYTHON_CMD% -m venv "%VENV%"
if errorlevel 1 goto failed

set "PYTHONPATH="
set "PYTHONHOME="
set "PIP_TARGET="
set "PIP_PREFIX="
"%VENV%\Scripts\python.exe" -m pip install --disable-pip-version-check -r "%SOURCE%\requirements.txt"
if errorlevel 1 goto fallback
"%VENV%\Scripts\python.exe" -m pip install --disable-pip-version-check --no-deps --no-build-isolation "%SOURCE%"
if errorlevel 1 goto fallback

goto installed

:fallback
echo [!] Package index installation failed. Checking dependencies available from the host Python.
if exist "%VENV%" rmdir /s /q "%VENV%"
%PYTHON_CMD% -m venv "%VENV%"
if errorlevel 1 goto failed
%PYTHON_CMD% "%SOURCE%\scripts\link_host_paths.py" "%VENV%\Scripts\python.exe" >nul
if errorlevel 1 goto failed
"%VENV%\Scripts\python.exe" "%SOURCE%\scripts\check_dependencies.py"
if errorlevel 1 goto failed
"%VENV%\Scripts\python.exe" -m pip install --disable-pip-version-check --no-deps --no-build-isolation "%SOURCE%"
if errorlevel 1 goto failed

:installed
"%VENV%\Scripts\imr-intruder.exe" version >nul
if errorlevel 1 goto failed
>"%APP_HOME%\current-version" echo %VERSION%
copy /y "%SOURCE%\uninstall.cmd" "%APP_HOME%\uninstall.cmd" >nul
copy /y "%SOURCE%\scripts\windows_path.py" "%APP_HOME%\windows_path.py" >nul

>"%BIN_DIR%\imr-intruder.cmd" echo @echo off
>>"%BIN_DIR%\imr-intruder.cmd" echo setlocal
>>"%BIN_DIR%\imr-intruder.cmd" echo set "IMR_INTRUDER_HOME=%APP_HOME%"
>>"%BIN_DIR%\imr-intruder.cmd" echo set "IMR_INTRUDER_CONFIG=%CONFIG_HOME%"
>>"%BIN_DIR%\imr-intruder.cmd" echo set "IMR_INTRUDER_STATE=%STATE_HOME%"
>>"%BIN_DIR%\imr-intruder.cmd" echo set "IMR_INTRUDER_DATA=%DATA_HOME%"
>>"%BIN_DIR%\imr-intruder.cmd" echo set "IMR_INTRUDER_CACHE=%CACHE_HOME%"
>>"%BIN_DIR%\imr-intruder.cmd" echo set /p VERSION=^<"%APP_HOME%\current-version"
>>"%BIN_DIR%\imr-intruder.cmd" echo call "%APP_HOME%\releases\%%VERSION%%\venv\Scripts\imr-intruder.exe" %%*

%PYTHON_CMD% "%SOURCE%\scripts\windows_path.py" install "%BIN_DIR%" "%APP_HOME%" "%CONFIG_HOME%" "%STATE_HOME%" "%DATA_HOME%" "%CACHE_HOME%"
if errorlevel 1 goto failed

set "PATH=%BIN_DIR%;%PATH%"
set "IMR_INTRUDER_HOME=%APP_HOME%"
set "IMR_INTRUDER_CONFIG=%CONFIG_HOME%"
set "IMR_INTRUDER_STATE=%STATE_HOME%"
set "IMR_INTRUDER_DATA=%DATA_HOME%"
set "IMR_INTRUDER_CACHE=%CACHE_HOME%"
call "%BIN_DIR%\imr-intruder.cmd" doctor --json >nul
if errorlevel 1 goto failed
if exist "%BACKUP%" rmdir /s /q "%BACKUP%"

echo.
echo [+] imr-intruder v%VERSION% installed successfully.
echo [+] Open a new CMD window and run: imr-intruder --help
exit /b 0

:failed
echo [ERROR] Installation failed.
if exist "%RELEASE_DIR%" rmdir /s /q "%RELEASE_DIR%"
if exist "%BACKUP%" move "%BACKUP%" "%RELEASE_DIR%" >nul
if defined OLD_VERSION (
  >"%APP_HOME%\current-version" echo %OLD_VERSION%
) else (
  del /q "%APP_HOME%\current-version" 2>nul
  del /q "%BIN_DIR%\imr-intruder.cmd" 2>nul
)
exit /b 1
