# AI Trading Engine

A modular Python AI trading research platform for backtesting, strategy evaluation, paper trading simulation, and live-safe signal generation.

This repository does **not** perform live broker order execution.

## Project Overview

The platform currently supports:

- Historical backtesting and strategy research
- Walk-forward validation and Monte Carlo robustness testing
- Portfolio-level research and relative-strength analysis
- Scanner + decision pipeline for ranked opportunities and picks
- Multi-family analysis framework (technical, quant, fundamental, macro, sentiment, intermarket, derivatives)
- Portfolio-aware decision planning (allocation, sizing, and risk overlays)
- Paper trading simulation with fills, positions, and PnL tracking
- Live-safe signal pipeline on fresh/latest bars (no execution)

Primary use today:

- Research and validation
- Paper trading rehearsal
- Live-safe signal monitoring

Not yet in scope:

- Live order execution

## System Architecture

Layer flow:

`Data Providers -> Research Engine -> Strategy Engine -> Scanner/Monitoring/Decision -> Portfolio & Risk Engine -> Paper Trading Engine -> Live Signal Pipeline -> (future) Execution Layer`

Current layers:

1. Data Providers (`src/data/`)
2. Research / Backtesting (`src/core/`, `src/research/`)
3. Strategy Layer (`src/strategies/`)
4. Decision and Picking (`src/scanners/`, `src/monitoring/`, `src/decision/`)
5. Portfolio & Risk Planning (`src/decision/portfolio_engine.py`)
6. Paper Trading (`src/paper_trading/`)
7. Live-safe Signals (`src/live/`, `src/realtime/`)
8. Broker Adapters (integration-oriented, no live execution path enabled)
9. Runtime Guardrails (`src/runtime/`)
10. Artifact Contracts + Workflow Smoke Paths (`src/runtime/artifact_contracts.py`, `src/runtime/workflow_orchestrator.py`)

See detailed architecture: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

## Strategy Contract

Strategy code is signal-generation only. It must not perform order execution,
broker side effects, portfolio sizing, or notifications.

Current standardized contract in `src/strategies/base_strategy.py`:

- `on_bar(data, current_bar, bar_index) -> Signal` (legacy-compatible path)
- `generate_signal(...) -> StrategySignal` (structured contract)
- `generate_signals(...) -> list[StrategySignal]` (fan-out friendly list form)

`StrategySignal` fields:

- `action` (`buy`, `sell`, `exit`, `hold`)
- `strategy_name`
- optional context: `symbol`, `timestamp`, `timeframe`
- optional quality metadata: `confidence`, `rationale`, `tags`, `metadata`

The engine normalizes both legacy and structured outputs so existing workflows
remain compatible while new strategies can adopt structured signals directly.

Minimal strategy example:

```python
from src.strategies.base_strategy import BaseStrategy, Signal


class ExampleStrategy(BaseStrategy):
    def on_bar(self, data, current_bar, bar_index):
        if bar_index < 20:
            return Signal.HOLD
        return Signal.BUY if float(current_bar["close"]) > float(data["close"].iloc[-2]) else Signal.HOLD
```

Consumers can call either `on_bar(...)` (legacy) or `generate_signal(...)`
(structured). Strategy modules should remain execution-disabled and side-effect free.

### Adding a New Strategy

1. Create a class under `src/strategies/` that subclasses `BaseStrategy`.
2. Implement `on_bar(...) -> Signal` for legacy compatibility.
3. Optionally override `generate_signal(...) -> StrategySignal` to provide richer metadata.
4. Keep strategy code signal-only (no broker calls, no order placement, no notifications).
5. Register the class in `src/strategies/registry.py` if it should be discoverable by name.

Compatibility behavior:

- Legacy consumers can still use enum outputs.
- Updated consumers normalize both enum and structured outputs via `BaseStrategy.normalize_signal(...)`.

## Capability Matrix

| Feature | Supported | Notes |
| --- | --- | --- |
| Backtesting | yes | Multi-symbol historical simulation |
| Walk-forward testing | yes | Research validation |
| Monte Carlo analysis | yes | Robustness testing |
| Portfolio simulation | yes | Active-allocation corrected behavior |
| Portfolio-aware planning | yes | Allocation/sizing/risk overlays for decision outputs |
| Paper trading | yes | Simulated fills only |
| Live signal generation | yes | Fresh/latest-bar pipeline |
| Live order execution | no | Placeholder interface only |

