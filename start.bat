@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>nul
title AI WORKSTATION

set "HERE=%~dp0"
set "ROOT="
if exist "%HERE%server.py" set "ROOT=%HERE%"
if not defined ROOT if exist "%HERE%..\server.py" for %%I in ("%HERE%..") do set "ROOT=%%~fI"
if not defined ROOT (
  echo [ERROR] server.py was not found next to this script or one level up.
  pause
  exit /b 1
)
cd /d "%ROOT%"
set "PORT=5000"
if defined AIWS_PORT set "PORT=%AIWS_PORT%"
set "URL=http://127.0.0.1:%PORT%/"
set "WANT_DL="
if /i "%~1"=="--get-ffmpeg" set "WANT_DL=1"
set "FORCE="
if /i "%~1"=="--force" set "FORCE=1"

echo ============================================================
echo   AI WORKSTATION - launcher
echo   project: %ROOT%
echo ============================================================
echo.

set "PROBE="
call :find_python
if defined PROBE goto :probe_ok
call :install_python
if defined PROBE goto :probe_ok

echo [ERROR] No working Python 3.10+ was found on this computer.
echo   The "python" from the Microsoft Store is a stub and does not work.
echo   Install Python from https://www.python.org/downloads/
echo   ^(tick "Add python.exe to PATH" during setup^), then run this file again.
start "" "https://www.python.org/downloads/"
pause
exit /b 1

:find_python
if defined PROBE goto :eof
if defined AIWS_PYTHON call :trypy "%AIWS_PYTHON%"
if defined PROBE goto :eof
py -3 -c "import sys;sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>nul
if not errorlevel 1 set "PROBE=py -3"
if defined PROBE goto :eof
call :trypy python3
if defined PROBE goto :eof
call :trypy python
if defined PROBE goto :eof
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do call :trypy "%%D\python.exe"
if defined PROBE goto :eof
for /d %%D in ("%ProgramFiles%\Python3*") do call :trypy "%%D\python.exe"
if defined PROBE goto :eof
call :trypy "%USERPROFILE%\miniconda3\python.exe"
if defined PROBE goto :eof
call :trypy "%USERPROFILE%\anaconda3\python.exe"
if defined PROBE goto :eof
for /d %%D in ("%USERPROFILE%\.conda\envs\*") do call :trypy "%%D\python.exe"
if defined PROBE goto :eof
for /d %%D in ("%USERPROFILE%\.workbuddy\binaries\python\envs\*") do call :trypy "%%D\Scripts\python.exe"
if defined PROBE goto :eof
for /d %%D in ("%USERPROFILE%\.workbuddy\binaries\python\versions\*") do call :trypy "%%D\python.exe"
goto :eof

:install_python
where winget >nul 2>nul
if errorlevel 1 goto :eof
echo.
echo [1/5] No Python found on this machine - installing it via winget...
echo        Windows may ask for permission ^(UAC^) - please allow it.
echo        One-time step, needs an internet connection.
echo.
winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
echo.
call :find_python
if defined PROBE echo [1/5] Python installed.
goto :eof

:trypy
if defined PROBE goto :eof
if "%~1"=="" goto :eof
if not exist "%~1" goto :eof
"%~1" -c "import sys;sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>nul
if not errorlevel 1 set "PROBE=%~1"
goto :eof

:probe_ok
set "PYTHON=" & set "PYDIR=" & set "FFDIR=" & set "FFDIR_BAD=" & set "FFNOTE="
for /f "usebackq tokens=1,* delims==" %%A in (`%PROBE% "%HERE%env_probe.py" 2^>nul`) do set "%%A=%%B"
if defined PYTHON (
  echo [1/5] Python OK - using the environment already on this machine
) else (
  for /f "delims=" %%v in ('%PROBE% -c "import sys;print(sys.version.split()[0])" 2^>nul') do set "PYVER=%%v"
  echo [1/5] Python: %PYVER%
)

if defined PYTHON (
  set "PYBIN=%PYTHON%"
  echo [2/5] Dependencies OK - already installed, nothing to do
  goto :deps_done
)

set "PYBIN=%ROOT%\venv\Scripts\python.exe"
if not exist "venv\Scripts\python.exe" (
  echo [2/5] Creating virtual environment - first run only, ~10s...
  %PROBE% -m venv venv
  if errorlevel 1 (
    echo [ERROR] Could not create the virtual environment.
    pause
    exit /b 1
  )
) else (
  echo [2/5] Virtual environment OK
)
"venv\Scripts\python.exe" -c "import flask" >nul 2>nul
if errorlevel 1 (
  echo [3/5] Installing dependencies - first run only, ~1 min...
  "venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
  "venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo.
    echo [ERROR] Dependency installation failed. Slow network? Try:
    echo   venv\Scripts\python.exe -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
    echo.
    pause
    exit /b 1
  )
) else (
  echo [3/5] Dependencies OK
)
:deps_done

