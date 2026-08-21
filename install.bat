@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ========================================
echo  Expense Tracker - First-time install
echo ========================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python was not found on PATH.
    echo Install Python 3 from https://www.python.org/downloads/
    echo and check "Add python.exe to PATH" during setup.
    echo.
    pause
    exit /b 1
)

echo [1/3] Creating virtual environment (.venv)...
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
) else (
    echo       .venv already exists — skipping create.
)

echo [2/3] Installing dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: pip install failed.
    pause
    exit /b 1
)

echo [3/3] Setting up .env...
if not exist ".env" (
    if exist ".env.example" (
        copy /Y ".env.example" ".env" >nul
        echo       Created .env from .env.example
        echo       Edit .env if you want an OpenAI API key.
    ) else (
        echo WARNING: .env.example missing — skipped .env create.
    )
) else (
    echo       .env already exists — leaving it unchanged.
)

if not exist "data" mkdir data

echo.
echo Install complete.
echo Next: double-click run.bat to start the app.
echo.
pause
endlocal
