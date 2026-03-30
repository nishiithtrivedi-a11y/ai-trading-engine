"""
Bullish Intraday Regime Strategy
=================================
Regime-aware intraday strategy designed to capture upside momentum in
bullish market conditions on NSE equities (NIFTY 50 universe).

Core logic
----------
1. **Trend alignment**: Close > VWAP > EMA-20, with EMA-20 > EMA-50
   confirming higher-timeframe bullish structure.
2. **Momentum filter**: RSI between configurable bounds (default 40-70)
   to enter during momentum expansions, not exhausted moves.
3. **Trend strength**: ADX above threshold confirms a trending regime
   and filters out choppy/sideways price action.
4. **Volume confirmation**: Current bar volume exceeds rolling average,
   confirming institutional participation.
5. **Pullback entry**: Price must have pulled back toward VWAP or EMA-20
   within ATR-based tolerance, buying the dip in a confirmed uptrend.
6. **Session filter**: Only trades during configurable IST market hours.

Safety guarantee
----------------
Signal-only implementation. Never places, routes, or submits real orders.
All outputs are advisory StrategySignal objects consumed by the backtesting
engine or paper-trading monitor only.

Design
------
Uses the C1 incremental API: ``precompute()`` vectorises all indicators on
the full dataset so ``on_bar()`` is a fast row lookup with no per-bar
pandas operations.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Optional

import numpy as np
import pandas as pd

from src.strategies.base_strategy import BaseStrategy, Signal, StrategySignal

TIMEZONE = "Asia/Kolkata"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class BullishIntradayConfig:
    """All configurable parameters for the bullish intraday regime strategy."""

    # Trend filters
    ema_fast_period: int = 20
    ema_slow_period: int = 50

    # Momentum filter (RSI)
    rsi_period: int = 14
    rsi_entry_low: float = 40.0   # min RSI for entry (avoid dead momentum)
    rsi_entry_high: float = 70.0  # max RSI for entry (avoid overbought)

    # Trend strength (ADX)
    adx_period: int = 14
    adx_threshold: float = 25.0   # min ADX for trending confirmation

    # Volume filter
    volume_ma_period: int = 20
    volume_multiplier: float = 1.2  # min volume vs MA ratio

    # Pullback tolerance (ATR-based)
    atr_period: int = 14
    pullback_atr_mult: float = 1.0  # price must be within N ATRs of VWAP/EMA

    # Session
    session_start: str = "09:20"
    session_end: str = "15:00"
    timezone: str = TIMEZONE
    min_bars_warmup: int = 50  # min bars before first signal

    # Choppy market filter
    atr_chop_period: int = 5
    atr_chop_baseline: int = 20
    chop_ratio_limit: float = 1.5  # ATR5/ATR20 above this = toxic volatility


# ---------------------------------------------------------------------------
# Indicator helpers
# ---------------------------------------------------------------------------

def _ensure_utc_index(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "timestamp" in out.columns and not isinstance(out.index, pd.DatetimeIndex):
        out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True, errors="coerce")
        out = out.set_index("timestamp")
    if out.index.tz is None:
        out.index = out.index.tz_localize("UTC")
    elif str(out.index.tz) != "UTC":
        out.index = out.index.tz_convert("UTC")
    return out.sort_index()


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False, min_periods=span).mean()


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def _wilder_atr(df: pd.DataFrame, period: int) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [df["high"] - df["low"],
         (df["high"] - prev_close).abs(),
         (df["low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def _adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    prev_high = high.shift(1)
    prev_low = low.shift(1)

    up_move = high - prev_high
    down_move = prev_low - low

    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0),
        index=df.index,
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0),
        index=df.index,
    )

    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)

    alpha = 1.0 / period
    smooth_tr = tr.ewm(alpha=alpha, adjust=False, min_periods=period).mean()
    smooth_plus = plus_dm.ewm(alpha=alpha, adjust=False, min_periods=period).mean()
    smooth_minus = minus_dm.ewm(alpha=alpha, adjust=False, min_periods=period).mean()

    plus_di = 100.0 * smooth_plus / smooth_tr.replace(0, np.nan)
    minus_di = 100.0 * smooth_minus / smooth_tr.replace(0, np.nan)

    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx_line = dx.ewm(alpha=alpha, adjust=False, min_periods=period).mean()
    return adx_line


def _intraday_vwap(df: pd.DataFrame, tz: str = TIMEZONE) -> pd.Series:
    local = df.index.tz_convert(tz)
    date_key = pd.Series(local.normalize(), index=df.index)
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    pv = tp * df["volume"]
    cum_pv = pv.groupby(date_key).cumsum()
    cum_vol = df["volume"].groupby(date_key).cumsum()
    return (cum_pv / cum_vol.replace(0, np.nan)).rename("vwap")


def _in_session(index: pd.DatetimeIndex, start: str, end: str, tz: str) -> pd.Series:
    local = index.tz_convert(tz)
    hhmm = pd.Series(local.strftime("%H:%M"), index=index)
    return (hhmm >= start) & (hhmm <= end)


# ---------------------------------------------------------------------------
# Precompute
# ---------------------------------------------------------------------------

def precompute_bullish(df: pd.DataFrame, cfg: BullishIntradayConfig) -> pd.DataFrame:
    """Vectorised computation of all indicators for the bullish strategy."""
    data = _ensure_utc_index(df)
    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(data.columns)
    if missing:
        raise ValueError(f"Bullish strategy precompute: missing columns {sorted(missing)}")

    data = data.copy()

    # Session filter
    data["in_session"] = _in_session(
        data.index, cfg.session_start, cfg.session_end, cfg.timezone,
    )

    # Trend indicators
    data["ema_fast"] = _ema(data["close"], cfg.ema_fast_period)
    data["ema_slow"] = _ema(data["close"], cfg.ema_slow_period)
    data["vwap"] = _intraday_vwap(data, cfg.timezone)

    # Momentum
    data["rsi"] = _rsi(data["close"], cfg.rsi_period)

    # Trend strength
    data["adx"] = _adx(data, cfg.adx_period)

    # Volume
    data["vol_ma"] = data["volume"].rolling(
        cfg.volume_ma_period, min_periods=cfg.volume_ma_period,
    ).mean()

    # ATR for pullback tolerance
    data["atr"] = _wilder_atr(data, cfg.atr_period)

    # Choppy market detection
    data["atr_fast"] = _wilder_atr(data, cfg.atr_chop_period)
    data["atr_baseline"] = _wilder_atr(data, cfg.atr_chop_baseline)
    data["chop_ratio"] = data["atr_fast"] / data["atr_baseline"].replace(0, np.nan)

    # --- Composite signals ---
    # Trend alignment: close > VWAP, close > EMA fast, EMA fast > EMA slow
    data["trend_aligned"] = (
        (data["close"] > data["vwap"])
        & (data["close"] > data["ema_fast"])
        & (data["ema_fast"] > data["ema_slow"])
    )

    # Momentum in range
    data["momentum_ok"] = (
        (data["rsi"] >= cfg.rsi_entry_low)
        & (data["rsi"] <= cfg.rsi_entry_high)
    )

    # ADX trending
    data["trending"] = data["adx"] >= cfg.adx_threshold

    # Volume confirmation
    data["vol_confirmed"] = (
        data["vol_ma"].notna()
        & (data["volume"] >= data["vol_ma"] * cfg.volume_multiplier)
    )

    # Pullback to VWAP or EMA — price within ATR tolerance of support
    pullback_zone = data["atr"] * cfg.pullback_atr_mult
    near_vwap = (data["close"] - data["vwap"]).abs() <= pullback_zone
    near_ema = (data["close"] - data["ema_fast"]).abs() <= pullback_zone
    data["pullback_ok"] = near_vwap | near_ema

    # Not choppy
    data["not_choppy"] = (
        data["chop_ratio"].isna()  # early bars
        | (data["chop_ratio"] <= cfg.chop_ratio_limit)
    )

    # Final bullish entry signal
    data["bull_entry"] = (
        data["in_session"]
        & data["trend_aligned"]
        & data["momentum_ok"]
        & data["trending"]
        & data["vol_confirmed"]
        & data["pullback_ok"]
        & data["not_choppy"]
    )

    # Exit signal: definitive trend reversal — close drops below EMA slow
    # AND RSI confirms weakness (oversold territory).
    # The engine's stop-loss/trailing-stop handles normal adverse moves;
    # this EXIT only fires on structural trend breakdown.
    data["bull_exit"] = (
        data["in_session"]
        & (data["close"] < data["ema_slow"])
        & (data["rsi"] < 35)
    )

    return data


# ---------------------------------------------------------------------------
# Strategy class
# ---------------------------------------------------------------------------

class BullishIntradayRegimeStrategy(BaseStrategy):
    """
    Regime-aware intraday bullish momentum strategy.

    Captures upside moves when trend, momentum, volume, and regime align.
    Uses C1 incremental API for efficient backtesting.
    """

    config: BullishIntradayConfig

    @property
    def name(self) -> str:
        cfg = getattr(self, "config", BullishIntradayConfig())
        return f"BullishIntradayRegime(EMA{cfg.ema_fast_period}/{cfg.ema_slow_period},ADX{cfg.adx_threshold})"

    def initialize(self, params: Optional[dict[str, object]] = None) -> None:
        super().initialize(params)

        defaults = asdict(BullishIntradayConfig())
        for key in defaults:
            if key in self._params:
                defaults[key] = self._params[key]

        self.config = BullishIntradayConfig(
            ema_fast_period=int(defaults["ema_fast_period"]),
            ema_slow_period=int(defaults["ema_slow_period"]),
            rsi_period=int(defaults["rsi_period"]),
            rsi_entry_low=float(defaults["rsi_entry_low"]),
            rsi_entry_high=float(defaults["rsi_entry_high"]),
            adx_period=int(defaults["adx_period"]),
            adx_threshold=float(defaults["adx_threshold"]),
            volume_ma_period=int(defaults["volume_ma_period"]),
            volume_multiplier=float(defaults["volume_multiplier"]),
            atr_period=int(defaults["atr_period"]),
            pullback_atr_mult=float(defaults["pullback_atr_mult"]),
            session_start=str(defaults["session_start"]),
            session_end=str(defaults["session_end"]),
            timezone=str(defaults["timezone"]),
            min_bars_warmup=int(defaults["min_bars_warmup"]),
            atr_chop_period=int(defaults["atr_chop_period"]),
            atr_chop_baseline=int(defaults["atr_chop_baseline"]),
            chop_ratio_limit=float(defaults["chop_ratio_limit"]),
        )

        if self.config.ema_fast_period >= self.config.ema_slow_period:
            raise ValueError("ema_fast_period must be less than ema_slow_period")
        if self.config.adx_threshold < 0:
            raise ValueError("adx_threshold must be non-negative")
        if self.config.rsi_entry_low >= self.config.rsi_entry_high:
            raise ValueError("rsi_entry_low must be less than rsi_entry_high")

    def precompute(
        self, full_data: pd.DataFrame, context: Optional[dict[str, Any]] = None,
    ) -> None:
        if not getattr(self, "_is_initialized", False):
            self.initialize()

        prepared = precompute_bullish(full_data, self.config)
        if context is not None:
            context["bullish_prepared"] = prepared

    def on_bar(
        self,
        current_bar: pd.Series,
        bar_index: int,
        context: Optional[dict[str, Any]] = None,
    ) -> Signal | StrategySignal:
        if not getattr(self, "_is_initialized", False):
            self.initialize()

        prepared = context.get("bullish_prepared") if context else None
        if prepared is None or bar_index >= len(prepared):
            return Signal.HOLD

        # Warmup period
        if bar_index < self.config.min_bars_warmup:
            return Signal.HOLD

        row = prepared.iloc[bar_index]

        # Check session
        if not bool(row.get("in_session", False)):
            return Signal.HOLD

        # Check for NaN in critical indicators
        critical = (row.get("ema_fast"), row.get("ema_slow"), row.get("vwap"),
                     row.get("rsi"), row.get("adx"), row.get("atr"))
        if any(pd.isna(v) for v in critical):
            return Signal.HOLD

        # Entry signal
        if bool(row.get("bull_entry", False)):
            return self.build_signal(
                action=Signal.BUY,
                current_bar=current_bar,
                confidence=self._compute_confidence(row),
                rationale="bullish_regime_momentum_entry",
                tags=("intraday", "bullish", "regime_aware", "momentum"),
                metadata={
                    "close": float(row["close"]),
                    "vwap": float(row["vwap"]),
                    "ema_fast": float(row["ema_fast"]),
                    "ema_slow": float(row["ema_slow"]),
                    "rsi": float(row["rsi"]),
                    "adx": float(row["adx"]),
                    "atr": float(row["atr"]),
                    "volume_ratio": (
                        float(row["volume"] / row["vol_ma"])
                        if row.get("vol_ma") and row["vol_ma"] > 0
                        else 0.0
                    ),
                },
            )

        # Exit signal — trend structure broken
        if bool(row.get("bull_exit", False)):
            return self.build_signal(
                action=Signal.EXIT,
                current_bar=current_bar,
                confidence=0.65,
                rationale="bullish_trend_break_exit",
                tags=("intraday", "bullish", "exit"),
                metadata={
                    "close": float(row["close"]),
                    "ema_slow": float(row["ema_slow"]),
                },
            )

        return Signal.HOLD

    def _compute_confidence(self, row: pd.Series) -> float:
        """Dynamic confidence based on signal confluence strength."""
        score = 0.5  # base

        # ADX strength bonus
        adx_val = float(row.get("adx", 0))
        if adx_val > 30:
            score += 0.10
        elif adx_val > 25:
            score += 0.05

        # RSI sweet spot bonus (50-60 is ideal momentum)
        rsi_val = float(row.get("rsi", 50))
        if 48 <= rsi_val <= 62:
            score += 0.10
        elif 40 <= rsi_val <= 70:
            score += 0.05

        # Volume surge bonus
        vol_ma = row.get("vol_ma")
        if vol_ma and vol_ma > 0:
            vol_ratio = float(row["volume"]) / float(vol_ma)
            if vol_ratio > 1.5:
                score += 0.10
            elif vol_ratio > 1.2:
                score += 0.05

        return min(score, 0.95)
