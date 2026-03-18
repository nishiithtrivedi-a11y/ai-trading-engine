# Providers

## Config Location

- `config/data_providers.yaml`

Provider behavior is controlled through the provider factory and provider-specific settings.
The code-level source of truth is `src/data/provider_capabilities.py`.

---

## Phase 4 Analysis-Family Provider Selection

Phase 4 adds family-specific provider selection independent from the market-data
provider used for OHLCV.

Configured in `config/data_providers.yaml`:

```yaml
analysis_providers:
  fundamentals_provider: "none"   # alphavantage|finnhub|fmp|eodhd|none
  macro_provider: "none"          # alphavantage|finnhub|fmp|eodhd|none
  sentiment_provider: "none"      # alphavantage|finnhub|fmp|eodhd|none
  intermarket_provider: "derived" # derived|alphavantage|finnhub|fmp|eodhd|none
  allow_derived_sentiment_fallback: true
```

Family-level capability truth and routing:

- `src/data/provider_capabilities.py`
- `src/data/provider_router.py`
- `src/data/provider_factory.py`

### Analysis Provider Support Matrix (Phase 4)

| Provider | Fundamentals | Macro Indicators | Macro Calendar | News | Sentiment Scores | Intermarket Inputs | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `none` | no | no | no | no | no | no | placeholder |
| `derived` | no | partial | no | no | no | yes | partial |
| `alphavantage` | yes | yes | yes | yes | yes | yes | partial |
| `finnhub` | yes | yes | partial | yes | yes | yes | partial |
| `fmp` | yes | yes | yes | yes | yes | yes | partial |
| `eodhd` | yes | yes | yes | yes | partial | yes | partial |

### Provider-Supplied vs Derived Semantics

- Fundamental normalization keeps source field tags and marks derived fields explicitly.
- Macro normalization preserves indicator/event source, country tags, and freshness metadata.
- Sentiment uses provider scores when available and marks fallback-derived scores explicitly.
- Intermarket is primarily derived from available market/macro series and reports sparse coverage honestly.

### Diagnostics

Family-level diagnostics report:

- configured vs not configured
- available vs degraded/no-data
- coverage by family (fundamentals/macro/sentiment/news/calendar/intermarket)
- stale payload state

Execution remains disabled in all provider paths.

---
## Support Matrix (Phase 3 - Derivatives Intelligence + DhanHQ)

| Provider | Historical | Latest/Live | Derivative Hist. | Derivative Live | OI | Depth | Option Chain | Instrument Master | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `csv` | âœ“ | simulated | âœ— | âœ— | âœ— | âœ— | âœ— | âœ— | stable |
| `indian_csv` | âœ“ | simulated | âœ— | âœ— | âœ— | âœ— | âœ— | âœ— | stable |
| `zerodha` | âœ“ | âœ“ | **âœ“** | **âœ“** | **âœ“** | **âœ“** | via instruments | **âœ“** | partial (auth-gated) |
| `upstox` | partial | âœ— (SDK stub) | âœ— | âœ— | âœ— | âœ— | âœ— | âœ— | partial (CSV fallback) |
| `dhan` | **âœ“** | **âœ“** | **âœ“** | **âœ“** | **âœ“** | **âœ“** | **âœ“ (native API)** | âœ— | partial (optional SDK) |

---

## Zerodha / KiteConnect

### Segments Supported

| Segment | Exchange | Instruments |
| --- | --- | --- |
| CASH | NSE, BSE | Equities, ETFs, Indices |
| FO | NFO | NIFTY/BANKNIFTY/stock futures; NIFTY/BANKNIFTY/stock options |
| COMM | MCX | GOLD, SILVER, CRUDEOIL, NATURALGAS futures |
| CURR | CDS | USDINR, EURINR and other currency futures/options |

### What is implemented

