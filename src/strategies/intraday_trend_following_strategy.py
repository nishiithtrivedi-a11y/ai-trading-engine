from __future__ import annotations

"""
Intraday Trend Following Strategy

Python port of the uploaded Pine Script strategy.

Core logic preserved:
- Session filter (default 09:30-15:00 Asia/Kolkata)
- VWAP filter
- SuperTrend direction filter
- EMA trend filter
- Fixed take-profit and stop-loss exits

Designed to work without broker APIs or UI.
You can test it with a local OHLCV CSV and/or plug it into your existing AI engine.

Expected CSV columns:
    timestamp, open, high, low, close, volume

Timestamp should be parseable by pandas.
"""

from dataclasses import asdict, dataclass
from typing import Optional, Tuple

import numpy as np
import pandas as pd

from src.strategies.base_strategy import BaseStrategy, Signal, StrategySignal


@dataclass
class StrategyConfig:
    st_period: int = 10
    st_factor: float = 3.0
    ema_length: int = 200
    tp_percent: float = 1.0
    sl_percent: float = 0.5
    session_start: str = "09:30"
    session_end: str = "15:00"
    timezone: str = "Asia/Kolkata"
    initial_capital: float = 100000.0
    position_size_pct: float = 0.10  # 10% of equity per trade


class IntradayTrendFollowingStrategy(BaseStrategy):
    """
    Engine-ready strategy wrapper for intraday trend-following signal generation.

    This class emits standardized StrategySignal outputs only; execution,
    position management, and portfolio sizing remain outside strategy scope.
    """

    config: StrategyConfig

    @property
    def name(self) -> str:
        return "IntradayTrendFollowingStrategy"

    def initialize(self, params: Optional[dict[str, object]] = None) -> None:
        super().initialize(params)

        config_values = asdict(StrategyConfig())
        for key in config_values:
            if key in self._params:
                config_values[key] = self._params[key]

        self.config = StrategyConfig(
            st_period=int(config_values["st_period"]),
            st_factor=float(config_values["st_factor"]),
            ema_length=int(config_values["ema_length"]),
            tp_percent=float(config_values["tp_percent"]),
            sl_percent=float(config_values["sl_percent"]),
            session_start=str(config_values["session_start"]),
            session_end=str(config_values["session_end"]),
            timezone=str(config_values["timezone"]),
            initial_capital=float(config_values["initial_capital"]),
            position_size_pct=float(config_values["position_size_pct"]),
        )

        if self.config.st_period <= 0:
            raise ValueError("st_period must be positive")
        if self.config.ema_length <= 0:
            raise ValueError("ema_length must be positive")
        if self.config.st_factor <= 0:
            raise ValueError("st_factor must be positive")

        # Reset precomputed cache on re-initialization
        self._prepared_full: Optional[pd.DataFrame] = None

    def precompute(self, full_data: pd.DataFrame) -> None:
        """Pre-compute all indicator columns on the full dataset.

        Called once by the engine before the backtest loop begins.
        Stores the prepared dataframe for fast per-bar lookups in
        generate_signal().  Invalidated on re-initialization.
        """
        if not getattr(self, "_is_initialized", False):
            self.initialize()
        prepared = prepare_strategy_dataframe(full_data, self.config)
        self._prepared_full = prepared

    def generate_signal(
        self,
        data: pd.DataFrame,
        current_bar: pd.Series,
        bar_index: int,
        *,
        symbol: Optional[str] = None,
        timeframe: Optional[str] = None,
    ) -> StrategySignal:
        if not getattr(self, "_is_initialized", False):
            self.initialize()

        # --- A1: Use precomputed data when available ---
        prepared_full = getattr(self, "_prepared_full", None)
        if prepared_full is not None and 0 <= bar_index < len(prepared_full):
            # Fast path: read current bar from precomputed frame
            latest = prepared_full.iloc[bar_index]
        else:
            # Legacy fallback: recompute from scratch (live mode, tests, etc.)
            prepared = prepare_strategy_dataframe(data, self.config)
            if prepared.empty:
                return self.build_signal(
                    action=Signal.HOLD,
                    current_bar=current_bar,
                    symbol=symbol,
                    timeframe=timeframe,
                    confidence=0.0,
                    rationale="no_data",
                )
            latest = prepared.iloc[-1]

        in_session_now = bool(latest["is_in_session"])

        if not in_session_now:
            return self.build_signal(
                action=Signal.HOLD,
                current_bar=current_bar,
                symbol=symbol,
                timeframe=timeframe,
                confidence=0.0,
                rationale="outside_trading_session",
                metadata={"is_in_session": False},
            )

        indicator_values = (
            latest.get("vwap"),
            latest.get("ema"),
            latest.get("direction"),
        )
        if any(pd.isna(value) for value in indicator_values):
            return self.build_signal(
                action=Signal.HOLD,
                current_bar=current_bar,
                symbol=symbol,
                timeframe=timeframe,
                confidence=0.0,
                rationale="indicator_warmup",
                metadata={"is_in_session": True},
            )

        long_signal = bool(latest["long_signal"])
        short_signal = bool(latest["short_signal"])

        action = Signal.HOLD
        rationale = "no_intraday_setup"
        if long_signal and not short_signal:
            action = Signal.BUY
            rationale = "long_trend_setup"
        elif short_signal and not long_signal:
            action = Signal.SELL
            rationale = "short_trend_setup"

        confidence = 0.0 if action == Signal.HOLD else 0.75
        return self.build_signal(
            action=action,
            current_bar=current_bar,
            symbol=symbol,
            timeframe=timeframe,
            confidence=confidence,
            rationale=rationale,
            tags=("intraday", "trend_following"),
            metadata={
                "is_in_session": in_session_now,
                "close": float(latest["close"]),
                "vwap": float(latest["vwap"]),
                "ema": float(latest["ema"]),
                "direction": int(latest["direction"]),
                "long_signal": long_signal,
                "short_signal": short_signal,
            },
        )

    def on_bar(
        self,
        data: pd.DataFrame,
        current_bar: pd.Series,
        bar_index: int,
    ) -> Signal:
        return self.generate_signal(
            data=data,
            current_bar=current_bar,
            bar_index=bar_index,
        ).action


