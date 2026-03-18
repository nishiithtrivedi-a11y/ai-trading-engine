# Provider Session Management — Phase 21.x

## Overview

Phase 21.x provides safe provider session lifecycle management for broker/data provider connections. Connecting a provider **does NOT enable live trading** — execution remains structurally disabled.

## Module Layout

```
src/providers/
├── __init__.py
├── models.py              # ProviderType, SessionStatus, ProviderConfig, PROVIDER_REGISTRY
├── credential_store.py     # Safe masked credential handling, .env file management
└── session_manager.py      # Session lifecycle, validation, credential configuration
```

## Provider Registry

| Provider | Auth Type | Required Credentials |
|---|---|---|
| Zerodha Kite | Token | `API_KEY`, `API_SECRET`, `ACCESS_TOKEN` |
| DhanHQ | Token | `CLIENT_ID`, `ACCESS_TOKEN` |
| Upstox | OAuth | `API_KEY`, `API_SECRET`, `ACCESS_TOKEN` |

Credentials are stored as environment variables with the prefix `{PROVIDER}_{CREDENTIAL}` (e.g., `ZERODHA_API_KEY`).

## Session States

| State | Meaning |
|---|---|
| `not_configured` | Provider not set up |
| `credentials_missing` | Some required credentials absent |
| `active` | Session validated successfully |
| `expired` | Session token has expired |
| `invalid` | Auth validation failed |
| `error` | Unexpected error during validation |

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/providers/sessions` | All provider session states |
| GET | `/api/v1/providers/sessions/{type}` | Single provider status |
| POST | `/api/v1/providers/sessions/{type}/validate` | Validate/reconnect session via live SDK |
| POST | `/api/v1/providers/sessions/{type}/configure` | Store a single credential |
| POST | `/api/v1/providers/sessions/{type}/credentials` | Store multiple API credentials atomically |
| GET | `/api/v1/providers/sessions/{type}/login` | Get the Browser OAuth URL (Kite, Upstox) |
| GET | `/api/v1/providers/sessions/{type}/callback` | Handle the OAuth redirect and save Tokens |

## Provider Specific Auth Flows

### 1. Zerodha (Kite)
- **Settings Required:** Must have `ZERODHA_API_KEY` and `ZERODHA_API_SECRET` in `.env`.
- **Callback URL needed:** Configure your Kite Dev App redirect URL to: `http://127.0.0.1:8000/api/v1/providers/sessions/zerodha/callback`
- **UX Flow:** Click **Connect** in the UI. A browser popup opens. After Login, Kite redirects back to the system, which exchanges the token, saves it to `.env` using Python `dotenv`, and refreshes the memory state synchronously.
- **Constraints:** Zerodha tokens expire daily at 6 AM. The operator must click Connect once every morning.

### 2. Upstox
- **Settings Required:** Must have `UPSTOX_API_KEY` and `UPSTOX_API_SECRET` in `.env`.
- **Callback URL needed:** Configure Upstox App Redirect URI as: `http://127.0.0.1:8000/api/v1/providers/sessions/upstox/callback`. Must add `UPSTOX_REDIRECT_URI` to `.env`.
- **UX Flow:** Click **Connect** in the UI. Completes the OAuth 2.0 flow and saves `ACCESS_TOKEN` identically to Zerodha.

### 3. DhanHQ
- **Settings Required:** None upfront. Does not use OAuth.
- **UX Flow:** Generate a long-lived Client ID and Access Token from the Dhan Web Portal. Click **Config** in the UI, input the values, and the engine persists them to `.env`.
- **Constraints:** Manual generation required once, but does not need a daily reconnection.

## Security & Architecture
- **Zero Restart Architecture:** Modifying credentials via the UI edits the local `.env` file whilst updating the live `os.environ` thread. Validations immediately inherit the new token without requiring the command center API to restart.
- Credentials are NEVER echoed. The UI only displays Masked Values (`••••xyz`).
- Connecting a provider strictly enables market data and account feeds. Execution is strictly blocked outside Phase 22 routing models.
