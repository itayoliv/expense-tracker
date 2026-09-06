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

echo [1/4] Creating virtual environment (.venv)...
set "VENV_OK=0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" --version >nul 2>&1
    if not errorlevel 1 set "VENV_OK=1"
)
if "%VENV_OK%"=="0" (
    if exist ".venv" (
        echo       Existing .venv is missing or broken ^(e.g. copied from another PC^) — recreating.
        rmdir /s /q ".venv"
    )
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
) else (
    echo       .venv already exists — skipping create.
)

echo [2/4] Installing dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt
if errorlevel 1 (
    echo ERROR: pip install failed.
    pause
    exit /b 1
)

echo [3/4] Playwright package ready (uses installed Edge/Chrome for Yahoo Finance)...
REM Optional: download Playwright Chromium if Edge/Chrome are unavailable.
".venv\Scripts\python.exe" -m playwright install chromium >nul 2>&1
if errorlevel 1 (
    echo       Skipped Chromium download — will use Microsoft Edge or Chrome instead.
) else (
    echo       Playwright Chromium installed as a fallback browser.
)

echo [4/4] Setting up .env...
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
echo Optional: double-click connect_yahoo.bat to link Yahoo Finance portfolios.
echo.
pause
endlocal
