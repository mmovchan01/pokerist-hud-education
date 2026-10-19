@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
    where python >nul 2>nul
    if errorlevel 1 (
        echo Python not found. Install Python 3.10+ from python.org with Tcl/Tk and PATH enabled.
        pause
        exit /b 1
    )
    python bootstrap.py
) else (
    py -3 bootstrap.py
)
if errorlevel 1 (
    echo Startup failed. See the message above.
    pause
    exit /b 1
)
endlocal
