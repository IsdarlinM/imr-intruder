@echo off
rem Called by install.cmd/bootstrap_python.cmd. No SETLOCAL: exports variables.
set "PYTHON_EXE="
set "PYTHON_ARGS="
set "PYTHON_HOME="
set "PYTHON_SCRIPTS="

if defined PYTHON_OVERRIDE call :candidate "%PYTHON_OVERRIDE%" ""
if defined PYTHON_EXE exit /b 0

call :command py "-3"
call :command python ""
call :command python3 ""
call :command python3.14 ""
call :command python3.13 ""
call :command python3.12 ""
call :command python3.11 ""
call :command python3.10 ""
if defined PYTHON_EXE exit /b 0

for %%P in ("%LOCALAPPDATA%\Programs\Python\Launcher\py.exe" "%SystemRoot%\py.exe" "%ProgramFiles%\Python Launcher\py.exe") do call :candidate "%%~P" "-3"
if defined PYTHON_EXE exit /b 0

for %%V in (314 313 312 311 310) do (
  call :candidate "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" ""
  call :candidate "%LOCALAPPDATA%\Programs\Python\Python%%V-32\python.exe" ""
  call :candidate "%LOCALAPPDATA%\Programs\Python\Python%%V-arm64\python.exe" ""
  call :candidate "%ProgramFiles%\Python%%V\python.exe" ""
  call :candidate "%ProgramFiles%\Python%%V-32\python.exe" ""
  call :candidate "%ProgramFiles%\Python%%V-arm64\python.exe" ""
)
if defined PYTHON_EXE exit /b 0

for %%V in (3.14 3.13 3.12 3.11 3.10 3.14-64 3.13-64 3.12-64 3.11-64 3.10-64 3.14-32 3.13-32 3.12-32 3.11-32 3.10-32 3.14-arm64 3.13-arm64 3.12-arm64 3.11-arm64 3.10-arm64) do (
  call :registry "HKCU\Software\Python\PythonCore\%%V\InstallPath"
  call :registry "HKLM\Software\Python\PythonCore\%%V\InstallPath"
  call :registry "HKLM\Software\WOW6432Node\Python\PythonCore\%%V\InstallPath"
)
if defined PYTHON_EXE exit /b 0

for %%D in ("%LOCALAPPDATA%\Programs\Python" "%LOCALAPPDATA%\Python" "%LOCALAPPDATA%\Microsoft\WinGet\Packages") do call :tree "%%~D"
exit /b 0

:command
if defined PYTHON_EXE exit /b 0
for /f "delims=" %%P in ('%SystemRoot%\System32\where.exe %~1 2^>nul') do call :candidate "%%P" "%~2"
exit /b 0

:candidate
if defined PYTHON_EXE exit /b 0
if not exist "%~1" exit /b 0
if defined BOOT_LOG (
  >>"%BOOT_LOG%" echo Checking candidate: "%~1" %~2
  "%~1" %~2 -I -S -c "import operator,sys; raise SystemExit(not operator.ge(sys.version_info,(3,10)))" >>"%BOOT_LOG%" 2>&1
) else (
  "%~1" %~2 -I -S -c "import operator,sys; raise SystemExit(not operator.ge(sys.version_info,(3,10)))" >nul 2>&1
)
if errorlevel 1 exit /b 0
set "PYTHON_EXE=%~1"
set "PYTHON_ARGS=%~2"
for %%D in ("%~1") do set "PYTHON_HOME=%%~dpD"
set "PYTHON_SCRIPTS=%PYTHON_HOME%Scripts"
if defined BOOT_LOG >>"%BOOT_LOG%" echo Selected candidate: "%PYTHON_EXE%" %PYTHON_ARGS%
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
