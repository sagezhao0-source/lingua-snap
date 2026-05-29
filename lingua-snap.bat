@echo off
cd /d "%~dp0"
echo Starting LinguaSnap...
echo.
echo Usage: Click the floating bubble to start/stop recording
echo Right-click bubble for menu | Tray icon for options
echo.
start "" python "%CD%\main.py"