Expanded matrix: [`docs/CAPABILITIES.md`](docs/CAPABILITIES.md)

## Provider Support Matrix

| Provider | Historical Data | Live Quotes | Derivatives | OI | Depth | Segments | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CSV | yes | simulated reload | no | no | no | NSE | stable |
| Indian CSV | yes | simulated reload | no | no | no | NSE, BSE | stable |
| Zerodha | yes | yes | **yes** | **yes** | **yes** | NSE, BSE, NFO, MCX, CDS | partial (auth-gated) |
| Upstox | partial | no (SDK stub) | no | no | no | NSE, NFO | partial (CSV fallback) |
| **DhanHQ** | **yes** | **yes** | **yes** | **yes** | **yes** | NSE, BSE, NFO, MCX, CDS | **partial (optional SDK)** |

Provider details: [`docs/PROVIDERS.md`](docs/PROVIDERS.md)

Code-level provider capability registry: `src/data/provider_capabilities.py`

## Instrument Support Matrix

| Instrument | Status | Notes |
| --- | --- | --- |
| Equities | supported | primary workflow target |
| Equity indices | supported via symbols | benchmark/regime use cases |
| NFO futures | **intelligence supported** | canonical symbol, hydration, fetch path, Greeks/basis/roll signals via Zerodha or DhanHQ |
| NFO options | **intelligence supported** | canonical symbol, hydration, fetch path, option chain, IV/Greeks, skew, PCR, max pain |
| MCX futures | **intelligence supported** | canonical symbol, hydration, fetch path, basis/roll signals |
| CDS futures/options | **intelligence supported** | canonical symbol, hydration, fetch path, basis/roll signals |
| Crypto | not implemented | no dedicated provider/runtime path |

## Workflow Guides

### Research workflow

```bash
python scripts/run_nifty50_zerodha_research.py \
  --symbols-limit 5 \
  --regime-analysis \
  --build-regime-policy
```

Outputs include ranked research artifacts under `output/nifty50_research/` and policy artifacts under `research/`.
Each run also writes `output/nifty50_research/run_manifest.json`.

### Paper trading workflow

```bash
python scripts/run_paper_trading.py \
  --paper-trading \
  --provider indian_csv \
  --symbols RELIANCE.NS TCS.NS INFY.NS \
  --interval day \
  --output-dir output/paper_trading_run \
  --use-next-bar-fill \
  --paper-max-orders 10
```

Outputs include orders, positions, PnL, state, session summary markdown, and `run_manifest.json`.

### Live signal workflow

```bash
python scripts/run_live_signal_pipeline.py \
  --live-signals \
  --provider indian_csv \
  --symbols RELIANCE.NS TCS.NS INFY.NS \
  --interval day \
  --run-once \
  --paper-handoff \
  --output-dir output/live_signals_run
```

Outputs include `signals.csv`, `regime_snapshot.csv`, `session_state.json`, and optional `paper_handoff_signals.csv`.
Each cycle writes `run_manifest.json` with mode/provider/artifact metadata.

### Decision + portfolio workflow

```bash
python scripts/run_decision.py \
  --provider indian_csv \
  --symbols RELIANCE.NS TCS.NS INFY.NS \
  --interval day \
  --profile eod \
  --allocation-model conviction_weighted \
  --sizing-method risk_per_trade \
  --output-dir output/decision_portfolio_run
```

Outputs include decision artifacts plus portfolio-aware artifacts:

- `portfolio_plan.json`
- `portfolio_plan.csv`
- `portfolio_risk_summary.json`
- `allocation_summary.md`
- `portfolio_artifacts_meta.json`
- `run_manifest.json`

### Release smoke workflow

```bash
python scripts/run_release_smoke.py --output-dir output/release_smoke --symbols-limit 3
```

This runs a minimal research/paper/live-safe path and validates artifact bundles against runtime contracts.

### Daily dry-run workflow

```bash
python scripts/run_daily_dry_run.py --output-dir output/daily_dry_run --symbols-limit 3
```

This runs scanner -> monitoring -> decision in one safe chain, writes stage-level
manifests, validates scanner/monitoring/decision artifact contracts, and writes
`daily_dry_run_summary.json` + `daily_dry_run_summary.md`.

## Safety Boundaries

