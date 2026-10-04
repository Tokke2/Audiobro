@echo off
setlocal
chcp 65001 >nul
title Avinstallera ALL Python + installera om (Audiobro)
echo ================================================
echo  AVINSTALLERAR ALL PYTHON - sedan installerar om
echo  Kor som ADMINISTRATOR for bast resultat
echo ================================================
echo.
echo  VARNING: Stanger alla Python-program. Spara ditt arbete!
echo.
pause
echo.

echo [1/5] Avinstallerar Python via winget...
where winget >nul 2>&1
if %errorlevel%==0 (
  for %%P in (Python.Python.3.12 Python.Python.3.11 Python.Python.3.10 Python.Python.3.13 Python.Python.3.9 Python.Launcher) do (
    echo   Forsoker avinstallera %%P ...
    winget uninstall -e --id %%P --silent --accept-source-agreements 2>nul
  )
  echo   + Microsoft Store-Python (om finns)
  winget uninstall -e --id 9PJPW5LDXLZ5 --silent 2>nul
  powershell -Command "Get-AppxPackage *Python* | Remove-AppxPackage" 2>nul
) else (
  echo   winget saknas - hoppar winget-avinstall
)
echo.

echo [2/5] Raderar vanliga Python-mappar...
for %%D in (
  "%LOCALAPPDATA%\Programs\Python"
  "C:\Python312" "C:\Python313" "C:\Python311" "C:\Python310"
  "%USERPROFILE%\Documents\python"
  "%APPDATA%\Python"
) do (
  if exist %%D (
    echo   Raderar %%D
    rmdir /s /q %%D 2>nul
  )
)
echo.

echo [3/5] Rensar py-launcher cache...
where py >nul 2>&1 && py --list 2>nul
echo.

echo [4/5] Installerar Python 3.12 rent via winget...
where winget >nul 2>&1
if %errorlevel%==0 (
  winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
  if %errorlevel%==0 (
    echo   Python 3.12 installerad!
  ) else (
    echo   Winget install misslyckades - prova manuellt:
    echo   https://www.python.org/downloads/ ^(bocka i "Add python to PATH"^)
  )
) else (
  echo   Winget saknas - ladda ner manuellt:
  echo   https://www.python.org/downloads/
)
echo.

echo [5/5] Verifierar...
timeout /t 3 /nobreak >nul
where py >nul 2>&1 && py --version
where python >nul 2>&1 && python --version
echo.
echo Om du ser "Python 3.12.x" ovan ar det klart!
echo.
echo Nasta steg: Dubbelklicka "Starta Audiobro.bat" i samma mapp
echo Den kor: pip install -r requirements.txt och startar appen.
echo.
pause
