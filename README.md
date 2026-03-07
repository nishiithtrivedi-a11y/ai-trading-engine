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

### Future Scope (Not Yet Implemented)

- Live broker execution
- Advanced order routing/risk controls for production deployment
- UI/dashboard expansion for scanner workflows

## Installation

```bash
pip install -r requirements.txt
```

## How to Run

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
- Live trading/execution is future scope and should be implemented with additional production-grade safeguards.
