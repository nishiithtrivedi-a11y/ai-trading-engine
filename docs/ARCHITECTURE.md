# Architecture

## System Purpose

This platform is built for quantitative trading research, paper-trading simulation, and live-safe signal generation.

It is not a live execution system today.

## Layered Architecture

1. **Data Provider Layer** (`src/data/`)
   - Provider factory and provider config
   - CSV/Indian CSV stable paths
   - Zerodha/Upstox integration-ready paths
   - Phase 4 analysis-family normalization adapters (`fundamental_sources.py`, `macro_sources.py`, `sentiment_sources.py`, `intermarket_sources.py`)
   - Family-specific provider capability truth (`alphavantage`/`finnhub`/`fmp`/`eodhd`/`none` + `derived` for intermarket)

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
   - `AnalysisRegistry` — module registry with enable/disable/resolve/health_check; `create_default()` wires technical+quant, registers modules disabled by default
   - Active baseline modules: `TechnicalAnalysisModule` (RSI/SMA/EMA/ATR/Donchian via BaseStrategy), `QuantAnalysisModule` (volatility/momentum/Sharpe)
   - Phase 4 non-technical modules: `FundamentalAnalysisModule`, `MacroAnalysisModule`, `SentimentAnalysisModule`, `IntermarketAnalysisModule`
   - Real derivative modules (Phase 3): `FuturesAnalysisModule`, `OptionsAnalysisModule`, `CommoditiesAnalysisModule`, `ForexAnalysisModule`
   - Remaining stub module: crypto
   - `AnalysisProfileLoader` — YAML-driven named profiles; `apply_profile_by_name()` enables exactly the listed modules

10. **Instrument Master Layer** (`src/instruments/`)
    - `Exchange` enum (NSE/BSE/NFO/MCX/CDS) + `Segment` enum (CASH/FO/COMM/CURR)
    - `Instrument` dataclass with factory helpers `.equity()`, `.future()`, `.option()` and full validation
    - Symbol normalisation: canonical format `EXCHANGE:SYMBOL[-EXPIRY-SUFFIX]` with `format_canonical()` / `parse_canonical()` round-trip
    - `TradingCalendar` — NSE monthly/weekly expiry calculation, trading-day detection; NSE 2025–2026 holidays populated
    - `InstrumentRegistry` — canonical-keyed store with lookup by type/exchange/segment/underlying/expiry/option-chain

11. **Indian Derivatives Data Layer** (`src/instruments/`, `src/data/`) — Phase 2
    - `provider_mapping.py` — bidirectional Instrument ↔ Kite tradingsymbol, Upstox segment|symbol, and DhanHQ segment conversion
    - `hydrator.py` — `InstrumentHydrator` converts Kite `instruments()` rows and generic dicts to `Instrument` objects for all segments (NSE/BSE/NFO/MCX/CDS)
    - `contracts.py` — `ContractResolver` for active contract filtering, nearest expiry, option chain grouping, strikes list — all pure data/filtering, no execution
    - `quote_normalizer.py` — `NormalizedQuote` dataclass with OI, bid/ask, depth, `DataQualityFlags` (stale, missing OI, missing depth, degraded auth); normalizers for Kite and Upstox payloads
    - `derivative_data.py` — `DerivativeDataFetcher` for segment-aware historical and latest-quote routing via Zerodha; `resolve_active_contract()` helper
    - Extended `provider_capabilities.py` — `supports_historical_derivatives`, `supports_latest_derivatives`, `supports_oi`, `supports_market_depth`, `instrument_master_available` flags + `get_derivative_capability_summary()`
    - Extended `instrument_mapper.py` — `refresh_all_segments()`, `hydrate_registry()` for multi-segment instrument master population

12. **Derivatives Intelligence Layer** (`src/analysis/derivatives/`, `src/data/`) — Phase 3
    - `dhan_source.py` — `DhanHQDataSource` optional SDK provider; `fetch_option_chain()`, `fetch_expiry_list()`, graceful SDK-absent degradation
    - `provider_router.py` — `ProviderRoutingPolicy` named factory methods + `ProviderRouter.select_for_segment()` dispatch
    - `options/chain.py` — `OptionStrike`, `OptionChain`, `OptionChainBuilder` (from DhanHQ response / dict list / `InstrumentRegistry`)
    - `options/analytics.py` — pure-Python BSM (`black_scholes()`, `implied_volatility()` bisection), `OptionChainAnalyzer` (PCR, max pain, IV skew, OI concentration)
    - `futures/intelligence.py` — `FuturesContractInfo`, `FuturesContractFamily` (front/next/far, roll imminence), `FuturesContractResolver`, `ContinuousSeriesBuilder`
    - Activated `FuturesAnalysisModule`, `OptionsAnalysisModule`, `CommoditiesAnalysisModule`, `ForexAnalysisModule` — real `build_features()` implementations
    - 4 new analysis profiles: `index_futures`, `stock_futures`, `equity_options`, `inr_currency_derivatives`

