@echo off
rem Called by install.cmd. No SETLOCAL: exports PYTHON_EXE/PYTHON_ARGS.
set "PYTHON_VERSION=3.13.14"
set "PYTHON_TAG=313"
set "PYTHON_ID=Python.Python.3.13"
set "BOOT_LOG=%TEMP%\imr-intruder-python-bootstrap.log"
set "INSTALL_LOG=%TEMP%\imr-intruder-python-install.log"
set "WINGET_LOG=%TEMP%\imr-intruder-winget-python.log"
set "ARCH=%PROCESSOR_ARCHITECTURE%"
if defined PROCESSOR_ARCHITEW6432 set "ARCH=%PROCESSOR_ARCHITEW6432%"
set "TARGET=%LOCALAPPDATA%\Programs\Python\Python%PYTHON_TAG%"
if /I "%ARCH%"=="ARM64" set "TARGET=%TARGET%-arm64"
if /I "%ARCH%"=="x86" set "TARGET=%TARGET%-32"
if "%FORCE_PYTHON_BOOTSTRAP%"=="1" set "TARGET=%TARGET%-imr-intruder"
>"%BOOT_LOG%" echo imr-intruder Python bootstrap
>>"%BOOT_LOG%" echo Architecture: %ARCH%
>>"%BOOT_LOG%" echo Preferred target: %TARGET%

if "%FORCE_PYTHON_BOOTSTRAP%"=="1" goto direct
if "%NO_WINGET%"=="1" goto direct
set "WINGET="
if exist "%LOCALAPPDATA%\Microsoft\WindowsApps\winget.exe" set "WINGET=%LOCALAPPDATA%\Microsoft\WindowsApps\winget.exe"
if not defined WINGET for /f "delims=" %%W in ('%SystemRoot%\System32\where.exe winget.exe 2^>nul') do set "WINGET=%%W"
if not defined WINGET goto direct

"%WINGET%" install --id "%PYTHON_ID%" --exact --source winget --scope user --silent --accept-package-agreements --accept-source-agreements --disable-interactivity --log "%WINGET_LOG%"
set "WINGET_RESULT=%errorlevel%"
>>"%BOOT_LOG%" echo WinGet exit code: %WINGET_RESULT%
call :rediscover
if defined PYTHON_EXE exit /b 0

echo [!] WinGet did not expose a runnable Python. Trying the verified official installer.

:direct
set "URL=https://www.python.org/ftp/python/%PYTHON_VERSION%/python-%PYTHON_VERSION%-amd64.exe"
set "HASH=c54d9b9bbb8a36e6489363ddd01139707fd781d72f1f9e90c7ec65d0061368e0"
if /I "%ARCH%"=="ARM64" (set "URL=https://www.python.org/ftp/python/%PYTHON_VERSION%/python-%PYTHON_VERSION%-arm64.exe"& set "HASH=3090f98038f332ceeca0ba40d77b7a4d94a4a25b7107e6cf341547e91d983f18")
if /I "%ARCH%"=="x86" (set "URL=https://www.python.org/ftp/python/%PYTHON_VERSION%/python-%PYTHON_VERSION%.exe"& set "HASH=012f050539353e6521ac7976a6b63e232102977e1dfcc747ca7fb743357ae8d1")
set "INSTALLER=%TEMP%\python-%PYTHON_VERSION%-%RANDOM%.exe"
echo [+] Downloading verified Python %PYTHON_VERSION%
call :download "%URL%" "%INSTALLER%"
if errorlevel 1 (echo [ERROR] Python download failed: %URL%& exit /b 1)
call :verify "%INSTALLER%" "%HASH%"
if errorlevel 1 (del /q "%INSTALLER%" 2>nul& echo [ERROR] Python installer checksum failed.& exit /b 1)

echo [+] Installing Python for the current user
"%INSTALLER%" /quiet /log "%INSTALL_LOG%" InstallAllUsers=0 TargetDir="%TARGET%" PrependPath=0 AssociateFiles=0 Include_exe=1 Include_lib=1 Include_dev=1 Include_tools=1 Include_pip=1 Include_launcher=0 InstallLauncherAllUsers=0 Include_test=0 Include_doc=0 Include_tcltk=0 Include_symbols=0 Include_debug=0 Shortcuts=0
set "RESULT=%errorlevel%"
del /q "%INSTALLER%" 2>nul
>>"%BOOT_LOG%" echo Official installer exit code: %RESULT%
if "%RESULT%"=="1625" (echo [ERROR] Windows policy blocked Python installation ^(1625^). See %INSTALL_LOG%& exit /b 1)
if not "%RESULT%"=="0" if not "%RESULT%"=="3010" (echo [ERROR] Python installer failed with %RESULT%. See %INSTALL_LOG%& exit /b 1)

rem The legacy installer may enter maintenance mode for an existing runtime and
rem ignore TargetDir. Validate the requested path, then rediscover every actual
rem registered/WinGet location before declaring the installation unusable.
call :candidate "%TARGET%\python.exe"
if not defined PYTHON_EXE call :rediscover
if defined PYTHON_EXE exit /b 0

if "%RESULT%"=="3010" echo [ERROR] Python requested a Windows restart before it can be used.
if exist "%TARGET%\python.exe" (
  echo [ERROR] Python exists but Windows could not execute it: %TARGET%\python.exe
) else (
  echo [ERROR] The Python installer returned success but did not populate the requested directory.
)
echo [ERROR] Bootstrap log: %BOOT_LOG%
echo [ERROR] Installer log: %INSTALL_LOG%
echo [ERROR] WinGet log: %WINGET_LOG%
exit /b 1

:rediscover
for /l %%N in (1,1,15) do if not defined PYTHON_EXE (
  call "%SOURCE%\scripts\find_python.cmd"
  if not defined PYTHON_EXE "%SystemRoot%\System32\timeout.exe" /t 1 /nobreak >nul 2>&1
)
exit /b 0

:download
if exist "%SystemRoot%\System32\curl.exe" "%SystemRoot%\System32\curl.exe" --fail --location --retry 3 --retry-delay 2 --connect-timeout 20 --output "%~2" "%~1"
if exist "%~2" exit /b 0
if exist "%SystemRoot%\System32\certutil.exe" "%SystemRoot%\System32\certutil.exe" -urlcache -split -f "%~1" "%~2" >nul 2>&1
if exist "%~2" exit /b 0
exit /b 1

:verify
setlocal EnableDelayedExpansion
set "ACTUAL="
for /f "skip=1 tokens=*" %%H in ('%SystemRoot%\System32\certutil.exe -hashfile "%~1" SHA256') do if not defined ACTUAL set "ACTUAL=%%H"
set "ACTUAL=!ACTUAL: =!"
if /I not "!ACTUAL!"=="%~2" (endlocal& exit /b 1)
endlocal& exit /b 0

:candidate
if not exist "%~1" exit /b 0
>>"%BOOT_LOG%" echo Checking installed target: "%~1"
"%~1" -I -S -c "import operator,sys; raise SystemExit(not operator.ge(sys.version_info,(3,10)))" >>"%BOOT_LOG%" 2>&1
if errorlevel 1 exit /b 0
set "PYTHON_EXE=%~1"
set "PYTHON_ARGS="
for %%D in ("%~1") do set "PYTHON_HOME=%%~dpD"
set "PYTHON_SCRIPTS=%PYTHON_HOME%Scripts"
exit /b 0
