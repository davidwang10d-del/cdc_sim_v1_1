@echo off
setlocal
cd /d "%~dp0"
title CDC Sim

if not exist ".venv\Scripts\python.exe" (
    echo CDC Sim's local developer environment was not found.
    echo Run INSTALL_OR_REPAIR.bat first.
    pause
    exit /b 1
)

if not defined CDC_PROFILE set "CDC_PROFILE=development"

echo Starting CDC Sim...
echo The readiness page will open in your browser automatically.
echo Keep this window open while the committee is running.
echo Press Ctrl+C here to stop the local server.
echo.
".venv\Scripts\python.exe" server.py
if errorlevel 1 (
    echo.
    echo CDC Sim stopped because of an error.
    echo Open the readiness page or include the displayed Support ID in your beta report.
    pause
    exit /b 1
)
exit /b 0
