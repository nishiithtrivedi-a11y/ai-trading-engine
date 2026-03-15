# AI Trading Engine

A Python research platform for algorithmic trading strategy development on historical market data.

This repository is focused on **research and backtesting workflows**. It is not a live execution system.

## Project Overview

The project currently provides:

- Core backtesting engine (bar-by-bar simulation)
- Strategy framework with reusable indicators/helpers
- Research tooling:
  - optimizer (grid search)
  - walk-forward testing
  - Monte Carlo robustness analysis
  - multi-asset portfolio aggregation
  - strategy template generation/ranking
- Provider/config layer:
  - configurable provider factory
  - CSV / Indian CSV support
  - Zerodha / Upstox integration-ready stubs
  - symbol normalization/mapping
  - NSE universe utilities
- Phase 3 scanner layer:
  - universe scanning across symbols/timeframes/strategies
  - latest-state signal evaluation
  - setup generation (entry/stop/target)
  - opportunity classification and scoring
  - CSV/JSON export
- Phase 10 Streamlit dashboard:
  - local research and monitoring control room
  - read-oriented data views (no trade execution)
  - visualizes outputs from all phases
  - graceful empty states when data is missing
  - Control Center page: run engines via buttons (scanner, monitoring, decision, market intelligence, research lab, realtime cycle, full pipeline)
  - safe, bounded engine invocations (CSV provider, single-cycle realtime, no broker calls)
- Phase 4 market monitoring layer:
  - watchlist management (config/CSV/JSON/universe-backed)
  - market regime detection (explicit threshold logic)
  - relative/sector strength analysis
  - structured alert generation with dedupe
  - top-picks snapshot generation
  - monitoring artifact export (CSV/JSON)
- Phase 5 decision/pick layer:
  - regime-aware filtering and penalties
  - conviction scoring with explicit weighted components
  - trade plan generation from scanner opportunities
  - ranking + shortlist selection caps
  - final intraday/swing/positional pick outputs
  - decision artifact export (CSV/JSON)
- Phase 6 market intelligence layer:
  - market breadth metrics and state classification
  - sector rotation scoring and leader/laggard classification
  - volume intelligence signals and snapshots
  - volatility regime detection
  - unified market state assessment + export
- Phase 7 strategy research lab:
  - strategy candidate generation from templates/parameter grids
  - parameter surface analysis for stable/unstable regions
  - robustness analysis (walk-forward, Monte Carlo, perturbations)
  - strategy clustering and weighted research scoring
  - strategy discovery orchestration + export
- Phase 8 realtime market engine:
  - explicit config-driven ON/OFF runtime switch
  - finite-cycle simulated/polling run modes
  - market-hours gating with safe dry-run override
  - repeated monitoring/decision refresh snapshots
  - realtime status/history/alerts/snapshot export
- Phase 9 live market data / signal pipeline:
  - fresh/latest-bar signal pipeline with safe single-run default
  - watchlist/universe loading + session-state artifacts
  - relative-strength + regime snapshot + regime-policy selection
  - risk pre-check integration and paper-handoff CSV export
  - no live order placement
- Paper-trading engine:
  - safe paper-only session runner on fresh provider data
  - hypothetical paper orders, fills, positions, and PnL tracking
  - reuse of regime policy, risk manager, and execution cost/fill models
  - CSV/JSON/Markdown session artifacts

## Current Architecture

### 1. Core Backtesting Layer (`src/core/`)

- `backtest_engine.py`: simulation loop and signal handling
- `broker.py`, `execution.py`: order lifecycle and fills
- `portfolio.py`, `position.py`, `order.py`: portfolio/trade domain
- `data_handler.py`: validated OHLCV access
- `metrics.py`, `reporting.py`: performance metrics and outputs

### 2. Strategy Layer (`src/strategies/`)

- `base_strategy.py`: strategy contract and indicator helpers
- `sma_crossover.py`, `rsi_reversion.py`, `breakout.py`

### 3. Research Layer (`src/research/`)

