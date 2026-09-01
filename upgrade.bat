@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

echo ========================================
echo  Expense Tracker - Upgrade from old copy
echo ========================================
echo.
echo This copies your data from an older install into this folder.
echo Your old folder is left unchanged.
echo.

set "OLD_DIR="
set /p OLD_DIR="Path to your OLD install folder (drag folder here): "
set "OLD_DIR=!OLD_DIR:"=!"

if "!OLD_DIR!"=="" (
    echo ERROR: No path entered.
    echo.
    pause
    exit /b 1
)

if not exist "!OLD_DIR!\data\expenses.db" (
    echo ERROR: "!OLD_DIR!\data\expenses.db" was not found.
    echo The old folder must contain data\expenses.db.
    echo.
    pause
    exit /b 1
)

where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python was not found on PATH.
    echo Install Python 3 from https://www.python.org/downloads/
    echo and check "Add python.exe to PATH" during setup.
    echo.
    pause
    exit /b 1
)

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set "TIMESTAMP=%%i"
set "BACKUP_ROOT=data\backups\pre-upgrade-!TIMESTAMP!"

echo.
echo [1/5] Backing up current data ^(if any^) to !BACKUP_ROOT!...
if exist "data" (
    if not exist "data\backups" mkdir "data\backups"
    mkdir "!BACKUP_ROOT!"
    xcopy /E /I /Y "data\*" "!BACKUP_ROOT!\" >nul 2>&1
    echo       Saved a copy of this folder's current data.
) else (
    mkdir data
    echo       No existing data folder — skipped.
)

echo [2/5] Copying data from old install...
xcopy /E /I /Y "!OLD_DIR!\data\*" "data\" >nul
if errorlevel 1 (
    echo ERROR: Failed to copy data from "!OLD_DIR!\data".
    pause
    exit /b 1
)
echo       Copied data\ from old install.

echo [3/5] Copying expense_tracker\.env from old install ^(if present^)...
if exist "!OLD_DIR!\expense_tracker\.env" (
    copy /Y "!OLD_DIR!\expense_tracker\.env" "expense_tracker\.env" >nul
    echo       Copied expense_tracker\.env.
) else (
    echo       No .env in old install — keeping current or .env.example.
)

echo [4/5] Setting up virtual environment...
set "VENV_OK=0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" --version >nul 2>&1
    if not errorlevel 1 set "VENV_OK=1"
)
if "!VENV_OK!"=="0" (
    if exist ".venv" (
        echo       Existing .venv is missing or broken — recreating.
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

echo [5/5] Installing dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul 2>&1
".venv\Scripts\python.exe" -m pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt
if errorlevel 1 (
    echo ERROR: pip install failed.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -m playwright install chromium >nul 2>&1

echo.
echo Upgrade complete.
echo   - Data copied from: !OLD_DIR!
echo   - Old install was NOT modified.
echo   - On first start, the database migrates automatically.
echo.
echo Next: double-click run.bat to start the app.
echo.
pause
endlocal
