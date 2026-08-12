@echo off
setlocal
title SmartClean Twin Launcher
color 0B

set "PROJ=D:\UTP\UG Y2S3\03 Digital Twin"
set "REPO=%PROJ%\smartclean-twin"
set "OMNIDIR=C:\Omniverse\kit-app-template\_build\windows-x86_64\release"
set "OMNI=C:\Omniverse\kit-app-template\_build\windows-x86_64\release\digital_twin_viewer.kit.bat"
set "OMNISCENE=C:\Omniverse\open_smartclean.py"
set "WALKNB=project_walkthrough.ipynb"

echo ============================================================
echo    SmartClean Twin - Demonstration Launcher
echo ============================================================
echo.

REM ---------------------------------------------------------------- 1. Docker
REM The wait loop must stay at top level. Inside a parenthesised block cmd
REM expands %TRIES% once when it parses the block, before the counter is set,
REM which makes the comparison a syntax error.
docker info >nul 2>&1
if not errorlevel 1 goto dockerready

echo [1/7] Docker is not running. Starting Docker Desktop...
start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
echo       Waiting for the Docker engine, this can take up to 3 minutes.
set /a TRIES=0

:waitdocker
timeout /t 5 /nobreak >nul 2>&1 || ping -n 6 127.0.0.1 >nul
docker info >nul 2>&1
if not errorlevel 1 goto dockerstarted
set /a TRIES+=1
if %TRIES% LSS 36 goto waitdocker

echo.
echo       Docker did not start. If you saw an "Inference manager" or a
echo       "Secrets Engine" error, close Docker Desktop and run FIX-DOCKER.bat
echo.
pause
exit /b 1

:dockerstarted
echo       Docker engine is ready.
goto dockerdone

:dockerready
echo [1/7] Docker is already running.

:dockerdone

REM ------------------------------------------------------------ 2. Containers
echo [2/7] Starting the 9 SmartClean Twin containers...
cd /d "%REPO%"
docker compose up -d
echo       Waiting 20 seconds for the services to become healthy...
timeout /t 20 /nobreak >nul 2>&1 || ping -n 21 127.0.0.1 >nul

REM ------------------------------------------------------- 3. Control panel
echo [3/7] Opening the operator control panel...
start "" "http://localhost:8005"
timeout /t 2 /nobreak >nul 2>&1 || ping -n 3 127.0.0.1 >nul

REM ----------------------------------------------------------- 4. Grafana
echo [4/7] Opening the Grafana dashboard...
start "" "http://localhost:3001/d/smartclean-main"
timeout /t 2 /nobreak >nul 2>&1 || ping -n 3 127.0.0.1 >nul

REM ---------------------------------------------------------- 5. InfluxDB
echo [5/7] Opening the InfluxDB data explorer...
start "" "http://localhost:8086"
timeout /t 2 /nobreak >nul 2>&1 || ping -n 3 127.0.0.1 >nul

REM ---------------------------------------------- 6. Walkthrough notebook
REM Jupyter Lab is started from the repo, so the notebook's relative paths
REM resolve. It keeps its own window open; closing that window stops it.
echo [6/7] Opening the project walkthrough notebook in Jupyter Lab...
if not exist "%REPO%\%WALKNB%" goto nonb
start "Jupyter Lab" /D "%REPO%" cmd /c jupyter lab "%WALKNB%"
echo       Jupyter opens in your browser after a few seconds.
goto nbdone
:nonb
echo       Notebook not found at:
echo         %REPO%\%WALKNB%
:nbdone
timeout /t 2 /nobreak >nul 2>&1 || ping -n 3 127.0.0.1 >nul

REM ---------------------------------------------------------- 7. Omniverse
REM Run through cmd from its own directory. Kit resolves its extension paths
REM relative to where it runs, and handing the batch file to cmd rather than
REM to start directly is what reliably keeps the process alive.
echo [7/7] Launching NVIDIA Omniverse with the 3D scene...
if not exist "%OMNI%" goto noomni
if not exist "%OMNISCENE%" goto noscene
start "NVIDIA Omniverse" /D "%OMNIDIR%" cmd /c ""%OMNI%" --exec "%OMNISCENE%""
if errorlevel 1 (
    echo       Omniverse did not start. Launch it yourself with:
    echo         "%OMNI%" --exec "%OMNISCENE%"
) else (
    echo       Omniverse takes 1 to 3 minutes to open. Be patient.
)
goto omnidone
:noomni
echo       Omniverse launcher not found at:
echo         %OMNI%
goto omnidone
:noscene
echo       Scene script not found at:
echo         %OMNISCENE%
:omnidone

echo.
echo ============================================================
echo    Everything launched
echo ============================================================
echo.
echo   Control panel : http://localhost:8005
echo   Grafana       : http://localhost:3001/d/smartclean-main   (admin / admin)
echo   InfluxDB      : http://localhost:8086   (admin / adminpassword)
echo   Walkthrough   : project_walkthrough.ipynb in Jupyter Lab
echo   Omniverse     : opening in its own window
echo.
echo   ONE MANUAL STEP, once Omniverse has finished loading:
echo     1. Menu: Window ^> Script Editor
echo     2. Open this file, copy all of it, paste into the editor, click Run:
echo        %REPO%\omniverse\live_update.py
echo     3. Type this on a new line and Run:   start_live_update^(^)
echo.
echo   If it says "No module named influxdb_client", run this first,
echo   wait one minute, then repeat step 2:
echo     import omni.kit.pipapi
echo     omni.kit.pipapi.install^("influxdb-client", module="influxdb_client"^)
echo.
echo   Paste live_update.py only ONCE per Omniverse session. If you need to
echo   paste it again, restart Omniverse first, or two update loops will fight.
echo.
echo ============================================================
pause
