@echo off
REM Starts the AI Trading Copilot backend (creates the venv on first run).
REM Prefers Python 3.14/3.13/3.12: the MetaTrader5 package (Phase 2) does not support newer versions yet.
cd /d "%~dp0"
if not exist .venv (
  py -3.14 -m venv .venv 2>nul || py -3.13 -m venv .venv 2>nul || py -3.12 -m venv .venv 2>nul || (
    echo Fant ikke Python 3.12-3.14. Installer Python 3.14 fra python.org og huk av "Add Python to PATH".
    pause
    exit /b 1
  )
  call .venv\Scripts\activate
  python -m pip install -r requirements.txt
) else (
  call .venv\Scripts\activate
)
python -m app
pause