- **Historical OHLCV** for all segments via `ZerodhaDataSource.fetch_historical()`
- **Latest quote snapshot** via `ZerodhaDataSource.fetch_live()`
- **Instrument token lookup** via `KiteInstrumentMapper`
- **Multi-segment instrument master** via `KiteInstrumentMapper.refresh_all_segments()` â€” downloads `kite.instruments(exchange)` for NSE, BSE, NFO, MCX, CDS
- **Instrument hydration** via `InstrumentHydrator.hydrate_from_kite_list()` â€” converts Kite rows to canonical `Instrument` objects
- **Instrument master population** via `KiteInstrumentMapper.hydrate_registry()` â€” fills an `InstrumentRegistry` from cached instrument lists
- **OI passthrough** â€” Open Interest preserved in `NormalizedQuote.oi` where Kite provides it
- **Depth passthrough** â€” Bid/ask depth preserved in `NormalizedQuote.bid`, `.ask`, `.depth_bid_qty`, `.depth_ask_qty`
- **Derivative symbol mapping** â€” `instrument_to_kite_symbol()` converts `Instrument` to Kite tradingsymbol (e.g., `NFO:NIFTY-2026-04-30-FUT` â†’ `NIFTY26APRFUT`)
- **Reverse mapping** â€” `kite_symbol_to_instrument()` parses Kite tradingsymbols back to `Instrument` objects

### Kite symbol format reference

| Instrument type | Kite tradingsymbol | Canonical |
| --- | --- | --- |
| NSE equity | `RELIANCE` | `NSE:RELIANCE-EQ` |
| NFO monthly future | `NIFTY26APRFUT` | `NFO:NIFTY-2026-04-30-FUT` |
| NFO monthly call | `NIFTY26APR24500CE` | `NFO:NIFTY-2026-04-30-24500-CE` |
| NFO monthly put | `NIFTY26APR24500PE` | `NFO:NIFTY-2026-04-30-24500-PE` |
| MCX monthly future | `GOLD26APRFUT` | `MCX:GOLD-2026-04-30-FUT` |
| CDS monthly future | `USDINR26APRFUT` | `CDS:USDINR-2026-04-30-FUT` |

Monthly format: `{SYMBOL}{2-digit-year}{3-char-month}{FUT|STRIKE+CE|STRIKE+PE}`

Weekly options use a compact date-encoding format that varies; the library implements monthly format
correctly and documents weekly as best-effort â€” use the instrument master cache for authoritative
weekly symbols.

### What is NOT implemented for Zerodha

- Live execution (disabled by design â€” the system is research/paper-safe)
- WebSocket / streaming data (KiteTicker not integrated â€” snapshot polling only)
- Order placement, modification, or cancellation

### Auth and degraded states

- If no `access_token` is configured: `health_check()` returns `state="no_credentials"`
- If credentials are present but Kite auth fails: `health_check()` returns `state="auth_error"`
- `DataQualityFlags.degraded_auth=True` is set on quotes when auth is degraded

---

## DhanHQ (Phase 3)

DhanHQ is an optional switchable provider for derivative data. It requires the `dhanhq` Python package and valid `client_id` + `access_token` credentials.

### Health check states

| State | Meaning |
| --- | --- |
| `sdk_unavailable` | `dhanhq` package not installed â€” all methods raise gracefully |
| `no_credentials` | SDK present but `client_id`/`access_token` not configured |
| `sdk_configured` | SDK and credentials present â€” full API access |

### What is implemented

- **`fetch_option_chain(underlying, expiry, segment)`** â€” returns normalized `{"calls": [...], "puts": [...]}` rows with LTP, OI, IV, delta, theta, gamma, vega where the API provides them
- **`fetch_expiry_list(underlying, segment)`** â€” returns list of expiry date strings
- **Historical OHLCV** â€” via DhanHQ historical candles API
- **Live quote snapshots** â€” via DhanHQ market quote API
- **OI passthrough** â€” Open Interest in normalized quote model
- **Bid/ask + depth passthrough** â€” where API provides it
- **DhanHQ segment strings** in `provider_mapping.py`:

| Exchange | DhanHQ segment |
| --- | --- |
| NSE (equity) | `NSE_EQ` |
| BSE (equity) | `BSE_EQ` |
| NFO (F&O) | `NSE_FO` |
| MCX (commodity) | `MCX` |
| CDS (currency) | `CUR` |

### Provider routing (Phase 3)

Use `ProviderRoutingPolicy` to select a named routing strategy:

```python
from src.data.provider_router import ProviderRoutingPolicy, ProviderRouter

policy = ProviderRoutingPolicy.dhan_primary_zerodha_cash()
router = ProviderRouter(policy, available_providers=["zerodha", "dhan", "csv"])

router.select_for_segment("NFO")  # -> "dhan"
router.select_for_segment("NSE")  # -> "zerodha"
```

