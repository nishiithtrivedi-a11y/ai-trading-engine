# Architecture

## System Purpose

This platform is built for quantitative trading research, paper-trading simulation, and live-safe signal generation.

It is not a live execution system today.

## Layered Architecture

1. **Data Provider Layer** (`src/data/`)
   - Provider factory and provider config
   - CSV/Indian CSV stable paths
   - Zerodha/Upstox integration-ready paths

2. **Core Research Layer** (`src/core/`, `src/research/`)
   - Backtesting engine
   - Walk-forward and Monte Carlo validation
   - Portfolio backtesting and strategy optimization

3. **Strategy Layer** (`src/strategies/`)
   - Base strategy contracts and indicator helpers
   - Strategy implementations (SMA/RSI/Breakout and extensions)

4. **Scanner/Monitoring/Decision Layer** (`src/scanners/`, `src/monitoring/`, `src/decision/`)
   - Opportunity generation and scoring
   - Regime and watchlist-aware monitoring
   - Pick engine and trade-plan construction

5. **Portfolio & Risk Planning Layer** (`src/decision/portfolio_engine.py`)
   - Capital allocation recommendations (equal/volatility/conviction weighted)
   - Position sizing recommendations (fixed-fractional/risk-per-trade/ATR fallback)
   - Portfolio constraints (capital, positions, sector, correlation, risk caps)
   - Drawdown overlays (`normal`, `reduced_risk`, `no_new_risk`)

6. **Paper Trading Layer** (`src/paper_trading/`)
   - Simulated order/fill/position lifecycle
   - Session-level PnL tracking and artifact export

7. **Live-safe Signal Layer** (`src/live/`, `src/realtime/`)
   - Fresh/latest-bar signal cycles
   - Session/watchlist artifacts and optional paper handoff
   - No order placement

8. **Execution Placeholder Layer** (`src/execution/`)
   - Cost/fill realism models used for simulation
   - Placeholder execution interface reserved for future live phase

9. **Analysis Plugin Layer** (`src/analysis/`)
   - `BaseAnalysisModule` ABC — pluggable feature/signal/context contract
   - `FeatureOutput` — standardised multi-domain output schema (technical, quant, fundamental, macro, sentiment, intermarket, derivatives)
   - `AnalysisRegistry` — module registry with enable/disable/resolve/health_check; `create_default()` wires technical+quant, registers 9 stub modules disabled
   - Active modules: `TechnicalAnalysisModule` (RSI/SMA/EMA/ATR/Donchian via BaseStrategy), `QuantAnalysisModule` (volatility/momentum/Sharpe)
   - Stub modules: fundamental, macro, sentiment, intermarket, futures, options, commodities, forex, crypto
   - `AnalysisProfileLoader` — YAML-driven named profiles; `apply_profile_by_name()` enables exactly the listed modules

10. **Instrument Master Layer** (`src/instruments/`)
    - `Exchange` enum (NSE/BSE/NFO/MCX/CDS) + `Segment` enum (CASH/FO/COMM/CURR)
    - `Instrument` dataclass with factory helpers `.equity()`, `.future()`, `.option()` and full validation
    - Symbol normalisation: canonical format `EXCHANGE:SYMBOL[-EXPIRY-SUFFIX]` with `format_canonical()` / `parse_canonical()` round-trip
    - `TradingCalendar` — NSE monthly/weekly expiry calculation, trading-day detection; NSE 2025–2026 holidays populated
    - `InstrumentRegistry` — canonical-keyed store with lookup by type/exchange/segment/underlying/expiry/option-chain

11. **Indian Derivatives Data Layer** (`src/instruments/`, `src/data/`) — Phase 2
    - `provider_mapping.py` — bidirectional Instrument ↔ Kite tradingsymbol and Upstox segment|symbol conversion
    - `hydrator.py` — `InstrumentHydrator` converts Kite `instruments()` rows and generic dicts to `Instrument` objects for all segments (NSE/BSE/NFO/MCX/CDS)
    - `contracts.py` — `ContractResolver` for active contract filtering, nearest expiry, option chain grouping, strikes list — all pure data/filtering, no execution
    - `quote_normalizer.py` — `NormalizedQuote` dataclass with OI, bid/ask, depth, `DataQualityFlags` (stale, missing OI, missing depth, degraded auth); normalizers for Kite and Upstox payloads
    - `derivative_data.py` — `DerivativeDataFetcher` for segment-aware historical and latest-quote routing via Zerodha; `resolve_active_contract()` helper
    - Extended `provider_capabilities.py` — `supports_historical_derivatives`, `supports_latest_derivatives`, `supports_oi`, `supports_market_depth`, `instrument_master_available` flags + `get_derivative_capability_summary()`
    - Extended `instrument_mapper.py` — `refresh_all_segments()`, `hydrate_registry()` for multi-segment instrument master population

### How Provider-to-Canonical Mapping Works

```
Provider native (Kite)         Canonical internal          Instrument object
NIFTY26APRFUT        <-->   NFO:NIFTY-2026-04-30-FUT  <--> Instrument.future("NIFTY", date(2026,4,30))
NIFTY26APR24500CE    <-->   NFO:NIFTY-2026-04-30-24500-CE  <--> Instrument.option("NIFTY", ..., 24500, CALL)
GOLD26APRFUT         <-->   MCX:GOLD-2026-04-30-FUT   <--> Instrument.future("GOLD", ..., Exchange.MCX)
NSE_FO|NIFTY26APRFUT (Upstox) <--> same canonical     <--> same Instrument
```

### How Derivative Data Enters the System

```
KiteInstrumentMapper.refresh_all_segments(["NSE","NFO","MCX","CDS"])
  -> downloads kite.instruments(exchange) for each segment
  -> InstrumentHydrator.hydrate_from_kite_list() -> list[Instrument]
  -> InstrumentRegistry.add_many()          <- populated instrument master

DerivativeDataFetcher.fetch_instrument_history(instrument, timeframe, start, end)
  -> instrument_to_kite_symbol(instrument)  <- provider_mapping.py
  -> ZerodhaDataSource.fetch_historical()   <- existing Kite API path
  -> returns normalized DataFrame (OHLCV)

DerivativeDataFetcher.fetch_instrument_quote(instrument)
  -> returns NormalizedQuote with OI, depth, DataQualityFlags
```

## Flow Overview

`Provider data (+ Instrument Master) -> Strategy logic -> Research filtering -> Scanner/Monitoring/Decision (+ Analysis Plugin Layer) -> Portfolio & Risk Planning -> Paper/live-safe artifacts`

## Main CLI Entry Points

- `scripts/run_nifty50_zerodha_research.py`
- `scripts/run_scanner.py`
- `scripts/run_monitoring.py`
- `scripts/run_decision.py`
- `scripts/run_paper_trading.py`
- `scripts/run_live_signal_pipeline.py`

## Backward Compatibility

Current architecture is additive by phase. Existing research and simulation workflows remain valid while new layers add orchestration and outputs.
