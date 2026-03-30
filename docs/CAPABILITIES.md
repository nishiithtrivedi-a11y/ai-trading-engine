# Capabilities

## Capability Matrix

| Capability | Status | Entry Point | Outputs | Maturity |
| --- | --- | --- | --- | --- |
| Historical backtesting | supported | `main.py`, `src/core/backtest_engine.py` | performance metrics, trade logs | stable |
| Strategy optimization | supported | `optimize_sma.py`, `src/research/optimizer.py` | ranked parameter sets | stable |
| Walk-forward testing | supported | `run_rsi_walkforward.py`, `src/research/walk_forward.py` | train/test window reports | stable |
| Monte Carlo robustness | supported | `run_rsi_monte_carlo.py`, `src/research/monte_carlo.py` | distribution metrics | stable |
| Portfolio simulation | supported | `run_multi_asset_backtest.py`, `src/research/portfolio_backtester.py` | portfolio-level metrics | stable |
| Scanner engine | supported | `src/scanners/engine.py` | ranked opportunities CSV/JSON | stable |
| Monitoring snapshots | supported | `src/monitoring/market_monitor.py` | alerts/snapshots/regime outputs | stable |
| Decision picks | supported | `src/decision/pick_engine.py` | intraday/swing/positional picks | stable |
| Portfolio & risk planning | supported | `src/decision/portfolio_engine.py`, `scripts/run_decision.py` | portfolio plan, allocation summary, risk summary | stable |
| Market intelligence | supported | `src/market_intelligence/market_state_engine.py` | breadth/sector/volatility outputs | stable |
| Strategy research lab | supported | `src/research_lab/strategy_discovery_engine.py` | strategy score/cluster artifacts | stable |
| Paper trading | supported | `scripts/run_paper_trading.py` | orders/fills/positions/PnL/session summary | stable |
| Live-safe signal pipeline | supported | `scripts/run_live_signal_pipeline.py` | signals/watchlist/regime/paper-handoff | stable |
| Live order execution | not supported | placeholder only | none | future scope |
| Runtime mode guardrails | supported | `src/runtime/run_profiles.py`, `src/runtime/safety_guards.py` | mode safety checks | stable |
| Output manifest metadata | supported | `src/runtime/output_manifest.py` | `run_manifest.json` | stable |
| Artifact contracts | supported | `src/runtime/artifact_contracts.py` | explicit required/optional output bundles | stable |
| Workflow orchestration smoke paths | supported | `src/runtime/workflow_orchestrator.py`, `scripts/run_release_smoke.py` | release smoke summary + validated bundles | stable |
| Scanner/monitoring/decision contract bundles | supported | `src/runtime/artifact_contracts.py` + `src/runtime/daily_dry_run.py` | stage-level manifests + contract validation | stable |
| Daily dry-run orchestration | supported | `scripts/run_daily_dry_run.py` | scanner/monitoring/decision chain summary | stable |
| Modular analysis plugin framework | supported | `src/analysis/` | per-module feature dicts merged into FeatureOutput | stable |
| Analysis profiles (YAML-driven) | supported | `src/config/analysis_profiles.yaml`, `src/config/analysis_profiles.py` | enable/disable module sets by named profile | stable |
| Instrument master | supported | `src/instruments/` | Instrument model, canonical symbols, expiry calendar | stable |
| Symbol normalisation (canonical) | supported | `src/instruments/normalization.py` | `EXCHANGE:SYMBOL[-EXPIRY-SUFFIX]` round-trip | stable |
| Multi-segment provider capabilities | supported | `src/data/provider_capabilities.py` | supported_segments, supports_derivatives flags | stable |
| Technical analysis module | supported | `src/analysis/technical/module.py` | RSI/SMA/EMA/ATR/Donchian features | stable |
| Quant analysis module | supported | `src/analysis/quant/module.py` | volatility/momentum/z-score/Sharpe features | stable |
| Fundamental analysis module | supported (profile-driven, optional) | `src/analysis/fundamental/module.py` | normalized fundamentals, factor outputs, earnings-event risk flags, degraded-safe mode | stable (Phase 4) |
| Macro analysis module | supported (profile-driven, optional) | `src/analysis/macro/module.py` | inflation/growth trends, rate pressure, macro regime, calendar blackout flags | stable (Phase 4) |
| Sentiment/news analysis module | supported (profile-driven, optional) | `src/analysis/sentiment/module.py` | ticker/market/macro sentiment, intensity, caution hooks, freshness | stable (Phase 4) |
| Intermarket analysis module | supported (profile-driven, optional) | `src/analysis/intermarket/module.py` | cross-asset correlations, divergence, confirmation/contradiction flags | stable (Phase 4) |
| Derivatives modules (futures, options, commodities, forex) | **implemented** | `src/analysis/derivatives/*/module.py` | DTE, basis, PCR, OI, IV skew, max pain, roll signals | stable (Phase 3) |
| Crypto derivative module | stub (disabled) | `src/analysis/derivatives/crypto/module.py` | placeholder — returns `{}` | future scope |
| Derivative instrument hydration (Kite rows → Instrument objects) | supported | `src/instruments/hydrator.py` | Instrument objects for NFO/MCX/CDS | stable |
| Provider-native symbol mapping (canonical ↔ Kite ↔ Upstox) | supported | `src/instruments/provider_mapping.py`, `normalization.py` | Kite tradingsymbols, Upstox segment\|symbol | stable |
| Active contract resolution and option chain utilities | supported | `src/instruments/contracts.py` | nearest expiry, strikes, grouped option chain | stable |
| Normalized derivative quotes (OI, depth, quality flags) | supported | `src/data/quote_normalizer.py` | NormalizedQuote with DataQualityFlags | stable |
| Derivative-aware data fetch routing | supported | `src/data/derivative_data.py` | DataFrame (OHLCV) or NormalizedQuote per instrument | stable |
| Derivative capability flags (per-provider) | supported | `src/data/provider_capabilities.py` | historical_derivatives, OI, depth, instrument_master | stable |
| Multi-segment instrument master hydration | supported | `src/data/instrument_mapper.py` | InstrumentRegistry populated from Kite instrument lists | stable |
| NFO futures / options data fetch via Zerodha | supported | `src/data/derivative_data.py` + Zerodha | OHLCV + OI where available | stable |
| MCX commodity futures data fetch via Zerodha | supported | `src/data/derivative_data.py` + Zerodha | OHLCV | stable |
| CDS currency futures data fetch via Zerodha | supported | `src/data/derivative_data.py` + Zerodha | OHLCV | stable |
| Options analytics (Greeks, IV, skew) | **implemented** | `src/analysis/derivatives/options/analytics.py` | BSM price/Greeks, IV bisection, max pain, IV skew, OI concentration | stable (Phase 3) |
| Option chain builder | **implemented** | `src/analysis/derivatives/options/chain.py` | OptionChain + OptionStrike from DhanHQ / dict list / registry | stable (Phase 3) |
| Futures contract intelligence | **implemented** | `src/analysis/derivatives/futures/intelligence.py` | FuturesContractFamily, roll signals, basis, backwardation/contango | stable (Phase 3) |
| Continuous series scaffold | **implemented** | `src/analysis/derivatives/futures/intelligence.py` ContinuousSeriesBuilder | dte_roll / calendar_roll schedules, stitch_from_dataframes | stable (Phase 3) |
| DhanHQ data provider | **implemented** | `src/data/dhan_source.py`, `src/data/provider_capabilities.py` | option chain, expiry list, quotes; graceful degradation | partial (optional SDK) |
| Provider routing policies | **implemented** | `src/data/provider_router.py` | zerodha_only, dhan_only, dhan_primary_zerodha_cash, auto | stable (Phase 3) |
| Analysis-family provider capability registry | supported | `src/data/provider_capabilities.py` | `AnalysisFamily`, `AnalysisProviderFeatureSet`, diagnostics (`alphavantage/finnhub/fmp/eodhd/none/derived`) | stable (Phase 4) |
| Analysis-family provider routing | supported | `src/data/provider_router.py` | `AnalysisProviderRoutingPolicy`, `AnalysisProviderRouter.select_for_family()` | stable (Phase 4) |
| Analysis-family provider config | supported | `src/data/provider_config.py`, `config/data_providers.yaml` | per-family provider selection + sentiment fallback flag | stable (Phase 4) |
| Scanner/monitoring/decision additive analysis wiring | supported (optional) | `src/scanners/scorer.py`, `src/monitoring/snapshot_engine.py` | `analysis_features`, family summaries, `event_risk_flags`, provider metadata | stable (Phase 4) |
| Derivative analysis profiles (4 new) | **implemented** | `src/config/analysis_profiles.yaml` | index_futures, stock_futures, equity_options, inr_currency_derivatives | stable (Phase 3) |
| Upstox SDK derivatives fetch | not implemented (SDK stub) | `src/data/sources.py` UpstoxDataSource | CSV fallback only | future scope |
| NSE 2025–2026 trading holidays | populated | `src/instruments/calendar.py` | accurate trading-day detection | stable |
| FastAPI Backend Adapter | **implemented** | `src/api/` | read-only adapters for core outputs | stable (Phase 20) |
| React/Vite UI Dashboard | **implemented** | `frontend/` | scanner, decision, paper, logs, artifacts, profiles, derivatives, ai workspace, settings | stable (Phase 20/20.1) |
| AI Workspace / Automation | placeholder | `frontend/src/pages/AI`, `Automation` | advisory-only UI, execution disabled | stable (Phase 20) |
| Provider Auth & Sessions | implemented (read-only) | `frontend/src/pages/Settings`, `src/providers/`, `src/data/provider_runtime.py` | shared readiness/session diagnostics and configuration helpers, execution disabled | stable |