- No live execution occurs in current architecture.
- `src/execution/execution_interface.py` is placeholder-only and inert by design.
- Broker adapters exist for data/integration-readiness, not active live order placement.
- Paper trading and live-signal flows are explicit opt-in CLI paths with safe defaults.
- Shared runtime guardrails and mode profiles are centralized in `src/runtime/`.
- Artifact contracts and validation are centralized in `src/runtime/artifact_contracts.py` and `src/runtime/contract_validation.py`.
- Mid-pipeline scanner/monitoring/decision contract validation is available via the daily dry-run orchestrator.
- Portfolio planning outputs are recommendation-only and do not route broker orders.
- Provider credentials are sourced from environment settings (`.env` / process env), not persisted as plaintext YAML secrets.
- Market-session status includes holiday-aware checks via the trading calendar layer.

Safety details: [`docs/SAFETY.md`](docs/SAFETY.md)

## Quickstart

> **Looking for the operator guide?** See [docs/OPERATOR_QUICKSTART.md](docs/OPERATOR_QUICKSTART.md) for full commands, launcher details, and configuration.

Install dependencies:

```bash
pip install -r requirements.txt
```

Run one command per mode:

- Research: `python scripts/run_nifty50_zerodha_research.py --symbols-limit 5 --regime-analysis --build-regime-policy`
- Paper trading: `python scripts/run_paper_trading.py --paper-trading --provider indian_csv --symbols RELIANCE.NS TCS.NS INFY.NS --interval day --paper-output-dir output/paper_trading_run --paper-max-orders 10`
- Live-safe signals: `python scripts/run_live_signal_pipeline.py --live-signals --provider indian_csv --symbols RELIANCE.NS TCS.NS INFY.NS --interval day --run-once --output-dir output/live_signals_run`
- Decision + portfolio plan: `python scripts/run_decision.py --provider indian_csv --symbols RELIANCE.NS TCS.NS INFY.NS --interval day --profile eod --output-dir output/decision_run`
- UI Command Center: `uvicorn src.api.main:app --reload` (backend) and `npm run dev` (frontend)

## What Changed in Phase 20 (UI / Command Center)

- Built a premium **React/Vite** frontend and **FastAPI** backend to serve as an operator-grade trading dashboard.
- Features real-time state viewing for Scanner, Monitoring, Decision, Paper Trading, Provider Diagnostics, Artifact Explorer, and Profiles.
- Includes Derivatives Intelligence (with graceful fallback for offline modes) and AI Workspace / Automation panels (advisory/placeholder only).
- **Phase 20.1 UI Polish**: Enhanced UI trust with a global system clock, standardized disabled action semantics, Indian ecosystem currency (₹) consistency, and explicit read-only helper messaging in Profiles and Settings.
- **Phase 21+ Planning**: Integrated inert Provider Authentication & Sessions scaffolds in Settings for future broker/API key management.
- **Execution Rule:** All broker execution, strategy deployment, and live-routing UI controls are strictly disabled or marked as future visual placeholders, reinforcing the read-only and simulation-first architecture.

## What Changed in Phase 18

- Added portfolio and risk planning to decision outputs:
  - allocation models: `equal_weight`, `volatility_weighted`, `conviction_weighted`
  - sizing methods: `fixed_fractional`, `risk_per_trade`, `atr_based` (with fallback)
  - portfolio constraints: capital, position caps, per-position cap, sector/correlation controls
  - drawdown overlays: `normal`, `reduced_risk`, `no_new_risk`
- `run_decision.py` now emits portfolio-aware artifacts and metadata manifests.
- `run_paper_trading.py` can optionally consume `portfolio_plan.json` quantity/drawdown overlays.
- Live-safe paper handoff artifacts now include portfolio recommendation metadata fields.
- Live execution remains disabled.

## Indian Derivatives Data Layer (Phase 2)

Phase 2 makes Indian derivatives first-class data and instrument citizens without adding execution, analytics, or Greeks.

### What is real (fully implemented)

| Capability | Location |
|---|---|
| Kite/Zerodha derivative symbol format (`NIFTY26APRFUT`, `NIFTY26APR24500CE`) | `src/instruments/provider_mapping.py` |
| Upstox segment|symbol format (`NSE_FO\|NIFTY26APRFUT`) | `src/instruments/provider_mapping.py` |
| `to_provider_symbol()` for zerodha/upstox/csv | `src/instruments/normalization.py` |
| Round-trip canonical ↔ Kite symbol parsing | `src/instruments/provider_mapping.py` |
| Instrument hydration from Kite instruments() rows | `src/instruments/hydrator.py` |
| Active contract resolution and option chain utilities | `src/instruments/contracts.py` |
| NFO/MCX/CDS registry lookup (`list_by_underlying`, `list_by_expiry`, `list_option_chain`) | `src/instruments/registry.py` |
| Derivative-aware data fetch routing (`DerivativeDataFetcher`) | `src/data/derivative_data.py` |
| Normalized quote model with OI + depth + quality flags | `src/data/quote_normalizer.py` |
| Extended provider capability flags (historical_derivatives, OI, depth, instrument_master) | `src/data/provider_capabilities.py` |
| NSE 2025–2026 trading holidays populated | `src/instruments/calendar.py` |
| Multi-segment instrument mapper (`refresh_all_segments`, `hydrate_registry`) | `src/data/instrument_mapper.py` |

