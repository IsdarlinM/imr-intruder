@echo off
setlocal EnableExtensions
set "APP_HOME=%LOCALAPPDATA%\imr-intruder"
set "BIN_DIR=%USERPROFILE%\.local\bin"
if exist "%APP_HOME%\windows_path.py" python "%APP_HOME%\windows_path.py" remove "%BIN_DIR%"
del /Q "%BIN_DIR%\imr-intruder.cmd" 2>nul
rmdir /S /Q "%APP_HOME%" 2>nul
echo imr-intruder removed. Open a new CMD window to refresh PATH.
endlocal
