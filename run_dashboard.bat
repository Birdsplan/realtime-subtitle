@echo off
setlocal
cd /d "%~dp0"
title Realtime Subtitle Dashboard

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] .venv was not found.
    echo Run install_windows.bat or ask Codex to install project dependencies first.
    pause
    exit /b 1
)

if "%DEEPSEEK_API_KEY%"=="" (
    for /f "usebackq delims=" %%K in (`powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('DEEPSEEK_API_KEY','User')"`) do set "DEEPSEEK_API_KEY=%%K"
)

if "%DEEPSEEK_API_KEY%"=="" (
    echo [WARN] DEEPSEEK_API_KEY is not visible to this process.
    echo Translation will fail until the key is set.
    echo.
)

echo [Launcher] Starting dashboard...
".venv\Scripts\python.exe" dashboard.py

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Dashboard exited with code %errorlevel%.
    pause
)
