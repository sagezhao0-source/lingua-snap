@echo off
cd /d "%~dp0"

:: Check for admin privileges
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting administrator privileges...
    powershell -Command "Start-Process 'python' -ArgumentList '%CD%\main.py' -Verb RunAs"
    exit /b
)

:: Running as admin
echo Starting LinguaSnap...
python "%CD%\main.py"
echo.
echo LinguaSnap has exited. Press any key to close.
pause >nul
