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

echo [STEP] Checking Python...
python --version
if errorlevel 1 (
    echo [ERROR] Python not found in PATH. Please install Python.
    pause
    exit /b 1
)

echo.
echo [STEP] Checking Node/npm...
call npm --version
if errorlevel 1 (
    echo [ERROR] npm not found in PATH. Please install Node.js.
    pause
    exit /b 1
)

echo.
echo [STEP] Moving to project root...
cd /d "%~dp0.."
echo Current directory:
cd

echo.
echo [STEP] Starting Backend (Uvicorn)...
start "AI Trading Backend" cmd /k "cd /d %cd% && python -m uvicorn src.api.main:app --reload --port 8000"

echo.
echo [STEP] Starting Frontend (Vite)...
start "AI Trading Frontend" cmd /k "cd /d %cd%\frontend && call npm run dev"

echo.
echo [STEP] Waiting a few seconds before opening browser...
timeout /t 5 /nobreak >nul

echo.
echo [STEP] Opening browser...
start "" "http://localhost:5173"

echo.
echo ==========================================================
echo The Command Center startup commands were launched.
echo Backend API:  http://localhost:8000
echo API Docs:     http://localhost:8000/docs
echo UI Dashboard: http://localhost:5173
echo ==========================================================
echo.
pause