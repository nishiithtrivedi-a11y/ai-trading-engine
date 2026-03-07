from pathlib import Path

from src.core.data_handler import DataHandler
from src.research.optimizer import StrategyOptimizer
from src.strategies.sma_crossover import SMACrossoverStrategy
from src.utils.config import BacktestConfig, PositionSizingMethod, RiskConfig

DATA_FILE = "data/sample_data.csv"


def main() -> None:
    if not Path(DATA_FILE).exists():
        raise FileNotFoundError(f"Missing data file: {DATA_FILE}")

    data_handler = DataHandler.from_csv(DATA_FILE)

    config = BacktestConfig(
        initial_capital=100_000,
        fee_rate=0.001,
        slippage_rate=0.0005,
        position_sizing=PositionSizingMethod.PERCENT_OF_EQUITY,
        position_size_pct=0.95,
        intraday=False,
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
        output_dir="output/sma_optimizer_backtests",
        data_file=DATA_FILE,
    )

    optimizer = StrategyOptimizer(
        base_config=config,
        strategy_class=SMACrossoverStrategy,
        param_grid={
            "fast_period": [5, 10, 15, 20],
            "slow_period": [30, 50, 100, 200],
        },
        output_dir="output/optimization/sma_crossover",
        sort_by="sharpe_ratio",
        ascending=False,
        top_n=10,
    )

    results_df = optimizer.run(data_handler)
    optimizer.print_summary(top_n=10)

    print("Best result:")
    print(optimizer.get_best_result())
    print(f"\nSaved {len(results_df)} optimization runs.")


if __name__ == "__main__":
    main()