- `optimizer.py`
- `walk_forward.py`
- `monte_carlo.py`
- `multi_asset_backtester.py`
- `strategy_generator.py`

### 4. Provider/Config Layer (`src/data/`, `config/`)

- `provider_config.py`, `provider_factory.py`
- `base.py`, `sources.py`, `indian_data_loader.py`
- `symbol_mapping.py`, `nse_universe.py`
- `config/data_providers.yaml`

### 5. Scanner Layer (`src/scanners/`)

- `models.py`, `config.py`
- `universe_resolver.py`, `data_gateway.py`
- `signal_runner.py`, `setup_engine.py`
- `classifier.py`, `scorer.py`
- `engine.py`, `exporter.py`

### 6. Monitoring Layer (`src/monitoring/`)

- `models.py`, `config.py`
- `watchlist_manager.py`
- `regime_detector.py`
- `sector_strength.py`
- `alert_engine.py`
- `snapshot_engine.py`
- `scheduler.py` (optional local schedule abstraction)
- `market_monitor.py`
- `exporter.py`

### 7. Decision Layer (`src/decision/`)

- `models.py`, `config.py`
- `regime_filter.py`
- `conviction_engine.py`
- `trade_plan_builder.py`
- `portfolio_candidate_selector.py`
- `ranking_engine.py`
- `pick_engine.py`
- `exporter.py`

### 8. Market Intelligence Layer (`src/market_intelligence/`)

- `models.py`, `config.py`
- `market_breadth.py`
- `sector_rotation.py`
- `volume_intelligence.py`
- `volatility_regime.py`
- `institutional_flow.py` (graceful placeholder)
- `market_state_engine.py`
- `exporter.py`

### 9. Strategy Research Lab (`src/research_lab/`)

- `models.py`, `config.py`
- `strategy_generator.py`
- `parameter_surface.py`
- `robustness_analyzer.py`
- `strategy_cluster.py`
- `strategy_score_engine.py`
- `strategy_discovery_engine.py`
- `exporter.py`

### 10. Realtime Layer (`src/realtime/`)


- `models.py`, `config.py`
- `market_clock.py`
- `data_poller.py`
- `state_store.py`
- `event_bus.py`
- `alert_dispatcher.py`
- `snapshot_refresher.py`
- `realtime_engine.py`
- `exporter.py`

### 11. Paper Trading Layer (`src/paper_trading/`)

- `models.py`, `state_store.py`
- `paper_engine.py`
- `scripts/run_paper_trading.py`

### 12. Live Signal Layer (`src/live/`)

- `models.py`, `watchlist_manager.py`
- `market_session.py`, `signals_pipeline.py`
- `scripts/run_live_signal_pipeline.py`

### 13. Dashboard Layer (`src/ui/`)

- `app.py`: Streamlit application entry point with sidebar navigation
- `pages/`: Page modules (overview, control_center, backtests, optimization, walk-forward, monte_carlo, scanner, monitoring, decision_engine, realtime)
- `components/`: Reusable UI components (metrics_cards, tables, charts, filters, action_panels, status_panels)
- `utils/`: Loader, formatter, state management, and engine runner utilities

## Phase-by-Phase Status

### Phase 1 (Complete)

- Base backtesting engine and strategy execution loop
- Core metrics/reporting and data validation

### Phase 2 (Complete)

- Optimizer, walk-forward, Monte Carlo, multi-asset aggregation
- Strategy generation/ranking
- Provider config/factory and symbol mapping

### Phase 3 (Complete)

- Stock scanning and signal research engine on top of existing architecture
- Multi-timeframe scanning and opportunity ranking
- Setup generation (entry/stop/target), classification, exports

### Phase 4 (Complete)

- Market monitoring and analysis orchestration layer
- Watchlists + repeated-scan scheduling primitives
- Regime detection, relative strength, alerts, and top-picks snapshots
- Monitoring CSV/JSON export bundle for future UI/automation

### Phase 5 (Complete)

