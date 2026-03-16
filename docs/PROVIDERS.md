# Providers

## Config Location

- `config/data_providers.yaml`

Provider behavior is controlled through the provider factory and provider-specific settings.

## Support Matrix

| Provider | Historical | Near-live/latest | Current status |
| --- | --- | --- | --- |
| `csv` | yes | simulated via file reload/latest bar | stable |
| `indian_csv` | yes | simulated via file reload/latest bar | stable |
| `zerodha` | partial | partial | integration-ready; depends on credentials and implemented endpoints |
| `upstox` | placeholder | placeholder | integration-ready structure; full implementation pending |

## Practical Guidance

- Use CSV/Indian CSV for deterministic local runs and testing.
- Use Zerodha paths for integration testing where credentials are available.
- Treat Upstox as scaffolded architecture until provider methods are implemented.

## Code Source of Truth

Provider support is now codified in:

- `src/data/provider_capabilities.py`

Use this registry for runtime validation and workflow gating instead of relying
only on README/doc tables.

## Symbol and Universe Handling

- NSE symbol normalization and mapping are supported.
- Universe resolution supports built-ins and custom CSV watchlists.
