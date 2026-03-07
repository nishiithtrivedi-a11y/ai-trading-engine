# AI Trading Backtesting Engine

A modular, production-quality backtesting framework for trading strategies, built from scratch in Python.

## Project Structure

```
AI Trading/
├── src/
│   ├── core/
│   │   ├── backtest_engine.py   # Main simulation loop
│   │   ├── broker.py            # Order routing, sizing, risk exits
│   │   ├── data_handler.py      # OHLCV data loading and access
│   │   ├── execution.py         # Fill simulation (slippage, fees)
│   │   ├── metrics.py           # Performance metric computation
│   │   ├── order.py             # Order domain objects
│   │   ├── portfolio.py         # Cash, positions, equity tracking
│   │   ├── position.py          # Position and Trade objects
│   │   └── reporting.py         # Terminal output, plots, CSV/JSON export
│   ├── strategies/
│   │   ├── base_strategy.py     # Abstract strategy interface
│   │   ├── sma_crossover.py     # SMA crossover strategy
│   │   ├── rsi_reversion.py     # RSI mean reversion strategy
│   │   └── breakout.py          # Donchian breakout strategy
│   └── utils/
│       ├── config.py            # Pydantic configuration models
│       ├── logger.py            # Logging setup
│       └── validators.py        # OHLCV data validation
├── tests/                       # Unit tests (62 tests)
├── data/                        # Market data CSV files
├── output/                      # Reports, plots, trade logs
├── main.py                      # Entry point — runs all strategies
├── generate_sample_data.py      # Synthetic data generator
└── requirements.txt
```

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Generate sample data
python generate_sample_data.py

# Run backtests
python main.py

# Run tests
python -m pytest tests/ -v
```

## How It Works

The engine runs a bar-by-bar simulation loop:

1. **Load data** — CSV with timestamp, open, high, low, close, volume
2. **Initialize strategy** — pass configuration parameters
3. **For each bar:**
   - Check risk exits (stop-loss, take-profit, trailing stop)
   - Execute pending orders from previous bar (next-bar-open execution)
   - Strategy generates signal based only on data up to current bar
   - Submit new orders based on signal
   - Record portfolio state
4. **After last bar** — close open positions (configurable), compute metrics, generate report

## How to Add a New Strategy

Create a new file in `src/strategies/`:

```python
from src.strategies.base_strategy import BaseStrategy, Signal

class MyStrategy(BaseStrategy):

    @property
    def name(self) -> str:
        return "MyStrategy"

    def on_bar(self, data, current_bar, bar_index) -> Signal:
        # data: all bars up to current (no lookahead)
        # current_bar: current OHLCV as pd.Series
        # bar_index: 0-based position

        # Use built-in helpers:
        sma = self.sma(data["close"], period=20)
        rsi = self.rsi(data["close"], period=14)

        # Return Signal.BUY, Signal.SELL, Signal.EXIT, or Signal.HOLD
        return Signal.HOLD
```

Then use it in your runner:

```python
from src.core.backtest_engine import BacktestEngine
from src.core.data_handler import DataHandler
from src.utils.config import BacktestConfig
from src.strategies.my_strategy import MyStrategy

config = BacktestConfig(
    initial_capital=100_000,
    strategy_params={"my_param": 42},
)
engine = BacktestEngine(config, MyStrategy())
engine.run(DataHandler.from_csv("data/sample_data.csv"))
engine.generate_report()
```

## CSV Data Format

```csv
timestamp,open,high,low,close,volume
2020-01-01,100.0,102.5,99.5,101.0,1000000
2020-01-02,101.0,103.0,100.0,102.5,1200000
```

The engine auto-detects common timestamp column names (timestamp, datetime, date) and handles multiple datetime formats.

## Configuration

All settings are validated via Pydantic:

```python
BacktestConfig(
    initial_capital=100_000,      # Starting cash
    fee_rate=0.001,               # 0.1% per trade
    slippage_rate=0.0005,         # 0.05% slippage
    position_sizing="percent_of_equity",
    position_size_pct=0.95,       # Use 95% of equity per trade
    risk=RiskConfig(
        stop_loss_pct=0.05,       # 5% stop loss
        take_profit_pct=0.10,     # 10% take profit
        trailing_stop_pct=0.03,   # 3% trailing stop
        max_drawdown_kill_pct=0.25,  # Stop trading at 25% drawdown
    ),
    execution_mode="next_bar_open",  # or "same_bar_close"
    close_positions_at_end=True,
    trading_days_per_year=252,
    risk_free_rate=0.0,
)
```

## Metrics Computed

| Metric | Description |
|--------|-------------|
| Total Return | Absolute and percentage |
| Annualized Return / CAGR | Configurable trading days |
| Sharpe Ratio | Annualized, excess returns |
| Sortino Ratio | Downside-only volatility |
| Max Drawdown | Absolute and percentage |
| Win Rate | Winners / total trades |
| Profit Factor | Gross profit / gross loss |
| Expectancy | Average PnL per trade |
| Exposure | % of bars with open position |
| Buy-and-Hold benchmark | Automatic comparison |

## Anti-Bias Design

- **Lookahead bias**: Signals on bar t execute at bar t+1 open. Strategies only see `data[:current+1]`.
- **Gap risk**: Stop-losses fill at the open price when it gaps through the stop level.
- **Transaction costs**: Fees and slippage are always applied — no frictionless backtests.
- **Trailing stops**: Ratchet up only, never down.
- **Data validation**: Rejects duplicate timestamps, negative prices, high < low violations.

## Outputs

- Terminal summary report with strategy vs buy-and-hold comparison
- Equity curve plot (PNG)
- Drawdown plot (PNG)
- Trade log (CSV) with entry/exit timestamps, prices, PnL, fees, bars held, exit reason
- Metrics summary (JSON)

## Limitations

- Long-only (short-selling architecture is stubbed but not implemented)
- Single-asset per backtest
- Single active position at a time
- No partial fills (placeholder architecture only)
- Slippage is a fixed percentage, not volume-based
- No order book simulation
- Synthetic sample data — use real market data for meaningful results

## Version 2 Roadmap

- Multi-asset portfolio backtesting
- Short selling support
- Parameter sweep / grid search optimization
- Walk-forward analysis
- Monte Carlo resampling for robustness testing
- Volume-based slippage model
- Partial fill simulation
- Benchmark comparison against custom indices
- Paper trading adapter (broker API bridge)
- Live trading integration hooks
- Web dashboard for results visualization