- Decision/pick engine on top of scanner + monitoring outputs
- Rule-based regime filtering and transparent rejection reasons
- Conviction scoring + deterministic ranking
- Portfolio-style shortlist selection by horizon/sector/duplicates
- Export-ready final pick outputs for future UI/execution integration

### Phase 6 (Complete)

- Additive market intelligence layer for explainable macro/context signals
- Breadth, sector rotation, volume intelligence, and volatility regime components
- Unified market-state assessment with confidence scoring and risk environment
- CSV/JSON export bundle for future automation/UI consumption

### Phase 7 (Complete)

- Additive strategy research lab for discovery and robustness ranking
- Candidate generation + parameter surface + robustness analysis
- Strategy clustering + weighted score engine + orchestrated discovery workflow
- CSV/JSON export artifacts for strategy research pipelines

### Phase 8 (Complete)

- Additive realtime observer engine for repeated, safe, non-executing cycles
- Explicit config ON/OFF switch (`realtime.enabled`) with default OFF behavior
- Supported realtime modes: `off`, `simulated`, `polling`
- Market-hours gating with dry-run support and bounded cycles (`max_cycles_per_run`)
- Realtime cycle orchestration of poll -> monitoring refresh -> decision refresh
- Realtime export artifacts for future UI/automation (`realtime_status`, history, snapshot, alerts, manifest)

### Phase 9 (Complete)

- Additive live-safe signal pipeline over fresh/latest data snapshots
- Watchlist/universe loading with session artifacts (`signals`, `watchlist`, `regime_snapshot`, `session_state`, `session_summary`)
- Relative-strength ranking + regime snapshots + optional regime-policy strategy selection
- Optional paper handoff export (`paper_handoff_signals.csv`)
- Explicit safety boundary: signal generation only, no broker execution

### Phase 10 (Complete)

- Streamlit-based local research and monitoring dashboard
- Read-oriented UI over all phase outputs (no trade execution)
- Pages: Overview, Control Center, Backtests, Optimization, Walk-Forward, Monte Carlo, Scanner, Monitoring, Decision Engine, Realtime
- Control Center: button-driven engine execution (scanner, monitoring, decision, market intelligence, research lab, realtime cycle)
- Full research pipeline button (MI -> Scanner -> Monitoring -> Decision) with stage-by-stage progress
- Engine runner wrappers with structured RunResult outcomes and graceful error handling
- Session-level run history and per-engine last-run tracking
- Modular architecture: components, pages, utility layers
- Graceful empty-state handling for missing data
- Reusable loader/formatter/state/runner utilities with test coverage

### Paper Trading Layer (Complete)

- Additive paper-only trading workflow on top of provider/strategy/regime/risk/execution modules
- Safe opt-in CLI (`scripts/run_paper_trading.py`) with no live broker routing
- Tracks paper orders, fills, positions, realized/unrealized PnL, and session journal
- Exports `paper_orders.csv`, `paper_positions.csv`, `paper_pnl.csv`, `paper_session_summary.md`, and `paper_state.json`

### Future Scope (Not Yet Implemented)

- Live broker execution
- Advanced order routing/risk controls for production deployment
- Automated scheduling/orchestration services for continuous research runs

## Installation

```bash
pip install -r requirements.txt
```

## How to Run

### Streamlit Dashboard (Phase 10)

```bash
streamlit run src/ui/app.py
```

The dashboard does not execute trades or place orders. It visualizes outputs from all earlier phases and provides a Control Center for running research engines via buttons. Pages show graceful empty states when data is not yet available.

Dashboard pages:
- **Overview**: Platform status, market state, decision summary, data availability
- **Control Center**: Run engines via buttons, full pipeline execution, run history, config summary
- **Backtests**: Equity curves, drawdowns, trade logs, performance metrics
- **Optimization**: Strategy ranking tables, parameter analysis
- **Walk-Forward**: Per-window train/test metrics, out-of-sample summaries
- **Monte Carlo**: Percentile analysis, probability of profit, simulation config
- **Scanner**: Ranked opportunities, score breakdown, classification distribution
- **Monitoring**: Market regime, top picks, alerts, relative strength
- **Decision Engine**: Intraday/swing/positional picks, rejected opportunities
- **Realtime**: Engine status, cycle history, snapshots, alerts

