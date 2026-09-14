@echo off
title GoXLR Mini - Spotify overlay
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    set "PY=py -3"
) else (
    set "PY=python"
)

if not exist ".venv\Scripts\python.exe" (
    echo [*] Prvo pokretanje - stvaram virtualno okruzenje i instaliram ovisnosti...
    %PY% -m venv .venv || goto :error
    ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :error
)

".venv\Scripts\python.exe" goxlr_overlay.py %*
goto :eof

:error
echo.
echo [!] Nesto je poslo po zlu. Provjeri je li Python 3.10+ instaliran.
pause
