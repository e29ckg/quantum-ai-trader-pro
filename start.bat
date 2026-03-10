@echo off
title Quantum AI Trader PRO - System Launcher
color 0A

echo ===================================================
echo   [ QUANTUM AI TRADER PRO - STARTUP SEQUENCE ]
echo ===================================================
echo.

:: 1. สั่งรัน Backend (FastAPI) ในหน้าต่างใหม่
echo [1/2] 📡 Starting Backend Server (FastAPI / AI Engine)...
start "Quantum AI - Backend" cmd /k "venv\Scripts\activate && uvicorn api.server:app --host 127.0.0.1 --port 8000"

:: รอ 3 วินาทีให้ Backend เปิดเสร็จก่อน
timeout /t 3 /nobreak >nul

:: 2. สั่งรัน Frontend (Vue 3 Dashboard) ในหน้าต่างใหม่
echo [2/2] 🖥️ Starting Frontend Dashboard (Vue 3)...
cd dashboard
start "Quantum AI - Frontend" cmd /k "npm run dev"

echo.
echo ===================================================
echo   ✅ ALL SYSTEMS ONLINE!
echo   Dashboard will be available at: http://localhost:5173
echo   (You can close this launcher window now)
echo ===================================================
pause