| Policy factory | derivatives_provider | cash_provider |
| --- | --- | --- |
| `zerodha_only()` | `zerodha` | `zerodha` |
| `dhan_only()` | `dhan` | `dhan` |
| `dhan_primary_zerodha_cash()` | `dhan` | `zerodha` |
| `auto()` | first available derivative-capable | first available |

### Config

In `config/data_providers.yaml`:

```yaml
dhan:
  api_key: "<client_id>"
  access_token: "<access_token>"
```

### What is NOT implemented for DhanHQ

- Live order execution (permanently disabled by design)
- WebSocket / streaming data
- Full instrument master download (`instrument_master_available=False`)
- Upstox-style segment|symbol format (DhanHQ uses its own segment strings)

---

## Upstox

### What is implemented

- **CSV fallback** for historical OHLCV (via file-based loader when SDK is unavailable)
- **Capability reporting** â€” provider declares `implementation_status=PARTIAL`; all derivative flags (`supports_historical_derivatives`, `supports_oi`, etc.) are `False` â€” honest representation
- **Segment awareness** â€” `supported_segments=("NSE", "NFO")` declared even though NFO fetch via SDK is not yet implemented
- **Health check** states: `csv_fallback_only`, `sdk_present_auth_configured`, `not_implemented`

### Upstox segment|symbol format (for future SDK integration)

| Exchange | Upstox segment prefix |
| --- | --- |
| NSE (equity) | `NSE_EQ` |
| BSE (equity) | `BSE_EQ` |
| NFO (F&O) | `NSE_FO` |
| MCX (commodity) | `MCX_FO` |
| CDS (currency) | `CDS_FO` |

Format: `{SEGMENT}|{KITE_TRADINGSYMBOL}` e.g., `NSE_FO|NIFTY26APRFUT`

### What is NOT implemented for Upstox

- SDK historical data fetch (raises `NotImplementedError` â€” CSV fallback is the safe path)
- Live quotes via SDK
- OI, depth
- Instrument master download

Upstox SDK integration remains integration-ready scaffolding. When the SDK path is implemented
in a future phase, the `supports_historical_derivatives` flag will be updated to `True`.

---

## CSV / Indian CSV

- Stable, deterministic, no credentials required
- No derivative support â€” file-based OHLCV data for equities only
- `indian_csv` adds IST timezone normalization and BSE support
- Derivative instruments can be modeled in the `InstrumentRegistry` but data must come from another provider

---

## Practical Guidance

- Use **CSV/Indian CSV** for deterministic local runs, backtesting, and testing (equity only).
- Use **Zerodha** for real Indian market data including derivatives (requires valid credentials).
- Use **DhanHQ** for option chain data, expiry lists, and live derivative quotes (requires optional `dhanhq` package + credentials).
- Use `ProviderRoutingPolicy.dhan_primary_zerodha_cash()` when you want Dhan for derivatives and Zerodha for equity.
- Treat **Upstox** as scaffolded architecture for derivatives until the SDK path is implemented.
- Always check `src/data/provider_capabilities.py` for the authoritative runtime capability flags.
- Use `validate_provider_workflow()` to gate workflows by actual provider capability.
- Use `get_derivative_capability_summary(provider_name)` for a structured derivative readiness report.

---

## Symbol and Universe Handling

- NSE equity symbol normalization: `src/data/symbol_mapping.py`
- Canonical instrument format: `src/instruments/normalization.py`
- Provider-native format (Kite/Upstox/DhanHQ): `src/instruments/provider_mapping.py`
- Instrument hydration from provider payloads: `src/instruments/hydrator.py`
- Universe resolution (NIFTY50, BANKNIFTY, custom): `src/data/nse_universe.py`
- Active contract resolution (nearest expiry, option chain): `src/instruments/contracts.py`
- Derivative intelligence (option chain, Black-Scholes, futures families): `src/analysis/derivatives/`
- Provider routing policies: `src/data/provider_router.py`

## Code Source of Truth

Provider support is codified in `src/data/provider_capabilities.py`.
Use this registry for runtime validation and workflow gating instead of relying only on doc tables.

