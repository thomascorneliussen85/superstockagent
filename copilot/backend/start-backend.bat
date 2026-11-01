@echo off
REM Starts the AI Trading Copilot backend (creates the venv on first run).
cd /d "%~dp0"
if not exist .venv (
  py -3.12 -m venv .venv || py -3 -m venv .venv
  call .venv\Scripts\activate
  pip install -r requirements.txt
) else (
  call .venv\Scripts\activate
)
python -m app