### Using the Control Center

The Control Center page lets you run engines directly from the dashboard:

1. Open the dashboard: `streamlit run src/ui/app.py`
2. Select **Control Center** from the sidebar
3. Click **Run Full Pipeline** to run Market Intelligence, Scanner, Monitoring, and Decision Engine in sequence
4. Or run individual engines using the dedicated buttons
5. View run history and output status at the bottom of the page

Available buttons:
- **Run Scanner** -- scans the NIFTY 50 universe with RSI + SMA strategies
- **Run Monitoring** -- market regime, alerts, relative strength
- **Run Decision Engine** -- runs monitoring + pick engine (intraday/swing/positional)
- **Run Market Intelligence** -- breadth, sector rotation, volume, volatility regime
- **Run Research Lab** -- strategy discovery and robustness scoring
- **Run One Realtime Cycle** -- single simulated cycle (safe, bounded)
- **Run Full Pipeline** -- MI > Scanner > Monitoring > Decision in sequence

All actions are **research-only**: they use the CSV data provider, never place trades, and realtime is limited to single simulated cycles.

### Main backtest demo

```bash
python main.py
```

### Optimizer

```bash
python optimize_sma.py
```

### Multi-asset research

```bash
python run_multi_asset_backtest.py
```

### Walk-forward

```bash
python run_rsi_walkforward.py
```

### Monte Carlo

```bash
python run_rsi_monte_carlo.py
```

### Strategy ranking

```bash
python run_strategy_ranking.py data/RELIANCE_1D.csv 10
```

### Scanner engine (example)

No dedicated top-level scanner runner script is required; scanner is run via `StockScannerEngine`.

```python
from src.scanners import (
    ScannerConfig, StrategyScanSpec, StockScannerEngine, SetupMode
)
from src.strategies.rsi_reversion import RSIReversionStrategy
from src.strategies.sma_crossover import SMACrossoverStrategy

cfg = ScannerConfig(
    universe_name="custom",
    custom_universe_file="data/universe/custom_universe.csv",
    provider_name="csv",
    data_dir="data",
    timeframes=["1D"],
    setup_mode=SetupMode.ATR_R_MULTIPLE,
    strategy_specs=[
        StrategyScanSpec(
            strategy_class=RSIReversionStrategy,
            params={"rsi_period": 14, "oversold": 30, "overbought": 70},
            timeframes=["1D"],
        ),
        StrategyScanSpec(
            strategy_class=SMACrossoverStrategy,
            params={"fast_period": 10, "slow_period": 30},
            timeframes=["1D"],
        ),
    ],
)

result = StockScannerEngine(scanner_config=cfg).run(export=True)
print(result.to_dataframe(top_n=10))
```

Scanner output files are written under `output/scanner*` paths configured in `ExportConfig`.

### Monitoring engine (example)

