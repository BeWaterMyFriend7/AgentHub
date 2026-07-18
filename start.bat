@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python 3.11 or newer was not found.
  echo Install Python and enable "Add Python to PATH", then run this file again.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/3] Creating virtual environment...
  python -m venv .venv
  if errorlevel 1 goto :error
)

echo [2/3] Installing dependencies...
".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :error

echo [3/3] Starting Agent Session Hub...
set "PYTHONPATH=%CD%\src"
".venv\Scripts\python.exe" -m agent_hub.main
goto :eof

:error
echo.
echo Startup failed. Review the error above.
pause
exit /b 1
