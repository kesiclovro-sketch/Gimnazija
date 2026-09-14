@echo off
setlocal
title GoXLR Mini - Spotify overlay
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    set "PY=py -3"
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo.
        echo [!] Python nije pronaden.
        echo     Instaliraj Python 3.10 ili noviji s https://www.python.org/downloads/
        echo     VAZNO: pri instalaciji stavi kvacicu na "Add python.exe to PATH".
        echo.
        pause
        exit /b 1
    )
    set "PY=python"
)

if not exist ".venv\Scripts\python.exe" (
    echo [*] Prvo pokretanje - stvaram virtualno okruzenje i instaliram ovisnosti...
    %PY% -m venv .venv
    if errorlevel 1 goto :error
    ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto :error
    echo.
)

".venv\Scripts\python.exe" goxlr_overlay.py %*
set "CODE=%errorlevel%"

echo.
if not "%CODE%"=="0" (
    echo [!] Program je zavrsio s greskom ^(kod %CODE%^).
    echo     Detalji su gore i u datoteci goxlr_overlay.log
) else (
    echo [*] Program je zavrsen.
)
echo.
pause
exit /b %CODE%

:error
echo.
echo [!] Instalacija nije uspjela. Provjeri imas li internet vezu i
echo     je li instaliran Python 3.10 ili noviji.
echo.
pause
exit /b 1
