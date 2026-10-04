@echo off
setlocal
title Audiobro - installer och start v1.0.0
echo ==========================================
echo  Audiobro - installerar Python + tillagg
echo  och startar appen (v1.0.0)
echo ==========================================
echo.

REM Hitta Python (py launcher forst, sedan python)
set PY=
where py >nul 2>&1
if %errorlevel%==0 set PY=py
if not defined PY (
  where python >nul 2>&1
  if %errorlevel%==0 set PY=python
)

if not defined PY (
  echo [1/4] Python hittades inte - forsoker installera via winget...
  where winget >nul 2>&1
  if %errorlevel%==0 (
    echo   Kor: winget install Python.Python.3.12
    winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
    if %errorlevel%==0 (
      echo   Klart! Stang detta fonster, oppna en NY terminal och kor bat-filen igen.
      pause
      exit /b 0
    ) else (
      echo   Winget misslyckades (kanske redan installerad men inte i PATH).
    )
  ) else (
    echo   Winget saknas pa denna Windows.
  )
  echo.
  echo   LOSNING: Ladda ner Python manuellt:
  echo   https://www.python.org/downloads/
  echo   Viktigt: bocka i "Add python.exe to PATH" i installern!
  echo.
  pause
  exit /b 1
)

echo [1/4] Hittade Python: %PY%
%PY% --version
if %errorlevel% neq 0 (
  echo Kunde inte kora %PY% --version
  pause
  exit /b 1
)
echo.

echo [2/4] Uppdaterar pip...
%PY% -m pip install --upgrade pip
if %errorlevel% neq 0 (
  echo Varning: pip upgrade misslyckades - forsoker anda fortsatta...
)
echo.

echo [3/4] Installerar/uppdaterar tillagg...
if exist requirements.txt (
  echo   Hittade requirements.txt - kor pip install -r requirements.txt --upgrade
  %PY% -m pip install --upgrade -r requirements.txt
) else (
  echo   Ingen requirements.txt - installerar standardpaket
  %PY% -m pip install --upgrade beautifulsoup4 lxml requests mutagen Pillow rapidfuzz
)
if %errorlevel% neq 0 (
  echo.
  echo  pip install misslyckades.
  echo   Tips: Hogerklicka bat-filen och kor "Kor som administrator"
  echo   eller kor manuellt: %PY% -m pip install beautifulsoup4 lxml requests mutagen Pillow rapidfuzz
  pause
  exit /b 1
)
echo   Klart!
echo.

echo [4/4] Startar Audiobro...
if exist Audiobro.pyw (
  echo   Startar: %PY% Audiobro.pyw
  start "" %PY%w Audiobro.pyw 2>nul
  if %errorlevel% neq 0 start "" %PY% Audiobro.pyw
) else if exist ags\gui.py (
  echo   Startar: %PY% -m ags.gui
  start "" %PY% -m ags.gui
) else (
  echo   Hittar inte Audiobro.pyw i %CD%
  dir /b 2>nul
  pause
  exit /b 1
)

echo.
echo ==========================================
echo  Klart! Audiobro bor oppna nu.
echo  Om inget hander: kor manuellt i terminal:
echo    %PY% Audiobro.pyw
echo  och kolla efter fel (t.ex. WAF-token behovs).
echo  Detta fonster stangs om 5 sek...
echo ==========================================
timeout /t 5 >nul
exit /b 0
