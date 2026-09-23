@echo off
setlocal EnableExtensions
cd /d "%~dp0..\.."

set "DEV_DB=data\dev\expenses.db"
if not exist "%DEV_DB%" if not exist "%DEV_DB%-wal" if not exist "%DEV_DB%-shm" (
    echo No scratch database found at data\dev\
    pause
    exit /b 0
)

echo Deleting scratch database under data\dev\...
del /Q "%DEV_DB%" 2>nul
del /Q "%DEV_DB%-wal" 2>nul
del /Q "%DEV_DB%-shm" 2>nul
del /Q "%DEV_DB%-journal" 2>nul
echo Done. Next scripts\dev\run-dev.bat will create a fresh empty DB.
pause
endlocal
