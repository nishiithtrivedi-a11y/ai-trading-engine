"""
Trade setup construction for actionable scanner signals.

This module converts a signal snapshot into a long-side setup with
entry, stop-loss and target values.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.core.data_handler import DataHandler
from src.scanners.config import ScannerConfig, SetupMode
from src.scanners.models import OpportunitySide, SignalSnapshot, TradeSetup
from src.strategies.base_strategy import BaseStrategy


class SetupEngineError(Exception):
    """Raised when a trade setup cannot be built from signal/data."""


@dataclass
class SetupEngine:
    def build_setup(
        self,
        signal: SignalSnapshot,
        data_handler: DataHandler,
        scanner_config: ScannerConfig,
    ) -> TradeSetup:
        if not signal.is_actionable:
            raise SetupEngineError("Cannot build setup for non-actionable signal")

        if signal.signal != "buy":
            raise SetupEngineError(
                f"Only long-side BUY setups are supported, got '{signal.signal}'"
            )

        entry = float(signal.close_price)
        if entry <= 0:
            raise SetupEngineError("Entry price must be positive")

        stop = self._compute_stop_loss(entry, data_handler, scanner_config)
        if stop >= entry:
            raise SetupEngineError("Stop-loss must be below entry for long setup")

        risk_per_unit = entry - stop
        target = entry + risk_per_unit * float(scanner_config.setup_target_rr)

        setup = TradeSetup(
            entry_price=entry,
            stop_loss=stop,
            target_price=target,
            side=OpportunitySide.LONG,
            risk_model=scanner_config.setup_mode.value,
            extras={
                "risk_per_unit": risk_per_unit,
                "target_rr": scanner_config.setup_target_rr,
                "timeframe": signal.timeframe,
            },
        )

        self._validate_setup_sanity(setup, scanner_config)
        return setup

    def _compute_stop_loss(
        self,
        entry: float,
        data_handler: DataHandler,
        scanner_config: ScannerConfig,
    ) -> float:
        mode = scanner_config.setup_mode

        if mode == SetupMode.FIXED_PCT:
            return entry * (1.0 - float(scanner_config.setup_fixed_stop_pct))

        if mode == SetupMode.ATR_R_MULTIPLE:
            atr_value = self._latest_atr(data_handler, scanner_config.setup_atr_period)
            stop = entry - float(scanner_config.setup_stop_atr_mult) * atr_value
            return stop

        raise SetupEngineError(f"Unsupported setup mode: {mode}")

    @staticmethod
    def _latest_atr(data_handler: DataHandler, period: int) -> float:
        df = data_handler.data
        if len(df) < period + 1:
            raise SetupEngineError(
                f"Not enough data for ATR stop (need at least {period + 1} bars)"
            )

        atr_series = BaseStrategy.atr(
            high=df["high"],
            low=df["low"],
            close=df["close"],
            period=period,
        )
        atr_val = atr_series.iloc[-1]

        if pd.isna(atr_val) or float(atr_val) <= 0:
            raise SetupEngineError("ATR is unavailable or non-positive on latest bar")

        return float(atr_val)

    @staticmethod
    def _validate_setup_sanity(setup: TradeSetup, cfg: ScannerConfig) -> None:
        entry = float(setup.entry_price)
        if entry <= 0:
            raise SetupEngineError("Invalid setup entry price")

        stop_distance_pct = float(setup.risk_per_unit) / entry

        if stop_distance_pct < float(cfg.setup_min_stop_distance_pct):
            raise SetupEngineError(
                f"Stop distance {stop_distance_pct:.4f} below minimum "
                f"{cfg.setup_min_stop_distance_pct:.4f}"
            )

        if stop_distance_pct > float(cfg.setup_max_stop_distance_pct):
            raise SetupEngineError(
                f"Stop distance {stop_distance_pct:.4f} above maximum "
                f"{cfg.setup_max_stop_distance_pct:.4f}"
            )

        rr = float(setup.risk_reward_ratio)
        if rr < float(cfg.setup_min_rr):
            raise SetupEngineError(
                f"Risk-reward {rr:.3f} below minimum {cfg.setup_min_rr:.3f}"
            )