def _ensure_datetime_index(df: pd.DataFrame, timestamp_col: str = "timestamp") -> pd.DataFrame:
    out = df.copy()
    if not isinstance(out.index, pd.DatetimeIndex):
        if timestamp_col not in out.columns:
            raise ValueError(
                "DataFrame must either have a DatetimeIndex or a 'timestamp' column."
            )
        out[timestamp_col] = pd.to_datetime(out[timestamp_col], utc=True, errors="coerce")
        if out[timestamp_col].isna().any():
            raise ValueError("Some timestamps could not be parsed.")
        out = out.set_index(timestamp_col)

    if out.index.tz is None:
        out.index = out.index.tz_localize("UTC")

    return out.sort_index()


def _true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - prev_close).abs()
    tr3 = (df["low"] - prev_close).abs()
    return pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)


def atr(df: pd.DataFrame, period: int) -> pd.Series:
    tr = _true_range(df)
    # Wilder's smoothing approximation
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False, min_periods=length).mean()


def intraday_vwap(df: pd.DataFrame, timezone: str = "Asia/Kolkata") -> pd.Series:
    local_index = df.index.tz_convert(timezone)
    day_key = pd.Series(local_index.date, index=df.index)
    typical_price = (df["high"] + df["low"] + df["close"]) / 3.0
    pv = typical_price * df["volume"]
    cum_pv = pv.groupby(day_key).cumsum()
    cum_vol = df["volume"].groupby(day_key).cumsum()
    return cum_pv / cum_vol.replace(0, np.nan)


