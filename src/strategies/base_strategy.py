"""
Base strategy interface for the backtesting engine.

All strategies must inherit from BaseStrategy and implement
the on_bar() method.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Optional

import pandas as pd

from src.utils.market_sessions import DEFAULT_TIMEZONE


class Signal(Enum):
    """Trading signals that strategies can emit."""
    BUY = "buy"
    SELL = "sell"
    EXIT = "exit"
    HOLD = "hold"


class BaseStrategy(ABC):
    """Abstract base class for trading strategies.

    Subclasses must implement:
        - on_bar(): Called each bar to generate a trading signal.

    Optionally override:
        - initialize(): Set up indicators and state.
        - name: Property for the strategy name.

    The strategy receives only data available up to the current bar,
    preventing lookahead bias by design.
    """

    def __init__(self, **kwargs: Any) -> None:
        self._params: dict[str, Any] = kwargs
        self._is_initialized: bool = False

    @property
    def name(self) -> str:
        """Human-readable strategy name."""
        return self.__class__.__name__

    def initialize(self, params: Optional[dict[str, Any]] = None) -> None:
        """Initialize the strategy with parameters.

        Called once before the backtest loop begins. Override this
        to set up indicators, state variables, etc.

        Args:
            params: Strategy-specific parameters from config.
        """
        if params:
            self._params.update(params)
        self._is_initialized = True

    def get_param(self, key: str, default: Any = None) -> Any:
        """Get a strategy parameter.

        Args:
            key: Parameter name.
            default: Default value if not set.

        Returns:
            Parameter value.
        """
        return self._params.get(key, default)

    @abstractmethod
    def on_bar(
        self,
        data: pd.DataFrame,
        current_bar: pd.Series,
        bar_index: int,
    ) -> Signal:
        """Process a new bar and generate a trading signal.

        This method is called once per bar during the backtest.
        The `data` parameter contains ONLY bars from the start up to
        and including the current bar — no future data.

        Args:
            data: All available historical data up to current bar.
                  Use data["close"].rolling(...) etc. for indicators.
            current_bar: The current bar's OHLCV data as a Series.
            bar_index: The index of the current bar (0-based).

        Returns:
            A Signal indicating the desired action.
        """
        ...

    @staticmethod
    def sma(series: pd.Series, period: int) -> pd.Series:
        """Simple Moving Average helper."""
        return series.rolling(window=period, min_periods=period).mean()

    @staticmethod
    def ema(series: pd.Series, period: int) -> pd.Series:
        """Exponential Moving Average helper."""
        return series.ewm(span=period, adjust=False, min_periods=period).mean()

    @staticmethod
    def rsi(series: pd.Series, period: int = 14) -> pd.Series:
        """Relative Strength Index helper."""
        delta = series.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)

        avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    @staticmethod
    def donchian_high(series: pd.Series, period: int) -> pd.Series:
        """Donchian Channel upper band (rolling high)."""
        return series.rolling(window=period, min_periods=period).max()

    @staticmethod
    def donchian_low(series: pd.Series, period: int) -> pd.Series:
        """Donchian Channel lower band (rolling low)."""
        return series.rolling(window=period, min_periods=period).min()

    @staticmethod
    def atr(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        period: int = 14,
    ) -> pd.Series:
        """Average True Range helper."""
        prev_close = close.shift(1)
        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()

        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return true_range.rolling(window=period, min_periods=period).mean()

    @staticmethod
    def crossover(fast: pd.Series, slow: pd.Series) -> pd.Series:
        """True where fast crosses above slow."""
        return (fast > slow) & (fast.shift(1) <= slow.shift(1))

    @staticmethod
    def crossunder(fast: pd.Series, slow: pd.Series) -> pd.Series:
        """True where fast crosses below slow."""
        return (fast < slow) & (fast.shift(1) >= slow.shift(1))

    @staticmethod
    def require_columns(data: pd.DataFrame, columns: list[str]) -> None:
        """Validate that required columns exist in the dataframe."""
        missing = [col for col in columns if col not in data.columns]
        if missing:
            raise ValueError(f"Missing required columns: {missing}")

    @staticmethod
    def vwap(
        data: pd.DataFrame,
        price_col: str = "close",
        volume_col: str = "volume",
        timestamp_col: str = "timestamp",
        timezone: str = DEFAULT_TIMEZONE,
        window: Optional[int] = None,
    ) -> pd.Series:
        """
        Intraday VWAP with daily session reset.

        Formula:
            cumulative(price * volume) / cumulative(volume)
        """
        required_cols = {price_col, volume_col, timestamp_col}
        missing = required_cols - set(data.columns)
        if missing:
            raise ValueError(f"Missing required columns for VWAP: {sorted(missing)}")

        df = data.copy()
        df[timestamp_col] = pd.to_datetime(df[timestamp_col])

        if getattr(df[timestamp_col].dt, "tz", None) is None:
            df[timestamp_col] = df[timestamp_col].dt.tz_localize(timezone)
        else:
            df[timestamp_col] = df[timestamp_col].dt.tz_convert(timezone)

        df["session_date"] = df[timestamp_col].dt.normalize()
        df["_pv"] = df[price_col].astype(float) * df[volume_col].astype(float)

        if window is None:
            cumulative_pv = df.groupby("session_date")["_pv"].cumsum()
            cumulative_volume = df.groupby("session_date")[volume_col].cumsum()
            vwap_series = cumulative_pv / cumulative_volume.replace(0, pd.NA)
        else:
            parts: list[pd.Series] = []

            for _, group in df.groupby("session_date", sort=False):
                rolling_pv = group["_pv"].rolling(window=window, min_periods=1).sum()
                rolling_vol = group[volume_col].rolling(window=window, min_periods=1).sum()
                group_vwap = rolling_pv / rolling_vol.replace(0, pd.NA)
                parts.append(group_vwap)

            vwap_series = pd.concat(parts).sort_index()

        return vwap_series.rename("vwap")

    @staticmethod
    def typical_price_vwap(
        data: pd.DataFrame,
        high_col: str = "high",
        low_col: str = "low",
        close_col: str = "close",
        volume_col: str = "volume",
        timestamp_col: str = "timestamp",
        timezone: str = DEFAULT_TIMEZONE,
        window: Optional[int] = None,
    ) -> pd.Series:
        """
        VWAP using typical price = (high + low + close) / 3.
        """
        required_cols = {high_col, low_col, close_col, volume_col, timestamp_col}
        missing = required_cols - set(data.columns)
        if missing:
            raise ValueError(
                f"Missing required columns for typical price VWAP: {sorted(missing)}"
            )

        df = data.copy()
        df["__typical_price"] = (
            df[high_col].astype(float)
            + df[low_col].astype(float)
            + df[close_col].astype(float)
        ) / 3.0

        return BaseStrategy.vwap(
            data=df,
            price_col="__typical_price",
            volume_col=volume_col,
            timestamp_col=timestamp_col,
            timezone=timezone,
            window=window,
        )