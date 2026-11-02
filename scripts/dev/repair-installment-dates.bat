@echo off
setlocal
cd /d "%~dp0..\.."
chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"
set "TARGET_DB=%~1"
if "%TARGET_DB%"=="" set "TARGET_DB=data/expenses.db"
echo Repairing installment dates in %TARGET_DB%
echo.
".venv\Scripts\python.exe" scripts\dev\repair_installment_dates.py "%TARGET_DB%"
echo.
pause
endlocal
