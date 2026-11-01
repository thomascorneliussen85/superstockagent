@echo off
setlocal EnableExtensions EnableDelayedExpansion
title AI Trading Copilot - installasjon
rem Engangsinstallasjon: henter programmet fra GitHub til %USERPROFILE%\AITradingCopilot,
rem tar med innstillinger (.env, API-nokkel, token, journal) fra en gammel zip-installasjon,
rem og lager snarveier paa skrivebordet. Etterpaa oppdaterer du med "AI Copilot - oppdater".

set "REPO=https://github.com/thomascorneliussen85/superstockagent.git"
set "BRANCH=ccr-1b41e58f-tt6dni"
set "DEST=%USERPROFILE%\AITradingCopilot"

echo.
echo  AI Trading Copilot - installasjon
echo  Mappe: %DEST%
echo.

call :find_git
if not defined GIT goto :no_git
echo  Bruker git: !GIT!

if exist "%DEST%\.git" (
  echo  Programmet er allerede installert. Kjorer oppdatering i stedet.
  call "%DEST%\copilot\oppdater.bat"
  goto :end
)

echo  Henter programmet fra GitHub. Forste gang kan det komme et vindu
echo  der du logger inn paa GitHub - gjor det, saa husker Windows det.
echo.
"!GIT!" clone --branch %BRANCH% "%REPO%" "%DEST%"
if errorlevel 1 goto :clone_failed

rem --- Ta med innstillinger fra gammel zip-installasjon ---
set "NEWB=%DEST%\copilot\backend"
for %%D in ("%USERPROFILE%\Downloads\copilot-backend\copilot-backend" "%USERPROFILE%\Downloads\copilot-backend" "%USERPROFILE%\Desktop\copilot-backend") do (
  if exist "%%~D\.env" if not exist "%NEWB%\.env" (
    echo  Fant gamle innstillinger i %%~D - kopierer .env og data
    copy /y "%%~D\.env" "%NEWB%\.env" >nul
    if exist "%%~D\data" xcopy /e /i /y /q "%%~D\data" "%NEWB%\data" >nul
  )
)

rem --- Snarveier paa skrivebordet ---
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s=New-Object -ComObject WScript.Shell; $d=[Environment]::GetFolderPath('Desktop');" ^
  "$a=$s.CreateShortcut(\"$d\AI Copilot - start.lnk\"); $a.TargetPath='%NEWB%\start-backend.bat'; $a.WorkingDirectory='%NEWB%'; $a.Save();" ^
  "$b=$s.CreateShortcut(\"$d\AI Copilot - oppdater.lnk\"); $b.TargetPath='%DEST%\copilot\oppdater.bat'; $b.WorkingDirectory='%DEST%\copilot'; $b.Save()"

echo.
echo  FERDIG. Gjor dette EN gang i Chrome:
echo   1. Aapne chrome://extensions
echo   2. Fjern den gamle "AI Trading Copilot" - Remove
echo   3. Trykk "Last inn upakket" og velg mappen:
echo      %DEST%\copilot\extension\dist
echo   4. Start backend med snarveien "AI Copilot - start" paa skrivebordet.
echo      Var tokenet nytt, lim det inn i utvidelsens innstillinger.
echo.
echo  Senere oppdateringer: dobbeltklikk "AI Copilot - oppdater".
goto :end

:find_git
set "GIT="
for /f "delims=" %%G in ('where git 2^>nul') do if not defined GIT set "GIT=%%G"
if defined GIT goto :eof
for %%P in ("%ProgramFiles%\Git\cmd\git.exe" "%ProgramFiles(x86)%\Git\cmd\git.exe" "%LOCALAPPDATA%\Programs\Git\cmd\git.exe") do (
  if not defined GIT if exist "%%~P" set "GIT=%%~P"
)
if defined GIT goto :eof
for /d %%A in ("%LOCALAPPDATA%\GitHubDesktop\app-*") do (
  if exist "%%~A\resources\app\git\cmd\git.exe" set "GIT=%%~A\resources\app\git\cmd\git.exe"
)
goto :eof

:no_git
echo  FEIL: Fant ikke git.
echo  Installer "Git for Windows" fra https://git-scm.com/download/win - velg standardvalg -
echo  og kjor denne filen paa nytt.
goto :end

:clone_failed
echo.
echo  FEIL: Klarte ikke aa hente fra GitHub.
echo  - Sjekk at du logget inn med kontoen som har tilgang til superstockagent.
echo  - Har du bare GitHub Desktop: installer ogsaa "Git for Windows" fra
echo    https://git-scm.com/download/win - den har innlogging til GitHub innebygd.
goto :end

:end
echo.
pause
