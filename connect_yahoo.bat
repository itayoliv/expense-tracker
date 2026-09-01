@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "VENV_OK=0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" --version >nul 2>&1
    if not errorlevel 1 set "VENV_OK=1"
)
if "%VENV_OK%"=="0" (
    echo Virtual environment not found or broken ^(common after copying from another PC^).
    echo Run install.bat once before using connect_yahoo.bat.
    echo.
    pause
    exit /b 1
)

if not exist "data" mkdir data

echo ========================================
echo  Connect Yahoo Finance
echo ========================================
echo.
echo A browser window will open.
echo 1. Log in to Yahoo Finance if asked.
echo 2. Wait until your portfolios page loads.
echo 3. Return here — the session will be saved automatically.
echo.
echo Your password is never stored — only a local browser session.
echo.

".venv\Scripts\python.exe" -m expense_tracker.yahoo_finance connect
set ERR=%ERRORLEVEL%

echo.
if %ERR% neq 0 (
    echo Connection failed. See the message above.
) else (
    echo Done. Start the app with run.bat, then open Investments and click Refresh.
)
echo.
pause
endlocal
exit /b %ERR%
