# Automation Engine Architecture — Phase 21

## Overview

The Phase 21 automation layer provides safe, bounded, repeatable pipeline execution with run history persistence and outbound notification support. It builds upon the existing `Scheduler`, `WorkflowOrchestrator`, and `AlertEngine` modules without modifying their interfaces.

**Execution remains structurally disabled.** All pipelines run in `research`, `paper`, or `live_safe` modes. No broker orders are placed.

## Module Layout

```
src/automation/
├── __init__.py
├── models.py               # PipelineType, TriggerSource, RunStatus, JobDefinition, RunRecord, RunManifest
├── scheduler_service.py     # AutomationSchedulerService (dispatch, cooldown, scheduling)
├── run_store.py             # RunStore (file-based JSON persistence, retention)
└── notification/
    ├── __init__.py
    ├── models.py            # NotificationType, ChannelType, ContactTarget, NotificationPreferences
    ├── service.py           # NotificationService (channel dispatch, preferences management)
    └── channels/
        ├── __init__.py
        ├── base.py          # BaseNotificationChannel ABC + placeholder adapters
        ├── email_channel.py # SMTP email adapter
        └── telegram_channel.py  # Telegram Bot API adapter
```

## Pipeline Types

| Pipeline | Execution Mode | Default Schedule |
|---|---|---|
| `morning_scan` | research | Daily 09:15 IST |
| `intraday_refresh` | research | Every 30 min |
| `decision_refresh` | research | Manual |
| `eod_processing` | research | Daily 15:45 IST |
| `paper_refresh` | paper | Manual |
| `live_safe_refresh` | live_safe | Manual |
| `manual_rescan` | research | Manual |

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/automation/schedules` | All job definitions with next/last run |
| GET | `/api/v1/automation/runs` | Recent run history |
| GET | `/api/v1/automation/runs/{run_id}` | Single run details |
| POST | `/api/v1/automation/trigger/{pipeline_type}` | Manual trigger |
| GET | `/api/v1/automation/notification/preferences` | Get preferences (masked) |
| PUT | `/api/v1/automation/notification/preferences` | Update preferences |
| POST | `/api/v1/automation/notification/test/{channel_type}` | Test notification |

## Notification Channels

- **Email** — SMTP via env vars (`NOTIFICATION_SMTP_*`)
- **Telegram** — Bot API via env var (`NOTIFICATION_TELEGRAM_BOT_TOKEN`)
- **WhatsApp / Slack / Discord / Webhook** — Placeholder adapters (future phases)

All secrets are read from environment variables only. Notification channels are outbound-only — no trade approval via messaging.

## Safety Guarantees

1. `PipelineType` → execution mode mapping never returns `"live"`
2. `RunProfile.execution_allowed` remains `False` for all modes
3. Rate limiting (configurable cooldown per job, default 300s)
4. All contact targets are masked in API responses and logs
5. Notification failures never break automation dispatch
