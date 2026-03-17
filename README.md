# AI Trading Engine

A modular Python AI trading research platform for backtesting, strategy evaluation, paper trading simulation, and live-safe signal generation.

This repository does **not** perform live broker order execution.

## Project Overview

The platform currently supports:

- Historical backtesting and strategy research
- Walk-forward validation and Monte Carlo robustness testing
- Portfolio-level research and relative-strength analysis
- Scanner + decision pipeline for ranked opportunities and picks
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

| Provider | Historical Data | Live Quotes | Status |
| --- | --- | --- | --- |
| CSV | yes | simulated reload | stable |
| Zerodha | partial | partial | provider + broker integration paths, execution disabled |
| Upstox | partial | partial (safe fallback) | safe data-only partial integration |

Provider details: [`docs/PROVIDERS.md`](docs/PROVIDERS.md)

Code-level provider capability registry: `src/data/provider_capabilities.py`

## Instrument Support Matrix

| Instrument | Status | Notes |
| --- | --- | --- |
| Equities | supported | primary workflow target |
| Equity indices | supported via symbols | benchmark/regime use cases |
| Futures | not implemented | contract/expiry workflow missing |
| Options | not implemented | strike/expiry/greeks workflow missing |
| Commodities | not implemented | dedicated data + contract model not implemented |
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

Safety details: [`docs/SAFETY.md`](docs/SAFETY.md)

## Quickstart

Install dependencies:

```bash
pip install -r requirements.txt
```

Run one command per mode:

- Research: `python scripts/run_nifty50_zerodha_research.py --symbols-limit 5 --regime-analysis --build-regime-policy`
- Paper trading: `python scripts/run_paper_trading.py --paper-trading --provider indian_csv --symbols RELIANCE.NS TCS.NS INFY.NS --interval day --paper-output-dir output/paper_trading_run --paper-max-orders 10`
- Live-safe signals: `python scripts/run_live_signal_pipeline.py --live-signals --provider indian_csv --symbols RELIANCE.NS TCS.NS INFY.NS --interval day --run-once --output-dir output/live_signals_run`
- Decision + portfolio plan: `python scripts/run_decision.py --provider indian_csv --symbols RELIANCE.NS TCS.NS INFY.NS --interval day --profile eod --output-dir output/decision_run`

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

## Testing

Run all tests:

```bash
python -m pytest tests -q
```

## Git Workflow for AI Tools

Follow [`AI_AGENT_WORKFLOW.md`](AI_AGENT_WORKFLOW.md):

- Branches: `claude/*` and `codex/*`
- Commits: `claude:` and `codex:` prefixes
- Never push directly to `main`
- Use PR-based merge flow