## Phase 20 Notes — UI Command Center

- Introduced a premium React/Vite frontend and FastAPI backend serving as a thin adapter over the core engine.
- Views include Scanner, Monitoring, Decision, Paper Trading, Diagnostics, Artifact Explorer, Profiles, Derivatives, AI Workspace, and Settings.
- Graceful degradation: Handles missing artifacts and disconnected live feeds seamlessly (e.g., Derivatives shows CSV/offline modes).
- **Phase 20.1 Polish**: Added global header clock (Local System Time + Timezone), Indian ecosystem currency (₹) harmonization, and explicit read-only badges/helper-text for Profiles and Settings.
- **Provider readiness/session management**: Settings and API now surface read-only runtime readiness and session validation paths backed by shared provider runtime logic.
- AI Workspace is an advisory-only placeholder. Live execution and broker routing controls remain visually disabled placeholders.

## Phase 3 Notes — Derivatives Intelligence + DhanHQ

- **DhanHQ** added as an optional switchable provider. When `dhanhq` SDK is absent or credentials are missing, `DhanHQDataSource` degrades gracefully and reports its health state honestly.
- **Option chain analytics** are pure-Python (no scipy). Black-Scholes uses `math.erf` for CDF; IV computed via bisection in [1e-6, 5.0] sigma.
- **Futures contract intelligence**: `FuturesContractResolver` labels front/next/far, detects roll imminence (DTE ≤ 5), computes basis and contango/backwardation. `ContinuousSeriesBuilder` provides roll schedule scaffolding (no price adjustment — research-grade).
- **Derivative analysis modules** (futures, options, commodities, forex) are now real implementations registered in the `AnalysisRegistry`. `create_default()` still explicitly disables them — enable via a named analysis profile.
- **Provider routing**: `ProviderRoutingPolicy` named factory methods select the right provider per segment; `ProviderRouter.select_for_segment()` is the single dispatch call.
- All safety constraints maintained: no execution, no WebSocket, no live order paths.

