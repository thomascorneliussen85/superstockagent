@echo off
setlocal
title AI Trading Copilot - backend
cd /d "%~dp0"

echo.
echo  AI Trading Copilot - starter backend
echo  Mappe: %CD%
echo.

if not exist "requirements.txt" goto :not_extracted
if not exist "app\main.py" goto :not_extracted

rem --- Finn en Python-versjon som MetaTrader5 stotter: 3.14, 3.13 eller 3.12 ---
set "PY="
for %%V in (3.14 3.13 3.12) do (
  if not defined PY (
    py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V"
  )
)
if not defined PY (
  python -c "import sys; sys.exit(0 if (3,12) <= sys.version_info[:2] <= (3,14) else 1)" >nul 2>&1 && set "PY=python"
)
if not defined PY goto :no_python
echo  Bruker Python: %PY%

rem --- Innstillinger: lag .env fra malen forste gang ---
if not exist ".env" (
  copy /y ".env.example" ".env" >nul
  echo  Laget innstillingsfilen .env - standard er MT5-modus, kun lesing.
)

rem --- Lag Python-miljo forste gang, eller hvis en tidligere installasjon feilet ---
if not exist ".venv\Scripts\python.exe" (
  if exist ".venv" rmdir /s /q ".venv"
  echo  Forste oppstart: lager Python-miljo...
  %PY% -m venv .venv
  if errorlevel 1 goto :venv_failed
)

rem --- Installer pakker hvis requirements.txt er ny eller endret siden sist ---
fc /b "requirements.txt" ".venv\requirements.installert" >nul 2>&1
if errorlevel 1 (
  echo  Installerer/oppdaterer pakker. Dette tar 1-2 minutter...
  echo.
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto :pip_failed
  copy /y "requirements.txt" ".venv\requirements.installert" >nul
)

:run
echo.
".venv\Scripts\python.exe" -m app
echo.
echo  Backend stoppet. Feilkode: %ERRORLEVEL%
echo  Ta et skjermbilde av dette vinduet hvis det sto en feilmelding over.
goto :end

:not_extracted
echo  FEIL: Filene er ikke pakket ut.
echo  Hoyreklikk copilot-backend.zip, velg "Pakk ut alle...",
echo  og dobbeltklikk start-backend.bat i den UTPAKKEDE mappen.
goto :end

:no_python
echo  FEIL: Fant ikke Python 3.12, 3.13 eller 3.14.
echo  Installer Python 3.14 fra https://www.python.org/downloads/windows/
echo  og huk av "Add Python to PATH" i installasjonen. Kjor deretter denne filen paa nytt.
goto :end

:venv_failed
echo  FEIL: Klarte ikke aa lage Python-miljo.
goto :end

:pip_failed
echo  FEIL: Installasjon av pakker feilet. Sjekk internettforbindelsen og prov igjen.
echo  Ta et skjermbilde av feilmeldingen over hvis det fortsatt feiler.
if exist ".venv\requirements.installert" del ".venv\requirements.installert"
goto :end

:end
echo.
pause