13. **Phase 4 Multi-Layer Analysis Expansion** (`src/analysis/`, `src/data/`) — Combined Phase 4
    - `fundamental_sources.py` — normalized company/factor/event models with source/derived metadata
    - `macro_sources.py` — normalized macro indicator + calendar models with country tags and freshness
    - `sentiment_sources.py` — normalized ticker/market/macro news models with provider-vs-derived semantics
    - `intermarket_sources.py` — derived cross-asset series normalization for intermarket context
    - `provider_capabilities.py` — analysis-family provider truth (`AnalysisFamily`, `AnalysisProviderFeatureSet`, diagnostics)
    - `provider_router.py` — `AnalysisProviderRoutingPolicy` + `AnalysisProviderRouter` family-level routing
    - `provider_factory.py` — family-level provider report (`analysis_capability_report`)
    - Additive scanner/monitoring/decision context wiring:
      - `analysis_features`
      - `fundamental_summary`, `macro_summary`, `sentiment_summary`, `intermarket_summary`
      - `event_risk_flags`
      - `analysis_provider_metadata`

14. **UI / Command Center Layer (`frontend/`, `src/api/`)** — Phase 20
    - `src/api/` — FastAPI backend acting as a thin read-only adapter over existing artifacts, configs, and logs.
    - `frontend/` — React/Vite SPA providing operator-grade surfaces: Scanner, Decision, Paper Trading, Diagnostics, Artifact Explorer, Profiles, Derivatives, AI Workspace, and Settings.
    - Designed with explicit execution separation (broker routing controls remain disabled visual placeholders).

### How Provider-to-Canonical Mapping Works

```
Provider native (Kite)         Canonical internal          Instrument object
NIFTY26APRFUT        <-->   NFO:NIFTY-2026-04-30-FUT  <--> Instrument.future("NIFTY", date(2026,4,30))
NIFTY26APR24500CE    <-->   NFO:NIFTY-2026-04-30-24500-CE  <--> Instrument.option("NIFTY", ..., 24500, CALL)
GOLD26APRFUT         <-->   MCX:GOLD-2026-04-30-FUT   <--> Instrument.future("GOLD", ..., Exchange.MCX)
NSE_FO|NIFTY26APRFUT (Upstox)  <--> same canonical    <--> same Instrument
NSE_FO + NIFTY26APRFUT (Dhan)  <--> same canonical    <--> same Instrument
```

### How Provider Routing Works (Phase 3)

```
ProviderRoutingPolicy.dhan_primary_zerodha_cash()
  -> derivatives_provider = "dhan"
  -> cash_provider = "zerodha"

ProviderRouter.select_for_segment("NFO")
  -> returns "dhan"   (derivatives segment)

ProviderRouter.select_for_segment("NSE")
  -> returns "zerodha" (cash segment)
```

### How Analysis Provider Routing Works (Phase 4)

```
AnalysisProviderRoutingPolicy(
  fundamentals_provider="fmp",
  macro_provider="alphavantage",
  sentiment_provider="finnhub",
  intermarket_provider="derived",
)

AnalysisProviderRouter.select_for_family("fundamentals")
  -> "fmp"

AnalysisProviderRouter.select_for_family("intermarket")
  -> "derived" (or fallback provider if configured and supported)
```

Analysis-family routing is independent from market-data routing and can be
switched per family without changing equity/derivatives data providers.

### How Option Chain Intelligence Works (Phase 3)

```
DhanHQDataSource.fetch_option_chain(underlying, expiry, segment)
  -> raw DhanHQ API response

OptionChainBuilder.from_dhan_response(underlying, expiry, dhan_chain)
  -> OptionChain with OptionStrike objects per strike

OptionChainAnalyzer.enrich_greeks(chain, T)
  -> black_scholes() + implied_volatility() for strikes missing IV/Greeks
  -> returns enriched OptionChain

OptionChainAnalyzer.analyze(chain)
  -> ChainAnalytics: pcr, max_pain, iv_skew, oi_concentration
```

### How Futures Intelligence Works (Phase 3)

```
FuturesContractResolver.get_contract_family(registry, underlying, exchange, as_of)
  -> FuturesContractFamily with front/next/far FuturesContractInfo

FuturesContractResolver.get_roll_signal(family)
  -> {"action": "roll_to_next"|"hold_front", "front_dte": ..., "next_canonical": ...}

FuturesContractResolver.compute_basis(spot_price, futures_price)
  -> {"basis": ..., "basis_pct": ..., "contango": bool, "backwardation": bool}

ContinuousSeriesBuilder.build_roll_schedule(contracts, as_of)
  -> ContinuousSeriesMetadata with roll dates and contract sequence
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
