@echo off
title KHSAR Attendance System

REM Copy .env.example to .env if .env doesn't exist
if not exist .env (
    copy .env.example .env
    echo .env created from .env.example — sila kemaskini nilai sebelum teruskan.
    pause
)

REM Install dependencies if needed
pip show flask >nul 2>&1 || pip install -r requirements.txt

echo.
echo ============================================
echo   KHSAR Attendance System
echo ============================================
echo   Web Dashboard : http://localhost:8080
echo   Telegram Bot  : running in background
echo ============================================
echo.

REM Start Telegram bot in background
start "KHSAR Bot" cmd /c "set SERVICE_MODE=bot && python main.py & pause"

REM Start web app (foreground)
set SERVICE_MODE=web
python main.py
