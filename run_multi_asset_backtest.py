from pathlib import Path

from src.core.data_handler import DataHandler
from src.data.nse_universe import NSEUniverseLoader
from src.research.multi_asset_backtester import (
    AllocationMethod,
    MultiAssetBacktester,
)
from src.strategies.sma_crossover import SMACrossoverStrategy
from src.utils.config import BacktestConfig, PositionSizingMethod, RiskConfig


def load_symbol_data(symbols: list[str], timeframe_suffix: str = "1D") -> dict[str, DataHandler]:
    """
    Load symbol CSVs from the data directory.

    Expected filenames:
    data/RELIANCE_1D.csv
    data/TCS_1D.csv
    data/INFY_1D.csv
    """
    symbol_to_data = {}

    for symbol in symbols:
        clean_symbol = symbol.replace(".NS", "")
        file_path = Path("data") / f"{clean_symbol}_{timeframe_suffix}.csv"

        if file_path.exists():
            symbol_to_data[symbol] = DataHandler.from_csv(str(file_path))
        else:
            print(f"Skipping {symbol}: missing file {file_path}")

    return symbol_to_data


def main() -> None:
    loader = NSEUniverseLoader()

    # Start small for first run
    symbols = loader.get_custom_universe("data/universe/custom_universe.csv")[:5]

    symbol_to_data = load_symbol_data(symbols, timeframe_suffix="1D")

    if not symbol_to_data:
        raise FileNotFoundError(
            "No symbol data files found. Add files like data/RELIANCE_1D.csv"
        )

    config = BacktestConfig(
        initial_capital=100_000,
        fee_rate=0.001,
        slippage_rate=0.0005,
        position_sizing=PositionSizingMethod.PERCENT_OF_EQUITY,
        position_size_pct=0.95,
        intraday=False,
        risk=RiskConfig(
            stop_loss_pct=0.05,
            trailing_stop_pct=0.03,
        ),
        strategy_params={
            "fast_period": 10,
            "slow_period": 30,
        },
        output_dir="output/multi_asset_single_runs",
        data_file="data/sample_data.csv",
    )

    backtester = MultiAssetBacktester(
        base_config=config,
        strategy_class=SMACrossoverStrategy,
        symbol_to_data=symbol_to_data,
        allocation_method=AllocationMethod.EQUAL_WEIGHT,
        output_dir="output/multi_asset_portfolio",
    )

    backtester.run()
    backtester.print_summary()


if __name__ == "__main__":
    main()