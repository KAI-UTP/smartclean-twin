@echo off
setlocal
title Fix Docker Desktop startup error
color 0E

echo ============================================================
echo    Fix the Docker Desktop "Inference manager" /
echo    "Secrets Engine" startup error
echo ============================================================
echo.
echo  Cause: Docker Desktop creates Unix socket files under a path that
echo  contains a space (your Windows user name). Its listener cannot parse
echo  that path, so the socket is left behind and the next start fails
echo  trying to remove it.
echo.
echo  This script closes Docker, moves those stale socket folders aside,
echo  and starts Docker again. Nothing is deleted; the folders are renamed
echo  with a .stale suffix and Docker recreates them.
echo.
pause

echo.
echo [1/3] Closing Docker Desktop...
taskkill /f /im "Docker Desktop.exe"  >nul 2>&1
taskkill /f /im "com.docker.backend.exe" >nul 2>&1
taskkill /f /im "com.docker.build.exe"   >nul 2>&1
timeout /t 6 /nobreak >nul

echo [2/3] Moving stale socket folders aside...
set "STAMP=%RANDOM%"
if exist "%LOCALAPPDATA%\Docker\run" (
    move "%LOCALAPPDATA%\Docker\run" "%LOCALAPPDATA%\Docker\run.stale-%STAMP%" >nul 2>&1
    if errorlevel 1 (echo       could not move Docker\run) else (echo       moved Docker\run)
)
if exist "%LOCALAPPDATA%\docker-secrets-engine" (
    move "%LOCALAPPDATA%\docker-secrets-engine" "%LOCALAPPDATA%\docker-secrets-engine.stale-%STAMP%" >nul 2>&1
    if errorlevel 1 (echo       could not move docker-secrets-engine) else (echo       moved docker-secrets-engine)
)

echo [3/3] Starting Docker Desktop...
start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
echo       Waiting for the engine...

set /a TRIES=0
:wait
timeout /t 5 /nobreak >nul
docker info >nul 2>&1
if not errorlevel 1 goto ready
set /a TRIES+=1
if %TRIES% GEQ 36 (
    echo.
    echo  Docker still did not start.
    echo  Next things to try, in order:
    echo    1. Restart Windows. That clears stale sockets reliably.
    echo    2. Docker Desktop ^> Settings ^> turn off Docker AI / Model Runner.
    echo    3. Reinstall Docker Desktop.
    echo.
    pause
    exit /b 1
)
goto wait

:ready
echo.
echo  Docker engine is running again.
echo  You can now run START-SMARTCLEAN-TWIN.bat
echo.
pause
