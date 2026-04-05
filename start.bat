@echo off
title KHSAR Attendance System

REM Copy .env.example to .env if .env doesn't exist
if not exist .env (
    copy .env.example .env
    echo .env created from .env.example — sila kemaskini nilai sebelum teruskan.
    pause
)

REM Install/update dependencies from requirements
py -3 -m pip install -r requirements.txt

echo.
echo ============================================
echo   KHSAR Attendance System
echo ============================================
echo   Web Dashboard : http://localhost:8080
echo   Telegram Bot  : running together
echo ============================================
echo.

REM Start web + bot together
set SERVICE_MODE=all
py -3 main.py