```python
from src.monitoring import (
    AlertEngineConfig,
    MarketMonitor,
    MonitoringConfig,
    RegimeDetectorConfig,
    RelativeStrengthConfig,
    SnapshotConfig,
    WatchlistDefinition,
)
from src.scanners import ScannerConfig, SetupMode, StrategyScanSpec
from src.strategies.rsi_reversion import RSIReversionStrategy
from src.strategies.sma_crossover import SMACrossoverStrategy

scanner_cfg = ScannerConfig(
    provider_name="csv",
    data_dir="data",
    timeframes=["1D"],
    setup_mode=SetupMode.ATR_R_MULTIPLE,
    strategy_specs=[
        StrategyScanSpec(
            strategy_class=RSIReversionStrategy,
            params={"rsi_period": 14, "oversold": 30, "overbought": 70},
            timeframes=["1D"],
        ),
        StrategyScanSpec(
            strategy_class=SMACrossoverStrategy,
            params={"fast_period": 10, "slow_period": 30},
            timeframes=["1D"],
        ),
    ],
)

monitor_cfg = MonitoringConfig(
    scanner_config=scanner_cfg,
    watchlists=[
        WatchlistDefinition(
            name="focus",
            symbols=["RELIANCE.NS", "TCS.NS", "INFY.NS"],
        )
    ],
    regime=RegimeDetectorConfig(benchmark_symbol="NIFTY50.NS", timeframe="1D"),
    relative_strength=RelativeStrengthConfig(benchmark_symbol="NIFTY50.NS", timeframe="1D"),
    alerts=AlertEngineConfig(min_opportunity_score=65.0),
    snapshot=SnapshotConfig(top_n=10, min_score=60.0),
)

result = MarketMonitor(config=monitor_cfg).run(export=True, watchlist_names=["focus"])
print(result.snapshot.to_dict() if result.snapshot else {})
print(result.exports)
```

Monitoring outputs are written under `output/monitoring*` paths configured in `MonitoringExportConfig`.

### Decision pick engine (example)

```python
from src.decision import DecisionConfig, PickEngine
from src.monitoring import MarketMonitor, MonitoringConfig

# Phase 4 monitoring result (or use ScanResult directly)
monitor_result = MarketMonitor(config=MonitoringConfig()).run(export=False)

decision_cfg = DecisionConfig()
pick_result = PickEngine(decision_config=decision_cfg).run(
    monitoring_result=monitor_result
)

print("Intraday:", [p.symbol for p in pick_result.top_intraday])
print("Swing:", [p.symbol for p in pick_result.top_swing])
print("Positional:", [p.symbol for p in pick_result.top_positional])
print("Rejected:", len(pick_result.rejected_opportunities))
```

Decision outputs are written under `output/decision*` paths configured in `DecisionExportConfig`.

### Market intelligence engine (example)

```python
from src.market_intelligence import (
    MarketIntelligenceConfig,
    MarketIntelligenceExporter,
    MarketStateEngine,
)

cfg = MarketIntelligenceConfig(
    provider_name="csv",
    data_dir="data",
)

symbols = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS"]
sector_map = {
    "IT": ["TCS.NS", "INFY.NS"],
    "BANKING": ["HDFCBANK.NS", "ICICIBANK.NS"],
    "ENERGY": ["RELIANCE.NS"],
}

engine = MarketStateEngine()
result = engine.run(
    symbols=symbols,
    sector_symbol_map=sector_map,
    config=cfg,
    benchmark_symbol="NIFTY50.NS",
)
exports = MarketIntelligenceExporter().export_all(result, cfg.export)
print(result.market_state.to_dict())
print({k: str(v) for k, v in exports.items()})
```

Market intelligence outputs are written under `output/market_intelligence*` paths configured in `MarketIntelligenceExportConfig`.

### Strategy research lab (example)

```python
from src.core.data_handler import DataHandler
from src.research_lab import StrategyDiscoveryConfig, StrategyDiscoveryEngine
from src.utils.config import BacktestConfig

handler = DataHandler.from_csv("data/RELIANCE_1D.csv")

base_cfg = BacktestConfig(
    data_source="csv",
    data_file="data/RELIANCE_1D.csv",
)

discovery_cfg = StrategyDiscoveryConfig(top_n=10)
result = StrategyDiscoveryEngine().run(
    base_config=base_cfg,
    data_handler=handler,
    config=discovery_cfg,
    export=True,
)

print(len(result.strategy_scores))
print(result.exports)
```

Research lab outputs are written under `output/research_lab*` paths configured in `ResearchLabExportConfig`.

### Realtime engine (example)

The realtime engine is safe by default: `enabled=false` + `mode=off` means no realtime loop runs.

