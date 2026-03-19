# Provider Session Management - Phase 21.x

## Overview

Provider session management validates broker/data connectivity for read-only data access.

Connecting a provider does **not** enable live trading. Execution remains structurally disabled.

## Provider IDs and Required Credentials

| Provider ID | Display Name | Required Credentials |
|---|---|---|
| `zerodha` | Zerodha Kite | `ZERODHA_API_KEY`, `ZERODHA_API_SECRET`, `ZERODHA_ACCESS_TOKEN` |
| `upstox` | Upstox | `UPSTOX_API_KEY`, `UPSTOX_API_SECRET`, `UPSTOX_ACCESS_TOKEN` |
| `dhan` | DhanHQ | `DHAN_CLIENT_ID`, `DHAN_ACCESS_TOKEN` |

Credentials are stored in local environment settings (`.env` / process env).
Tracked YAML config must not store secret values.

## Session States

| State | Meaning |
|---|---|
| `not_configured` | Provider has credentials but not validated in current process |
| `credentials_missing` | Required credentials missing |
| `active` | Session validated successfully |
| `expired` | Token/session expired |
| `invalid` | Credential/session validation failed |
| `error` | Unexpected validation error |

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/providers/sessions` | All provider session states |
| GET | `/api/v1/providers/sessions/{type}` | Single provider status |
| POST | `/api/v1/providers/sessions/{type}/validate` | Validate/reconnect read-only session |
| POST | `/api/v1/providers/sessions/{type}/configure` | Store a single credential |
| POST | `/api/v1/providers/sessions/{type}/credentials` | Store multiple credentials |
| GET | `/api/v1/providers/sessions/zerodha/login` | Zerodha login URL |
| GET | `/api/v1/providers/sessions/zerodha/callback` | Zerodha callback handler |
| GET | `/api/v1/providers/sessions/upstox/login` | Upstox login URL |
| GET | `/api/v1/providers/sessions/upstox/callback` | Upstox callback handler |

## Runtime Source Selection

Runtime source can be promoted from Settings only when the provider session is `active`.

- Primary runtime source is persisted to `config/data_providers.yaml`.
- Secret fields are scrubbed during persistence.
- If a primary broker session is inactive, platform status reports fallback behavior.

## Safety Notes

- Provider validation calls are read-only session checks.
- No order placement is enabled by session connectivity.
- Credential values are masked in API responses.
