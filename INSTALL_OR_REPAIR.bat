@echo off
setlocal
cd /d "%~dp0"
title CDC Sim source setup

echo CDC Sim source/developer setup
echo Private beta testers should use the signed Windows installer instead.
echo.

set "PYTHON_CMD="
where py >nul 2>nul
if not errorlevel 1 (
    py -3.12 -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)" >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=py -3.12"
)
if not defined PYTHON_CMD (
    where python >nul 2>nul
    if not errorlevel 1 (
        python -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)" >nul 2>nul
        if not errorlevel 1 set "PYTHON_CMD=python"
    )
)
if not defined PYTHON_CMD goto no_python

echo Creating the isolated Python environment...
%PYTHON_CMD% -m venv .venv
if errorlevel 1 goto failed

if not exist ".venv\Scripts\python.exe" goto failed
".venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)"
if errorlevel 1 (
    echo Existing .venv is not Python 3.12.
    echo Rename or remove only .venv, then run this setup again.
    goto failed
)

echo Installing pinned dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip check
if errorlevel 1 goto failed

echo.
echo Install/repair complete.
echo Double-click START_CDC_SIM.bat. The readiness page will open automatically.
pause
exit /b 0

:no_python
echo.
echo Python 3.12 64-bit was not found.
echo This setup is for developers. Beta testers should use the Windows installer.
echo Developers: install Python 3.12 from python.org, then run this file again.
pause
exit /b 1

:failed
echo.
echo Setup did not complete. Nothing has been reported as successfully installed.
echo Check the message above, your internet connection, and available disk space.
pause
exit /b 1
