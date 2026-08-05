@echo off
rem Called by install.cmd. Intentionally no SETLOCAL: exports PYTHON_EXE/PYTHON_ARGS.
set "PYTHON_EXE="
set "PYTHON_ARGS="
if defined PYTHON_OVERRIDE call :candidate "%PYTHON_OVERRIDE%" ""
if defined PYTHON_EXE exit /b 0
for %%C in (py python python3 python3.14 python3.13 python3.12 python3.11 python3.10) do call :command %%C
if defined PYTHON_EXE exit /b 0
for %%P in ("%LOCALAPPDATA%\Programs\Python\Launcher\py.exe" "%SystemRoot%\py.exe" "%ProgramFiles%\Python Launcher\py.exe") do call :candidate "%%~P" "-3"
if defined PYTHON_EXE exit /b 0
for %%V in (314 313 312 311 310) do (
  call :candidate "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" ""
  call :candidate "%LOCALAPPDATA%\Programs\Python\Python%%V-32\python.exe" ""
  call :candidate "%LOCALAPPDATA%\Programs\Python\Python%%V-arm64\python.exe" ""
  call :candidate "%ProgramFiles%\Python%%V\python.exe" ""
)
if defined PYTHON_EXE exit /b 0
for %%V in (3.14 3.13 3.12 3.11 3.10) do (
  call :registry "HKCU\Software\Python\PythonCore\%%V\InstallPath"
  call :registry "HKLM\Software\Python\PythonCore\%%V\InstallPath"
  call :registry "HKLM\Software\WOW6432Node\Python\PythonCore\%%V\InstallPath"
)
if defined PYTHON_EXE exit /b 0
for %%D in ("%LOCALAPPDATA%\Programs\Python" "%LOCALAPPDATA%\Microsoft\WinGet\Packages") do call :tree "%%~D"
exit /b 0

:command
if defined PYTHON_EXE exit /b 0
for /f "delims=" %%P in ('%SystemRoot%\System32\where.exe %~1 2^>nul') do call :candidate "%%P" ""
if /I "%~1"=="py" if not defined PYTHON_EXE for /f "delims=" %%P in ('%SystemRoot%\System32\where.exe py.exe 2^>nul') do call :candidate "%%P" "-3"
exit /b 0

:candidate
if defined PYTHON_EXE exit /b 0
if not exist "%~1" exit /b 0
"%~1" %~2 -c "import sys; raise SystemExit(sys.version_info ^< (3,10))" >nul 2>&1
if errorlevel 1 exit /b 0
set "PYTHON_EXE=%~1"
set "PYTHON_ARGS=%~2"
exit /b 0

:registry
if defined PYTHON_EXE exit /b 0
for /f "tokens=2,*" %%A in ('%SystemRoot%\System32\reg.exe query "%~1" /v ExecutablePath 2^>nul ^| %SystemRoot%\System32\findstr.exe /I "REG_SZ REG_EXPAND_SZ"') do call :candidate "%%B" ""
for /f "tokens=2,*" %%A in ('%SystemRoot%\System32\reg.exe query "%~1" /ve 2^>nul ^| %SystemRoot%\System32\findstr.exe /I "REG_SZ REG_EXPAND_SZ"') do call :candidate "%%B\python.exe" ""
exit /b 0

:tree
if defined PYTHON_EXE exit /b 0
if not exist "%~1" exit /b 0
for /f "delims=" %%P in ('%SystemRoot%\System32\where.exe /r "%~1" python.exe 2^>nul') do call :candidate "%%P" ""
exit /b 0