if exist "bin\ffmpeg.exe" goto :ff_bin
if defined FFDIR goto :ff_own
if defined FFDIR_BAD goto :ff_bad
goto :ff_download

:ff_bin
echo [4/5] ffmpeg OK - project bin/
goto :start_server

:ff_own
set "FFMPEG_PATH=%FFDIR%"
set "FFPROBE=%FFDIR%\ffprobe.exe"
echo [4/5] ffmpeg OK - using yours: %FFDIR%
goto :start_server

:ff_bad
if defined WANT_DL goto :ff_download
set "FFMPEG_PATH=%FFDIR_BAD%"
set "FFPROBE=%FFDIR_BAD%\ffprobe.exe"
echo [4/5] ffmpeg: using the build already on this machine:
echo        %FFDIR_BAD%
echo.
echo [WARN] Self-test note: that build cannot open files whose name contains
echo   Chinese characters - most assets in this project are named in Chinese.
echo   Thumbnails / duration probing / final rendering of those files may fail.
echo   For an official build instead, re-run:  start.bat --get-ffmpeg
echo.
goto :start_server

:ff_download
echo [4/5] No ffmpeg found on this machine - downloading a portable build, ~90 MB once...
if not exist "bin" mkdir "bin"
set "FFTMP=%TEMP%\aiws_ffmpeg"
if exist "%FFTMP%" rmdir /s /q "%FFTMP%" >nul 2>nul
mkdir "%FFTMP%" >nul 2>nul

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$urls=@('https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip','https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip');" ^
  "$ok=$false;" ^
  "foreach($u in $urls){ try{ Write-Host ('   trying ' + $u); Invoke-WebRequest -Uri $u -OutFile \"$env:TEMP\aiws_ffmpeg\ff.zip\" -UseBasicParsing; $ok=$true; break } catch { Write-Host '   failed, next mirror' } };" ^
  "if(-not $ok){ exit 1 };" ^
  "Expand-Archive -Path \"$env:TEMP\aiws_ffmpeg\ff.zip\" -DestinationPath \"$env:TEMP\aiws_ffmpeg\x\" -Force;" ^
  "Get-ChildItem -Path \"$env:TEMP\aiws_ffmpeg\x\" -Recurse -Include ffmpeg.exe,ffprobe.exe | ForEach-Object { Copy-Item $_.FullName -Destination '%ROOT%\bin\' -Force };"

if not exist "bin\ffmpeg.exe" (
  echo       mirrors unreachable - trying the PyPI mirror - ffmpeg only...
  "%PYBIN%" -m pip install imageio-ffmpeg --quiet -i https://pypi.tuna.tsinghua.edu.cn/simple >nul 2>nul
  if not errorlevel 1 (
    "%PYBIN%" -c "import imageio_ffmpeg,shutil;shutil.copy(imageio_ffmpeg.get_ffmpeg_exe(),r'bin\ffmpeg.exe')" >nul 2>nul
  )
)

if exist "bin\ffmpeg.exe" (
  echo [4/5] ffmpeg OK - downloaded into project bin/
) else (
  echo.
  echo [WARN] Could not fetch ffmpeg. The service still starts; only video
  echo   composing / frame grabbing will be unavailable.
  echo   Manual fix - no admin rights needed: put ffmpeg.exe + ffprobe.exe into
  echo   %ROOT%\bin\   - or point FFMPEG_PATH / FFPROBE at their location.
  echo.
)
if exist "%FFTMP%" rmdir /s /q "%FFTMP%" >nul 2>nul

:start_server
echo [5/5] Starting service on port %PORT% ...
start "AI WORKSTATION server" /D "%ROOT%" "%PYBIN%" server.py

set /a TRIES=0
:wait
set /a TRIES+=1
"%PYBIN%" -c "import urllib.request,sys;sys.exit(0 if urllib.request.urlopen('%URL%api/config',timeout=2).status==200 else 1)" >nul 2>nul
if not errorlevel 1 goto :ready
if %TRIES% GEQ 40 goto :timeout
ping -n 2 127.0.0.1 >nul
goto :wait

:ready
echo.
echo [OK] Service is up: %URL%
start "" "%URL%"
echo.
echo  Keep the "AI WORKSTATION server" window open while you work.
echo  Close that window to stop the service.
goto :done

:timeout
echo.
echo [WARN] No answer from the service within 40 seconds.
echo   Check the "AI WORKSTATION server" window for the error message.

:done
echo.
pause
