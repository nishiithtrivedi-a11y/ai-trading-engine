# Automation Engine Architecture — Phase 21

## Overview

The Phase 21 automation layer provides safe, bounded, repeatable pipeline execution with run history persistence and outbound notification support. It delegates schedule computation to the existing `Scheduler` class (`src/monitoring/scheduler.py`) and exposes a pluggable `PipelineRunner` callback that defaults to a no-op runner for this phase. Integration with `WorkflowOrchestrator` or real script runners is intentionally deferred to a future phase via the runner hook — the interface is ready for that wiring.

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

| Channel | Status | Config |
|---|---|---|
| Email (SMTP) | ✅ Implemented | `NOTIFICATION_SMTP_HOST/PORT/USER/PASSWORD/FROM/USE_TLS` |
| Telegram | ✅ Implemented | `NOTIFICATION_TELEGRAM_BOT_TOKEN` (env var) + `chat_id` per contact |
| WhatsApp | 🔲 Placeholder only | Not implemented — reserved for future phase |
| Slack | 🔲 Placeholder only | Not implemented — reserved for future phase |
| Discord | 🔲 Placeholder only | Not implemented — reserved for future phase |
| Webhook | 🔲 Placeholder only | Not implemented — reserved for future phase |

All secrets are read from environment variables **only**. Notification channels are **outbound-only** — no inbound command handling, no trade approval via messaging.

## Safety Guarantees

1. `PipelineType` → execution mode mapping (`execution_mode_for_pipeline()`) never returns `"live"` — enforced by exhaustive enum match and tested by `test_execution_mode_never_live`
2. All dispatched `RunRecord` objects carry `execution_mode` set only at dispatch time via #1 above — no post-dispatch override path exists
3. Rate limiting (configurable cooldown per job, default 300s) — returns HTTP 429 on violation
4. All contact targets are masked in API responses and logs — `to_safe_dict()` is used at every response boundary
5. Notification failures never break automation dispatch — all `notification_hook` calls are wrapped in silent try/except
