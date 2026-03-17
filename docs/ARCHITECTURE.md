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
    - `TradingCalendar` — NSE monthly/weekly expiry calculation, trading-day detection, holiday overlay stub
    - `InstrumentRegistry` — canonical-keyed store with lookup by type/exchange/segment

## Flow Overview

`Provider data -> Strategy logic -> Research filtering -> Scanner/Monitoring/Decision (+ Analysis Plugin Layer) -> Portfolio & Risk Planning -> Paper/live-safe artifacts`

## Main CLI Entry Points

- `scripts/run_nifty50_zerodha_research.py`
- `scripts/run_scanner.py`
- `scripts/run_monitoring.py`
- `scripts/run_decision.py`
- `scripts/run_paper_trading.py`
- `scripts/run_live_signal_pipeline.py`

## Backward Compatibility

Current architecture is additive by phase. Existing research and simulation workflows remain valid while new layers add orchestration and outputs.
