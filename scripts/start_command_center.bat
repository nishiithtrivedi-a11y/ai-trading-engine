@echo off
setlocal
color 0B
echo ==========================================================
echo AI Quant Trading Command Center - Local Launcher
echo ==========================================================
echo.
echo NOTE: Execution is completely disabled. This platform runs in 
echo research, paper_safe, and live_safe modes only.
echo.

:: Check for Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found in PATH. Please install Python.
    pause
    exit /b 1
)

:: Check for Node.js
npm --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] npm not found in PATH. Please install Node.js.
    pause
    exit /b 1
)

:: Ensure we are in the project root
cd /d "%~dp0.."

echo [INFO] Starting Backend (Uvicorn)...
start "AI Trading Backend" cmd /k "python -m uvicorn src.api.main:app --reload --port 8000"

echo [INFO] Starting Frontend (Vite)...
cd frontend
start "AI Trading Frontend" cmd /k "npm run dev"

echo.
echo ==========================================================
echo The Command Center has been started in separate windows.
echo - Backend API:  http://localhost:8000
echo - API Docs:     http://localhost:8000/docs
echo - UI Dashboard: http://localhost:5173
echo.
echo Press any key to exit this launcher prompt...
pause >nul
