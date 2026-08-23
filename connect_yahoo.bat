@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Virtual environment not found.
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
