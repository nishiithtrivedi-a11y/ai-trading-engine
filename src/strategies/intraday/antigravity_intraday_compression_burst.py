"""
Antigravity Compression Burst Strategy [V3]
===========================================
A high-probability intraday strategy for NSE NIFTY 50 equities.
Focuses on HIGH-QUALITY Volatility Expansions.

V3 Changes (Alpha Final)
-----------------------
1. Reverted to Long-Only (Shorts were too noisy in 2024 Nifty regime).
2. Climax Volume: Increased to 2.5x to filter for true institutional moves.
3. Pulse Check: Breakout bar must close in the top 25% of its own range.
4. Width Expansion: BB Width must be increasing (Volatility Expansion confirmed).
5. ATR Trailing Stop: 2.0 ATR trailing for better trade breathing room.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Optional

import numpy as np
import pandas as pd

from src.strategies.base_strategy import BaseStrategy, Signal, StrategySignal

TIMEZONE = "Asia/Kolkata"


@dataclass
class ACBConfig:
    """Configurable parameters for HIGHER QUALITY ACB."""
    # Volatility Squeeze
    bb_period: int = 20
    bb_std: float = 2.0 
    kc_period: int = 20
    kc_mult: float = 1.5
    squeeze_threshold_bars: int = 3
    
    # Trend & Momentum
    ema_fast: int = 20
    ema_slow: int = 50
    rsi_period: int = 14
    rsi_entry: float = 60.0 # Higher momentum floor
    
    # Volume filter
    vol_ma_period: int = 20
    vol_multiplier: float = 2.5 # Climax volume
    
    # Session
    session_start: str = "09:45" # Avoid opening noise
    session_end: str = "14:30"
    timezone: str = TIMEZONE
    min_warmup: int = 60
    
    # Risk
    atr_period: int = 14
    trailing_atr_mult: float = 2.0


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


def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss.replace(0, 1e-9))
    return 100 - (100 / (1 + rs))


def precompute_acb(df: pd.DataFrame, cfg: ACBConfig) -> pd.DataFrame:
    """Vectorised precomputation for (V3) ACB strategy."""
    data = _ensure_utc_index(df)
    data = data.copy()
    
    # Session filter
    local = data.index.tz_convert(cfg.timezone)
    hhmm = pd.Series(local.strftime("%H:%M"), index=data.index)
    data["in_session"] = (hhmm >= cfg.session_start) & (hhmm <= cfg.session_end)
    
    # Indicators
    typical_price = (data["high"] + data["low"] + data["close"]) / 3.0
    
    # Bollinger Bands
    ma = typical_price.rolling(window=cfg.bb_period).mean()
    std = typical_price.rolling(window=cfg.bb_period).std()
    data["bb_upper"] = ma + (cfg.bb_std * std)
    data["bb_lower"] = ma - (cfg.bb_std * std)
    data["bb_width"] = (data["bb_upper"] - data["bb_lower"]) / ma
    
    # Keltner Channels
    prev_close = data["close"].shift(1)
    tr = pd.concat([
        data["high"] - data["low"],
        (data["high"] - prev_close).abs(),
        (data["low"] - prev_close).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(window=cfg.kc_period).mean()
    data["kc_upper"] = ma + (cfg.kc_mult * atr)
    data["kc_lower"] = ma - (cfg.kc_mult * atr)
    data["atr_signal"] = tr.rolling(window=cfg.atr_period).mean()
    
    # Squeeze Detection
    data["is_squeeze"] = (data["bb_upper"] < data["kc_upper"]) & (data["bb_lower"] > data["kc_lower"])
    data["is_coiled"] = data["is_squeeze"].rolling(window=cfg.squeeze_threshold_bars).sum() >= cfg.squeeze_threshold_bars
    data["was_coiled"] = data["is_coiled"].rolling(window=5).max().astype(bool)
    
    # Expansion Detection
    data["width_expanding"] = data["bb_width"] > data["bb_width"].shift(1)
    
    # Quality Filter: Close in top 25% of bar
    bar_range = (data["high"] - data["low"]).replace(0, 1e-9)
    data["relative_close"] = (data["close"] - data["low"]) / bar_range
    data["is_strong_close"] = data["relative_close"] > 0.75
    
    # Trend & Momentum
    data["ema_20"] = data["close"].ewm(span=cfg.ema_fast, adjust=False).mean()
    data["ema_50"] = data["close"].ewm(span=cfg.ema_slow, adjust=False).mean()
    data["rsi"] = calculate_rsi(data["close"], cfg.rsi_period)
    
    # VWAP
    vwap_data = data.reset_index()
    from src.strategies.base_strategy import BaseStrategy
    data["vwap"] = BaseStrategy.vwap(vwap_data, timezone=cfg.timezone).values
    
    # Volume
    data["vol_ma"] = data["volume"].rolling(window=cfg.vol_ma_period).mean()
    
    # Entry Signal
    data["acb_long_entry"] = (
        data["in_session"]
        & data["was_coiled"]
        & data["width_expanding"]
        & data["is_strong_close"]
        & (data["close"] > data["bb_upper"])
        & (data["volume"] > data["vol_ma"] * cfg.vol_multiplier)
        & (data["rsi"] > cfg.rsi_entry)
        & (data["close"] > data["vwap"])
        & (data["ema_20"] > data["ema_50"])
    )
    
    # Exit Signal (Initial logic: EMA cross, but on_bar will handle Trailing ATR)
    data["acb_long_exit_base"] = (
        (data["close"] < data["ema_20"]) | (~data["in_session"])
    )
    
    return data


class AntigravityIntradayCompressionBurst(BaseStrategy):
    """
    Antigravity Compression Burst Strategy (V3).
    """
    
    config: ACBConfig
    _trailing_stop: float = 0.0
    
    @property
    def name(self) -> str:
        return "AntigravityIntradayCompressionBurst"
        
    def initialize(self, params: Optional[dict[str, Any]] = None) -> None:
        super().initialize(params)
        
        defaults = asdict(ACBConfig())
        for key in defaults:
            if key in self._params:
                # Type coerce
                if key in ["bb_std", "kc_mult", "vol_multiplier", "rsi_entry", "trailing_atr_mult"]:
                    defaults[key] = float(self._params[key])
                elif key in ["bb_period", "kc_period", "squeeze_threshold_bars", "atr_period"]:
                    defaults[key] = int(self._params[key])
                else:
                    defaults[key] = self._params[key]
        
        self.config = ACBConfig(**defaults)
        
    def precompute(self, full_data: pd.DataFrame, context: Optional[dict[str, Any]] = None) -> None:
        if not getattr(self, "_is_initialized", False):
            self.initialize()
            
        prepared = precompute_acb(full_data, self.config)
        if context is not None:
            context["acb_prepared"] = prepared
            
    def on_bar(self, current_bar: pd.Series, bar_index: int, context: Optional[dict[str, Any]] = None) -> Signal | StrategySignal:
        if not getattr(self, "_is_initialized", False):
            self.initialize()
            
        prepared = context.get("acb_prepared") if context else None
        if prepared is None or bar_index >= len(prepared):
            return Signal.HOLD
            
        if bar_index < self.config.min_warmup:
            return Signal.HOLD
            
        row = prepared.iloc[bar_index]
        
        # Entry
        if bool(row.get("acb_long_entry", False)):
            # Set initial trailing stop
            self._trailing_stop = float(row["close"] - (row["atr_signal"] * self.config.trailing_atr_mult))
            
            return self.build_signal(
                action=Signal.BUY,
                current_bar=current_bar,
                confidence=0.92,
                rationale="V3 Climax: Squeeze + Expansion + Volume + Close Quality",
                tags=("antigravity", "compression", "burst", "climax")
            )
            
        # Trailing Stop Management (if in a position)
        if self._trailing_stop > 0:
            new_stop = float(row["close"] - (row["atr_signal"] * self.config.trailing_atr_mult))
            if new_stop > self._trailing_stop:
                self._trailing_stop = new_stop
                
            if float(row["close"]) < self._trailing_stop:
                self._trailing_stop = 0
                return self.build_signal(action=Signal.EXIT, current_bar=current_bar, rationale="ATR Trailing Stop hit")
        
        # Base Exit
        if bool(row.get("acb_long_exit_base", False)):
            self._trailing_stop = 0
            return self.build_signal(action=Signal.EXIT, current_bar=current_bar, rationale="Trend weakness or session end")
            
        return Signal.HOLD
