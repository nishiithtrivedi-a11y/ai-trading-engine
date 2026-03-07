from __future__ import annotations

from pathlib import Path

from src.core.backtest_engine import BacktestEngine
from src.core.data_handler import DataHandler
from src.strategies.sma_crossover import SMACrossoverStrategy
from src.strategies.rsi_reversion import RSIReversionStrategy
from src.strategies.breakout import BreakoutStrategy
from src.utils.config import BacktestConfig, RiskConfig, PositionSizingMethod
from src.utils.logger import setup_logger
from src.data.nse_universe import NSEUniverseLoader

logger = setup_logger("main")


def run_sma_crossover(data_handler: DataHandler) -> dict:
    """Run the SMA Crossover strategy backtest."""
    config = BacktestConfig(
        initial_capital=100_000,
        fee_rate=0.001,
        slippage_rate=0.0005,
        position_sizing=PositionSizingMethod.PERCENT_OF_EQUITY,
        position_size_pct=0.95,
        intraday=True,
        force_square_off_at_close=True,
        allow_entries_only_during_market_hours=True,
        risk=RiskConfig(
            stop_loss_pct=0.05,
            trailing_stop_pct=0.03,
        ),
        strategy_params={
            "fast_period": 10,
            "slow_period": 30,
        },
        output_dir="output/sma_crossover_intraday",
        data_file="data/sample_data.csv",
    )

    strategy = SMACrossoverStrategy()
    engine = BacktestEngine(config, strategy)
    engine.run(data_handler)
    engine.generate_report(show_plots=False)
    return engine.get_results()


def run_rsi_reversion(data_handler: DataHandler) -> dict:
    """Run the RSI Mean Reversion strategy backtest."""
    config = BacktestConfig(
        initial_capital=100_000,
        fee_rate=0.001,
        slippage_rate=0.0005,
        position_sizing=PositionSizingMethod.PERCENT_OF_EQUITY,
        position_size_pct=0.95,
        intraday=True,
        force_square_off_at_close=True,
        allow_entries_only_during_market_hours=True,
        risk=RiskConfig(
            stop_loss_pct=0.04,
            take_profit_pct=0.06,
        ),
        strategy_params={
            "rsi_period": 14,
            "oversold": 30,
            "overbought": 70,
        },
        output_dir="output/rsi_reversion_intraday",
        data_file="data/sample_data.csv",
    )

    strategy = RSIReversionStrategy()
    engine = BacktestEngine(config, strategy)
    engine.run(data_handler)
    engine.generate_report(show_plots=False)
    return engine.get_results()


def run_breakout(data_handler: DataHandler) -> dict:
    """Run the Donchian Breakout strategy backtest."""
    config = BacktestConfig(
        initial_capital=100_000,
        fee_rate=0.001,
        slippage_rate=0.0005,
        position_sizing=PositionSizingMethod.PERCENT_OF_EQUITY,
        position_size_pct=0.95,
        intraday=True,
        force_square_off_at_close=True,
        allow_entries_only_during_market_hours=True,
        risk=RiskConfig(
            trailing_stop_pct=0.04,
        ),
        strategy_params={
            "entry_period": 20,
            "exit_period": 10,
        },
        output_dir="output/breakout_intraday",
        data_file="data/sample_data.csv",
    )

    strategy = BreakoutStrategy()
    engine = BacktestEngine(config, strategy)
    engine.run(data_handler)
    engine.generate_report(show_plots=False)
    return engine.get_results()


def show_available_universe() -> None:
    """Display sample symbols from built-in NSE universes."""
    loader = NSEUniverseLoader()

    nifty50 = loader.get_nifty50()
    banknifty = loader.get_banknifty_constituents()

    print("\n" + "=" * 80)
    print("NSE UNIVERSE LOADER")
    print("=" * 80)
    print(f"NIFTY 50 symbols loaded: {len(nifty50)}")
    print("Sample:", ", ".join(nifty50[:10]))
    print()
    print(f"BANK NIFTY constituents loaded: {len(banknifty)}")
    print("Sample:", ", ".join(banknifty[:10]))
    print("=" * 80 + "\n")


def compare_strategies(results: dict[str, dict]) -> None:
    """Print a comparison table of strategy results."""
    print("\n" + "=" * 80)
    print("STRATEGY COMPARISON")
    print("=" * 80)

    headers = ["Metric", *results.keys()]
    row_format = "{:<25}" + "{:>18}" * len(results)

    print(row_format.format(*headers))
    print("-" * 80)

    metric_keys = [
        ("Total Return", "total_return_pct", "{:.2%}"),
        ("Annualized Return", "annualized_return", "{:.2%}"),
        ("Sharpe Ratio", "sharpe_ratio", "{:.4f}"),
        ("Sortino Ratio", "sortino_ratio", "{:.4f}"),
        ("Max Drawdown", "max_drawdown_pct", "{:.2%}"),
        ("Win Rate", "win_rate", "{:.2%}"),
        ("Profit Factor", "profit_factor", "{:.4f}"),
        ("Num Trades", "num_trades", "{:d}"),
        ("Expectancy", "expectancy", "${:,.2f}"),
        ("Avg Bars Held", "avg_bars_held", "{:.1f}"),
        ("Exposure", "exposure_pct", "{:.2%}"),
        ("Total Fees", "total_fees", "${:,.2f}"),
    ]

    for label, key, fmt in metric_keys:
        values = []
        for _, res in results.items():
            metrics = res.get("metrics", {})
            value = metrics.get(key, 0)
            try:
                if fmt.startswith("${"):
                    values.append(fmt.format(value))
                elif "d" in fmt:
                    values.append(fmt.format(int(value)))
                else:
                    values.append(fmt.format(value))
            except (ValueError, TypeError, OverflowError):
                values.append(str(value))
        print(row_format.format(label, *values))

    print("=" * 80 + "\n")


def main() -> None:
    """Run all three strategies and compare results."""
    data_file = "data/sample_data.csv"

    if not Path(data_file).exists():
        logger.info("Sample data not found, generating...")
        from generate_sample_data import generate_sample_ohlcv

        df = generate_sample_ohlcv()
        Path("data").mkdir(exist_ok=True)
        df.to_csv(data_file, index=False)
        logger.info(f"Generated sample data: {len(df)} bars")

    data_handler = DataHandler.from_csv(data_file)

    print("\n" + "#" * 80)
    print("#  AI TRADING BACKTESTING ENGINE")
    print("#" * 80)

    show_available_universe()

    results: dict[str, dict] = {}

    print("\n>>> Running SMA Crossover Strategy...")
    results["SMA Crossover"] = run_sma_crossover(data_handler)

    print("\n>>> Running RSI Mean Reversion Strategy...")
    results["RSI Reversion"] = run_rsi_reversion(data_handler)

    print("\n>>> Running Breakout Strategy...")
    results["Breakout"] = run_breakout(data_handler)

    compare_strategies(results)

    print("Reports saved to output/ directory.")
    print("Done.\n")


if __name__ == "__main__":
    main()