### Supported Indian segments

| Exchange | Segment | Instruments | Provider |
|---|---|---|---|
| NSE | CASH | Equities, ETFs, Indices | Zerodha ✓, CSV ✓ |
| BSE | CASH | Equities, ETFs | Zerodha ✓ |
| NFO | FO | NIFTY/BANKNIFTY futures + options | Zerodha ✓ |
| MCX | COMM | GOLD, CRUDEOIL, SILVER futures | Zerodha ✓ |
| CDS | CURR | USDINR and other forex futures/options | Zerodha ✓ |

### Canonical derivative symbol format

```
EXCHANGE:UNDERLYING[-EXPIRY-SUFFIX]

NFO:NIFTY-2026-04-30-FUT       # NFO monthly future
NFO:NIFTY-2026-04-30-24500-CE  # NFO monthly call option
MCX:GOLD-2026-04-30-FUT        # MCX commodity future
CDS:USDINR-2026-04-30-FUT      # CDS forex future
```

### What is NOT yet implemented from Phase 2 scope

- Upstox SDK derivative fetch (SDK path raises NotImplementedError — CSV fallback only)
- Live streaming / WebSocket data
- Execution of any kind (permanently disabled by design)
- MCX/CDS weekly expiry exact symbol mapping (monthly format is correct; weekly is best-effort)

Options analytics (Greeks, IV, skew) and futures continuous series logic were deferred from Phase 2 and are now implemented in Phase 3 — see below.

---

## Derivatives Intelligence Layer (Phase 3)

Phase 3 builds actual derivatives analytics and a switchable DhanHQ data provider on top of the Phase 2 data layer.

### DhanHQ Switchable Provider

| Feature | Status |
|---|---|
| Optional `dhanhq` SDK (graceful degradation when absent or unconfigured) | implemented |
| Health check states: `sdk_unavailable`, `no_credentials`, `sdk_configured` | implemented |
| `fetch_option_chain()` returning normalized CE/PE rows per strike | implemented |
| `fetch_expiry_list()` for underlying | implemented |
| DhanHQ segment strings: `NSE_EQ`, `NSE_FO`, `MCX`, `CUR` | implemented |
| DhanHQ ↔ canonical symbol conversion in `provider_mapping.py` | implemented |
| `"dhan"` entry in `_PROVIDER_CAPABILITIES` with full derivative flags | implemented |

### Provider Routing (`src/data/provider_router.py`)

Named routing policies for segment-aware provider selection:

| Policy | Description |
|---|---|
| `zerodha_only` | All segments via Zerodha |
| `dhan_only` | All segments via DhanHQ |
| `dhan_primary_zerodha_cash` | Derivatives via DhanHQ, cash via Zerodha |
| `auto` | Segment-smart routing with fallback chain |

### Option Chain Intelligence (`src/analysis/derivatives/options/`)

| Component | Capability |
|---|---|
| `OptionStrike` | Per-strike CE/PE struct: LTP, OI, volume, bid/ask, IV, delta, theta, gamma, vega |
| `OptionChain` | Full chain with ATM strike, chain PCR, max pain, IV skew |
| `OptionChainBuilder` | Build from DhanHQ response, generic dict list, or `InstrumentRegistry` |
| `OptionChainAnalyzer` | PCR, max pain, IV skew, OI concentration, strike ladder |
| `black_scholes()` | Pure-Python BSM (no scipy) — price, delta, gamma, theta, vega, rho |
| `implied_volatility()` | Bisection IV solver in [1e-6, 5.0] sigma range |
| `classify_moneyness()` | ATM / ITM / OTM classification |
| `enrich_greeks()` | Compute IV + Greeks for strikes missing them |

### Futures Contract Intelligence (`src/analysis/derivatives/futures/intelligence.py`)

