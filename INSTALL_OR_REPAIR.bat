@echo off
setlocal
cd /d "%~dp0"

echo CDC Sim install/repair
echo This creates a local .venv folder and installs requirements.txt.
echo Nothing is installed globally.
echo.

where py >nul 2>nul
if %errorlevel%==0 (
    py -3.12 -m venv .venv
) else (
    python -m venv .venv
)

if not exist ".venv\Scripts\python.exe" (
    echo Could not create .venv.
    echo Install Python 3.12 or newer, then run this file again.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -m pip install --upgrade pip setuptools wheel
".venv\Scripts\python.exe" -m pip install -r requirements.txt
".venv\Scripts\python.exe" -m pip check

echo.
echo Install/repair complete.
echo Next: double-click START_CDC_SIM.bat.
pause
