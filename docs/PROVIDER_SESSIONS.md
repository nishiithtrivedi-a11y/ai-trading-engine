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
| POST | `/api/v1/providers/sessions/{type}/validate` | Validate/reconnect session |
| POST | `/api/v1/providers/sessions/{type}/configure` | Store credential (masked response) |

## Security

- Raw credential values are **never** returned by any API endpoint or logged
- All API responses use masked indicators (last 3 chars visible, e.g. `•••••def`)
- Credentials are stored in `.env` file and loaded via `os.environ`
- Connecting a provider does NOT enable execution — `safety_gate.py` enforces this independently

## Known Limitations (Phase 21.x)

- **Session validation is mock only:** `validate_session()` currently simulates a successful `ACTIVE` state if credentials are present. Real broker SDK connection tests (Kite `profile()`, Dhan margin query, Upstox profile) are intentionally deferred to a future phase. The interface is ready for that wiring with no API changes required.
- **`.env` file write is append/update only:** If the `.env` file is managed by an external tool (e.g. dotenv-vault, docker secret injection), the `store_credential` path may conflict. In those setups, credential configuration should be done by setting env vars directly and skipping the configure API.
- **No session expiry tracking:** `expiry_time` and `expired` state detection from broker token timestamps are not yet implemented. Expiry tracking is deferred to real SDK integration.