| Component | Capability |
|---|---|
| `FuturesContractInfo` | Per-contract: DTE, position (front/next/far), lot size, active flag |
| `FuturesContractFamily` | front/next/far labeling; `is_roll_imminent` (DTE ≤ 5) |
| `FuturesContractResolver` | `get_contract_family()`, `compute_basis()`, `get_roll_signal()` |
| `ContinuousSeriesBuilder` | `dte_roll` and `calendar_roll` roll schedules; `stitch_from_dataframes()` |

### Activated Derivative Analysis Modules

Phase 3 promotes four derivative modules from stub to real implementation:

| Module | Key Features |
|---|---|
| `FuturesAnalysisModule` | DTE, roll imminence, basis, basis_pct, contango/backwardation, OI, price change |
| `OptionsAnalysisModule` | PCR, call/put OI totals, IV skew, ATM strike, max pain, call resistance, put support |
| `CommoditiesAnalysisModule` | Delegates to FuturesAnalysisModule + `asset_class="commodity"` |
| `ForexAnalysisModule` | Delegates to FuturesAnalysisModule + `asset_class="currency"` + currency pair |

### New Analysis Profiles (Phase 3)

| Profile | Enabled Modules |
|---|---|
| `index_futures` | technical, quant, futures |
| `stock_futures` | technical, quant, futures |
| `equity_options` | technical, quant, options |
| `inr_currency_derivatives` | technical, quant, futures, forex |

### What is NOT implemented in Phase 3 (by design)

- Live order execution (permanently disabled)
- WebSocket / streaming data
- Volatility surface interpolation or skew models beyond simple slope
- Cross-provider credential orchestration for every external analysis API endpoint
- Upstox SDK derivatives path (remains CSV fallback)
- Crypto provider or data path

---

## Combined Phase 4 — Fundamental + Macro + Sentiment + Intermarket

Phase 4 upgrades the non-technical analysis families from placeholders to
modular, profile-driven components with switchable provider selection.

### What Phase 4 adds

- Fundamental normalization + factor engine (`value`, `quality`, `growth`, `leverage`, `profitability`, `cash-flow quality`, earnings-event risk flags)
- Macro normalization + context engine (inflation/growth trends, rate pressure, yield-curve context, calendar/event blackout hooks)
- Sentiment/news normalization + feature engine (ticker/market/macro sentiment, intensity, caution flags, freshness)
- Intermarket feature engine (cross-asset correlations, divergence, confirmation/contradiction flags)
- Family-specific provider selection:
  - fundamentals: `alphavantage` / `finnhub` / `fmp` / `eodhd` / `none`
  - macro: `alphavantage` / `finnhub` / `fmp` / `eodhd` / `none`
  - sentiment: `alphavantage` / `finnhub` / `fmp` / `eodhd` / `none`
  - intermarket: `derived` (plus fallback routing support)
- Additive scanner -> monitoring -> decision wiring:
  - `analysis_features`
  - `fundamental_summary`, `macro_summary`, `sentiment_summary`, `intermarket_summary`
  - `event_risk_flags`
  - `analysis_provider_metadata`

### Provider-supplied vs derived

- Provider-supplied fields are preserved and tagged in normalized bundles.
- Derived fields are explicit (for example `fcf_yield` from `free_cash_flow / market_cap` when missing from provider payload).
- Sentiment uses provider scores when supplied; a lightweight keyword fallback is optional.
- Intermarket is intentionally derived from available market/macro series and reports degraded coverage honestly when sparse.

### Profile wiring (Phase 4)

Representative profile combinations now include:

- `intraday_equity`: technical + quant
- `swing_equity`: technical + quant + fundamental + sentiment
- `positional_equity`: technical + quant + fundamental + macro + sentiment + intermarket
- `macro_swing`: macro + intermarket + technical (+ quant overlay)
- `index_options`: technical + quant + options + sentiment
- `commodity_futures`: technical + quant + futures + commodities + macro + intermarket
- `inr_currency_derivatives`: technical + quant + futures + forex + macro + intermarket
- `full`: all available families

### What remains deferred after Phase 4

- Live order execution (still disabled)
- Heavy NLP stack beyond lightweight sentiment fallback
- Full external API client implementations for every analysis provider endpoint in all regions
- Crypto execution/runtime expansion

---

## Modular Analysis Framework (Phase 1 — Modular Foundation)

A pluggable, multi-asset analysis architecture has been layered on top of the existing engine.
All additions are backward-compatible — no existing behaviour was altered.

