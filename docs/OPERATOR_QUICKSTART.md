# Operator Quickstart

This document provides a reference for running the AI Quant Trading Command Center locally.

> **CRITICAL SAFETY NOTE**: This platform is designed to run completely inert. It monitors, simulates, and plans, but **DOES NOT execute live orders**. All broker and session integrations are strictly read-only or simulation boundaries.

---

## 🚀 Local Launcher (Fastest Way)

We provide bundled scripts to start both the Python backend API and the React/Vite frontend UI concurrently.

**On Windows (PowerShell):**
```powershell
.\scripts\start_command_center.ps1
```

**On Windows (Command Prompt):**
```cmd
.\scripts\start_command_center.bat
```

When started, the launcher boots:
- **Backend API:** `http://localhost:8000` (FastAPI)
- **Frontend UI:** `http://localhost:5173` (React)

You can hit `Ctrl+C` in the launcher window to terminate both processes.

### Desktop Shortcut Setup (Optional)
To create a Windows desktop shortcut:
1. Right-click your Desktop -> **New** -> **Shortcut**.
2. Set the target to: `cmd.exe /c "C:\Path\To\AI Trading\scripts\start_command_center.bat"`
3. Name it "AI Command Center" and save.

---

## ⚙️ Manual Startup

### Backend
Start the FastAPI backend with uvicorn from the project root:
```bash
python -m uvicorn src.api.main:app --reload --port 8000
```
API Documentation will be available at: http://localhost:8000/docs

### Frontend
Start the Vite dev server from the `frontend/` directory:
```bash
cd frontend
npm install
npm run dev
```

---

## 🛠️ CLI Pipeline Triggers
While the UI can trigger automated pipelines under the "Automation" tab, you can also run them manually from your terminal.

| Pipeline | Command Runner | Description |
|----------|---------------|-------------|
| **Scanner** | `python scripts/run_scanner.py` | Runs strategy scans across symbols |
| **Monitoring** | `python scripts/run_monitoring.py` | Refreshes real-time criteria tracking |
| **Decision** | `python scripts/run_decision.py` | Allocates simulated portfolio risk limits |
| **Paper Trade**| `python scripts/run_paper_trading.py`| Tracks simulated PnL against signals |
| **Live Safe** | `python scripts/run_live_signal_pipeline.py`| Prepares signals without placing orders |

Check the `README.md` for specific arguments for each command.

---

## 🔑 Broker Sessions & Credentials
The platform allows configuring API Keys and Access Tokens via the Settings panel for:
- Zerodha (Kite)
- DhanHQ
- Upstox

To read from your environment instead of UI configuration, set variables using the provider prefix, such as `ZERODHA_API_KEY`, `DHAN_CLIENT_ID`, `UPSTOX_ACCESS_TOKEN`, etc.

When a session is "Validated", the backend performs a real **read-only** call (e.g. fetching your profile or margin limits) to prove the SDK auth is intact. **No orders are placed.**
