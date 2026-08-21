@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Virtual environment not found.
    echo Run install.bat once before using run.bat.
    echo.
    pause
    exit /b 1
)

if not exist "expense_tracker\.env" (
    if exist "expense_tracker\.env.example" (
        copy /Y "expense_tracker\.env.example" "expense_tracker\.env" >nul
        echo Created expense_tracker\.env from .env.example
    )
)

if not exist "data" mkdir data

echo Starting Expense Tracker...
echo Open http://127.0.0.1:5000 in your browser.
echo Press Ctrl+C in this window to stop the server.
echo.

start "" "http://127.0.0.1:5000"
".venv\Scripts\python.exe" -m expense_tracker

echo.
echo Server stopped.
pause
endlocal
