@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Local Python environment was not found.
    echo Run INSTALL_OR_REPAIR.bat first, then run this file again.
    pause
    exit /b 1
)

echo Starting CDC Sim...
echo.
echo When the server is ready, open this address in a browser:
echo http://127.0.0.1:5000
echo.
echo Keep this window open while committee is running.
echo Press Ctrl+C in this window to stop the server.
echo.
".venv\Scripts\python.exe" server.py
pause
