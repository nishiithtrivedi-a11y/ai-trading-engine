"""
Signal evaluation layer for scanner research.

Evaluates only the latest bar state for one symbol/timeframe/strategy.
No backtesting and no execution behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from src.core.data_handler import DataHandler
from src.scanners.config import StrategyScanSpec, normalize_timeframe
from src.scanners.models import SignalSnapshot
from src.strategies.base_strategy import BaseStrategy, Signal


class SignalRunnerError(Exception):
    """Raised when scanner signal evaluation fails."""


@dataclass
class SignalRunner:
    min_required_bars: int = 2

    def run_signal(
        self,
        symbol: str,
        timeframe: str,
        strategy_spec: StrategyScanSpec,
        data_handler: DataHandler,
    ) -> SignalSnapshot:
        if len(data_handler) == 0:
            raise SignalRunnerError("Cannot run signal: data handler is empty")

        tf = normalize_timeframe(timeframe)
        latest_ts = data_handler.data.index[-1]
        latest_bar = data_handler.data.iloc[-1]
        close_price = float(latest_bar["close"])

        if len(data_handler) < self.min_required_bars:
            return SignalSnapshot(
                symbol=symbol,
                timeframe=tf,
                strategy_name=strategy_spec.strategy_name,
                signal="hold",
                timestamp=latest_ts,
                close_price=close_price,
                strategy_params=dict(strategy_spec.params),
                extras={
                    "reason": "insufficient_data",
                    "bars_available": len(data_handler),
                    "min_required_bars": self.min_required_bars,
                    "confidence": 0.0,
                    "bars_since_trigger": None,
                },
            )

        strategy = strategy_spec.strategy_class()

        try:
            strategy.initialize(strategy_spec.params)
        except Exception as exc:  # noqa: BLE001
            raise SignalRunnerError(
                f"Failed to initialize strategy '{strategy_spec.strategy_name}': {exc}"
            ) from exc

        full_data = data_handler.data
        bar_index = len(full_data) - 1

        try:
            raw_signal = strategy.on_bar(full_data, latest_bar, bar_index)
        except Exception as exc:  # noqa: BLE001
            raise SignalRunnerError(
                f"Strategy '{strategy_spec.strategy_name}' failed on latest bar: {exc}"
            ) from exc

        normalized_signal = self._normalize_signal(raw_signal)
        confidence = self._estimate_confidence(normalized_signal)

        extras: dict[str, Any] = {
            "bars_available": len(data_handler),
            "bar_index": bar_index,
            "confidence": confidence,
            "latest_open": float(latest_bar.get("open", close_price)),
            "latest_high": float(latest_bar.get("high", close_price)),
            "latest_low": float(latest_bar.get("low", close_price)),
            "latest_close": close_price,
            "latest_volume": float(latest_bar.get("volume", 0.0)),
            "bars_since_trigger": None,
        }

        if normalized_signal == "buy":
            extras["bars_since_trigger"] = self._bars_since_trigger(
                strategy=strategy,
                full_data=full_data,
            )

        self._attach_strategy_metrics(
            strategy_name=strategy_spec.strategy_name,
            params=strategy_spec.params,
            full_data=full_data,
            extras=extras,
        )

        return SignalSnapshot(
            symbol=symbol,
            timeframe=tf,
            strategy_name=strategy_spec.strategy_name,
            signal=normalized_signal,
            timestamp=latest_ts,
            close_price=close_price,
            strategy_params=dict(strategy_spec.params),
            extras=extras,
        )

    @staticmethod
    def _normalize_signal(value: Any) -> str:
        if isinstance(value, Signal):
            return value.value

        if isinstance(value, str):
            clean = value.strip().lower()
            if clean in {"buy", "sell", "exit", "hold"}:
                return clean

        raise SignalRunnerError(f"Unsupported strategy signal output: {value!r}")

    @staticmethod
    def _estimate_confidence(signal: str) -> float:
        if signal == "buy":
            return 1.0
        if signal in {"sell", "exit"}:
            return 0.6
        return 0.0

    def _bars_since_trigger(self, strategy: Any, full_data: pd.DataFrame) -> int | None:
        """
        Count bars since current actionable streak started (latest bar included).

        Returns:
            0 for a fresh trigger on latest bar,
            positive integer for older active trigger,
            None if unavailable.
        """
        try:
            streak = 0
            for idx in range(len(full_data) - 1, -1, -1):
                window = full_data.iloc[: idx + 1]
                bar = window.iloc[-1]
                raw_signal = strategy.on_bar(window, bar, idx)
                norm = self._normalize_signal(raw_signal)
                if norm == "buy":
                    streak += 1
                    continue
                break
            if streak <= 0:
                return None
            return streak - 1
        except Exception:
            return None

    @staticmethod
    def _attach_strategy_metrics(
        strategy_name: str,
        params: dict[str, Any],
        full_data: pd.DataFrame,
        extras: dict[str, Any],
    ) -> None:
        close = full_data["close"]

        if strategy_name == "RSIReversionStrategy":
            period = int(params.get("rsi_period", 14))
            oversold = float(params.get("oversold", 30))
            rsi_series = BaseStrategy.rsi(close, period)
            rsi_now = rsi_series.iloc[-1] if len(rsi_series) > 0 else pd.NA
            rsi_prev = rsi_series.iloc[-2] if len(rsi_series) > 1 else pd.NA

            if pd.notna(rsi_now):
                extras["rsi_current"] = float(rsi_now)
                extras["oversold_threshold"] = oversold
            if pd.notna(rsi_now) and pd.notna(rsi_prev):
                extras["rsi_slope"] = float(rsi_now - rsi_prev)
            return

        if strategy_name == "SMACrossoverStrategy":
            fast_period = int(params.get("fast_period", 10))
            slow_period = int(params.get("slow_period", 30))
            fast = BaseStrategy.sma(close, fast_period)
            slow = BaseStrategy.sma(close, slow_period)

            fast_now = fast.iloc[-1] if len(fast) > 0 else pd.NA
            slow_now = slow.iloc[-1] if len(slow) > 0 else pd.NA
            if pd.isna(fast_now) or pd.isna(slow_now):
                return

            spread = float(fast_now - slow_now)
            extras["sma_spread"] = spread

            atr_series = BaseStrategy.atr(
                high=full_data["high"],
                low=full_data["low"],
                close=full_data["close"],
                period=14,
            )
            atr_now = atr_series.iloc[-1] if len(atr_series) > 0 else pd.NA

            if pd.notna(atr_now) and float(atr_now) > 0:
                extras["sma_spread_norm"] = float(spread / float(atr_now))
            else:
                price = float(close.iloc[-1])
                if price > 0:
                    extras["sma_spread_norm"] = float(spread / price)