def supertrend_legacy(
    df: pd.DataFrame, period: int = 10, factor: float = 3.0
) -> Tuple[pd.Series, pd.Series]:
    """
    Original pandas/.iloc implementation — preserved for validation testing.

    Returns:
        supertrend_line, direction

    direction convention:
    -1 => bullish, +1 => bearish
    """
    a = atr(df, period)
    hl2 = (df["high"] + df["low"]) / 2.0
    upperband = hl2 + factor * a
    lowerband = hl2 - factor * a

    final_upper = upperband.copy()
    final_lower = lowerband.copy()

    for i in range(1, len(df)):
        prev_close = df["close"].iloc[i - 1]

        if pd.isna(final_upper.iloc[i - 1]):
            final_upper.iloc[i] = upperband.iloc[i]
        elif (upperband.iloc[i] < final_upper.iloc[i - 1]) or (prev_close > final_upper.iloc[i - 1]):
            final_upper.iloc[i] = upperband.iloc[i]
        else:
            final_upper.iloc[i] = final_upper.iloc[i - 1]

        if pd.isna(final_lower.iloc[i - 1]):
            final_lower.iloc[i] = lowerband.iloc[i]
        elif (lowerband.iloc[i] > final_lower.iloc[i - 1]) or (prev_close < final_lower.iloc[i - 1]):
            final_lower.iloc[i] = lowerband.iloc[i]
        else:
            final_lower.iloc[i] = final_lower.iloc[i - 1]

    st = pd.Series(index=df.index, dtype="float64")
    direction = pd.Series(index=df.index, dtype="int64")

    for i in range(len(df)):
        if i == 0 or pd.isna(a.iloc[i]):
            st.iloc[i] = np.nan
            direction.iloc[i] = 1
            continue

        prev_st = st.iloc[i - 1]
        prev_final_upper = final_upper.iloc[i - 1]
        prev_final_lower = final_lower.iloc[i - 1]
        close_i = df["close"].iloc[i]

        if pd.isna(prev_st):
            if close_i <= final_upper.iloc[i]:
                st.iloc[i] = final_upper.iloc[i]
                direction.iloc[i] = 1
            else:
                st.iloc[i] = final_lower.iloc[i]
                direction.iloc[i] = -1
            continue

        if np.isclose(prev_st, prev_final_upper, equal_nan=False):
            if close_i <= final_upper.iloc[i]:
                st.iloc[i] = final_upper.iloc[i]
                direction.iloc[i] = 1
            else:
                st.iloc[i] = final_lower.iloc[i]
                direction.iloc[i] = -1
        else:
            if close_i >= final_lower.iloc[i]:
                st.iloc[i] = final_lower.iloc[i]
                direction.iloc[i] = -1
            else:
                st.iloc[i] = final_upper.iloc[i]
                direction.iloc[i] = 1

    return st, direction


def supertrend(
    df: pd.DataFrame, period: int = 10, factor: float = 3.0
) -> Tuple[pd.Series, pd.Series]:
    """
    Optimised SuperTrend using numpy arrays instead of pandas .iloc loops.

    Same logic as supertrend_legacy(), but ~50-100x faster per element
    because plain array indexing replaces pandas scalar access.

    Returns:
        supertrend_line, direction

    direction convention:
    -1 => bullish, +1 => bearish
    """
    n = len(df)
    a = atr(df, period)
    hl2 = (df["high"] + df["low"]) / 2.0
    upperband_s = hl2 + factor * a
    lowerband_s = hl2 - factor * a

    # Extract to numpy for fast scalar access
    close_arr = df["close"].to_numpy(dtype=np.float64)
    atr_arr = a.to_numpy(dtype=np.float64)
    upper_arr = upperband_s.to_numpy(dtype=np.float64)
    lower_arr = lowerband_s.to_numpy(dtype=np.float64)

    fu = upper_arr.copy()  # final_upper
    fl = lower_arr.copy()  # final_lower

    # --- Loop 1: compute final_upper and final_lower ---
    for i in range(1, n):
        prev_close = close_arr[i - 1]

        # BUG 1 FIX preserved: seed from current band when previous is NaN
        fu_prev = fu[i - 1]
        if np.isnan(fu_prev):
            fu[i] = upper_arr[i]
        elif upper_arr[i] < fu_prev or prev_close > fu_prev:
            fu[i] = upper_arr[i]
        else:
            fu[i] = fu_prev

        fl_prev = fl[i - 1]
        if np.isnan(fl_prev):
            fl[i] = lower_arr[i]
        elif lower_arr[i] > fl_prev or prev_close < fl_prev:
            fl[i] = lower_arr[i]
        else:
            fl[i] = fl_prev

    # --- Loop 2: compute SuperTrend line and direction ---
    st_arr = np.empty(n, dtype=np.float64)
    dir_arr = np.empty(n, dtype=np.int64)

    for i in range(n):
        if i == 0 or np.isnan(atr_arr[i]):
            st_arr[i] = np.nan
            dir_arr[i] = 1
            continue

        prev_st = st_arr[i - 1]
        c = close_arr[i]

        if np.isnan(prev_st):
            if c <= fu[i]:
                st_arr[i] = fu[i]
                dir_arr[i] = 1
            else:
                st_arr[i] = fl[i]
                dir_arr[i] = -1
            continue

        if np.isclose(prev_st, fu[i - 1]):
            if c <= fu[i]:
                st_arr[i] = fu[i]
                dir_arr[i] = 1
            else:
                st_arr[i] = fl[i]
                dir_arr[i] = -1
        else:
            if c >= fl[i]:
                st_arr[i] = fl[i]
                dir_arr[i] = -1
            else:
                st_arr[i] = fu[i]
                dir_arr[i] = 1

    st_series = pd.Series(st_arr, index=df.index, dtype="float64")
    dir_series = pd.Series(dir_arr, index=df.index, dtype="int64")
    return st_series, dir_series


