@echo off
cd /d "%~dp0..\.."
set "EXPENSE_DB=data/dev/expenses.db"
echo Using scratch database: %EXPENSE_DB%
call run.bat