### Analysis Plugin Framework (`src/analysis/`)

| Component | Purpose |
|-----------|---------|
| `BaseAnalysisModule` ABC | Plugin contract: `name`, `is_enabled()`, `supports()`, `build_features()`, `build_signals()`, `build_context()`, `health_check()` |
| `FeatureOutput` | Standardised multi-domain output dataclass with slots `technical`, `quant`, `fundamental`, `macro`, `sentiment`, `intermarket`, `derivatives` |
| `AnalysisRegistry` | Central hub: register/enable/disable/resolve modules; `create_default()` wires technical+quant and registers optional modules disabled by default |
| `TechnicalAnalysisModule` | Delegates entirely to `BaseStrategy` static methods — zero indicator duplication |
| `QuantAnalysisModule` | Rolling volatility (annualised), momentum, return z-score, Sharpe, volume z-score |
| Phase 4 non-technical modules | `fundamental`, `macro`, `sentiment`, `intermarket` with normalized provider payload support and degraded-safe outputs |
| Derivative modules | `futures`, `options`, `commodities`, `forex` with real feature implementations |
| Remaining stub module | `crypto` (disabled by default) |

### Instrument Master (`src/instruments/`)

- **`Exchange` enum**: NSE, BSE, NFO, MCX, CDS
- **`Segment` enum**: CASH, FO, COMM, CURR with `from_exchange()` inference
- **`Instrument` dataclass**: factory helpers `.equity()`, `.future()`, `.option()`; validates all type-specific fields
- **Symbol normalisation**: `format_canonical()` / `parse_canonical()` with round-trip guarantee for all asset classes
- **Canonical format**: `EXCHANGE:SYMBOL[-EXPIRY-SUFFIX]` e.g. `NSE:RELIANCE-EQ`, `NFO:NIFTY-2026-04-30-FUT`, `NFO:NIFTY-2026-04-30-24500-CE`
- **`TradingCalendar`**: NSE monthly/weekly expiry calculation, trading-day detection, holiday overlay stub
- **`InstrumentRegistry`**: canonical-keyed store with lookup by type/exchange/segment

### Analysis Profiles (`src/config/`)

Nine named profiles defined in `analysis_profiles.yaml` (default, intraday_equity, swing_equity, positional_equity, index_options, commodity_futures, forex_futures, macro_swing, full).
`AnalysisProfileLoader.apply_profile_by_name()` enables exactly the listed modules and disables all others.

### Provider Capability Extension

`ProviderFeatureSet` now carries `supported_segments: tuple[str, ...]` and `supports_derivatives: bool`
with backward-compatible defaults plus a `supports_segment()` helper.

### Integration

- `StockScannerEngine` accepts optional `analysis_registry`; forwards to `OpportunityScorer.score()` which calls `FeatureOutput.from_modules()` and stores results under `score_components["analysis_features"]`.
- `ConvictionEngine.score()` accepts optional `analysis_context` (reserved for Phase 2).

---

## Regression Hardening Pass (post-Phase 18)

A maintenance and regression-hardening pass verified all previously fixed research correctness behaviors and added tests locking in:

- **Portfolio backtester allocation**: both `reserve_full_capacity=False` (default, divides by active symbol count) and `reserve_full_capacity=True` (conservative, divides by `max_positions`) modes.
- **Walk-forward config clone chain**: all three fallback paths (`model_copy` → `copy` → `deepcopy`) are exercised.
- **RSI edge cases**: pure-gain series → RSI=100, pure-loss → RSI=0, flat → RSI≈50.
- **Monte Carlo Sharpe formula**: equity-curve return–based annualized Sharpe `(mean/std)*sqrt(252)` is locked in via regression tests across all three simulation modes.
- **Paper trading edge cases**: zero-cash entry rejection, stop-loss/take-profit defaults, PnL history bar count, final equity non-negative.
- **Decision modules**: `conviction_engine`, `ranking_engine`, and `trade_plan_builder` now all emit structured debug/warning logs.
- **Upstox health_check**: all three status paths (`not_implemented`, `csv_fallback_only`, `sdk_present_auth_configured`) are tested with their specific `state` keys.

## Testing

Run all tests:

```bash
python -m pytest tests -q
```

## Git Workflow for AI Tools

Follow [`AI_AGENT_WORKFLOW.md`](AI_AGENT_WORKFLOW.md):

- Branches: `codex/*`
- Commits: `codex:` prefix
- Never push directly to `main`
- Use PR-based merge flow