def in_session(index: pd.DatetimeIndex, start: str, end: str, timezone: str) -> pd.Series:
    local = index.tz_convert(timezone)
    hhmm = local.strftime("%H:%M")
    return pd.Series((hhmm >= start) & (hhmm <= end), index=index)


def prepare_strategy_dataframe(
    df: pd.DataFrame, config: Optional[StrategyConfig] = None
) -> pd.DataFrame:
    config = config or StrategyConfig()
    data = _ensure_datetime_index(df)

    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(data.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    data = data.copy()
    data["is_in_session"] = in_session(
        data.index, config.session_start, config.session_end, config.timezone
    )
    data["vwap"] = intraday_vwap(data, timezone=config.timezone)
    data["supertrend"], data["direction"] = supertrend(
        data, period=config.st_period, factor=config.st_factor
    )
    data["ema"] = ema(data["close"], config.ema_length)

    data["long_signal"] = (
        data["is_in_session"]
        & (data["close"] > data["vwap"])
        & (data["direction"] < 0)
        & (data["close"] > data["ema"])
    )
    data["short_signal"] = (
        data["is_in_session"]
        & (data["close"] < data["vwap"])
        & (data["direction"] > 0)
        & (data["close"] < data["ema"])
    )
    return data


def backtest_strategy(
    df: pd.DataFrame, config: Optional[StrategyConfig] = None
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    config = config or StrategyConfig()
    data = prepare_strategy_dataframe(df, config)

    equity = config.initial_capital
    current_position = 0  # 1 = long, -1 = short, 0 = flat
    entry_price = None
    entry_time = None
    position_units = 0.0

    trades = []
    equity_curve = []

    for ts, row in data.iterrows():
        close_px = float(row["close"])
        high_px = float(row["high"])
        low_px = float(row["low"])

        # Exit logic first
        if current_position == 1 and entry_price is not None:
            tp = entry_price * (1 + config.tp_percent / 100)
            sl = entry_price * (1 - config.sl_percent / 100)
            exit_reason = None
            exit_price = None

            if low_px <= sl:
                exit_price = sl
                exit_reason = "stop_loss"
            elif high_px >= tp:
                exit_price = tp
                exit_reason = "take_profit"

            if exit_reason is not None:
                pnl = (exit_price - entry_price) * position_units
                equity += pnl
                trades.append(
                    {
                        "entry_time": entry_time,
                        "exit_time": ts,
                        "side": "long",
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "units": position_units,
                        "pnl": pnl,
                        "exit_reason": exit_reason,
                    }
                )
                current_position = 0
                entry_price = None
                entry_time = None
                position_units = 0.0

        elif current_position == -1 and entry_price is not None:
            tp = entry_price * (1 - config.tp_percent / 100)
            sl = entry_price * (1 + config.sl_percent / 100)
            exit_reason = None
            exit_price = None

            if high_px >= sl:
                exit_price = sl
                exit_reason = "stop_loss"
            elif low_px <= tp:
                exit_price = tp
                exit_reason = "take_profit"

            if exit_reason is not None:
                pnl = (entry_price - exit_price) * position_units
                equity += pnl
                trades.append(
                    {
                        "entry_time": entry_time,
                        "exit_time": ts,
                        "side": "short",
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "units": position_units,
                        "pnl": pnl,
                        "exit_reason": exit_reason,
                    }
                )
                current_position = 0
                entry_price = None
                entry_time = None
                position_units = 0.0

        # BUG 2 FIX: session-end force close (intraday – must be flat before midnight IST).
        # Runs after TP/SL checks; only fires when position is still open at session end.
        session_end_reached = False
        if current_position != 0 and entry_price is not None:
            ts_ist = ts.tz_convert(config.timezone)
            if ts_ist.strftime("%H:%M") >= config.session_end:
                exit_px = close_px
                if current_position == 1:
                    pnl = (exit_px - entry_price) * position_units
                    side = "long"
                else:
                    pnl = (entry_price - exit_px) * position_units
                    side = "short"
                equity += pnl
                trades.append(
                    {
                        "entry_time": entry_time,
                        "exit_time": ts,
                        "side": side,
                        "entry_price": entry_price,
                        "exit_price": exit_px,
                        "units": position_units,
                        "pnl": pnl,
                        "exit_reason": "session_end",
                    }
                )
                current_position = 0
                entry_price = None
                entry_time = None
                position_units = 0.0
                session_end_reached = True

        # Entry logic after exits (skip if session just ended to avoid re-entry)
        if current_position == 0 and not session_end_reached:
            if bool(row["long_signal"]):
                current_position = 1
                entry_price = close_px
                entry_time = ts
                position_value = equity * config.position_size_pct
                position_units = position_value / close_px if close_px > 0 else 0.0
            elif bool(row["short_signal"]):
                current_position = -1
                entry_price = close_px
                entry_time = ts
                position_value = equity * config.position_size_pct
                position_units = position_value / close_px if close_px > 0 else 0.0

        # Mark-to-market equity curve
        unrealized = 0.0
        if current_position == 1 and entry_price is not None:
            unrealized = (close_px - entry_price) * position_units
        elif current_position == -1 and entry_price is not None:
            unrealized = (entry_price - close_px) * position_units

        equity_curve.append(
            {
                "timestamp": ts,
                "equity": equity + unrealized,
                "position": current_position,
                "close": close_px,
            }
        )

    trades_df = pd.DataFrame(trades)
    equity_df = pd.DataFrame(equity_curve).set_index("timestamp")

    net_profit = equity - config.initial_capital
    total_trades = int(len(trades_df))
    wins = int((trades_df["pnl"] > 0).sum()) if total_trades else 0
    losses = int((trades_df["pnl"] <= 0).sum()) if total_trades else 0
    win_rate = (wins / total_trades * 100.0) if total_trades else 0.0

    if not equity_df.empty:
        roll_max = equity_df["equity"].cummax()
        drawdown = equity_df["equity"] / roll_max - 1.0
        max_drawdown_pct = float(drawdown.min() * 100)
    else:
        max_drawdown_pct = 0.0

    summary = {
        "initial_capital": config.initial_capital,
        "final_equity": float(equity),
        "net_profit": float(net_profit),
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "win_rate_pct": float(win_rate),
        "max_drawdown_pct": max_drawdown_pct,
    }

    return data, trades_df, summary


def load_ohlcv_csv(path: str) -> pd.DataFrame:
    return pd.read_csv(path)


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Backtest the intraday trend following strategy.")
    parser.add_argument("csv_path", help="Path to OHLCV CSV with timestamp/open/high/low/close/volume")
    parser.add_argument("--timezone", default="Asia/Kolkata")
    parser.add_argument("--session-start", default="09:30")
    parser.add_argument("--session-end", default="15:00")
    parser.add_argument("--st-period", type=int, default=10)
    parser.add_argument("--st-factor", type=float, default=3.0)
    parser.add_argument("--ema-length", type=int, default=200)
    parser.add_argument("--tp-percent", type=float, default=1.0)
    parser.add_argument("--sl-percent", type=float, default=0.5)
    args = parser.parse_args()

    cfg = StrategyConfig(
        timezone=args.timezone,
        session_start=args.session_start,
        session_end=args.session_end,
        st_period=args.st_period,
        st_factor=args.st_factor,
        ema_length=args.ema_length,
        tp_percent=args.tp_percent,
        sl_percent=args.sl_percent,
    )

    df = load_ohlcv_csv(args.csv_path)
    _, trades_df, summary = backtest_strategy(df, cfg)

    print(json.dumps(summary, indent=2, default=str))
    if not trades_df.empty:
        print("\nLast 10 trades:")
        print(trades_df.tail(10).to_string(index=False))
    else:
        print("\nNo trades generated.")
