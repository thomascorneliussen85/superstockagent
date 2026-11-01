@echo off
setlocal EnableExtensions EnableDelayedExpansion
title AI Trading Copilot - oppdatering
rem Henter siste versjon fra GitHub. Dine filer (.env med API-nokkel, data med token
rem og journal, .venv) er ikke en del av git og blir aldri rort.
cd /d "%~dp0.."

set "GIT="
for /f "delims=" %%G in ('where git 2^>nul') do if not defined GIT set "GIT=%%G"
for %%P in ("%ProgramFiles%\Git\cmd\git.exe" "%LOCALAPPDATA%\Programs\Git\cmd\git.exe") do (
  if not defined GIT if exist "%%~P" set "GIT=%%~P"
)
for /d %%A in ("%LOCALAPPDATA%\GitHubDesktop\app-*") do (
  if not defined GIT if exist "%%~A\resources\app\git\cmd\git.exe" set "GIT=%%~A\resources\app\git\cmd\git.exe"
)
if not defined GIT (
  echo  FEIL: Fant ikke git. Installer Git for Windows fra https://git-scm.com/download/win
  goto :end
)

for /f "delims=" %%B in ('"!GIT!" rev-parse --abbrev-ref HEAD') do set "BRANCH=%%B"
for /f "delims=" %%V in ('"!GIT!" rev-parse --short HEAD') do set "OLD=%%V"
echo.
echo  Oppdaterer AI Trading Copilot ^(gren !BRANCH!^) ...
"!GIT!" fetch origin !BRANCH!
if errorlevel 1 (
  echo  FEIL: Fikk ikke kontakt med GitHub. Sjekk internett og innlogging.
  goto :end
)
"!GIT!" reset --hard origin/!BRANCH! >nul
for /f "delims=" %%V in ('"!GIT!" rev-parse --short HEAD') do set "NEW=%%V"

if "!OLD!"=="!NEW!" (
  echo  Du har allerede siste versjon ^(!NEW!^).
  goto :end
)
echo.
echo  Oppdatert fra !OLD! til !NEW!. Endringer:
"!GIT!" log --oneline --no-decorate !OLD!..!NEW!
echo.
echo  For aa ta i bruk den nye versjonen:
echo   1. Lukk det svarte backend-vinduet og start "AI Copilot - start" igjen
echo      ^(nye pakker installeres automatisk ved behov^).
echo   2. Chrome: aapne chrome://extensions og trykk oppdater-pilen paa AI Trading Copilot,
echo      og last inn TradingView paa nytt med F5.

:end
echo.
pause
