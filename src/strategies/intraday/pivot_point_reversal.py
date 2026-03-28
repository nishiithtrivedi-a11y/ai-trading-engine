"""Pivot point reversal strategy."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.strategies.base_strategy import BaseStrategy, Signal, StrategySignal


@dataclass
class PivotPointReversalConfig:
    timezone: str = "Asia/Kolkata"
    reversal_buffer_pct: float = 0.0


class PivotPointReversalStrategy(BaseStrategy):
    """Reversal signals around prior-session pivot levels (R1/S1)."""

    config: PivotPointReversalConfig

    def initialize(self, params: dict[str, object] | None = None) -> None:
        super().initialize(params)
        cfg = PivotPointReversalConfig(
            timezone=str(self.get_param("timezone", "Asia/Kolkata")),
            reversal_buffer_pct=float(self.get_param("reversal_buffer_pct", 0.0)),
        )
        if cfg.reversal_buffer_pct < 0:
            raise ValueError("reversal_buffer_pct must be >= 0")
        self.config = cfg

    def generate_signal(
        self,
        data: pd.DataFrame,
        current_bar: pd.Series,
        bar_index: int,
        *,
        symbol: str | None = None,
        timeframe: str | None = None,
    ) -> StrategySignal:
        if not getattr(self, "_is_initialized", False):
            self.initialize()
        self.require_columns(data, ["high", "low", "close"])
        if not isinstance(data.index, pd.DatetimeIndex):
            raise ValueError("PivotPointReversalStrategy requires DatetimeIndex data")
        if len(data) < 5:
            return self.build_signal(
                action=Signal.HOLD,
                current_bar=current_bar,
                symbol=symbol,
                timeframe=timeframe,
                confidence=0.0,
                rationale="insufficient_bars",
            )

        idx = data.index
        if "_cached_local_ts" in data.columns:
            local_idx = pd.DatetimeIndex(data["_cached_local_ts"])
        elif idx.tz is None:
            local_idx = idx.tz_localize("UTC").tz_convert(self.config.timezone)
        else:
            local_idx = idx.tz_convert(self.config.timezone)

        day_keys = pd.Series(local_idx.date, index=data.index)
        current_day = day_keys.iloc[-1]

        # B3 fix: use only the *most recent* completed session (the last day
        # strictly before current_day), not all prior history.
        # Using all prior days would produce extreme H/L values pulled from
        # weeks/months of history, not the prior-session pivots that the
        # strategy is intended to trade.
        all_prior_days = sorted(
            {d for d in day_keys.unique() if d < current_day}
        )
        if not all_prior_days:
            return self.build_signal(
                action=Signal.HOLD,
                current_bar=current_bar,
                symbol=symbol,
                timeframe=timeframe,
                confidence=0.0,
                rationale="no_previous_session",
            )

        prior_session_day = all_prior_days[-1]  # most recent completed session
        prev_mask = day_keys == prior_session_day
        prev_data = data.loc[prev_mask]

        prev_high = float(prev_data["high"].max())
        prev_low = float(prev_data["low"].min())
        prev_close = float(prev_data["close"].iloc[-1])

        pivot = (prev_high + prev_low + prev_close) / 3.0
        r1 = 2.0 * pivot - prev_low
        s1 = 2.0 * pivot - prev_high

        close_now = float(current_bar["close"])
        close_prev = float(data["close"].iloc[-2])
        buffer = self.config.reversal_buffer_pct

        action = Signal.HOLD
        rationale = "no_pivot_reversal"
        if close_prev < s1 * (1 - buffer) and close_now > s1:
            action = Signal.BUY
            rationale = "support_reclaim_reversal"
        elif close_prev > r1 * (1 + buffer) and close_now < r1:
            action = Signal.SELL
            rationale = "resistance_reject_reversal"

        return self.build_signal(
            action=action,
            current_bar=current_bar,
            symbol=symbol,
            timeframe=timeframe,
            confidence=0.7 if action != Signal.HOLD else 0.0,
            rationale=rationale,
            tags=("intraday", "pivot", "reversal"),
            metadata={
                "pivot": pivot,
                "r1": r1,
                "s1": s1,
                "previous_close": prev_close,
            },
        )

    def on_bar(self, data: pd.DataFrame, current_bar: pd.Series, bar_index: int) -> Signal:
        return self.generate_signal(data, current_bar, bar_index).action

