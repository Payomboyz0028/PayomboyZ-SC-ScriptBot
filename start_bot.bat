@echo off
chcp 65001 >nul
title SC-HUB Client Service & Work-Allocation Bot
color 0b

echo =====================================================================
echo   💎 SC-HUB CLIENT SERVICE & WORK-ALLOCATION BOT (SC-Script-Bot)
echo =====================================================================
echo.

cd /d "%~dp0"

py -3.12 -c "import discord, PIL, aiohttp" 2>nul
if %errorlevel% neq 0 (
    echo [*] Checking and installing required dependencies...
    py -3.12 -m pip install -r requirements.txt
    echo.
)

echo [*] Launching SC-HUB bot runtime with Python 3.12...
py -3.12 bot.py

pause
