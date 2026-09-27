@echo off
rem Double-click to open the Crusader Wars 2 launcher. It runs from source
rem (dev\app\main.py) with the project's .venv; there is no build step.
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo The .venv folder is missing. Set it up once with:
  echo   python -m venv .venv
  echo   .venv\Scripts\pip install -r dev\requirements.txt
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "dev\app\main.py"
