@echo off
chcp 65001 >nul
title SC-HUB Unified System Launcher
color 0b

echo =====================================================================
echo   💎 SC-HUB UNIFIED ECOSYSTEM LAUNCHER (BOT + EXECUTIVE WEB BACK-OFFICE)
echo =====================================================================
echo.

cd /d "%~dp0"

echo [*] Launching Discord Client Service Bot in a separate window...
start "SC-HUB Discord Bot" cmd /c "start_bot.bat"

echo [*] Launching Executive Web Management Console in a separate window...
start "SC-HUB Web Console" cmd /c "cd /d "%~dp0Website" && start_website.bat"

echo.
echo [✓] Both services have been launched!
echo     - Discord Bot: Operating on Discord Guild
echo     - Executive Web Hub: http://127.0.0.1:8080
echo.
timeout /t 5
