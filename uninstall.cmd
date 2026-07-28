@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "APP_HOME=%IMR_INTRUDER_HOME%"
if not defined APP_HOME set "APP_HOME=%LOCALAPPDATA%\Programs\imr-intruder"
set "CONFIG_HOME=%IMR_INTRUDER_CONFIG%"
if not defined CONFIG_HOME set "CONFIG_HOME=%APPDATA%\imr-intruder"
set "STATE_HOME=%IMR_INTRUDER_STATE%"
if not defined STATE_HOME set "STATE_HOME=%LOCALAPPDATA%\imr-intruder\state"
set "DATA_HOME=%IMR_INTRUDER_DATA%"
if not defined DATA_HOME set "DATA_HOME=%LOCALAPPDATA%\imr-intruder\data"
set "CACHE_HOME=%IMR_INTRUDER_CACHE%"
if not defined CACHE_HOME set "CACHE_HOME=%LOCALAPPDATA%\imr-intruder\cache"
set "BIN_DIR=%APP_HOME%\bin"
set "PURGE=0"
if /I "%~1"=="/PURGE" set "PURGE=1"

if exist "%BIN_DIR%\imr-intruder.cmd" call "%BIN_DIR%\imr-intruder.cmd" web stop >nul 2>&1
set "PYTHON_CMD="
py -3 -c "import sys" >nul 2>&1 && set "PYTHON_CMD=py -3"
if not defined PYTHON_CMD python -c "import sys" >nul 2>&1 && set "PYTHON_CMD=python"
if defined PYTHON_CMD if exist "%APP_HOME%\windows_path.py" %PYTHON_CMD% "%APP_HOME%\windows_path.py" remove "%BIN_DIR%" "%APP_HOME%" "%CONFIG_HOME%" "%STATE_HOME%" "%DATA_HOME%" "%CACHE_HOME%"

if exist "%APP_HOME%\releases" rmdir /s /q "%APP_HOME%\releases"
if exist "%BIN_DIR%" rmdir /s /q "%BIN_DIR%"
del /q "%APP_HOME%\current-version" 2>nul
if "%PURGE%"=="1" (
  rmdir /s /q "%APP_HOME%" 2>nul
  rmdir /s /q "%CONFIG_HOME%" 2>nul
  rmdir /s /q "%STATE_HOME%" 2>nul
  rmdir /s /q "%DATA_HOME%" 2>nul
  rmdir /s /q "%CACHE_HOME%" 2>nul
)
echo imr-intruder uninstalled.
exit /b 0
