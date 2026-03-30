"""
Bearish Intraday Regime Strategy
=================================
Regime-aware intraday strategy designed to profit in bearish market
conditions on NSE equities (NIFTY 50 universe).

Since the backtesting engine is long-only (no short selling), this strategy
captures **oversold bounce / mean-reversion** opportunities that arise
during bearish regimes. When a stock is under bearish pressure and reaches
an oversold extreme, it buys the snap-back rally for a quick intraday gain.

This is complementary to the bullish strategy:
- Bullish strategy: rides momentum in uptrends (trend-following)
- Bearish strategy: captures bounce plays in downtrends (mean-reversion)

Core logic
----------
1. **Bearish regime context**: EMA-20 < EMA-50 confirming macro downtrend.
2. **Oversold condition**: RSI drops below configurable threshold (default 30),
   indicating selling exhaustion.
3. **VWAP distance**: Price well below VWAP (>= N ATRs), indicating an
   extreme intraday deviation ripe for mean-reversion.
4. **Volume climax**: Volume spike relative to average — capitulation
   selling that often precedes bounces.
5. **Bullish candle confirmation**: Current bar closes green (close > open),
   suggesting sellers are losing control.
6. **Session filter**: Only trades during configurable IST market hours,
   avoiding the last 30 minutes to limit end-of-day risk.

Exit
----
- Strategy EXIT when price returns to VWAP (mean-reversion target reached)
- Engine handles stop-loss / trailing-stop for adverse moves

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
class BearishIntradayConfig:
    """All configurable parameters for the bearish intraday regime strategy."""

    # Trend filters (bearish regime confirmation)
    ema_fast_period: int = 20
    ema_slow_period: int = 50

    # Oversold threshold (RSI)
    rsi_period: int = 14
    rsi_oversold: float = 30.0     # RSI must drop below this for entry
    rsi_recovery: float = 45.0     # RSI rising back above this confirms bounce

    # Volume spike filter
    volume_ma_period: int = 20
    volume_spike_mult: float = 1.3  # volume must exceed MA by this factor

    # VWAP distance filter (ATR-based)
    atr_period: int = 14
    vwap_distance_atr: float = 0.5  # price must be >= N ATRs below VWAP

    # Bullish candle confirmation
    require_green_candle: bool = True

    # Session
    session_start: str = "09:20"
    session_end: str = "14:30"  # avoid last 45 min for bounce plays
    timezone: str = TIMEZONE
    min_bars_warmup: int = 50  # min bars before first signal

    # Choppy market filter
    atr_chop_period: int = 5
    atr_chop_baseline: int = 20
    chop_ratio_limit: float = 1.8  # higher tolerance — bounces happen in volatile markets


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

def precompute_bearish(df: pd.DataFrame, cfg: BearishIntradayConfig) -> pd.DataFrame:
    """Vectorised computation of all indicators for the bearish bounce strategy."""
    data = _ensure_utc_index(df)
    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(data.columns)
    if missing:
        raise ValueError(f"Bearish strategy precompute: missing columns {sorted(missing)}")

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

    # Volume
    data["vol_ma"] = data["volume"].rolling(
        cfg.volume_ma_period, min_periods=cfg.volume_ma_period,
    ).mean()

    # ATR
    data["atr"] = _wilder_atr(data, cfg.atr_period)

    # Choppy market detection
    data["atr_fast"] = _wilder_atr(data, cfg.atr_chop_period)
    data["atr_baseline"] = _wilder_atr(data, cfg.atr_chop_baseline)
    data["chop_ratio"] = data["atr_fast"] / data["atr_baseline"].replace(0, np.nan)

    # --- Composite signals ---

    # Bearish macro regime: EMA fast < EMA slow (downtrend)
    data["bearish_regime"] = data["ema_fast"] < data["ema_slow"]

    # Oversold: RSI below threshold (or was below recently — within 3 bars)
    rsi_below = data["rsi"] <= cfg.rsi_oversold
    data["oversold"] = (
        rsi_below
        | rsi_below.shift(1, fill_value=False)
        | rsi_below.shift(2, fill_value=False)
    )

    # VWAP distance: price below VWAP by at least N ATRs
    vwap_dist = data["vwap"] - data["close"]
    data["below_vwap"] = vwap_dist >= (data["atr"] * cfg.vwap_distance_atr)

    # Volume spike
    data["vol_spike"] = (
        data["vol_ma"].notna()
        & (data["volume"] >= data["vol_ma"] * cfg.volume_spike_mult)
    )

    # Bullish candle (bounce confirmation)
    data["green_candle"] = data["close"] > data["open"] if cfg.require_green_candle else True

    # Not excessively choppy
    data["not_choppy"] = (
        data["chop_ratio"].isna()
        | (data["chop_ratio"] <= cfg.chop_ratio_limit)
    )

    # Final bounce entry signal: BUY the oversold bounce in bearish regime
    data["bear_bounce_entry"] = (
        data["in_session"]
        & data["bearish_regime"]
        & data["oversold"]
        & data["below_vwap"]
        & data["vol_spike"]
        & data["green_candle"]
        & data["not_choppy"]
    )

    # Exit signal: price returns to VWAP (mean-reversion target)
    data["bear_bounce_exit"] = (
        data["in_session"]
        & (data["close"] >= data["vwap"])
        & data["bearish_regime"]  # only relevant in bearish context
    )

    return data


# ---------------------------------------------------------------------------
# Strategy class
# ---------------------------------------------------------------------------

class BearishIntradayRegimeStrategy(BaseStrategy):
    """
    Regime-aware intraday bearish bounce / mean-reversion strategy.

    Buys oversold bounces in bearish regimes for quick intraday gains.
    Complementary to the bullish trend-following strategy.
    Uses C1 incremental API for efficient backtesting.
    """

    config: BearishIntradayConfig

    @property
    def name(self) -> str:
        cfg = getattr(self, "config", BearishIntradayConfig())
        return f"BearishIntradayRegime(EMA{cfg.ema_fast_period}/{cfg.ema_slow_period},RSI<{cfg.rsi_oversold})"

    def initialize(self, params: Optional[dict[str, object]] = None) -> None:
        super().initialize(params)

        defaults = asdict(BearishIntradayConfig())
        for key in defaults:
            if key in self._params:
                defaults[key] = self._params[key]

        self.config = BearishIntradayConfig(
            ema_fast_period=int(defaults["ema_fast_period"]),
            ema_slow_period=int(defaults["ema_slow_period"]),
            rsi_period=int(defaults["rsi_period"]),
            rsi_oversold=float(defaults["rsi_oversold"]),
            rsi_recovery=float(defaults["rsi_recovery"]),
            volume_ma_period=int(defaults["volume_ma_period"]),
            volume_spike_mult=float(defaults["volume_spike_mult"]),
            atr_period=int(defaults["atr_period"]),
            vwap_distance_atr=float(defaults["vwap_distance_atr"]),
            require_green_candle=bool(defaults["require_green_candle"]),
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
        if self.config.rsi_oversold >= self.config.rsi_recovery:
            raise ValueError("rsi_oversold must be less than rsi_recovery")

    def precompute(
        self, full_data: pd.DataFrame, context: Optional[dict[str, Any]] = None,
    ) -> None:
        if not getattr(self, "_is_initialized", False):
            self.initialize()

        prepared = precompute_bearish(full_data, self.config)
        if context is not None:
            context["bearish_prepared"] = prepared

    def on_bar(
        self,
        current_bar: pd.Series,
        bar_index: int,
        context: Optional[dict[str, Any]] = None,
    ) -> Signal | StrategySignal:
        if not getattr(self, "_is_initialized", False):
            self.initialize()

        prepared = context.get("bearish_prepared") if context else None
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
                     row.get("rsi"), row.get("atr"))
        if any(pd.isna(v) for v in critical):
            return Signal.HOLD

        # Entry signal: BUY the oversold bounce
        if bool(row.get("bear_bounce_entry", False)):
            return self.build_signal(
                action=Signal.BUY,
                current_bar=current_bar,
                confidence=self._compute_confidence(row),
                rationale="bearish_regime_oversold_bounce",
                tags=("intraday", "bearish_regime", "mean_reversion", "bounce"),
                metadata={
                    "close": float(row["close"]),
                    "vwap": float(row["vwap"]),
                    "ema_fast": float(row["ema_fast"]),
                    "ema_slow": float(row["ema_slow"]),
                    "rsi": float(row["rsi"]),
                    "atr": float(row["atr"]),
                    "vwap_distance": float(row["vwap"] - row["close"]),
                    "volume_ratio": (
                        float(row["volume"] / row["vol_ma"])
                        if row.get("vol_ma") and row["vol_ma"] > 0
                        else 0.0
                    ),
                },
            )

        # Exit signal: price returned to VWAP (target reached)
        if bool(row.get("bear_bounce_exit", False)):
            return self.build_signal(
                action=Signal.EXIT,
                current_bar=current_bar,
                confidence=0.70,
                rationale="bearish_bounce_vwap_target_reached",
                tags=("intraday", "bearish_regime", "exit"),
                metadata={
                    "close": float(row["close"]),
                    "vwap": float(row["vwap"]),
                },
            )

        return Signal.HOLD

    def _compute_confidence(self, row: pd.Series) -> float:
        """Dynamic confidence based on bounce quality signals."""
        score = 0.50  # base

        # Deeper oversold = higher confidence
        rsi_val = float(row.get("rsi", 50))
        if rsi_val < 20:
            score += 0.15
        elif rsi_val < 25:
            score += 0.10
        elif rsi_val < 30:
            score += 0.05

        # Larger VWAP distance = stronger mean-reversion potential
        vwap_dist = float(row.get("vwap", 0) - row.get("close", 0))
        atr_val = float(row.get("atr", 1))
        if atr_val > 0:
            dist_atrs = vwap_dist / atr_val
            if dist_atrs > 1.5:
                score += 0.10
            elif dist_atrs > 1.0:
                score += 0.05

        # Volume spike strength
        vol_ma = row.get("vol_ma")
        if vol_ma and vol_ma > 0:
            vol_ratio = float(row["volume"]) / float(vol_ma)
            if vol_ratio > 2.0:
                score += 0.10
            elif vol_ratio > 1.5:
                score += 0.05

        return min(score, 0.95)
