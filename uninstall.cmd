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

if "%~1"=="" goto parsed
if /I "%~1"=="/PURGE" (
  set "PURGE=1"
  shift
  goto parsed
)
if /I "%~1"=="/?" goto help
if /I "%~1"=="/HELP" goto help
echo [ERROR] Unknown option: %~1
exit /b 2

:help
echo Usage: uninstall.cmd [/PURGE]
echo.
echo   /PURGE   Also remove configuration, state, data, and cache.
exit /b 0

:parsed
if exist "%BIN_DIR%\imr-intruder.cmd" call "%BIN_DIR%\imr-intruder.cmd" web stop >nul 2>&1

set "PYTHON_EXE="
set "CURRENT_VERSION="
if exist "%APP_HOME%\current-version" set /p CURRENT_VERSION=<"%APP_HOME%\current-version"
if defined CURRENT_VERSION if exist "%APP_HOME%\releases\%CURRENT_VERSION%\venv\Scripts\python.exe" (
  set "PYTHON_EXE=%APP_HOME%\releases\%CURRENT_VERSION%\venv\Scripts\python.exe"
)

if not defined PYTHON_EXE (
  for /f "delims=" %%P in ('"%SystemRoot%\System32\where.exe" python.exe 2^>nul') do if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
)
if not defined PYTHON_EXE if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"

if defined PYTHON_EXE if exist "%APP_HOME%\windows_path.py" (
  "%PYTHON_EXE%" "%APP_HOME%\windows_path.py" remove "%BIN_DIR%" "%APP_HOME%" "%CONFIG_HOME%" "%STATE_HOME%" "%DATA_HOME%" "%CACHE_HOME%" >nul 2>&1
)

if exist "%APP_HOME%\releases" rmdir /s /q "%APP_HOME%\releases"
if exist "%BIN_DIR%" rmdir /s /q "%BIN_DIR%"
del /q "%APP_HOME%\current-version" 2>nul
del /q "%APP_HOME%\windows_path.py" 2>nul

if "%PURGE%"=="1" (
  rmdir /s /q "%APP_HOME%" 2>nul
  rmdir /s /q "%CONFIG_HOME%" 2>nul
  rmdir /s /q "%STATE_HOME%" 2>nul
  rmdir /s /q "%DATA_HOME%" 2>nul
  rmdir /s /q "%CACHE_HOME%" 2>nul
)

echo imr-intruder uninstalled.
exit /b 0
