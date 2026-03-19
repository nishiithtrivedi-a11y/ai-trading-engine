# Operator Quickstart

Run the AI Quant Trading Command Center locally for analysis, monitoring, and paper/live-safe workflows.

## Safety First

This platform is execution-disabled by design.

- It can monitor, analyze, and simulate.
- It does not place live broker orders.
- Provider connections are for session/data validation only.

## Fastest Startup

### Windows PowerShell

```powershell
.\scripts\start_command_center.ps1
```

### Windows Command Prompt

```cmd
.\scripts\start_command_center.bat
```

Services:

- Backend API: `http://localhost:8000`
- Frontend UI: `http://localhost:5173`

## Manual Startup

### Backend

```bash
python -m uvicorn src.api.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Runtime Source Selection

1. Open **Settings**.
2. Connect and validate a provider session.
3. Click **Set as Primary** for an active provider.
4. Runtime source is persisted to `config/data_providers.yaml`.

If selected broker session is inactive, the system reports fallback/offline modes truthfully.

## Provider Credentials

Store credentials in `.env` (or process env), not in tracked YAML files.

- Zerodha: `ZERODHA_API_KEY`, `ZERODHA_API_SECRET`, `ZERODHA_ACCESS_TOKEN`
- Upstox: `UPSTOX_API_KEY`, `UPSTOX_API_SECRET`, `UPSTOX_ACCESS_TOKEN`
- DhanHQ: `DHAN_CLIENT_ID`, `DHAN_ACCESS_TOKEN`

## Automation Triggers

Automation endpoints are available under `/api/v1/automation`.

- Repeated triggers respect cooldown and return `429`.
- Run history includes status, duration, market phase, runtime source, and errors.
- Manifests are written under `output/automation/<pipeline>/<run_id>/run_manifest.json`.

## Reminder

Provider connectivity does not grant execution authority. Execution remains disabled.
