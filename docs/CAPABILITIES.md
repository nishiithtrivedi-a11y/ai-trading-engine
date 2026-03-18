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
| Fundamental / macro / sentiment / intermarket modules | stub (disabled) | `src/analysis/{fundamental,macro,sentiment,intermarket}/` | placeholder — returns `{}` | future scope |
| Derivatives modules (futures, options, commodities, forex, crypto) | stub (disabled) | `src/analysis/derivatives/*/` | placeholder — returns `{}` | future scope |
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
| Options analytics (Greeks, IV, skew) | not implemented | — | — | future scope (Phase 3+) |
| Futures continuous series / roll-over | not implemented | — | — | future scope (Phase 3+) |
| Upstox SDK derivatives fetch | not implemented (SDK stub) | `src/data/sources.py` UpstoxDataSource | CSV fallback only | future scope |
| NSE 2025–2026 trading holidays | populated | `src/instruments/calendar.py` | accurate trading-day detection | stable |

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
