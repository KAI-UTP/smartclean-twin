@echo off
setlocal enabledelayedexpansion
title SmartClean Twin - Phone Access
color 0B

set "REPO=D:\UTP\UG Y2S3\03 Digital Twin\smartclean-twin"

echo ============================================================
echo    Control the robot from your phone
echo ============================================================
echo.
echo  This publishes the operator console through a Cloudflare
echo  tunnel and prints an https address. Open that address on
echo  your phone, from any network, including mobile data.
echo.
echo  The console is protected with a password, because the
echo  address is reachable from the internet while the tunnel
echo  is open. Closing this window closes the tunnel.
echo.

set /p CONSOLE_PW=Choose a password for the console:
if "%CONSOLE_PW%"=="" (
    echo.
    echo  A password is required. Nothing was started.
    pause
    exit /b 1
)

echo.
echo [1/3] Applying the password to the console...
cd /d "%REPO%"
set "CONSOLE_PASSWORD=%CONSOLE_PW%"
docker compose up -d web-control
if errorlevel 1 (
    echo       Could not restart the console. Is Docker running?
    pause
    exit /b 1
)
timeout /t 8 /nobreak >nul

echo [2/3] Checking the console is up...
curl -s -o nul -w "      local check: HTTP %%{http_code}\n" http://localhost:8005/health

echo [3/3] Opening the tunnel. Look for the trycloudflare.com address below.
echo.
echo       Sign in on your phone with:
echo         username: operator
echo         password: %CONSOLE_PW%
echo.
echo       Keep this window open. Press Ctrl+C to stop sharing.
echo ============================================================
echo.

cloudflared tunnel --url http://localhost:8005

echo.
echo  Tunnel closed. The console is no longer reachable from the internet.
echo  It is still available on this laptop at http://localhost:8005
pause
