"""
Generate sample OHLCV data for testing the backtesting engine.

Creates a realistic-looking synthetic price series with trends,
mean reversion, and volatility clustering.
"""

import numpy as np
import pandas as pd


def generate_sample_ohlcv(
    start_date: str = "2020-01-01",
    num_bars: int = 1000,
    initial_price: float = 100.0,
    daily_volatility: float = 0.02,
    trend: float = 0.0003,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate synthetic OHLCV data.

    Uses geometric Brownian motion with added intraday ranges.

    Args:
        start_date: Start date for the data.
        num_bars: Number of bars to generate.
        initial_price: Starting price.
        daily_volatility: Daily return standard deviation.
        trend: Daily drift (positive = uptrend).
        seed: Random seed for reproducibility.

    Returns:
        DataFrame with timestamp, open, high, low, close, volume columns.
    """
    rng = np.random.default_rng(seed)

    # Generate daily returns with slight mean-reversion
    returns = rng.normal(trend, daily_volatility, num_bars)

    # Add some momentum / trending behavior
    for i in range(1, num_bars):
        returns[i] += 0.1 * returns[i - 1]  # Slight autocorrelation

    # Generate close prices
    close_prices = np.zeros(num_bars)
    close_prices[0] = initial_price
    for i in range(1, num_bars):
        close_prices[i] = close_prices[i - 1] * (1 + returns[i])

    # Generate OHLC from close prices
    open_prices = np.zeros(num_bars)
    high_prices = np.zeros(num_bars)
    low_prices = np.zeros(num_bars)

    open_prices[0] = initial_price
    for i in range(1, num_bars):
        # Open is close of previous bar with small gap
        gap = rng.normal(0, daily_volatility * 0.2)
        open_prices[i] = close_prices[i - 1] * (1 + gap)

    for i in range(num_bars):
        bar_range = abs(close_prices[i] - open_prices[i])
        extra_range = rng.exponential(daily_volatility * close_prices[i] * 0.5)

        high_prices[i] = max(open_prices[i], close_prices[i]) + extra_range
        low_prices[i] = min(open_prices[i], close_prices[i]) - extra_range
        low_prices[i] = max(low_prices[i], 0.01)  # Prevent negative prices

    # Generate volume with clustering
    base_volume = 1_000_000
    volume = rng.lognormal(
        mean=np.log(base_volume),
        sigma=0.5,
        size=num_bars,
    ).astype(int)

    # Higher volume on larger moves
    abs_returns = np.abs(returns)
    volume_multiplier = 1 + abs_returns / daily_volatility
    volume = (volume * volume_multiplier).astype(int)

    # Create date range (business days)
    dates = pd.bdate_range(start=start_date, periods=num_bars)

    df = pd.DataFrame({
        "timestamp": dates,
        "open": np.round(open_prices, 4),
        "high": np.round(high_prices, 4),
        "low": np.round(low_prices, 4),
        "close": np.round(close_prices, 4),
        "volume": volume,
    })

    return df


if __name__ == "__main__":
    df = generate_sample_ohlcv(
        start_date="2020-01-01",
        num_bars=1000,
        initial_price=100.0,
        daily_volatility=0.02,
        trend=0.0003,
        seed=42,
    )

    output_path = "data/sample_data.csv"
    df.to_csv(output_path, index=False)
    print(f"Generated {len(df)} bars of sample data")
    print(f"Date range: {df['timestamp'].iloc[0]} to {df['timestamp'].iloc[-1]}")
    print(f"Price range: {df['low'].min():.2f} to {df['high'].max():.2f}")
    print(f"Saved to {output_path}")
