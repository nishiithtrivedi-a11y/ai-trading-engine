# Providers

## Config Location

- `config/data_providers.yaml`

Provider behavior is controlled through the provider factory and provider-specific settings.
The code-level source of truth is `src/data/provider_capabilities.py`.

---

## Support Matrix (Phase 2 — Indian Derivatives Data Layer)

| Provider | Historical | Latest/Live | Derivative Hist. | Derivative Live | OI | Depth | Instrument Master | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `csv` | ✓ | simulated | ✗ | ✗ | ✗ | ✗ | ✗ | stable |
| `indian_csv` | ✓ | simulated | ✗ | ✗ | ✗ | ✗ | ✗ | stable |
| `zerodha` | ✓ | ✓ | **✓** | **✓** | **✓** | **✓** | **✓** | partial (auth-gated) |
| `upstox` | partial | ✗ (SDK stub) | ✗ | ✗ | ✗ | ✗ | ✗ | partial (CSV fallback) |

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
- **Multi-segment instrument master** via `KiteInstrumentMapper.refresh_all_segments()` — downloads `kite.instruments(exchange)` for NSE, BSE, NFO, MCX, CDS
- **Instrument hydration** via `InstrumentHydrator.hydrate_from_kite_list()` — converts Kite rows to canonical `Instrument` objects
- **Instrument master population** via `KiteInstrumentMapper.hydrate_registry()` — fills an `InstrumentRegistry` from cached instrument lists
- **OI passthrough** — Open Interest preserved in `NormalizedQuote.oi` where Kite provides it
- **Depth passthrough** — Bid/ask depth preserved in `NormalizedQuote.bid`, `.ask`, `.depth_bid_qty`, `.depth_ask_qty`
- **Derivative symbol mapping** — `instrument_to_kite_symbol()` converts `Instrument` to Kite tradingsymbol (e.g., `NFO:NIFTY-2026-04-30-FUT` → `NIFTY26APRFUT`)
- **Reverse mapping** — `kite_symbol_to_instrument()` parses Kite tradingsymbols back to `Instrument` objects

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
correctly and documents weekly as best-effort — use the instrument master cache for authoritative
weekly symbols.

### What is NOT implemented for Zerodha

- Live execution (disabled by design — the system is research/paper-safe)
- WebSocket / streaming data (KiteTicker not integrated — snapshot polling only)
- Order placement, modification, or cancellation

### Auth and degraded states

- If no `access_token` is configured: `health_check()` returns `state="no_credentials"`
- If credentials are present but Kite auth fails: `health_check()` returns `state="auth_error"`
- `DataQualityFlags.degraded_auth=True` is set on quotes when auth is degraded

---

## Upstox

### What is implemented

- **CSV fallback** for historical OHLCV (via file-based loader when SDK is unavailable)
- **Capability reporting** — provider declares `implementation_status=PARTIAL`; all derivative flags (`supports_historical_derivatives`, `supports_oi`, etc.) are `False` — honest representation
- **Segment awareness** — `supported_segments=("NSE", "NFO")` declared even though NFO fetch via SDK is not yet implemented
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

- SDK historical data fetch (raises `NotImplementedError` — CSV fallback is the safe path)
- Live quotes via SDK
- OI, depth
- Instrument master download

Upstox SDK integration remains integration-ready scaffolding. When the SDK path is implemented
in a future phase, the `supports_historical_derivatives` flag will be updated to `True`.

---

## CSV / Indian CSV

- Stable, deterministic, no credentials required
- No derivative support — file-based OHLCV data for equities only
- `indian_csv` adds IST timezone normalization and BSE support
- Derivative instruments can be modeled in the `InstrumentRegistry` but data must come from another provider

---

## Practical Guidance

- Use **CSV/Indian CSV** for deterministic local runs, backtesting, and testing (equity only).
- Use **Zerodha** for real Indian market data including derivatives (requires valid credentials).
- Treat **Upstox** as scaffolded architecture for derivatives until the SDK path is implemented.
- Always check `src/data/provider_capabilities.py` for the authoritative runtime capability flags.
- Use `validate_provider_workflow()` to gate workflows by actual provider capability.
- Use `get_derivative_capability_summary(provider_name)` for a structured derivative readiness report.

---

## Symbol and Universe Handling

- NSE equity symbol normalization: `src/data/symbol_mapping.py`
- Canonical instrument format: `src/instruments/normalization.py`
- Provider-native format (Kite/Upstox): `src/instruments/provider_mapping.py`
- Instrument hydration from provider payloads: `src/instruments/hydrator.py`
- Universe resolution (NIFTY50, BANKNIFTY, custom): `src/data/nse_universe.py`
- Active contract resolution (nearest expiry, option chain): `src/instruments/contracts.py`

## Code Source of Truth

Provider support is codified in `src/data/provider_capabilities.py`.
Use this registry for runtime validation and workflow gating instead of relying only on doc tables.
