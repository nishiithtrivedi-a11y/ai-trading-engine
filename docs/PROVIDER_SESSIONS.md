# Provider Sessions and Runtime Readiness

## Purpose

Provider session APIs validate read-only connectivity only.
They do not enable live execution.

The platform now uses one shared readiness source for:

- UI provider health and platform status
- runner/provider validation
- provider factory instantiation checks
- diagnostics tooling

Shared runtime module:

- `src/data/provider_runtime.py`

## State Layers

Provider state is evaluated in three layers:

1. Static config (`config/data_providers.yaml`)
- `default_provider`
- per-provider `enabled`
- non-secret settings only

2. Credential resolution
- environment variables / local `.env`
- compatibility aliases where needed (for example Dhan `CLIENT_ID` and `API_KEY`)
- optional config fallback for backward compatibility

3. Runtime session state
- `active`, `not_configured`, `credentials_missing`, `invalid`, etc.
- used for session-required providers

## Provider Credentials

Preferred credential source is environment variables or local `.env`.
Do not commit real secrets to tracked config files.

### Zerodha

- `ZERODHA_API_KEY`
- `ZERODHA_API_SECRET`
- `ZERODHA_ACCESS_TOKEN`

### Upstox

- `UPSTOX_API_KEY`
- `UPSTOX_API_SECRET`
- `UPSTOX_ACCESS_TOKEN`

### DhanHQ

- `DHAN_CLIENT_ID`
- `DHAN_ACCESS_TOKEN`

Compatibility note:

- `DHAN_API_KEY` is accepted as an alias for `DHAN_CLIENT_ID`.

## Runtime Readiness States

Main provider runtime states:

- `ready`
- `partial`
- `missing_secrets`
- `session_invalid`
- `disabled`
- `misconfigured`
- `unsupported`

`enabled` in YAML means "allowed by config", not "ready right now".

## API Endpoints

Session management:

- `GET /api/v1/providers/sessions`
- `GET /api/v1/providers/sessions/{provider}`
- `POST /api/v1/providers/sessions/{provider}/validate`
- `POST /api/v1/providers/sessions/{provider}/configure`
- `POST /api/v1/providers/sessions/{provider}/credentials`

Unified health/readiness views:

- `GET /api/v1/providers/health`
- `GET /api/v1/platform/status`

## Diagnostics CLI

Use the shared diagnostics script:

```bash
python scripts/check_provider_readiness.py --provider zerodha
python scripts/check_provider_readiness.py --all
python scripts/check_provider_readiness.py --all --mode research --timeframe 5m
```

The script reports missing credentials by name only and never prints secret values.

## Runtime Source Selection

`/api/v1/platform/runtime-source` can set primary runtime source only when
the target provider satisfies readiness/session requirements for safe use.

Promoting a provider to primary does not change execution safety boundaries.
Execution remains disabled.

