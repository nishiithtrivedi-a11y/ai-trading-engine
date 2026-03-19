# Automation Engine Architecture - Phase 21

## Overview

The automation layer provides safe, bounded pipeline triggering for research, paper, and live-safe workflows.

It now dispatches through `WorkflowOrchestrator` (not a no-op runner), persists run records, writes per-run manifests, and emits outbound notifications.

Execution remains structurally disabled. No broker orders are placed.

## Module Layout

```
src/automation/
|- models.py            # PipelineType, TriggerSource, RunStatus, JobDefinition, RunRecord, RunManifest
|- scheduler_service.py # AutomationSchedulerService (dispatch, cooldown, market gating)
|- run_store.py         # File-based run history persistence
|- notification/        # Outbound notifications (email/telegram + placeholders)
```

## Supported Pipelines

| Pipeline | Execution Mode | Default Schedule | Orchestrator Path |
|---|---|---|---|
| `morning_scan` | research | Daily 09:15 IST | `scripts/run_scanner.py --profile morning` |
| `intraday_refresh` | research | Every 30 min | `scripts/run_monitoring.py --profile intraday` |
| `decision_refresh` | research | Manual | `scripts/run_decision.py --profile intraday` |
| `eod_processing` | research | Daily 15:45 IST | `scripts/run_decision.py --profile eod` |
| `paper_refresh` | paper | Manual | `scripts/run_paper_trading.py --paper-trading ...` |
| `live_safe_refresh` | live_safe | Manual | `scripts/run_live_signal_pipeline.py --live-signals ...` |
| `manual_rescan` | research | Manual | `scripts/run_scanner.py --run-once` |

## Cooldown and Trigger Rules

- Cooldown is enforced in the actual trigger path before dispatch.
- Cooldown uses both in-memory timestamps and persisted run history (survives process restart).
- Violations return HTTP `429` with remaining cooldown time.
- Market-session gating blocks live-data-dependent pipelines when market is closed unless runtime source is offline (`csv` or `indian_csv`).

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/automation/schedules` | Job definitions + next/last run |
| GET | `/api/v1/automation/runs` | Recent run history |
| GET | `/api/v1/automation/runs/{run_id}` | Single run details |
| POST | `/api/v1/automation/trigger/{pipeline_type}` | Manual trigger |
| GET | `/api/v1/automation/notification/preferences` | Preferences (masked) |
| PUT | `/api/v1/automation/notification/preferences` | Update preferences |
| POST | `/api/v1/automation/notification/test/{channel_type}` | Test channel |

## Run Truthfulness and Manifests

Every run record and manifest includes:

- `status` and `duration_seconds`
- `execution_mode`
- `market_phase`
- `runtime_source`
- `error_message` and `error_details` when failed

Manifests are written under `output/automation/<pipeline>/<run_id>/run_manifest.json`.

## Safety Guarantees

1. `PipelineType -> execution_mode` never returns `live`.
2. Dispatch only runs research, paper, or live-safe scripts.
3. Notification failures never break pipeline dispatch.
4. Execution remains disabled independent of provider connectivity.