## Combined Phase 4 Notes — Fundamental + Macro + Sentiment + Intermarket

- Non-technical analysis families are now implemented and remain profile-driven/optional.
- Family-specific provider selection is supported independently from market-data provider selection:
  - fundamentals: `alphavantage` / `finnhub` / `fmp` / `eodhd` / `none`
  - macro: `alphavantage` / `finnhub` / `fmp` / `eodhd` / `none`
  - sentiment: `alphavantage` / `finnhub` / `fmp` / `eodhd` / `none`
  - intermarket: `derived` (plus routed fallback support)
- Provider-supplied vs derived values are explicit in normalized models:
  - fundamentals: derived `fcf_yield` fallback when provider omits it
  - sentiment: provider score first, lightweight keyword fallback optional
  - intermarket: intentionally derived from available market/macro series
- Scanner/monitoring/decision integration is additive:
  - existing ranking behavior is preserved
  - context enrichment includes `analysis_features`, per-family summaries, and `event_risk_flags`
- Degraded and no-provider states are first-class and non-breaking.
- Live execution remains disabled.

## Phase 18 Notes

- Decision runner now emits portfolio-aware artifacts:
  - `portfolio_plan.json`
  - `portfolio_plan.csv`
  - `portfolio_risk_summary.json`
  - `allocation_summary.md`
  - `portfolio_artifacts_meta.json`
- Portfolio planning is recommendation-only and does not place broker orders.
- Drawdown overlays can move recommendation mode between:
  - `normal`
  - `reduced_risk`
  - `no_new_risk`

## Notes

- Core workflows are optimized for research correctness and simulation safety.
- All production order execution concerns are intentionally deferred.
- Safety-first defaults remain enforced across paper/live-safe runners.
- Runner validation and provider compatibility checks are shared via `src/runtime/runner_validation.py`.
- Artifact bundles are validated against run-mode contracts via `src/runtime/contract_validation.py`.
