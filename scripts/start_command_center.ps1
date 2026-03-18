# AI Quant Trading Command Center - local launcher
$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "AI Quant Trading Command Center - Local Launcher" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "NOTE: Execution is completely disabled. This platform runs in" -ForegroundColor Yellow
Write-Host "research, paper_safe, and live_safe modes only." -ForegroundColor Yellow
Write-Host ""

# Check Python
try {
    $null = python --version
} catch {
    Write-Host "[ERROR] Python not found in PATH. Please install Python." -ForegroundColor Red
    Read-Host "Press Enter to exit..."
    exit
}

# Check NPM
try {
    $null = npm --version
} catch {
    Write-Host "[ERROR] npm not found in PATH. Please install Node.js." -ForegroundColor Red
    Read-Host "Press Enter to exit..."
    exit
}

# Ensure context is project root
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -Path "$ProjectRoot\.."

Write-Host "[INFO] Starting Backend (Uvicorn)..." -ForegroundColor Green
Start-Process -NoNewWindow -FilePath "python" -ArgumentList "-m uvicorn src.api.main:app --reload --port 8000" -PassThru

Write-Host "[INFO] Starting Frontend (Vite)..." -ForegroundColor Green
Set-Location -Path "frontend"
Start-Process -NoNewWindow -FilePath "npm" -ArgumentList "run dev" -PassThru

Write-Host ""
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "The Command Center has been started." -ForegroundColor White
Write-Host "- Backend API:  http://localhost:8000" -ForegroundColor White
Write-Host "- API Docs:     http://localhost:8000/docs" -ForegroundColor White
Write-Host "- UI Dashboard: http://localhost:5173" -ForegroundColor White
Write-Host ""
Write-Host "Press Ctrl+C to terminate the services." -ForegroundColor Yellow

# Wait indefinitely to keep the processes running in this window
try {
    while ($true) { Start-Sleep -Seconds 1 }
} catch {
    Write-Host "Shutting down..."
}
