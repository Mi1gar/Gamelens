@echo off
title Game Lens
echo ============================
echo   Game Lens
echo ============================
echo.

REM Start Python HTTP API (no GUI needed, lightweight)
start "GameLens API" /min cmd /c "cd /d %~dp0 && python engine/http_api.py"

REM Wait for API
timeout /t 2 /nobreak >nul

REM Start Vite dev server + open browser
echo.
echo UI: http://localhost:1420
echo.
cd /d %~dp0ui
start "" http://localhost:1420
call npx vite --host --port 1420