```python
from src.decision import DecisionConfig
from src.monitoring import MonitoringConfig
from src.realtime import RealTimeEngine, RealTimeEngineConfig, RealtimeConfig, RealTimeMode
from src.scanners import ScannerConfig, StrategyScanSpec, SetupMode
from src.strategies.rsi_reversion import RSIReversionStrategy
from src.strategies.sma_crossover import SMACrossoverStrategy

scanner_cfg = ScannerConfig(
    provider_name="csv",
    data_dir="data",
    universe_name="custom",
    custom_universe_file="data/universe/custom_universe.csv",
    timeframes=["1D"],
    setup_mode=SetupMode.ATR_R_MULTIPLE,
    strategy_specs=[
        StrategyScanSpec(
            strategy_class=RSIReversionStrategy,
            params={"rsi_period": 14, "oversold": 30, "overbought": 70},
            timeframes=["1D"],
        ),
        StrategyScanSpec(
            strategy_class=SMACrossoverStrategy,
            params={"fast_period": 10, "slow_period": 30},
            timeframes=["1D"],
        ),
    ],
)

monitor_cfg = MonitoringConfig(scanner_config=scanner_cfg)
decision_cfg = DecisionConfig()

rt_cfg = RealTimeEngineConfig(
    realtime=RealtimeConfig(
        enabled=True,
        mode=RealTimeMode.SIMULATED,
        provider_name="csv",
        symbols=["RELIANCE.NS", "TCS.NS", "INFY.NS"],
        timeframes=["1D"],
        max_cycles_per_run=3,
        only_during_market_hours=False,
        enable_polling=True,
        enable_event_bus=True,
        enable_alert_dispatch=True,
        persist_snapshots=True,
        persist_alerts=True,
        output_dir="output/realtime",
    ),
    monitoring=monitor_cfg,
    decision=decision_cfg,
)

engine = RealTimeEngine(config=rt_cfg)
result = engine.run(export=True)
print(result.to_dict()["summary"])
print(result.exports)
```

Realtime outputs are written under `output/realtime*`.

### Paper trading engine (example)

Safe default: nothing runs unless `--paper-trading` is passed.

```bash
python scripts/run_paper_trading.py \
  --paper-trading \
  --provider indian_csv \
  --symbols RELIANCE.NS TCS.NS INFY.NS HDFCBANK.NS ICICIBANK.NS \
  --interval day \
  --paper-output-dir output/paper_trading_run \
  --paper-max-orders 10
```

Optional regime-aware selection:

```bash
python scripts/run_paper_trading.py \
  --paper-trading \
  --provider indian_csv \
  --symbols RELIANCE.NS TCS.NS INFY.NS \
  --regime-policy-json research/regime_policy.json
```

Artifacts written under `output/paper_trading*` include:

- `paper_orders.csv`
- `paper_positions.csv`
- `paper_pnl.csv`
- `paper_journal.csv`
- `paper_session_summary.md`
- `paper_state.json`

### Live signal pipeline (example)

Safe default: nothing runs unless `--live-signals` is passed.

```bash
python scripts/run_live_signal_pipeline.py \
  --live-signals \
  --provider indian_csv \
  --symbols RELIANCE.NS TCS.NS INFY.NS \
  --interval day \
  --run-once \
  --output-dir output/live_signals_smoke
```

With optional paper handoff:

```bash
python scripts/run_live_signal_pipeline.py \
  --live-signals \
  --provider indian_csv \
  --symbols RELIANCE.NS TCS.NS INFY.NS HDFCBANK.NS ICICIBANK.NS \
  --interval day \
  --run-once \
  --paper-handoff \
  --output-dir output/live_signals_nifty5
```

Artifacts written under `output/live_signals*` include:

- `signals.csv`
- `watchlist.csv`
- `regime_snapshot.csv`
- `session_summary.md`
- `session_state.json`
- `paper_handoff_signals.csv` (when `--paper-handoff` is enabled)

### Realtime Switches and Modes

Default config file:

- `config/realtime.yaml`

Core switches:

