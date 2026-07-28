@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "APP_ROOT=%LOCALAPPDATA%\Programs\imr-intruder"
set "BIN_DIR=%APP_ROOT%\bin"
set "STATE_ROOT=%LOCALAPPDATA%\imr-intruder"
set "PURGE=0"
if /I "%~1"=="/PURGE" set "PURGE=1"
if /I "%~1"=="--purge" set "PURGE=1"

if exist "%BIN_DIR%\imr-intruder.cmd" call "%BIN_DIR%\imr-intruder.cmd" web stop >nul 2>nul
if exist "%APP_ROOT%\windows_path.py" (
  where py >nul 2>nul
  if not errorlevel 1 (
    py -3 "%APP_ROOT%\windows_path.py" remove "%BIN_DIR%"
  ) else (
    python "%APP_ROOT%\windows_path.py" remove "%BIN_DIR%"
  )
)

rmdir /S /Q "%APP_ROOT%" 2>nul
if "%PURGE%"=="1" rmdir /S /Q "%STATE_ROOT%" 2>nul

echo imr-intruder removed. Open a new terminal to refresh PATH.
if "%PURGE%"=="0" echo Runtime logs/state were preserved in: %STATE_ROOT%
endlocal
