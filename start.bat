@echo off
setlocal
title Xianyu Auto Ship Tool
cd /d "%~dp0"

rem Mirror for Playwright browser download (faster in CN)
set "PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com/binaries/playwright"

if not exist ".venv\Scripts\python.exe" (
    echo [First run] Creating virtual environment and installing dependencies...
    echo Please wait, this may take a few minutes.
    where python >nul 2>nul
    if errorlevel 1 (
        echo ERROR: Python not found. Please install Python 3.9+ and check "Add to PATH".
        pause
        exit /b 1
    )
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
    if errorlevel 1 (
        echo ERROR: Failed to install dependencies. Check your network and retry.
        pause
        exit /b 1
    )
    echo Downloading Chromium browser kernel if needed...
    ".venv\Scripts\python.exe" -m playwright install chromium
)

echo Starting application...
".venv\Scripts\python.exe" main.py
if errorlevel 1 (
    echo Program exited with error code %errorlevel%
    pause
)
endlocal