- `realtime.enabled`: global ON/OFF
- `realtime.mode`: `off`, `simulated`, `polling`
- `realtime.enable_polling`
- `realtime.enable_alert_dispatch`
- `realtime.enable_scheduler`
- `realtime.enable_event_bus`
- `realtime.enable_live_provider`
- `realtime.persist_snapshots`
- `realtime.persist_alerts`
- `realtime.max_cycles_per_run`
- `realtime.only_during_market_hours`
- `realtime.dry_run`

Behavior:

- When `enabled=false` (or `mode=off`): no realtime cycle runs, no polling starts.
- When enabled + `simulated`: finite local cycles run against CSV/historical snapshots.
- When enabled + `polling`: provider live polling is attempted; unsupported live fetch gracefully falls back to snapshot polling.

## Provider Configuration

Provider settings are stored in:

- `config/data_providers.yaml`

Supported providers:

- `csv`
- `indian_csv`
- `zerodha` (integration-ready placeholder for historical/live)
- `upstox` (integration-ready placeholder for historical/live)

Notes:

- CSV scanning/backtesting is fully supported.
- Zerodha/Upstox classes include explicit interfaces and health checks, but historical/live API integrations remain placeholder where not implemented.
- Credentials can be supplied via config and/or environment variables (see provider config module).

## Scanner Output Shape

Typical opportunity fields include:

- `symbol`, `timeframe`, `strategy_name`, `timestamp`, `signal`
- `entry_price`, `stop_loss`, `target_price`
- `classification` (intraday/swing/positional)
- `score`
- flattened score components:
  - `score_signal`
  - `score_rr`
  - `score_trend`
  - `score_liquidity`
  - `score_freshness`
- `metadata` (detailed diagnostics)

## Decision Output Shape

Typical decision pick fields include:

- `symbol`, `timeframe`, `strategy_name`, `horizon`
- `entry_price`, `stop_loss`, `target_price`, `risk_reward`
- `conviction_score`
- `priority_rank`, `horizon_rank`
- `scanner_score`, `regime_compatibility`, `relative_strength_score`
- `conviction_breakdown` (component scores)
- `reasons`, `metadata`

Rejected opportunities include:

- original setup identifiers (`symbol/timeframe/strategy`)
- rejection reasons (explicit codes)
- explanatory notes

## Testing

Run all tests:

```bash
python -m pytest tests -q
```

Run scanner tests only:

```bash
python -m pytest tests/test_scanner_* -q
```

Run market intelligence tests:

```bash
python -m pytest tests/test_market_* tests/test_sector_rotation.py tests/test_volume_intelligence.py tests/test_volatility_regime.py -q
```

Run strategy research lab tests:

```bash
python -m pytest tests/test_strategy_* tests/test_parameter_surface.py tests/test_robustness_analyzer.py -q
```

Run UI and runner tests:

```bash
python -m pytest tests/test_ui_* -q
```

Run realtime tests:

```bash
python -m pytest tests/test_realtime_* tests/test_market_clock.py tests/test_data_poller.py tests/test_state_store.py tests/test_event_bus.py tests/test_alert_dispatcher.py tests/test_snapshot_refresher.py -q
```

Run paper-trading tests:

```bash
python -m pytest tests/test_paper_engine.py -q
```

Run live-signal pipeline tests:

```bash
python -m pytest tests/test_live_signal_pipeline.py tests/test_execution_interface_placeholder.py -q
```

## Git Workflow for AI Tools

See [AI_AGENT_WORKFLOW.md](AI_AGENT_WORKFLOW.md).

Key rules:

- Claude branch prefix: `claude/`
- Codex branch prefix: `codex/`
- Claude commit prefix: `claude:`
- Codex commit prefix: `codex:`
- Never push directly to `main`
- Use PRs for all integration

## Safety / Scope Note

This repository is a **research platform**.

- It is not financial advice.
- It does not guarantee profitability.
- Paper trading is simulated only and does not place live broker orders.
- Live signal pipeline outputs are signal artifacts only and do not place live broker orders.
- Live trading/execution is future scope and should be implemented with additional production-grade safeguards.
